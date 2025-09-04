import os
import streamlit as st
from streamlit.errors import StreamlitAPIException
import requests

# Fallback-Logik für BACKEND_URL: zuerst st.secrets, dann ENV, sonst Default
DEFAULT_BACKEND_URL = "http://localhost:8000"
try:
    BACKEND_URL = st.secrets["BACKEND_URL"]
except (FileNotFoundError, KeyError, StreamlitAPIException):
    BACKEND_URL = os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL)

# TODO: add Streamlit-based login und Token-Handling
# auth_token = st.session_state.get("token")
# AUTH_HEADERS = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}


def get_materials():
    try:
        r = requests.get(f"{BACKEND_URL}/materials")  # später mit AUTH_HEADERS
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def get_components():
    try:
        r = requests.get(f"{BACKEND_URL}/components")  # später mit AUTH_HEADERS
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def require_auth():
    if not st.session_state.get("token"):
        st.error("Please log in to access this page.")
        st.stop()


def render_materials():
    require_auth()
    st.header("Create material")
    with st.form("create_material"):
        name = st.text_input("Name")
        description = st.text_input("Description")
        submitted = st.form_submit_button("Create")
        if submitted and name:
            res = requests.post(
                f"{BACKEND_URL}/materials",
                json={"name": name, "description": description},
                # TODO: pass AUTH_HEADERS once login is implemented
            )
            if res.ok:
                st.success("Material created")
                st.experimental_rerun()
            else:
                st.error(res.text)

    st.header("Update material")
    materials = get_materials()
    if materials:
        mat_options = {f"{m['name']} (id:{m['id']})": m for m in materials}
        selected = st.selectbox("Select material", list(mat_options.keys()))
        mat = mat_options[selected]
        with st.form("update_material"):
            up_name = st.text_input("Name", mat["name"])
            up_desc = st.text_input("Description", mat.get("description", ""))
            updated = st.form_submit_button("Update")
            if updated:
                res = requests.put(
                    f"{BACKEND_URL}/materials/{mat['id']}",
                    json={"name": up_name, "description": up_desc},
                    # TODO: pass AUTH_HEADERS once login is implemented
                )
                if res.ok:
                    st.success("Material updated")
                    st.experimental_rerun()
                else:
                    st.error(res.text)
    else:
        st.info("No materials available")

    st.header("Existing materials")
    for m in materials:
        col1, col2 = st.columns([4, 1])
        col1.write(f"{m['name']} ({m['id']}) - {m.get('description', '')}")
        if col2.button("Delete", key=f"del_mat_{m['id']}"):
            requests.delete(
                f"{BACKEND_URL}/materials/{m['id']}",
                # TODO: pass AUTH_HEADERS once login is implemented
            )
            st.experimental_rerun()


def render_components():
    require_auth()
    materials = get_materials()
    mat_dict = {m['name']: m['id'] for m in materials}
    components = get_components()

    st.header("Create component")
    with st.form("create_component"):
        name = st.text_input("Name")
        mat_name = st.selectbox("Material", list(mat_dict.keys())) if mat_dict else ""
        level = st.number_input("Level", min_value=0, step=1, format="%d")
        parent_candidates = [c for c in components if c['level'] == level - 1] if level > 0 else []
        parent_map = {f"{c['name']} (id:{c['id']})": c['id'] for c in parent_candidates}
        parent_label = st.selectbox("Parent", [""] + list(parent_map.keys())) if parent_map else ""
        parent_id = parent_map.get(parent_label)
        submitted = st.form_submit_button("Create")
        if submitted and name and mat_dict:
            res = requests.post(
                f"{BACKEND_URL}/components",
                json={
                    "name": name,
                    "material_id": mat_dict[mat_name],
                    "level": int(level),
                    "parent_id": parent_id,
                },
                # TODO: pass AUTH_HEADERS once login is implemented
            )
            if res.ok:
                st.success("Component created")
                st.experimental_rerun()
            else:
                st.error(res.text)

    st.header("Update component")
    if components:
        comp_options = {f"{c['name']} (id:{c['id']})": c for c in components}
        selected = st.selectbox("Select component", list(comp_options.keys()))
        comp = comp_options[selected]
        with st.form("update_component"):
            up_name = st.text_input("Name", comp["name"])
            mat_names = list(mat_dict.keys())
            mat_idx = (
                mat_names.index(
                    next((n for n, i in mat_dict.items() if i == comp['material_id']), mat_names[0])
                )
                if mat_dict
                else 0
            )
            up_mat = st.selectbox("Material", mat_names, index=mat_idx) if mat_dict else ""
            up_level = st.number_input(
                "Level", min_value=0, step=1, format="%d", value=int(comp["level"])
            )
            parent_candidates = [
                c for c in components if c["level"] == up_level - 1 and c["id"] != comp["id"]
            ] if up_level > 0 else []
            parent_map = {f"{c['name']} (id:{c['id']})": c['id'] for c in parent_candidates}
            parent_default = next(
                (k for k, v in parent_map.items() if v == comp.get("parent_id")), ""
            )
            parent_index = (
                list(parent_map.keys()).index(parent_default) + 1 if parent_default else 0
            )
            up_parent_label = st.selectbox(
                "Parent", [""] + list(parent_map.keys()), index=parent_index
            )
            up_parent = parent_map.get(up_parent_label)
            updated = st.form_submit_button("Update")
            if updated:
                res = requests.put(
                    f"{BACKEND_URL}/components/{comp['id']}",
                    json={
                        "name": up_name,
                        "material_id": mat_dict.get(up_mat),
                        "level": int(up_level),
                        "parent_id": up_parent,
                    },
                    # TODO: pass AUTH_HEADERS once login is implemented
                )
                if res.ok:
                    st.success("Component updated")
                    st.experimental_rerun()
                else:
                    st.error(res.text)
    else:
        st.info("No components available")

    st.header("Existing components")
    for c in components:
        mat_name = next(
            (m['name'] for m in materials if m['id'] == c['material_id']), 'N/A'
        )
        parent_name = next(
            (p['name'] for p in components if p['id'] == c.get('parent_id')), 'None'
        )
        col1, col2 = st.columns([4, 1])
        col1.write(
            f"{c['name']} ({c['id']}) - Level: {c['level']} - Parent: {parent_name} - Material: {mat_name}"
        )
        if col2.button("Delete", key=f"del_comp_{c['id']}"):
            requests.delete(
                f"{BACKEND_URL}/components/{c['id']}",
                # TODO: pass AUTH_HEADERS once login is implemented
            )
            st.experimental_rerun()


def render_export_import():
    require_auth()
    st.header("Export/Import")
    st.info("Export/Import functionality not implemented yet.")


def render_projects():
    require_auth()
    st.header("Projects")
    st.info("Projects page not implemented yet.")


st.title("DIMOP 2.2")
page = st.session_state.get("page_select", "Projects")
if page == "Projects":
    render_projects()
elif page == "Materials":
    render_materials()
elif page == "Components":
    render_components()
elif page == "Export/Import":
    render_export_import()
