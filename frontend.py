# frontend.py
import os
import json
import requests
import streamlit as st
from streamlit.errors import StreamlitAPIException
from graphviz import Digraph

# ---------------------------
# Basic page config
# ---------------------------
st.set_page_config(page_title="DiMOP 2.2", page_icon="♻️", layout="wide")

# ---------------------------
# Rerun helpers (compat across Streamlit versions)
# ---------------------------
def do_rerun():
    """Compatibility helper for Streamlit rerun."""
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
    elif hasattr(st, "rerun"):
        st.rerun()

def rerun():
    """Backward compatible wrapper."""
    do_rerun()

# ---------------------------
# Backend URL resolution
# Order: st.secrets -> ENV -> default
# ---------------------------
DEFAULT_BACKEND_URL = "http://localhost:8000"
try:
    BACKEND_URL = st.secrets["BACKEND_URL"]
except (FileNotFoundError, KeyError, StreamlitAPIException):
    BACKEND_URL = os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL)

# ---------------------------
# Session defaults
# ---------------------------
for key, default in [
    ("is_auth", False),
    ("auth_token", None),
    ("user_name", None),
    ("project_id", None),
    ("projects_cache", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------
# Auth header helper
# ---------------------------
def auth_headers():
    token = st.session_state.get("auth_token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}

# ---------------------------
# Simple API helpers
# ---------------------------
def api_get(path: str, params=None):
    url = f"{BACKEND_URL.rstrip('/')}/{path.lstrip('/')}"
    try:
        r = requests.get(url, params=params or {}, headers=auth_headers(), timeout=30)
        r.raise_for_status()
        if r.content:
            return r.json()
        return None
    except requests.RequestException as e:
        st.error(f"GET {url} failed: {e}")
        return None

def api_post(path: str, payload=None):
    url = f"{BACKEND_URL.rstrip('/')}/{path.lstrip('/')}"
    try:
        r = requests.post(url, data=json.dumps(payload or {}), headers={
            "Content-Type": "application/json",
            **auth_headers()
        }, timeout=30)
        r.raise_for_status()
        if r.content:
            return r.json()
        return None
    except requests.RequestException as e:
        st.error(f"POST {url} failed: {e}")
        return None

# ---------------------------
# Data fetching helpers
# ---------------------------
def get_projects():
    """Fetch once and cache."""
    if st.session_state.projects_cache is not None:
        return st.session_state.projects_cache
    data = api_get("/projects")
    if isinstance(data, list):
        st.session_state.projects_cache = data
    else:
        st.session_state.projects_cache = []
    return st.session_state.projects_cache

def get_materials(project_id: int):
    if not project_id:
        return []
    data = api_get("/materials", params={"project_id": project_id})
    return data if isinstance(data, list) else []

def get_components_tree(project_id: int):
    if not project_id:
        return {}
    data = api_get("/components/tree", params={"project_id": project_id})
    return data if isinstance(data, dict) else {}

# ---------------------------
# UI Helpers
# ---------------------------
def hide_streamlit_chrome_for_logged_out():
    """
    When not authenticated:
      - Hide sidebar entirely
      - Keep a clean 'DIMOP 2.2' landing with login form
    """
    st.markdown(
        """
        <style>
            /* Hide sidebar entirely */
            [data-testid="stSidebar"] { display: none !important; }
            /* Hide hamburger menu and Streamlit footer */
            [data-testid="baseButton-headerNoPadding"] { display: none !important; }
            footer { visibility: hidden; }
            /* Optional: reduce top padding for a tighter look */
            .block-container { padding-top: 2rem; }
        </style>
        """,
        unsafe_allow_html=True
    )

def logout_button():
    with st.sidebar:
        st.markdown("### Account")
        if st.button("Logout", use_container_width=True):
            for k in ["is_auth", "auth_token", "user_name", "project_id", "projects_cache"]:
                st.session_state[k] = None if k != "is_auth" else False
            rerun()

def project_selector():
    with st.sidebar:
        st.markdown("### Project")
        projects = get_projects()
        if not projects:
            st.info("No projects available.")
            return
        # Build mapping
        names = [p.get("name", f"Project {p.get('id')}") for p in projects]
        ids = [p.get("id") for p in projects]

        # Determine current index
        if st.session_state.project_id in ids:
            current_idx = ids.index(st.session_state.project_id)
        else:
            current_idx = 0

        choice = st.selectbox("Select project", options=list(range(len(names))),
                              format_func=lambda i: names[i], index=current_idx)
        chosen_id = ids[choice]
        if chosen_id != st.session_state.project_id:
            st.session_state.project_id = chosen_id
            rerun()

# ---------------------------
# Views
# ---------------------------
def render_login():
    hide_streamlit_chrome_for_logged_out()
    st.title("DiMOP 2.2")

    st.write("Please sign in to continue.")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", value="", autocomplete="username")
        password = st.text_input("Password", value="", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in")
        if submitted:
            if not username or not password:
                st.warning("Please enter both username and password.")
            else:
                # Adjust to your backend auth endpoint/response
                resp = api_post("/auth/login", {"username": username, "password": password})
                if resp and "access_token" in resp:
                    st.session_state.is_auth = True
                    st.session_state.auth_token = resp["access_token"]
                    st.session_state.user_name = username
                    # Reset caches on new login
                    st.session_state.projects_cache = None
                    st.session_state.project_id = None
                    st.success("Signed in successfully.")
                    rerun()
                else:
                    st.error("Invalid credentials or server error.")

def render_components_graph(project_id: int):
    """
    Renders a simple component tree graph using Graphviz.
    Expects backend /components/tree to return a dict like:
    {
      "id": 1, "name": "Product A", "children": [
        {"id": 2, "name": "Assembly B", "children": [...]},
        ...
      ]
    }
    """
    tree = get_components_tree(project_id)
    if not tree:
        st.info("No component tree available.")
        return

    dot = Digraph(comment="Component Tree", format="svg")
    dot.attr(rankdir="LR", concentrate="true", fontsize="10")

    def add_node(n):
        nid = str(n.get("id"))
        label = n.get("name", f"Node {nid}")
        dot.node(nid, label=label, shape="box", style="rounded")
        for child in n.get("children", []):
            cid = str(child.get("id"))
            dot.edge(nid, cid)
            add_node(child)

    add_node(tree)
    st.graphviz_chart(dot.source, use_container_width=True)

def render_app():
    # Sidebar controls
    logout_button()
    project_selector()

    st.title("DiMOP 2.2")
    if not st.session_state.project_id:
        st.warning("Please select a project from the sidebar.")
        return

    # Main content tabs
    tab1, tab2 = st.tabs(["Overview", "Materials"])

    with tab1:
        st.subheader("Components")
        render_components_graph(st.session_state.project_id)

        st.subheader("Create a new component")
        # IMPORTANT: Use a form with submit button; no callbacks on other widgets
        with st.form("create_component_form", clear_on_submit=True):
            comp_name = st.text_input("Component name")
            parent_id = st.number_input(
                "Parent component ID (leave 0 for root)", min_value=0, value=0, step=1
            )
            weight = st.number_input("Weight (kg)", min_value=0.0, value=0.0, step=0.01, format="%.4f")
            submitted = st.form_submit_button("Create component")
            if submitted:
                payload = {
                    "project_id": st.session_state.project_id,
                    "name": comp_name,
                    "parent_id": int(parent_id) if parent_id else None,
                    "weight": float(weight),
                }
                resp = api_post("/components", payload)
                if resp and resp.get("id"):
                    st.success(f"Component created (ID: {resp['id']}).")
                    rerun()
                else:
                    st.error("Failed to create component.")

    with tab2:
        st.subheader("Materials by project")
        mats = get_materials(st.session_state.project_id)
        if not mats:
            st.info("No materials found for the selected project.")
        else:
            # Simple table
            st.dataframe(
                [
                    {
                        "ID": m.get("id"),
                        "Name": m.get("name"),
                        "Family": m.get("family"),
                        "GWP_total": m.get("gwp_total"),
                        "ADPf": m.get("adpf"),
                        "Dangerous": bool(m.get("is_dangerous")),
                    }
                    for m in mats
                ],
                use_container_width=True,
            )

        st.divider()
        st.subheader("Add material")
        with st.form("add_material_form", clear_on_submit=True):
            m_name = st.text_input("Material name")
            m_family = st.text_input("Material family (optional)")
            m_gwp = st.number_input("GWP total", min_value=0.0, value=0.0, step=0.001, format="%.6f")
            m_adpf = st.number_input("ADPf", min_value=0.0, value=0.0, step=0.001, format="%.6f")
            m_danger = st.checkbox("Dangerous substance")
            submitted = st.form_submit_button("Create material")
            if submitted:
                payload = {
                    "project_id": st.session_state.project_id,
                    "name": m_name,
                    "family": m_family or None,
                    "gwp_total": float(m_gwp),
                    "adpf": float(m_adpf),
                    "is_dangerous": bool(m_danger),
                }
                resp = api_post("/materials", payload)
                if resp and resp.get("id"):
                    st.success(f"Material created (ID: {resp['id']}).")
                    # Invalidate cache? materials aren’t cached here, simply rerun.
                    rerun()
                else:
                    st.error("Failed to create material.")

# ---------------------------
# Main router
# ---------------------------
def main():
    if not st.session_state.is_auth:
        render_login()
        return

    # Authenticated app
    render_app()

if __name__ == "__main__":
    main()
