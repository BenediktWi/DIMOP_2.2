# DIMOP_2.2

This repository contains a simple example with a FastAPI backend and a Streamlit
frontend. It demonstrates how to build a minimal full‑stack application in
Python.

## Requirements

- **Python 3.10+**
- `fastapi`, `sqlalchemy`, `uvicorn`, `streamlit`

Install the dependencies with:

```bash
python3 -m pip install fastapi sqlalchemy uvicorn streamlit
```

## Running the backend

Start the API server with Uvicorn. The database `app.db` will be created
automatically in the repository root.

```bash
uvicorn backend:app --reload
```

## Starting the Streamlit frontend

Launch the web interface once the backend is running:

```bash
streamlit run frontend.py
```

## Packaging with PyInstaller

You can create a standalone executable of either entry point using
[PyInstaller](https://pyinstaller.org/). First install it:

```bash
python3 -m pip install pyinstaller
```

Then build the executable with the `--onefile` flag. For example, to package the
Streamlit frontend run:

```bash
pyinstaller --onefile frontend.py
```

The resulting binary is placed inside the `dist` directory. Execute it from
there so that any bundled assets can be found correctly.
