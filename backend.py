from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
# TODO: configure OAuth2PasswordBearer and related utilities for authentication
# from fastapi.security import OAuth2PasswordBearer
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import (
    declarative_base,
    relationship,
    sessionmaker,
    Session,
)

DATABASE_URL = "sqlite:///app.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    components = relationship(
        "Component", back_populates="material", cascade="all, delete-orphan"
    )


class Component(Base):
    __tablename__ = "components"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"))
    level = Column(Integer, nullable=False)
    parent_id = Column(Integer, ForeignKey("components.id", ondelete="SET NULL"))
    material = relationship("Material", back_populates="components")
    parent = relationship("Component", remote_side=[id], back_populates="children")
    children = relationship(
        "Component", back_populates="parent", cascade="all, delete-orphan"
    )


# Pydantic schemas
class MaterialBase(BaseModel):
    name: str
    description: Optional[str] = None


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
    level: int
    parent_id: Optional[int] = None


class ComponentCreate(ComponentBase):
    pass


class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    material_id: Optional[int] = None
    level: Optional[int] = None
    parent_id: Optional[int] = None


class ComponentRead(ComponentBase):
    id: int

    class Config:
        orm_mode = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# TODO: implement `get_current_user` using the OAuth2 scheme above
# def get_current_user(token: str = Depends(oauth2_scheme)):
#     """Validate the token and return the current user."""
#     pass


app = FastAPI()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# Material routes
# TODO: use Depends(get_current_user) in each route to require authentication
@app.post("/materials", response_model=MaterialRead)
def create_material(material: MaterialCreate, db: Session = Depends(get_db)):
    db_material = Material(**material.dict())
    db.add(db_material)
    db.commit()
    db.refresh(db_material)
    return db_material


@app.get("/materials", response_model=List[MaterialRead])
def read_materials(db: Session = Depends(get_db)):
    return db.query(Material).all()


@app.get("/materials/{material_id}", response_model=MaterialRead)
def read_material(material_id: int, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


@app.put("/materials/{material_id}", response_model=MaterialRead)
def update_material(
    material_id: int, material_update: MaterialUpdate, db: Session = Depends(get_db)
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
def delete_material(material_id: int, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    db.delete(material)
    db.commit()
    return {"ok": True}


# Component routes
# TODO: secure these routes with Depends(get_current_user)
@app.post("/components", response_model=ComponentRead)
def create_component(component: ComponentCreate, db: Session = Depends(get_db)):
    if not db.get(Material, component.material_id):
        raise HTTPException(status_code=400, detail="Material does not exist")
    parent = None
    if component.parent_id is not None:
        parent = db.get(Component, component.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent component does not exist")
        if component.level != parent.level + 1:
            raise HTTPException(
                status_code=400, detail="Parent must be exactly one level lower"
            )
    elif component.level != 0:
        raise HTTPException(
            status_code=400, detail="Non-root components must have a parent"
        )
    db_component = Component(**component.dict())
    db.add(db_component)
    db.commit()
    db.refresh(db_component)
    return db_component


@app.get("/components", response_model=List[ComponentRead])
def read_components(db: Session = Depends(get_db)):
    return db.query(Component).all()


@app.get("/components/{component_id}", response_model=ComponentRead)
def read_component(component_id: int, db: Session = Depends(get_db)):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    return component


@app.put("/components/{component_id}", response_model=ComponentRead)
def update_component(
    component_id: int, component_update: ComponentUpdate, db: Session = Depends(get_db)
):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    update_data = component_update.dict(exclude_unset=True)
    if update_data.get("material_id") and not db.get(Material, update_data["material_id"]):
        raise HTTPException(status_code=400, detail="Material does not exist")
    new_parent_id = update_data.get("parent_id", component.parent_id)
    new_level = update_data.get("level", component.level)
    if new_parent_id is not None:
        parent = db.get(Component, new_parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent component does not exist")
        if new_level != parent.level + 1:
            raise HTTPException(
                status_code=400, detail="Parent must be exactly one level lower"
            )
    elif new_level != 0:
        raise HTTPException(
            status_code=400, detail="Non-root components must have a parent"
        )
    for key, value in update_data.items():
        setattr(component, key, value)
    db.commit()
    db.refresh(component)
    return component


@app.delete("/components/{component_id}")
def delete_component(component_id: int, db: Session = Depends(get_db)):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    db.delete(component)
    db.commit()
    return {"ok": True}
