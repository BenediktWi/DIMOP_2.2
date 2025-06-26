import json
import requests
import typer

API_URL = "http://localhost:8000"

app = typer.Typer(help="Simple CLI frontend for the FastAPI backend")

@app.command()
def list_materials():
    resp = requests.get(f"{API_URL}/materials/")
    typer.echo(json.dumps(resp.json(), indent=2))

@app.command()
def add_material(name: str, gwp: int):
    payload = {"Name": name, "GWP": gwp}
    resp = requests.post(f"{API_URL}/materials/", json=payload)
    typer.echo(json.dumps(resp.json(), indent=2))

@app.command()
def list_components():
    resp = requests.get(f"{API_URL}/components/")
    typer.echo(json.dumps(resp.json(), indent=2))

@app.command()
def add_component(
    name: str,
    ebene: int,
    material_id: int,
    parent_id: int | None = None,
    atomar: bool = True,
    gewicht: int = 0,
    wiederverwendbar: bool = True,
    verbindungstyp: str = "unknown",
):
    payload = {
        "Name": name,
        "Ebene": ebene,
        "Parent_ID": parent_id,
        "Atomar": atomar,
        "Gewicht": gewicht,
        "Komponente_Wiederverwendbar": wiederverwendbar,
        "Verbindungstyp": verbindungstyp,
        "Material_ID": material_id,
    }
    resp = requests.post(f"{API_URL}/components/", json=payload)
    typer.echo(json.dumps(resp.json(), indent=2))

if __name__ == "__main__":
    app()
