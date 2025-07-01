# DIMOP_2.2

This repository contains a simple example with a FastAPI backend and a Streamlit
frontend. It demonstrates how to build a minimal full‑stack application in
Python.

## Requirements

- **Python 3.10+**
- `fastapi`, `sqlalchemy`, `uvicorn`, `streamlit`, `requests`

Install the dependencies with:

```bash
pip install -r requirements.txt
```

## Running the backend

Start the API server with Uvicorn. The database `app.db` will be created automatically in the repository root. If an old `app.db` from a previous version exists, delete it or add the missing column as shown below; otherwise the API will fail with `no such column: materials.co2_value`.

```bash
python -m uvicorn backend:app --reload
```

### Upgrade from previous versions

Version 2.2 introduces a new `co2_value` column on the `materials` table. The
example doesn't use a migration tool, so the easiest way to apply the change is
to delete the existing `app.db` file and let FastAPI recreate it on the next
startup. If you want to keep your data you can also add the column manually.
Without this step the API will fail to start with the error `no such column: materials.co2_value`.

```sql
ALTER TABLE materials ADD COLUMN co2_value FLOAT;
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
