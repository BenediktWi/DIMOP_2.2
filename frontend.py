import streamlit as st
import requests

BACKEND_URL = st.secrets.get("BACKEND_URL", "http://localhost:8000")


def get_materials():
    try:
        r = requests.get(f"{BACKEND_URL}/materials")
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def get_components():
    try:
        r = requests.get(f"{BACKEND_URL}/components")
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
            requests.delete(f"{BACKEND_URL}/materials/{m['id']}")
            st.experimental_rerun()

elif page == "Components":
    materials = get_materials()
    mat_dict = {m['name']: m['id'] for m in materials}

    st.header("Create component")
    with st.form("create_component"):
        name = st.text_input("Name")
        mat_name = st.selectbox("Material", list(mat_dict.keys())) if mat_dict else ""
        submitted = st.form_submit_button("Create")
        if submitted and name and mat_dict:
            res = requests.post(
                f"{BACKEND_URL}/components",
                json={"name": name, "material_id": mat_dict[mat_name]},
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
            mat_idx = mat_names.index(
                next((n for n, i in mat_dict.items() if i == comp['material_id']), mat_names[0])
            ) if mat_dict else 0
            up_mat = st.selectbox("Material", mat_names, index=mat_idx) if mat_dict else ""
            updated = st.form_submit_button("Update")
            if updated:
                res = requests.put(
                    f"{BACKEND_URL}/components/{comp['id']}",
                    json={"name": up_name, "material_id": mat_dict.get(up_mat)},
                )
                if res.ok:
                    st.success("Component updated")
                else:
                    st.error(res.text)
    else:
        st.info("No components available")

    st.header("Existing components")
    for c in components:
        mat_name = next((m['name'] for m in materials if m['id'] == c['material_id']), 'N/A')
        col1, col2 = st.columns([4, 1])
        col1.write(f"{c['name']} ({c['id']}) - Material: {mat_name}")
        if col2.button("Delete", key=f"del_comp_{c['id']}"):
            requests.delete(f"{BACKEND_URL}/components/{c['id']}")
            st.experimental_rerun()

