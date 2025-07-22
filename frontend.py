import os
import streamlit as st
from streamlit.errors import StreamlitAPIException
from graphviz import Digraph
import requests

# Fallback-Logik für BACKEND_URL: zuerst st.secrets, dann ENV, sonst Default
DEFAULT_BACKEND_URL = "http://localhost:8000"
try:
    BACKEND_URL = st.secrets["BACKEND_URL"]
except (FileNotFoundError, KeyError, StreamlitAPIException):
    BACKEND_URL = os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL)

auth_token = st.session_state.get("token")

if not auth_token:
    with st.sidebar.form("login"):
        st.write("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            try:
                res = requests.post(
                    f"{BACKEND_URL}/token",
                    data={"username": username, "password": password},
                )
                res.raise_for_status()
                st.session_state.token = res.json().get("access_token")
                st.experimental_rerun()
            except Exception:
                st.error("Login failed")
else:
    st.sidebar.write("Logged in")
    if st.sidebar.button("Logout"):
        del st.session_state["token"]
        st.experimental_rerun()

AUTH_HEADERS = {
    "Authorization": f"Bearer {st.session_state['token']}"
} if st.session_state.get("token") else {}


def get_materials():
    try:
        r = requests.get(
            f"{BACKEND_URL}/materials",
            headers=AUTH_HEADERS,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def get_components():
    try:
        r = requests.get(
            f"{BACKEND_URL}/components",
            headers=AUTH_HEADERS,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def build_graphviz_tree(items):
    dot = Digraph()
    for comp in items:
        label = f"{comp['name']}\nLevel {comp.get('level', '')}"
        dot.node(str(comp['id']), label)
    for comp in items:
        parent = comp.get('parent_id')
        if parent:
            dot.edge(str(parent), str(comp['id']))
    return dot


st.title("DIMOP 2.2")
page = st.sidebar.selectbox(
    "Page",
    ["Materials", "Components", "Export/Import"],
)

if page == "Materials":
    st.header("Create material")
    with st.form("create_material"):
        name = st.text_input("Name")
        description = st.text_input("Description")
        co2_value = st.number_input("CO2 value", value=0.0)
        submitted = st.form_submit_button("Create")
        if submitted and name:
            res = requests.post(
                f"{BACKEND_URL}/materials",
                json={
                    "name": name,
                    "description": description,
                    "co2_value": co2_value,
                },
                headers=AUTH_HEADERS,
            )
            if res.ok:
                st.success("Material created")
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
            up_co2 = st.number_input(
                "CO2 value",
                value=mat.get("co2_value", 0.0) or 0.0,
            )
            updated = st.form_submit_button("Update")
            if updated:
                res = requests.put(
                    f"{BACKEND_URL}/materials/{mat['id']}",
                    json={
                        "name": up_name,
                        "description": up_desc,
                        "co2_value": up_co2,
                    },
                    headers=AUTH_HEADERS,
                )
                if res.ok:
                    st.success("Material updated")
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
                headers=AUTH_HEADERS,
            )
            st.experimental_rerun()

elif page == "Components":
    materials = get_materials()
    mat_dict = {m['name']: m['id'] for m in materials}
    components = get_components()

    st.header("Create component")
    with st.form("create_component"):
        name = st.text_input("Name")
        mat_name = (
            st.selectbox("Material", list(mat_dict.keys()))
            if mat_dict
            else ""
        )
        level = st.number_input("Level", value=0, step=1)
        parent_map = {
            "None": None,
            **{
                f"{c['name']} (id:{c['id']})": c["id"]
                for c in components
            },
        }
        parent_sel = st.selectbox("Parent component", list(parent_map.keys()))
        is_atomic = st.checkbox("Atomic")
        weight = st.number_input("Weight", value=0.0)
        reusable = st.checkbox("Reusable")
        connection_type = st.number_input("Connection type", value=0, step=1)
        submitted = st.form_submit_button("Create")
        if submitted and name and mat_dict:
            res = requests.post(
                f"{BACKEND_URL}/components",
                json={
                    "name": name,
                    "material_id": mat_dict[mat_name],
                    "level": level,
                    "parent_id": parent_map[parent_sel],
                    "is_atomic": is_atomic,
                    "weight": weight,
                    "reusable": reusable,
                    "connection_type": connection_type,
                },
                headers=AUTH_HEADERS,
            )
            if res.ok:
                st.success("Component created")
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
                    next(
                        (
                            n
                            for n, i in mat_dict.items()
                            if i == comp['material_id']
                        ),
                        mat_names[0],
                    )
                )
                if mat_dict
                else 0
            )
            up_mat = (
                st.selectbox("Material", mat_names, index=mat_idx)
                if mat_dict
                else ""
            )
            up_level = st.number_input(
                "Level",
                value=comp.get("level", 0) or 0,
                step=1,
            )
            parent_map = {
                "None": None,
                **{
                    f"{c['name']} (id:{c['id']})": c["id"]
                    for c in components
                },
            }
            current_parent = comp.get("parent_id")
            if current_parent is None:
                parent_idx = 0
            else:
                parent_idx = list(parent_map.values()).index(current_parent)
            up_parent = st.selectbox(
                "Parent component",
                list(parent_map.keys()),
                index=parent_idx,
            )
            up_atomic = st.checkbox(
                "Atomic",
                value=comp.get("is_atomic", False),
            )
            up_weight = st.number_input(
                "Weight",
                value=comp.get("weight", 0.0) or 0.0,
            )
            up_reusable = st.checkbox(
                "Reusable",
                value=comp.get("reusable", False),
            )
            up_conn = st.number_input(
                "Connection type",
                value=comp.get("connection_type", 0) or 0,
                step=1,
            )
            updated = st.form_submit_button("Update")
            if updated:
                res = requests.put(
                    f"{BACKEND_URL}/components/{comp['id']}",
                    json={
                        "name": up_name,
                        "material_id": mat_dict.get(up_mat),
                        "level": up_level,
                        "parent_id": parent_map[up_parent],
                        "is_atomic": up_atomic,
                        "weight": up_weight,
                        "reusable": up_reusable,
                        "connection_type": up_conn,
                    },
                    headers=AUTH_HEADERS,
                )
                if res.ok:
                    st.success("Component updated")
                else:
                    st.error(res.text)
    else:
        st.info("No components available")

    st.header("Existing components")
    for c in components:
        mat_name = next(
            (m['name'] for m in materials if m['id'] == c['material_id']),
            'N/A',
        )
        col1, col2 = st.columns([4, 1])
        col1.write(f"{c['name']} ({c['id']}) - Material: {mat_name}")
        if col2.button("Delete", key=f"del_comp_{c['id']}"):
            requests.delete(
                f"{BACKEND_URL}/components/{c['id']}",
                headers=AUTH_HEADERS,
            )
            st.experimental_rerun()

    def build_tree(items):
        comp_map = {c['id']: {**c, 'children': []} for c in items}
        roots = []
        for comp in comp_map.values():
            parent_id = comp.get('parent_id')
            if parent_id and parent_id in comp_map:
                comp_map[parent_id]['children'].append(comp)
            else:
                roots.append(comp)
        return roots

    def display_tree(nodes, level=0):
        for node in nodes:
            indent = " " * (level * 4)
            st.markdown(f"{indent}- {node['name']} (id:{node['id']})")
            if node['children']:
                display_tree(node['children'], level + 1)

    st.header("Component hierarchy")
    st.graphviz_chart(build_graphviz_tree(components))
    tree = build_tree(components)
    display_tree(tree)

    if st.button("Fertigstellen"):
        st.session_state.show_finish = True

    if st.session_state.get("show_finish"):
        with st.modal("Fertigstellen bestätigen"):
            st.write("Nachhaltigkeitsbewertung berechnen?")
            col1, col2 = st.columns(2)
            if col1.button("Ja, berechnen"):
                try:
                    res = requests.post(
                        f"{BACKEND_URL}/sustainability/calculate"
                    )
                    res.raise_for_status()
                    st.session_state.sustainability = res.json()
                except Exception as e:
                    st.session_state.sustainability = []
                    st.error(str(e))
                st.session_state.show_finish = False
                st.experimental_rerun()
            if col2.button("Abbrechen"):
                st.session_state.show_finish = False
                st.experimental_rerun()

    if st.session_state.get("sustainability"):
        st.header("Sustainability scores")
        for entry in st.session_state.sustainability:
            st.write(f"{entry['name']}: {entry['score']:.2f}")

elif page == "Export/Import":
    st.header("Export database")
    if st.button("Download CSV"):
        try:
            res = requests.get(
                f"{BACKEND_URL}/export",
                headers=AUTH_HEADERS,
            )
            res.raise_for_status()
            st.download_button(
                "Save export.csv",
                res.text,
                file_name="export.csv",
                mime="text/csv",
            )
            st.success("Export generated")
        except Exception as e:
            st.error(str(e))

    st.header("Import database")
    uploaded = st.file_uploader("CSV file", type="csv")
    if uploaded and st.button("Upload"):
        try:
            files = {"file": (uploaded.name, uploaded.getvalue(), "text/csv")}
            resp = requests.post(
                f"{BACKEND_URL}/import",
                files=files,
                headers=AUTH_HEADERS,
            )
            resp.raise_for_status()
            st.success("Import successful")
        except Exception as e:
            st.error(str(e))
