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


def initialize_engine(engine: Engine) -> None:
    inspector = inspect(engine)
    if "materials" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("materials")]
        if "co2_value" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN co2_value FLOAT"))
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


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)


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


class ProjectRead(BaseModel):
    id: int
    name: str

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
