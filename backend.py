from __future__ import annotations

from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session

DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(DATABASE_URL, echo=True, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)

class Base(DeclarativeBase):
    pass

class Material(Base):
    __tablename__ = "materials"
    Material_ID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    Name: Mapped[str]
    GWP: Mapped[int]
    components: Mapped[List["Component"]] = relationship(back_populates="material")

class Component(Base):
    __tablename__ = "components"
    ID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    Name: Mapped[str]
    Ebene: Mapped[int]
    Parent_ID: Mapped[Optional[int]] = mapped_column(ForeignKey("components.ID"), nullable=True)
    Atomar: Mapped[bool]
    Gewicht: Mapped[int]  # grams
    Komponente_Wiederverwendbar: Mapped[bool]
    Verbindungstyp: Mapped[str]
    Material_ID: Mapped[int] = mapped_column(ForeignKey("materials.Material_ID"))

    parent: Mapped[Optional["Component"]] = relationship(remote_side=[ID], backref="children")
    material: Mapped[Material] = relationship(back_populates="components")

# Pydantic schemas
class MaterialCreate(BaseModel):
    Name: str
    GWP: int

class MaterialRead(MaterialCreate):
    Material_ID: int

    class Config:
        orm_mode = True

class ComponentCreate(BaseModel):
    Name: str
    Ebene: int
    Parent_ID: Optional[int] = None
    Atomar: bool
    Gewicht: int
    Komponente_Wiederverwendbar: bool
    Verbindungstyp: str
    Material_ID: int

class ComponentRead(ComponentCreate):
    ID: int

    class Config:
        orm_mode = True

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)

@app.post("/materials/", response_model=MaterialRead)
def create_material(material: MaterialCreate, db: Session = Depends(get_db)):
    db_obj = Material(**material.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@app.get("/materials/", response_model=List[MaterialRead])
def read_materials(db: Session = Depends(get_db)):
    return db.query(Material).all()

@app.post("/components/", response_model=ComponentRead)
def create_component(component: ComponentCreate, db: Session = Depends(get_db)):
    db_obj = Component(**component.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@app.get("/components/", response_model=List[ComponentRead])
def read_components(db: Session = Depends(get_db)):
    return db.query(Component).all()

