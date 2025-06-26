# DIMOP_2.2

This repository contains a minimal example of a small full-stack application.  
The backend is built with **FastAPI** and **SQLAlchemy** using SQLite, while the
frontend is a command line interface built with **Typer**.

## Requirements

- Python 3.10+
- `fastapi`, `sqlalchemy`, `uvicorn`, `requests`, `typer`

You can install the dependencies with:

```bash
python3 -m pip install fastapi==0.110.0 sqlalchemy==2.0.29 \
    uvicorn==0.29.0 requests==2.31.0 typer==0.12.3
```

## Running the backend

Start the FastAPI server using Uvicorn. The database `app.db` will be
created automatically in the repository root.

```bash
uvicorn backend:app --reload
```

## Using the CLI frontend

The `frontend.py` file exposes a small set of commands to interact with the
API. With the backend running you can for instance add and list materials and
components:

```bash
# Add a material
python frontend.py add-material "Steel" 100

# List all materials
python frontend.py list-materials

# Add a component
python frontend.py add-component --name "Bolt" --ebene 1 --material-id 1

# List all components
python frontend.py list-components
```

Run `python frontend.py --help` to see all available commands.

