from typing import Dict, List, Optional
import csv
import io
import sqlite3
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    Boolean,
    inspect,
    text,
)
from sqlalchemy.orm import (
    declarative_base,
    relationship,
    sessionmaker,
    Session,
)
from sqlalchemy.exc import IntegrityError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

DATABASE_URL = "sqlite:///app.db"

_real_sqlite_connect = sqlite3.connect


def _sqlite_connect(*args, **kwargs):
    fk = kwargs.pop("foreign_keys", None)
    conn = _real_sqlite_connect(*args, **kwargs)
    if fk:
        conn.execute("PRAGMA foreign_keys=ON")
    return conn

sqlite3.connect = _sqlite_connect
sqlite3.dbapi2.connect = _sqlite_connect

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "foreign_keys": 1},
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False
)
Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    materials = relationship("Material", back_populates="project")
    components = relationship("Component", back_populates="project")


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    co2_value = Column(Float, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    project = relationship("Project", back_populates="materials")
    components = relationship(
        "Component",
        back_populates="material",
        cascade="all, delete-orphan",
    )


class Component(Base):
    __tablename__ = "components"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    level = Column(Integer, nullable=True)
    parent_id = Column(
        Integer,
        ForeignKey("components.id"),
        nullable=True,
    )
    is_atomic = Column(Boolean, default=False)
    weight = Column(Float, nullable=True)
    reusable = Column(Boolean, default=False)
    connection_type = Column(Integer, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    project = relationship("Project", back_populates="components")
    material_id = Column(
        Integer,
        ForeignKey("materials.id", ondelete="CASCADE"),
    )
    material = relationship("Material", back_populates="components")
    parent = relationship(
        "Component",
        remote_side=[id],
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children = relationship(
        "Component",
        back_populates="parent",
        cascade="all, delete-orphan",
    )


class Sustainability(Base):
    __tablename__ = "sustainability"

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(
        Integer,
        ForeignKey("components.id", ondelete="CASCADE"),
        unique=True,
    )
    name = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    component = relationship("Component")


# Pydantic schemas
class MaterialBase(BaseModel):
    name: str
    description: Optional[str] = None
    co2_value: Optional[float] = None


class ProjectBase(BaseModel):
    name: str


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    id: int

    class Config:
        orm_mode = True


class MaterialCreate(MaterialBase):
    project_id: int


class MaterialUpdate(MaterialBase):
    project_id: Optional[int] = None


class MaterialRead(MaterialBase):
    id: int
    project_id: int

    class Config:
        orm_mode = True


class ComponentBase(BaseModel):
    name: str
    material_id: int
    level: Optional[int] = None
    parent_id: Optional[int] = None
    is_atomic: Optional[bool] = None
    weight: Optional[float] = None
    reusable: Optional[bool] = None
    connection_type: Optional[int] = None
    project_id: int


class ComponentCreate(ComponentBase):
    pass


class ComponentUpdate(ComponentBase):
    project_id: Optional[int] = None


class ComponentRead(ComponentBase):
    id: int
    
    class Config:
        orm_mode = True


class SustainabilityBase(BaseModel):
    component_id: int
    name: str
    score: float


class SustainabilityRead(SustainabilityBase):
    id: int

    class Config:
        orm_mode = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def compute_component_score(
    component: Component,
    cache: Dict[int, float] | None = None,
) -> float:
    if cache is None:
        cache = {}
    if component.id in cache:
        return cache[component.id]

    if component.is_atomic:
        material_co2 = component.material.co2_value or 0
        weight = component.weight or 0
        score = weight * material_co2
    else:
        child_scores = [
            compute_component_score(child, cache)
            for child in component.children
        ]
        children_sum = sum(child_scores)
        weight = component.weight or 1
        reuse_factor = 0.9 if component.reusable else 1.0
        level = component.connection_type or 0
        bounded = min(max(level, 0), 5)
        connection_factor = 1.0 - 0.05 * bounded
        score = children_sum * weight * reuse_factor * connection_factor

    cache[component.id] = score
    return score


def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate the token and return the current user."""
    if token != "fake-super-secret-token":
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"username": "admin"}


app = FastAPI()


@app.on_event("startup")
def on_startup():
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
    inspector = inspect(engine)
    if "materials" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("materials")]
        if "co2_value" not in cols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE materials ADD COLUMN co2_value FLOAT")
                )
        if "project_id" not in cols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE materials ADD COLUMN project_id INTEGER")
                )
    if "components" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("components")]
        new_columns = [
            ("level", "INTEGER"),
            ("parent_id", "INTEGER"),
            ("is_atomic", "BOOLEAN"),
            ("weight", "FLOAT"),
            ("reusable", "BOOLEAN"),
            ("connection_type", "INTEGER"),
            ("project_id", "INTEGER"),
        ]
        for col_name, col_type in new_columns:
            if col_name not in cols:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE components ADD COLUMN {col_name} {col_type}"
                        )
                    )
    Base.metadata.create_all(bind=engine)


@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Very basic login that returns a static token."""
    if form_data.username == "admin" and form_data.password == "secret":
        return {"access_token": "fake-super-secret-token", "token_type": "bearer"}
    raise HTTPException(status_code=400, detail="Invalid credentials")


# Project routes
@app.post("/projects", response_model=ProjectRead)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    db_project = Project(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


@app.get("/projects", response_model=List[ProjectRead])
def read_projects(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return db.query(Project).all()


# Material routes
# TODO: use Depends(get_current_user) in each route to require authentication
@app.post("/materials", response_model=MaterialRead)
def create_material(
    material: MaterialCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not db.get(Project, material.project_id):
        raise HTTPException(status_code=400, detail="Project does not exist")
    db_material = Material(**material.dict())
    db.add(db_material)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, detail="Material name already exists"
        )
    db.refresh(db_material)
    return db_material


@app.get("/materials", response_model=List[MaterialRead])
def read_materials(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return db.query(Material).filter(Material.project_id == project_id).all()


@app.get("/materials/{material_id}", response_model=MaterialRead)
def read_material(
    material_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    material = db.get(Material, material_id)
    if not material or material.project_id != project_id:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


@app.put("/materials/{material_id}", response_model=MaterialRead)
def update_material(
    material_id: int, material_update: MaterialUpdate,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    material = db.get(Material, material_id)
    if not material or material.project_id != project_id:
        raise HTTPException(status_code=404, detail="Material not found")
    for key, value in material_update.dict(exclude_unset=True).items():
        setattr(material, key, value)
    db.commit()
    db.refresh(material)
    return material


@app.delete("/materials/{material_id}")
def delete_material(
    material_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    material = db.get(Material, material_id)
    if not material or material.project_id != project_id:
        raise HTTPException(status_code=404, detail="Material not found")
    db.delete(material)
    db.commit()
    return {"ok": True}


# Component routes
# TODO: secure these routes with Depends(get_current_user)
@app.post("/components", response_model=ComponentRead)
def create_component(
    component: ComponentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not db.get(Project, component.project_id):
        raise HTTPException(status_code=400, detail="Project does not exist")
    if not db.get(Material, component.material_id):
        raise HTTPException(
            status_code=400,
            detail="Material does not exist",
        )
    if component.parent_id and not db.get(
        Component,
        component.parent_id,
    ):
        raise HTTPException(
            status_code=400,
            detail="Parent component does not exist",
        )
    db_component = Component(**component.dict())
    db.add(db_component)
    db.commit()
    db.refresh(db_component)
    return db_component


@app.get("/components", response_model=List[ComponentRead])
def read_components(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return db.query(Component).filter(Component.project_id == project_id).all()


@app.get("/components/{component_id}", response_model=ComponentRead)
def read_component(
    component_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    component = db.get(Component, component_id)
    if not component or component.project_id != project_id:
        raise HTTPException(status_code=404, detail="Component not found")
    return component


@app.put("/components/{component_id}", response_model=ComponentRead)
def update_component(
    component_id: int, component_update: ComponentUpdate,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    component = db.get(Component, component_id)
    if not component or component.project_id != project_id:
        raise HTTPException(status_code=404, detail="Component not found")
    if component_update.material_id and not db.get(
        Material,
        component_update.material_id,
    ):
        raise HTTPException(
            status_code=400,
            detail="Material does not exist",
        )
    if component_update.parent_id and not db.get(
        Component,
        component_update.parent_id,
    ):
        raise HTTPException(
            status_code=400,
            detail="Parent component does not exist",
        )
    for key, value in component_update.dict(exclude_unset=True).items():
        setattr(component, key, value)
    db.commit()
    db.refresh(component)
    return component


@app.delete("/components/{component_id}")
def delete_component(
    component_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    component = db.get(Component, component_id)
    if not component or component.project_id != project_id:
        raise HTTPException(status_code=404, detail="Component not found")
    db.delete(component)
    db.commit()
    return {"ok": True}


@app.post(
    "/sustainability/calculate",
    response_model=List[SustainabilityRead],
)
def calculate_sustainability(
    project_id: int,
    db: Session = Depends(get_db),
):
    results = []
    cache: Dict[int, float] = {}
    components = db.query(Component).filter(Component.project_id == project_id).all()
    for comp in components:
        score = compute_component_score(comp, cache)
        record = (
            db.query(Sustainability)
            .filter(Sustainability.component_id == comp.id)
            .first()
        )
        if record:
            record.score = score
            record.name = comp.name
        else:
            record = Sustainability(
                component_id=comp.id,
                name=comp.name,
                score=score,
            )
            db.add(record)
        db.commit()
        db.refresh(record)
        results.append(record)
    return results


@app.get("/sustainability", response_model=List[SustainabilityRead])
def read_sustainability(
    project_id: int,
    db: Session = Depends(get_db),
):
    return (
        db.query(Sustainability)
        .join(Component)
        .filter(Component.project_id == project_id)
        .all()
    )


@app.get("/export")
def export_csv(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "model",
        "id",
        "name",
        "description",
        "co2_value",
        "project_id",
        "material_id",
        "level",
        "parent_id",
        "is_atomic",
        "weight",
        "reusable",
        "connection_type",
    ])
    for mat in db.query(Material).filter(Material.project_id == project_id).all():
        writer.writerow(
            [
                "material",
                mat.id,
                mat.name,
                mat.description or "",
                mat.co2_value if mat.co2_value is not None else "",
                mat.project_id,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
    for comp in db.query(Component).filter(Component.project_id == project_id).all():
        writer.writerow(
            [
                "component",
                comp.id,
                comp.name,
                "",
                "",
                comp.project_id,
                comp.material_id,
                comp.level if comp.level is not None else "",
                comp.parent_id if comp.parent_id is not None else "",
                comp.is_atomic if comp.is_atomic is not None else "",
                comp.weight if comp.weight is not None else "",
                comp.reusable if comp.reusable is not None else "",
                comp.connection_type if comp.connection_type is not None else "",
            ]
        )
    output.seek(0)
    return Response(output.getvalue(), media_type="text/csv")


@app.post("/import")
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode()))
    materials: List[Material] = []
    components: List[Component] = []
    for row in reader:
        model = row.get("model")
        if model == "material":
            materials.append(
                Material(
                    id=int(row["id"]),
                    name=row["name"],
                    description=row.get("description") or None,
                    co2_value=float(row["co2_value"]) if row.get("co2_value") else None,
                    project_id=int(row.get("project_id")) if row.get("project_id") else None,
                )
            )
        elif model == "component":
            components.append(
                Component(
                    id=int(row["id"]),
                    name=row["name"],
                    project_id=int(row.get("project_id")) if row.get("project_id") else None,
                    material_id=int(row.get("material_id")) if row.get("material_id") else None,
                    level=int(row["level"]) if row.get("level") else None,
                    parent_id=int(row["parent_id"]) if row.get("parent_id") else None,
                    is_atomic=row.get("is_atomic", "").lower() == "true",
                    weight=float(row["weight"]) if row.get("weight") else None,
                    reusable=row.get("reusable", "").lower() == "true",
                    connection_type=int(row["connection_type"]) if row.get("connection_type") else None,
                )
            )
    for mat in materials:
        db.merge(mat)
    db.commit()
    for comp in components:
        db.merge(comp)
    db.commit()
    return {
        "imported_materials": len(materials),
        "imported_components": len(components),
    }
