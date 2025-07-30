from typing import Dict, List, Optional
import csv
import io
import sqlite3
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Response
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
    total_gwp = Column(Float, nullable=True)
    fossil_gwp = Column(Float, nullable=True)
    biogenic_gwp = Column(Float, nullable=True)
    adpf = Column(Float, nullable=True)
    is_dangerous = Column(Boolean, default=False)
    plast_fam = Column(String, nullable=True)
    mara_plast_id = Column(Float, nullable=True)
    system_ability = Column(Integer, nullable=True)
    sortability = Column(Integer, nullable=True)
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
    total_gwp: Optional[float] = None
    fossil_gwp: Optional[float] = None
    biogenic_gwp: Optional[float] = None
    adpf: Optional[float] = None
    is_dangerous: Optional[bool] = None
    plast_fam: Optional[str] = None
    mara_plast_id: Optional[float] = None
    system_ability: Optional[int] = None
    sortability: Optional[int] = None


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
    # gather all atomic parts for this component
    def gather_atomic(comp: Component) -> List[Component]:
        if comp.is_atomic:
            return [comp]
        parts: List[Component] = []
        for ch in comp.children:
            parts.extend(gather_atomic(ch))
        return parts

    atomic_parts = gather_atomic(component)
    materials = [p.material for p in atomic_parts]
    weights = [p.weight or 0.0 for p in atomic_parts]

    total_weight = sum(weights) or 1.0

    # f1: all materials non dangerous
    f1 = 1.0 if all(not m.is_dangerous for m in materials) else 0.0

    # f2: system ability == 2 weighted by mass
    sys_weight = sum(
        w for w, m in zip(weights, materials) if (m.system_ability or 0) == 2
    )
    f2 = sys_weight / total_weight

    # f3: sortability and connection types
    families = {m.plast_fam for m in materials}
    sort_weight = sum(
        w * (m.sortability or 0) for w, m in zip(weights, materials)
    )
    sortable_percentage = sort_weight / total_weight

    relation_types: List[int] = []

    def gather_relations(comp: Component):
        for child in comp.children:
            if child.connection_type is not None:
                relation_types.append(child.connection_type)
            gather_relations(child)

    gather_relations(component)

    n_families = len(families)
    if n_families == 1:
        f3 = 1.0
    elif all(r not in (3, 4) for r in relation_types):
        f3 = 0.95 if n_families == 2 else 0.9
    elif sortable_percentage > 0.9:
        if n_families == 2:
            f3 = 0.85
        elif n_families == 3:
            f3 = 0.8
        else:
            f3 = 0.6
    else:
        f3 = 0.0

    # f4: material compatibility based on families
    mass_products = []
    compat_weighted = []
    for i, mi in enumerate(materials):
        for j, mj in enumerate(materials):
            mp = weights[i] * weights[j]
            comp_val = 1.0 if mi.plast_fam == mj.plast_fam else 0.0
            mass_products.append(mp)
            compat_weighted.append(mp * comp_val)

    mm = sum(mass_products) or 1.0
    vm = sum(compat_weighted) / mm
    f4 = 1 + 0.2 * (vm - 0.5)

    rv = f1 * f2 * f3 * f4
    rv = max(0.0, min(rv, 1.0))

    cache[component.id] = rv
    return rv


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
        if "is_dangerous" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN is_dangerous BOOLEAN"))
        if "plast_fam" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN plast_fam VARCHAR"))
        if "mara_plast_id" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN mara_plast_id FLOAT"))
        if "system_ability" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN system_ability INTEGER"))
        if "sortability" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE materials ADD COLUMN sortability INTEGER"))
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




# Project routes
@app.post("/projects", response_model=ProjectRead)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
):
    db_project = Project(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


@app.get("/projects", response_model=List[ProjectRead])
def read_projects(
    db: Session = Depends(get_db),
):
    return db.query(Project).all()


# Material routes
@app.post("/materials", response_model=MaterialRead)
def create_material(
    material: MaterialCreate,
    db: Session = Depends(get_db),
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
):
    return db.query(Material).filter(Material.project_id == project_id).all()


@app.get("/materials/{material_id}", response_model=MaterialRead)
def read_material(
    material_id: int,
    project_id: int,
    db: Session = Depends(get_db),
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
):
    material = db.get(Material, material_id)
    if not material or material.project_id != project_id:
        raise HTTPException(status_code=404, detail="Material not found")
    db.delete(material)
    db.commit()
    return {"ok": True}


# Component routes
@app.post("/components", response_model=ComponentRead)
def create_component(
    component: ComponentCreate,
    db: Session = Depends(get_db),
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
):
    return db.query(Component).filter(Component.project_id == project_id).all()


@app.get("/components/{component_id}", response_model=ComponentRead)
def read_component(
    component_id: int,
    project_id: int,
    db: Session = Depends(get_db),
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
):
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
        "is_dangerous",
        "plast_fam",
        "mara_plast_id",
        "system_ability",
        "sortability",
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
                mat.total_gwp if mat.total_gwp is not None else "",
                mat.fossil_gwp if mat.fossil_gwp is not None else "",
                mat.biogenic_gwp if mat.biogenic_gwp is not None else "",
                mat.adpf if mat.adpf is not None else "",
                mat.is_dangerous if mat.is_dangerous is not None else "",
                mat.plast_fam if mat.plast_fam is not None else "",
                mat.mara_plast_id if mat.mara_plast_id is not None else "",
                mat.system_ability if mat.system_ability is not None else "",
                mat.sortability if mat.sortability is not None else "",
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
                "",
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
                    total_gwp=float(row["total_gwp"]) if row.get("total_gwp") else None,
                    fossil_gwp=float(row["fossil_gwp"]) if row.get("fossil_gwp") else None,
                    biogenic_gwp=float(row["biogenic_gwp"]) if row.get("biogenic_gwp") else None,
                    adpf=float(row["adpf"]) if row.get("adpf") else None,
                    is_dangerous=row.get("is_dangerous", "").lower() == "true" if row.get("is_dangerous") else False,
                    plast_fam=row.get("plast_fam") or None,
                    mara_plast_id=float(row["mara_plast_id"]) if row.get("mara_plast_id") else None,
                    system_ability=int(row["system_ability"]) if row.get("system_ability") else None,
                    sortability=int(row["sortability"]) if row.get("sortability") else None,
                    project_id=int(row.get("project_id")) if row.get("project_id") else None,
                )
            )
        elif model == "component":
            components.append(
                Component(
                    id=int(row["id"]),
                    name=row["name"],
                    project_id=int(row.get("project_id")) if row.get("project_id") else None,
                    material_id=int(row["material_id"]) if row.get("material_id") and row["material_id"].isdigit() else None,
                    level=int(row["level"]) if row.get("level") else None,
                    parent_id=int(row["parent_id"]) if row.get("parent_id") else None,
                    is_atomic=str(row.get("is_atomic", "")).lower() == "true",
                    weight=float(row["weight"]) if row.get("weight") else None,
                    reusable=str(row.get("reusable", "")).lower() == "true",
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
