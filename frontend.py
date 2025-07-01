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

# AUTH_HEADERS = {
#     "Authorization": f"Bearer {auth_token}"
# } if auth_token else {}


def get_materials():
    try:
        r = requests.get(f"{BACKEND_URL}/materials")  # später mit
        # AUTH_HEADERS
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def get_components():
    try:
        r = requests.get(f"{BACKEND_URL}/components")  # später mit
        # AUTH_HEADERS
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


st.title("DIMOP 2.2")
page = st.sidebar.selectbox("Page", ["Materials", "Components"])

if page == "Materials":
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
                f"{BACKEND_URL}/materials/{m['id']}"
                # TODO: pass AUTH_HEADERS once login is implemented
            )
            st.experimental_rerun()

elif page == "Components":
    materials = get_materials()
    mat_dict = {m['name']: m['id'] for m in materials}

    st.header("Create component")
    with st.form("create_component"):
        name = st.text_input("Name")
        mat_name = (
            st.selectbox("Material", list(mat_dict.keys()))
            if mat_dict
            else ""
        )
        submitted = st.form_submit_button("Create")
        if submitted and name and mat_dict:
            res = requests.post(
                f"{BACKEND_URL}/components",
                json={"name": name, "material_id": mat_dict[mat_name]},
                # TODO: pass AUTH_HEADERS once login is implemented
            )
            if res.ok:
                st.success("Component created")
            else:
                st.error(res.text)

    st.header("Update component")
    components = get_components()
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
            updated = st.form_submit_button("Update")
            if updated:
                res = requests.put(
                    f"{BACKEND_URL}/components/{comp['id']}",
                    json={
                        "name": up_name,
                        "material_id": mat_dict.get(up_mat),
                    },
                    # TODO: pass AUTH_HEADERS once login is implemented
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
                f"{BACKEND_URL}/components/{c['id']}"
                # TODO: pass AUTH_HEADERS once login is implemented
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
