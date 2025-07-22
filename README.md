# DIMOP_2.2

This repository contains a simple example with a FastAPI backend and a Streamlit
frontend. It demonstrates how to build a minimal full‑stack application in
Python.

## Requirements

- **Python 3.10+**
- `fastapi`, `sqlalchemy`, `uvicorn`, `streamlit`, `requests`, `graphviz`

Install the dependencies with:

```bash
pip install -r requirements.txt
```

## Running the backend

Start the API server with Uvicorn. Each project is stored in its own SQLite file
inside the `projects` directory. A fresh install creates the default project at
`projects/default.db`. If you upgraded from an earlier release that used a
single `app.db` in the repository root, delete that file or migrate it as shown
below; otherwise the API will fail with `no such column: materials.co2_value`.

```bash
python -m uvicorn backend:app --reload
```

### Upgrade from previous versions

Version 2.2 introduces a new `co2_value` column on the `materials` table.
Newer versions may also require additional columns on the `components` table,
such as `connection_type` and `weight`.
Because the example doesn't use a migration tool, you have two options when
upgrading: delete the existing `app.db` file and let FastAPI recreate it on the
next startup, or manually add the missing columns using `ALTER TABLE`
statements. Without this step the API will fail to start with errors such as
`no such column: materials.co2_value`.

```sql
ALTER TABLE materials ADD COLUMN co2_value FLOAT;
ALTER TABLE components ADD COLUMN connection_type INTEGER;
ALTER TABLE components ADD COLUMN weight INTEGER;
```

## Starting the Streamlit frontend

Launch the web interface once the backend is running:

```bash
streamlit run frontend.py  # oder: python -m streamlit run frontend.py
```

The Streamlit app looks for the API at `http://localhost:8000` by default. If
your backend is running at a different address you can override the URL in two
ways:

1. Create a `.streamlit/secrets.toml` file in the project root containing:

   ```toml
   BACKEND_URL = "http://localhost:8000"
   ```

2. Or set the environment variable before launching Streamlit:

   ```bash
   export BACKEND_URL="http://localhost:8000"
   streamlit run frontend.py
   ```

The components page also displays a Graphviz diagram of the component hierarchy.
This requires the `graphviz` Python package from `requirements.txt`.

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

## Development

Install the development dependencies using:

```bash
pip install -r requirements-dev.txt
```

Run the test suite with:

```bash
pytest
```

Check the code style using the linter:

```bash
ruff check .
```

## CSV export/import

Two helper endpoints make it easy to backup the database contents.

- `GET /export` returns all materials and components in a single CSV file. Each
  row includes a `model` column with either `material` or `component` and the
  corresponding fields.
- `POST /import` accepts an uploaded CSV (field name `file`) and recreates the
  records in the database.

## Projects

Every project has its own SQLite database under the `projects/` directory. The
default project is stored as `projects/default.db`. New projects can be created
with `POST /projects` and listed using `GET /projects`. Individual projects can
be retrieved with `GET /projects/{project_id}`, updated via
`PUT /projects/{project_id}`, and removed with
`DELETE /projects/{project_id}`.

### Using projects in the app

1. Start the backend with `python -m uvicorn backend:app --reload`.
2. Launch the Streamlit frontend with `streamlit run frontend.py`.
3. Log in on the sidebar using the credentials `admin`/`secret`.
4. Select the active project from the dropdown at the top of the interface.
5. Create additional projects via the "New Project" option or the
   `POST /projects` API endpoint.

## Future authentication integration

The example application intentionally omits user authentication to keep the
code minimal. FastAPI provides utilities in `fastapi.security` for implementing
OAuth2 authentication. A common approach is to use
`OAuth2PasswordBearer` along with token‑based endpoints. The returned token can
then be required in every API route using `Depends`.

On the frontend side a small Streamlit login form could collect the user
credentials and store the received token in the session state. Subsequent
requests from Streamlit would include this token in the `Authorization` header.
These building blocks make it straightforward to add authentication later while
keeping the current example simple.
