from typing import Dict, List, Optional
import csv
import io
import sqlite3
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, validator
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
    UniqueConstraint,
)
from sqlalchemy.orm import (
    declarative_base,
    relationship,
    sessionmaker,
    Session,
)
from sqlalchemy.exc import IntegrityError, OperationalError

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
    connect_args={"check_same_thread": False, "foreign_keys": 1, "timeout": 30},
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False
)
Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    r_strategies = Column(String, nullable=True)
    materials = relationship("Material", back_populates="project")
    components = relationship(
        "Component",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    total_gwp = Column(Float, nullable=True)
    fossil_gwp = Column(Float, nullable=True)
    biogenic_gwp = Column(Float, nullable=True)
    adpf = Column(Float, nullable=True)
    density = Column(Float, nullable=True)
    is_dangerous = Column(Boolean, default=False)
    project_id = Column(Integer, ForeignKey("projects.id"))
    project = relationship("Project", back_populates="materials")
    components = relationship(
        "Component",
        back_populates="material",
        cascade="all, delete-orphan",
    )


class MaterialCompatibility(Base):
    __tablename__ = "material_compatibility"
    __table_args__ = (UniqueConstraint("material_id_1", "material_id_2"),)

    id = Column(Integer, primary_key=True, index=True)
    material_id_1 = Column(Integer, ForeignKey("materials.id"), nullable=False)
    material_id_2 = Column(Integer, ForeignKey("materials.id"), nullable=False)
    mv_bonus = Column(Float, nullable=True)
    mv_abzug = Column(Float, nullable=True)


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
    # Physical properties used to derive the component's weight
    volume = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    reusable = Column(Boolean, default=False)
    systemability = Column(Float, nullable=True)
    r_factor = Column(Float, nullable=True)
    trenn_eff = Column(Float, nullable=True)
    sort_eff = Column(Float, nullable=True)
    mv_bonus = Column(Float, nullable=True)
    mv_abzug = Column(Float, nullable=True)
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

    def get_weight(self) -> float:
        """Return the effective weight of the component.

        Weight is stored explicitly when a component is linked to a material.
        If ``weight`` is missing but ``volume`` and the material's ``density``
        are available, it is computed on the fly. When no data is available,
        atomic components default to ``0`` and non-atomic components default to
        ``1``.
        """
        if self.weight is not None:
            return self.weight
        if (
            self.volume is not None
            and self.material
            and self.material.density is not None
        ):
            return self.volume * self.material.density
        return 0.0 if self.is_atomic else 1.0


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


class SysSort(Base):
    __tablename__ = "sys_sort"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class Plast(Base):
    __tablename__ = "plast"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class Rel(Base):
    __tablename__ = "rel"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class Compability(Base):
    __tablename__ = "compability"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


def recalc_component_weight(db: Session, component: Component) -> float:
    """Recalculate component weight recursively."""
    if component.is_atomic:
        density = (
            component.material.density
            if component.material and component.material.density
            else 0.0
        )
        volume = component.volume or 0.0
        component.weight = volume * density
        db.add(component)
        return component.weight

    total = 0.0
    for child in component.children:
        total += recalc_component_weight(db, child)
    component.weight = total
    db.add(component)
    return total


def recalc_ancestors(db: Session, component: Optional[Component]):
    """Recalculate weights for ``component`` and its ancestors."""
    while component is not None:
        recalc_component_weight(db, component)
        component = component.parent


# Pydantic schemas
class MaterialBase(BaseModel):
    name: str
    description: Optional[str] = None
    total_gwp: Optional[float] = None
    fossil_gwp: Optional[float] = None
    biogenic_gwp: Optional[float] = None
    adpf: Optional[float] = None
    density: Optional[float] = None
    is_dangerous: Optional[bool] = None


class ProjectBase(BaseModel):
    name: str
    r_strategies: Optional[List[str]] = []


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    r_strategies: Optional[List[str]] = None


class ProjectRead(ProjectBase):
    id: int

    class Config:
        orm_mode = True

    @validator("r_strategies", pre=True, always=True)
    def _split_strategies(cls, v):  # type: ignore[no-untyped-def]
        if isinstance(v, str):
            return [s for s in v.split(",") if s]
        return v


class MaterialCreate(MaterialBase):
    project_id: int


class MaterialUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    total_gwp: Optional[float] = None
    fossil_gwp: Optional[float] = None
    biogenic_gwp: Optional[float] = None
    adpf: Optional[float] = None
    density: Optional[float] = None
    is_dangerous: Optional[bool] = None
    project_id: Optional[int] = None


class MaterialRead(MaterialBase):
    id: int
    project_id: int

    class Config:
        orm_mode = True


class ComponentBase(BaseModel):
    name: str
    material_id: Optional[int] = None
    level: Optional[int] = None
    parent_id: Optional[int] = None
    is_atomic: Optional[bool] = None
    volume: Optional[float] = None
    reusable: Optional[bool] = None
    systemability: Optional[float] = None
    r_factor: Optional[float] = None
    trenn_eff: Optional[float] = None
    sort_eff: Optional[float] = None
    mv_bonus: Optional[float] = 0.0
    mv_abzug: Optional[float] = 0.0
    project_id: int


class ComponentCreate(ComponentBase):
    pass


class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    material_id: Optional[int] = None
    level: Optional[int] = None
    parent_id: Optional[int] = None
    is_atomic: Optional[bool] = None
    volume: Optional[float] = None
    reusable: Optional[bool] = None
    systemability: Optional[float] = None
    r_factor: Optional[float] = None
    trenn_eff: Optional[float] = None
    sort_eff: Optional[float] = None
    mv_bonus: Optional[float] = None
    mv_abzug: Optional[float] = None
    project_id: Optional[int] = None


class ComponentRead(ComponentBase):
    id: int
    weight: Optional[float] = None

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
        f1 = component.get_weight()
        f2 = component.material.total_gwp or 0
        f3 = 1.0
        f4 = 1.0
    else:
        child_scores = [
            compute_component_score(child, cache)
            for child in component.children
        ]
        f1 = component.get_weight()
        f2 = sum(child_scores)
        f3 = 0.9 if component.reusable else 1.0
        f4 = 1.0
    score = f1 * f2 * f3 * f4

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
        if "total_gwp" not in cols:
            if "co2_value" in cols:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE materials RENAME COLUMN co2_value TO total_gwp"
                        )
                    )
            else:
                with engine.connect() as conn:
                    conn.execute(
                        text("ALTER TABLE materials ADD COLUMN total_gwp FLOAT")
                    )
        if "fossil_gwp" not in cols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE materials ADD COLUMN fossil_gwp FLOAT")
                )
        if "biogenic_gwp" not in cols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE materials ADD COLUMN biogenic_gwp FLOAT")
                )
        if "adpf" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN adpf FLOAT"))
        if "density" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN density FLOAT"))
        if "project_id" not in cols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE materials ADD COLUMN project_id INTEGER")
                )
        if "is_dangerous" not in cols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE materials ADD COLUMN is_dangerous BOOLEAN")
                )
        for deprecated in ["plast_fam", "mara_plast_id"]:
            if deprecated in cols:
                with engine.connect() as conn:
                    conn.execute(
                        text(f"ALTER TABLE materials DROP COLUMN {deprecated}")
                    )
    if "components" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("components")]
        # Remove deprecated density column if it exists; component density should
        # always come from the linked material.
        if "density" in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE components DROP COLUMN density"))
            cols.remove("density")
        new_columns = [
            ("level", "INTEGER"),
            ("parent_id", "INTEGER"),
            ("is_atomic", "BOOLEAN"),
            ("volume", "FLOAT"),
            ("weight", "FLOAT"),
            ("reusable", "BOOLEAN"),
            ("project_id", "INTEGER"),
            ("systemability", "FLOAT"),
            ("r_factor", "FLOAT"),
            ("trenn_eff", "FLOAT"),
            ("sort_eff", "FLOAT"),
            ("mv_bonus", "FLOAT"),
            ("mv_abzug", "FLOAT"),
        ]
        for col_name, col_type in new_columns:
            if col_name not in cols:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE components ADD COLUMN {col_name} {col_type}"
                        )
                    )
    if "projects" in inspector.get_table_names():
        pcols = [c["name"] for c in inspector.get_columns("projects")]
        if "r_strategies" not in pcols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE projects ADD COLUMN r_strategies VARCHAR")
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
    db_project = Project(
        name=project.name,
        r_strategies=",".join(project.r_strategies or []),
    )
    db.add(db_project)
    try:
        db.commit()
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database is busy")
    db.refresh(db_project)
    return db_project


@app.get("/projects", response_model=List[ProjectRead])
def read_projects(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return db.query(Project).all()


@app.put("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    project: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    db_project = db.get(Project, project_id)
    if not db_project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.name is not None:
        db_project.name = project.name
    if project.r_strategies is not None:
        db_project.r_strategies = ",".join(project.r_strategies)
    try:
        db.commit()
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database is busy")
    db.refresh(db_project)
    return db_project


@app.post("/projects/{project_id}/copy", response_model=ProjectRead)
def copy_project(
    project_id: int,
    project: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    source = db.get(Project, project_id)
    if not source:
        raise HTTPException(status_code=404, detail="Project not found")
    new_proj = Project(
        name=project.name,
        r_strategies=",".join(project.r_strategies or []),
    )
    db.add(new_proj)
    try:
        db.commit()
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database is busy")
    db.refresh(new_proj)

    material_map = {}
    for mat in source.materials:
        new_name = mat.name
        suffix = 1
        while db.query(Material).filter(Material.name == new_name).first():
            suffix += 1
            new_name = f"{mat.name} ({suffix})"
        new_mat = Material(
            name=new_name,
            description=mat.description,
            total_gwp=mat.total_gwp,
            fossil_gwp=mat.fossil_gwp,
            biogenic_gwp=mat.biogenic_gwp,
            adpf=mat.adpf,
            density=mat.density,
            is_dangerous=mat.is_dangerous,
            project_id=new_proj.id,
        )
        db.add(new_mat)
        db.flush()
        material_map[mat.id] = new_mat.id

    component_map = {}
    for comp in source.components:
        new_comp = Component(
            name=comp.name,
            level=comp.level,
            parent_id=None,
            is_atomic=comp.is_atomic,
            volume=comp.volume,
            weight=comp.weight,
            reusable=comp.reusable,
            systemability=comp.systemability,
            r_factor=comp.r_factor,
            trenn_eff=comp.trenn_eff,
            sort_eff=comp.sort_eff,
            mv_bonus=comp.mv_bonus,
            mv_abzug=comp.mv_abzug,
            project_id=new_proj.id,
            material_id=material_map.get(comp.material_id),
        )
        db.add(new_comp)
        db.flush()
        component_map[comp.id] = new_comp.id

    for comp in source.components:
        if comp.parent_id:
            new_id = component_map[comp.id]
            parent_new_id = component_map.get(comp.parent_id)
            if parent_new_id:
                db.query(Component).filter(Component.id == new_id).update(
                    {Component.parent_id: parent_new_id}
                )

    for mc in db.query(MaterialCompatibility).all():
        if mc.material_id_1 in material_map and mc.material_id_2 in material_map:
            db.add(
                MaterialCompatibility(
                    material_id_1=material_map[mc.material_id_1],
                    material_id_2=material_map[mc.material_id_2],
                    mv_bonus=mc.mv_bonus,
                    mv_abzug=mc.mv_abzug,
                )
            )

    try:
        db.commit()
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database is busy")
    db.refresh(new_proj)
    return new_proj

@app.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for material in project.materials:
        material.project_id = None
    try:
        db.delete(project)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Project could not be deleted due to constraints"
        )
    return Response(status_code=204)


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
    material_id: int,
    material_update: MaterialUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    updates = material_update.dict(exclude_unset=True)
    for key, value in updates.items():
        setattr(material, key, value)
    if "density" in updates:
        for comp in material.components:
            if comp.volume is not None and material.density is not None:
                comp.weight = comp.volume * material.density
            else:
                comp.weight = None
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
    material = db.get(Material, component.material_id) if component.material_id else None
    if component.is_atomic:
        if not material:
            raise HTTPException(
                status_code=400,
                detail="Material does not exist",
            )
    else:
        material = None
    if component.parent_id and not db.get(
        Component,
        component.parent_id,
    ):
        raise HTTPException(
            status_code=400,
            detail="Parent component does not exist",
        )
    data = component.dict()
    if not component.is_atomic:
        data["material_id"] = None
    db_component = Component(**data)
    db.add(db_component)
    db.commit()
    db.refresh(db_component)
    recalc_ancestors(db, db_component)
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
    component_id: int,
    component_update: ComponentUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    if (
        component_update.material_id is not None
        and not db.get(Material, component_update.material_id)
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
    if component.is_atomic and not component.material_id:
        raise HTTPException(
            status_code=400,
            detail="Atomic component must have material",
        )
    if not component.is_atomic:
        component.material_id = None
        component.volume = None
    db.commit()
    db.refresh(component)
    recalc_ancestors(db, component)
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
    parent = component.parent
    db.delete(component)
    db.commit()
    if parent is not None:
        db.refresh(parent)
        recalc_ancestors(db, parent)
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
    """Export materials, components and sustainability scores as CSV.

    Component rows include ``volume`` and ``weight`` columns. Material density
    is stored on the material itself.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "model",
        "id",
        "name",
        "description",
        "total_gwp",
        "fossil_gwp",
        "biogenic_gwp",
        "adpf",
        "density",
        "is_dangerous",
        "project_id",
        "material_id",
        "level",
        "parent_id",
        "is_atomic",
        "volume",
        "weight",
        "reusable",
        "systemability",
        "r_factor",
        "trenn_eff",
        "sort_eff",
        "mv_bonus",
        "mv_abzug",
        "component_id",
        "score",
    ])
    for mat in db.query(Material).filter(Material.project_id == project_id).all():
        writer.writerow(
            [
                "material",
                mat.id,
                mat.name,
                mat.description or "",
                mat.total_gwp if mat.total_gwp is not None else "",
                mat.fossil_gwp if mat.fossil_gwp is not None else "",
                mat.biogenic_gwp if mat.biogenic_gwp is not None else "",
                mat.adpf if mat.adpf is not None else "",
                mat.density if mat.density is not None else "",
                mat.is_dangerous if mat.is_dangerous is not None else "",
                mat.project_id,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
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
                "",
                "",
                "",
                "",
                "",
                comp.project_id,
                comp.material_id,
                comp.level if comp.level is not None else "",
                comp.parent_id if comp.parent_id is not None else "",
                comp.is_atomic if comp.is_atomic is not None else "",
                comp.volume if comp.volume is not None else "",
                comp.weight if comp.weight is not None else "",
                comp.reusable if comp.reusable is not None else "",
                comp.systemability if comp.systemability is not None else "",
                comp.r_factor if comp.r_factor is not None else "",
                comp.trenn_eff if comp.trenn_eff is not None else "",
                comp.sort_eff if comp.sort_eff is not None else "",
                comp.mv_bonus if comp.mv_bonus is not None else "",
                comp.mv_abzug if comp.mv_abzug is not None else "",
                "",
                "",
            ]
        )
    for sus in (
        db.query(Sustainability)
        .join(Component)
        .filter(Component.project_id == project_id)
        .all()
    ):
        writer.writerow(
            [
                "sustainability",
                sus.id,
                sus.name,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                project_id,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                sus.component_id,
                sus.score,
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
    """Load materials, components and sustainability data from a CSV file.

    The CSV format expects material rows to include ``density`` and component
    rows to include ``volume`` and ``weight``.
    """
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode()))
    materials: List[Material] = []
    components: List[Component] = []
    sustainabilities: List[Sustainability] = []
    for row in reader:
        model = row.get("model")
        if model == "material":
            materials.append(
                Material(
                    id=int(row["id"]),
                    name=row["name"],
                    description=row.get("description") or None,
                    total_gwp=float(row["total_gwp"]) if row.get("total_gwp") else None,
                    fossil_gwp=(
                        float(row["fossil_gwp"]) if row.get("fossil_gwp") else None
                    ),
                    biogenic_gwp=(
                        float(row["biogenic_gwp"]) if row.get("biogenic_gwp") else None
                    ),
                    adpf=float(row["adpf"]) if row.get("adpf") else None,
                    density=float(row["density"]) if row.get("density") else None,
                    is_dangerous=row.get("is_dangerous", "").lower() == "true",
                    project_id=(
                        int(row.get("project_id")) if row.get("project_id") else None
                    ),
                )
            )
        elif model == "component":
            components.append(
                Component(
                    id=int(row["id"]),
                    name=row["name"],
                    project_id=(
                        int(row.get("project_id")) if row.get("project_id") else None
                    ),
                    material_id=(
                        int(row.get("material_id")) if row.get("material_id") else None
                    ),
                    level=int(row["level"]) if row.get("level") else None,
                    parent_id=int(row["parent_id"]) if row.get("parent_id") else None,
                    is_atomic=row.get("is_atomic", "").lower() == "true",
                    volume=float(row["volume"]) if row.get("volume") else None,
                    weight=float(row["weight"]) if row.get("weight") else None,
                    reusable=row.get("reusable", "").lower() == "true",
                    systemability=(
                        float(row["systemability"])
                        if row.get("systemability")
                        else None
                    ),
                    r_factor=float(row["r_factor"]) if row.get("r_factor") else None,
                    trenn_eff=float(row["trenn_eff"]) if row.get("trenn_eff") else None,
                    sort_eff=float(row["sort_eff"]) if row.get("sort_eff") else None,
                    mv_bonus=float(row["mv_bonus"]) if row.get("mv_bonus") else None,
                    mv_abzug=float(row["mv_abzug"]) if row.get("mv_abzug") else None,
                )
            )
        elif model == "sustainability":
            sustainabilities.append(
                Sustainability(
                    id=int(row["id"]),
                    name=row["name"],
                    component_id=int(row["component_id"]),
                    score=float(row["score"]),
                )
            )
    for mat in materials:
        db.merge(mat)
    db.commit()
    for comp in components:
        db.merge(comp)
    db.commit()
    for sus in sustainabilities:
        db.merge(sus)
    db.commit()
    return {
        "imported_materials": len(materials),
        "imported_components": len(components),
        "imported_sustainabilities": len(sustainabilities),
    }


def _aggregate_metrics(component: Component) -> Dict[str, float]:
    """Recursively sum GWP and ADPf for component tree."""
    weight = component.get_weight()
    mat = component.material
    total = (mat.total_gwp or 0.0) * weight
    fossil = (mat.fossil_gwp or 0.0) * weight
    biogenic = (mat.biogenic_gwp or 0.0) * weight
    adpf = (mat.adpf or 0.0) * weight
    for child in component.children:
        child_vals = _aggregate_metrics(child)
        total += child_vals["total_gwp"]
        fossil += child_vals["fossil_gwp"]
        biogenic += child_vals["biogenic_gwp"]
        adpf += child_vals["adpf"]
    return {
        "total_gwp": total,
        "fossil_gwp": fossil,
        "biogenic_gwp": biogenic,
        "adpf": adpf,
    }


def _grade_from_rv(rv: float) -> str:
    if rv < 15:
        return "A"
    if rv < 30:
        return "B"
    if rv < 50:
        return "C"
    return "D"


@app.post("/evaluation/{component_id}")
def evaluate_component(
    component_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    component = db.get(Component, component_id)
    if not component or component.project_id != project_id:
        raise HTTPException(status_code=404, detail="Component not found")
    metrics = _aggregate_metrics(component)
    rv = metrics["total_gwp"]
    return {
        **metrics,
        "rv": rv,
        "grade": _grade_from_rv(rv),
    }


def _weight_fractions(components: List[Component]) -> Dict[int, float]:
    weights: Dict[int, float] = {}
    for c in components:
        w = c.get_weight() if hasattr(c, "get_weight") else (c.weight or 0.0)
        weights[c.id] = w
    total = sum(weights.values())
    return {cid: (w / total if total > 0 else 0.0) for cid, w in weights.items()}


def _gmv_terms(
    components: List[Component],
    fractions: Dict[int, float],
    db: Session,
) -> tuple[float, float, bool]:
    inspector = inspect(db.bind)
    has_table = "material_compatibility" in inspector.get_table_names()
    gmv_bonus = 0.0
    gmv_abzug = 0.0
    contaminated = False
    for i, ci in enumerate(components):
        for cj in components[i + 1:]:
            m1, m2 = ci.material_id, cj.material_id
            if not (m1 and m2):
                continue
            gf = fractions.get(ci.id, 0.0) * fractions.get(cj.id, 0.0)
            mv_bonus = None
            mv_abzug = None
            if has_table:
                m1, m2 = sorted([m1, m2])
                pair = (
                    db.query(MaterialCompatibility)
                    .filter(
                        MaterialCompatibility.material_id_1 == m1,
                        MaterialCompatibility.material_id_2 == m2,
                    )
                    .first()
                )
                if pair:
                    mv_bonus = pair.mv_bonus
                    mv_abzug = pair.mv_abzug
            if mv_bonus is None:
                bonuses = [ci.mv_bonus, cj.mv_bonus]
                bonuses = [b for b in bonuses if b is not None]
                mv_bonus = sum(bonuses) / len(bonuses) if bonuses else 0.0
            if mv_abzug is None:
                abzuege = [ci.mv_abzug, cj.mv_abzug]
                abzuege = [a for a in abzuege if a is not None]
                mv_abzug = max(abzuege) if abzuege else 0.0
            if mv_abzug == 3:
                contaminated = True
            gmv_bonus += gf * (mv_bonus or 0.0)
            gmv_abzug += gf * (mv_abzug or 0.0)
    return gmv_bonus, gmv_abzug, contaminated


@app.post("/recycle/{project_id}")
def recycle_evaluation(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    components = db.query(Component).filter(Component.project_id == project_id).all()
    if not components:
        raise HTTPException(status_code=404, detail="No components found")

    atomic = [c for c in components if c.is_atomic]
    if not atomic:
        return {"recycle_value": 0.0, "grade": "F"}
    if any((c.material and c.material.is_dangerous) for c in atomic):
        return {"recycle_value": 0.0, "grade": "F"}

    fractions = _weight_fractions(atomic)
    pW = sum((c.r_factor or 0.0) * fractions.get(c.id, 0.0) for c in atomic)
    eta_trenn = sum((c.trenn_eff or 0.0) * fractions.get(c.id, 0.0) for c in atomic)
    eta_sort = sum((c.sort_eff or 0.0) * fractions.get(c.id, 0.0) for c in atomic)
    gmv_bonus, gmv_abzug, contaminated = _gmv_terms(atomic, fractions, db)
    if contaminated:
        return {"recycle_value": 0.0, "grade": "F"}

    root = next((c for c in components if c.parent_id is None), components[0])
    s_faeh = 1.0 if (root.systemability or 0.0) >= 1 else 0.0
    if s_faeh == 0.0:
        return {"recycle_value": 0.0, "grade": "F"}

    r_val = s_faeh * pW * (eta_trenn * eta_sort + gmv_bonus - gmv_abzug)
    r_val = max(0.0, min(1.0, r_val))

    if r_val > 0.95:
        grade = "A"
    elif r_val > 0.85:
        grade = "B"
    elif r_val > 0.7:
        grade = "C"
    elif r_val > 0.5:
        grade = "D"
    elif r_val > 0.3:
        grade = "E"
    else:
        grade = "F"

    return {"recycle_value": round(r_val, 3), "grade": grade}
