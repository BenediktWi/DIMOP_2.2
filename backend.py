from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Depends
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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

DATABASE_URL = "sqlite:///app.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False
)
Base = declarative_base()


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
    weight = Column(Integer, nullable=True)
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


class ComponentBase(BaseModel):
    name: str
    material_id: int
    level: Optional[int] = None
    parent_id: Optional[int] = None
    is_atomic: Optional[bool] = None
    weight: Optional[int] = None
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
    sustainability_score: float


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


def compute_component_weight(
    component: Component,
    cache: Dict[int, int] | None = None,
) -> int:
    """Recursively compute and assign weights for a component hierarchy."""
    if cache is None:
        cache = {}
    if component.id in cache:
        return cache[component.id]

    if component.is_atomic:
        weight = component.weight or 0
    else:
        child_weights = [
            compute_component_weight(child, cache) for child in component.children
        ]
        weight = sum(child_weights)
        component.weight = weight

    cache[component.id] = weight
    return weight


def compute_component_score(
    component: Component,
    db: Session,
    cache: Dict[int, float] | None = None,
) -> float:
    """
    Recursively compute the sustainability score for a component hierarchy.
    For atomic components: score = weight * material.co2_value.
    For composite components: score = sum(child_scores) * reuse_factor * connection_factor.
    """
    if cache is None:
        cache = {}
    if component.id in cache:
        return cache[component.id]

    if component.is_atomic:
        material_co2 = component.material.co2_value or 0.0
        weight = component.weight or 0
        score = weight * material_co2
    else:
        # Compute scores for children
        child_scores = [compute_component_score(child, db, cache) for child in component.children]
        children_sum = sum(child_scores)
        # Apply reuse factor
        reuse_factor = 0.9 if component.reusable else 1.0
        # Compute connection factor based on connection_type level (0 to 5)
        level = component.connection_type or 0
        bounded = min(max(level, 0), 5)
        connection_factor = 1.0 - 0.05 * bounded
        # Final composite score
        score = children_sum * reuse_factor * connection_factor

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
    inspector = inspect(engine)
    if "materials" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("materials")]
        if "co2_value" not in cols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE materials ADD COLUMN co2_value FLOAT")
                )
    if "components" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("components")]
        new_columns = [
            ("level", "INTEGER"),
            ("parent_id", "INTEGER"),
            ("is_atomic", "BOOLEAN"),
            ("weight", "INTEGER"),
            ("reusable", "BOOLEAN"),
            ("connection_type", "INTEGER"),
        ]
        for col_name, col_type in new_columns:
            if col_name not in cols:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE components ADD COLUMN {col_name} {col_type}"
                        )
                    )
        for c in inspector.get_columns("components"):
            if c["name"] == "weight" and not isinstance(c["type"], Integer):
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE components RENAME COLUMN weight TO weight_old"))
                    conn.execute(text("ALTER TABLE components ADD COLUMN weight INTEGER"))
                    conn.execute(text("UPDATE components SET weight = CAST(weight_old AS INTEGER)"))
    Base.metadata.create_all(bind=engine)


@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Very basic login that returns a static token."""
    if form_data.username == "admin" and form_data.password == "secret":
        return {"access_token": "fake-super-secret-token", "token_type": "bearer"}
    raise HTTPException(status_code=400, detail="Invalid credentials")


# Material routes
@app.post("/materials", response_model=MaterialRead)
def create_material(
    material: MaterialCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
):
    return db.query(Material).all()


@app.get("/materials/{material_id}", response_model=MaterialRead)
def read_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(
            status_code=404,
            detail="Material not found",
        )
    return material


@app.put("/materials/{material_id}", response_model=MaterialRead)
def update_material(
    material_id: int, material_update: MaterialUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(
            status_code=404,
            detail="Material not found",
        )
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
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(
            status_code=404,
            detail="Material not found",
        )
    db.delete(material)
    db.commit()
    return {"ok": True}

# Component.routes
@app.post("/components", response_model=ComponentRead)
def create_component(
    component: ComponentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
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
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return db.query(Component).all()


@app.get("/components/{component_id}", response_model=ComponentRead)
def read_component(
    component_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(
            status_code=404,
            detail="Component not found",
        )
    return component


@app.put("/components/{component_id}", response_model=ComponentRead)
def update_component(
    component_id: int, component_update: ComponentUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(
            status_code=404,
            detail="Component not found",
        )
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
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(
            status_code=404,
            detail="Component not found",
        )
    db.delete(component)
    db.commit()
    return {"ok": True}

# Sustainability routes
@app.post(
    "/sustainability/calculate",
    response_model=List[SustainabilityRead],
)
def calculate_sustainability(db: Session = Depends(get_db)):
    results = []
    cache: Dict[int, float] = {}
    components = db.query(Component).all()
    for comp in components:
        compute_component_weight(comp)
        score = compute_component_score(comp, db, cache)
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
def read_sustainability(db: Session = Depends(get_db)):
    return db.query(Sustainability).all()
