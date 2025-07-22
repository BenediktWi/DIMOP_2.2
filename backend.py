from typing import Dict, List, Optional
import csv
import io
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    UploadFile,
    File,
    Response,
    Header,
)
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
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    declarative_base,
    relationship,
    sessionmaker,
    Session,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

ENGINES: Dict[str, Engine] = {}

Base = declarative_base()

PROJECTS_DB_URL = "sqlite:///projects.db"
projects_engine = create_engine(
    PROJECTS_DB_URL, connect_args={"check_same_thread": False}
)
ProjectsSessionLocal = sessionmaker(
    bind=projects_engine, autoflush=False, autocommit=False
)
ProjectsBase = declarative_base()


class Project(ProjectsBase):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)


def initialize_engine(engine: Engine) -> None:
    inspector = inspect(engine)
    # migrations for materials table
    if "materials" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("materials")]
        if "co2_value" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN co2_value FLOAT"))
    # migrations for components table
    if "components" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("components")]
        new_columns = [
            ("level", "INTEGER"),
            ("parent_id", "INTEGER"),
            ("is_atomic", "BOOLEAN"),
            ("weight", "FLOAT"),
            ("reusable", "BOOLEAN"),
            ("connection_type", "INTEGER"),
        ]
        for col_name, col_type in new_columns:
            if col_name not in cols:
                with engine.connect() as conn:
                    conn.execute(
                        text(f"ALTER TABLE components ADD COLUMN {col_name} {col_type}")
                    )
    # create any missing tables
    Base.metadata.create_all(bind=engine)


def get_engine(project_id: str) -> Engine:
    engine = ENGINES.get(project_id)
    if engine is None:
        engine = create_engine(
            f"sqlite:///app_{project_id}.db",
            connect_args={"check_same_thread": False},
        )
        initialize_engine(engine)
        ENGINES[project_id] = engine
    return engine


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    co2_value = Column(Float, nullable=True)
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


class MaterialCreate(MaterialBase):
    pass


class MaterialUpdate(MaterialBase):
    pass


class MaterialRead(MaterialBase):
    id: int

    class Config:
        orm_mode = True


class ProjectBase(BaseModel):
    name: str


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    id: int

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


class ComponentCreate(ComponentBase):
    pass


class ComponentUpdate(ComponentBase):
    pass


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


def get_db(project_id: str = Header(..., alias="X-Project")):
    engine = get_engine(project_id)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_projects_db():
    db = ProjectsSessionLocal()
    try:
        yield db
    finally:
        db.close()


def compute_component_score(
    component: Component,
    db: Session,
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
            compute_component_score(child, db, cache)
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


def init_project_db(project_id: int) -> None:
    """Create a new database for the given project with the default schema."""
    url = f"sqlite:///project_{project_id}.db"
    proj_engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=proj_engine)


def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate the token and return the current user."""
    if token != "fake-super-secret-token":
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"username": "admin"}


app = FastAPI()


@app.on_event("startup")
def on_startup() -> None:
    """Initialize the default project database and the projects listing database on startup."""
    # ensure default project engine and its schema are initialized
    get_engine("default")
    # ensure the projects table exists
    ProjectsBase.metadata.create_all(bind=projects_engine)


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
    db: Session = Depends(get_projects_db),
    current_user: dict = Depends(get_current_user),
):
    db_project = Project(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    init_project_db(db_project.id)
    return db_project


@app.get("/projects", response_model=List[ProjectRead])
def read_projects(
    db: Session = Depends(get_projects_db),
    current_user: dict = Depends(get_current_user),
):
    return db.query(Project).all()


# Material routes
@app.post("/materials", response_model=MaterialRead)
def create_material(
    material: MaterialCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    db_material = Material(**material.dict())
    db.add(db_material)
    db.commit()
    db.refresh(db_material)
    return db_material


@app.get("/materials", response_model=List[MaterialRead])
def read_materials(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    return db.query(Material).all()


@app.get("/materials/{material_id}", response_model=MaterialRead)
def read_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


@app.put("/materials/{material_id}", response_model=MaterialRead)
def update_material(
    material_id: int,
    material_update: MaterialUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    for key, value in material_update.dict(exclude_unset=True).items():
        setattr(material, key, value)
    db.commit()
    db.refresh(material)
    return material


@app.delete("/materials/{material_id}")
def delete_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    db.delete(material)
    db.commit()
    return {"ok": True}


# Component routes
@app.post("/components", response_model=ComponentRead)
def create_component(
    component: ComponentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    if not db.get(Material, component.material_id):
        raise HTTPException(status_code=400, detail="Material does not exist")
    if component.parent_id and not db.get(Component, component.parent_id):
        raise HTTPException(status_code=400, detail="Parent component does not exist")
    db_component = Component(**component.dict())
    db.add(db_component)
    db.commit()
    db.refresh(db_component)
    return db_component


@app.get("/components", response_model=List[ComponentRead])
def read_components(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    return db.query(Component).all()


@app.get("/components/{component_id}", response_model=ComponentRead)
def read_component(
    component_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    return component


@app.put("/components/{component_id}", response_model=ComponentRead)
def update_component(
    component_id: int,
    component_update: ComponentUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _project_id: str = Header(..., alias="X-Project"),
):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    if component_update.material_id and not db.get(Material, component_update.material_id):
        raise HTTPException(status_code=400, detail="Material does not exist")
    if component_update.parent_id and not db.get(Component, component_update.parent_id):
        raise HTTPException(status_code=400, detail="Parent component does not exist")
    for key, value in component_update.dict(exclude_unset=True).items():
        setattr(component, key, value)
    db.commit()
    db.refresh(component)
    return component


@app.delete("/components/{component_id}")
def delete_component(
    component_id: int, 
    db: Session = Depends(get_db),
    current
