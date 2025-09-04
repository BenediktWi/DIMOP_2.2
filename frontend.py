import os
import streamlit as st
from streamlit.errors import StreamlitAPIException
from graphviz import Digraph
import requests

# ---------- Navigation helpers ----------
def navigate(to_page: str):
    """Programmatic navigation without touching widget-bound keys directly."""
    st.session_state["_nav_to"] = to_page
    st.rerun()

def require_auth():
    if "token" not in st.session_state:
        navigate("Projects")

# ---------- Rerun helpers ----------
def do_rerun():
    """Compatibility helper for Streamlit rerun."""
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
    elif hasattr(st, "rerun"):
        st.rerun()

def rerun():
    """Backward compatible wrapper."""
    do_rerun()

# ---------- Backend URL ----------
DEFAULT_BACKEND_URL = "http://localhost:8000"
try:
    BACKEND_URL = st.secrets["BACKEND_URL"]
except (FileNotFoundError, KeyError, StreamlitAPIException):
    BACKEND_URL = os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL)

# ---------- Auth headers (rebuilt on each run) ----------
AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['token']}"} if "token" in st.session_state else {}

# ---------- Labels for R strategies ----------
LABELS = {
    "R0": "Refuse",
    "R1": "Rethink",
    "R2": "Reduce",
    "R3": "Reuse",
    "R4": "Repair",
    "R5": "Refurbish",
    "R6": "Remanufacture",
    "R7": "Repurpose",
    "R8": "Recycle",
    "R9": "Recover",
}

# ---------- API helpers ----------
def get_materials():
    project_id = st.session_state.get("project_id")
    if not project_id:
        return []
    try:
        r = requests.get(
            f"{BACKEND_URL}/materials",
            params={"project_id": project_id},
            headers=AUTH_HEADERS,
        )
        if r.ok:
            return r.json()
        st.error(r.text)
    except Exception as e:
        st.error(str(e))
    return []

def get_components():
    project_id = st.session_state.get("project_id")
    if not project_id:
        return []
    try:
        r = requests.get(
            f"{BACKEND_URL}/components",
            params={"project_id": project_id},
            headers=AUTH_HEADERS,
        )
        if r.ok:
            return r.json()
        st.error(r.text)
    except Exception as e:
        st.error(str(e))
    return []

def get_projects():
    try:
        r = requests.get(
            f"{BACKEND_URL}/projects",
            headers=AUTH_HEADERS,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return []

# ---------- Projects (Landing) ----------
def render_projects():
    st.title("Your Projects")

    # Unauthenticated: show login form in main
    if "token" not in st.session_state:
        with st.form("login_main"):
            st.subheader("Sign in")
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                try:
                    res = requests.post(f"{BACKEND_URL}/token", data={"username": u, "password": p})
                    res.raise_for_status()
                    st.session_state["token"] = res.json().get("access_token")
                    navigate("Projects")
                except Exception:
                    st.error("Login failed")
        return

    # Authenticated: load projects
    try:
        projects = get_projects() or []
    except Exception:
        projects = []

    # Sort older first; fallback by id
    def sort_key(p):
        return (p.get("created_at") or ""), p.get("id", 0)

    projs_sorted = sorted(projects, key=sort_key)

    # Tiles list incl. Create tile at the end
    tiles = projs_sorted + [{"__create__": True}]

    # Create Project dialog
    @st.dialog("Create Project")
    def create_project_dialog():
        new_name = st.text_input("Project name")
        r_opts = {
            "Refuse (R0)": "R0",
            "Rethink (R1)": "R1",
            "Reduc
