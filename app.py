import requests
import streamlit as st

API_URL = "http://localhost:8000"

st.title("DIMOP Admin")

# ------- Material Section -------
st.header("Materials")

with st.form("add_material_form"):
    m_name = st.text_input("Name")
    m_gwp = st.number_input("GWP", value=0, step=1)
    submitted = st.form_submit_button("Add Material")
    if submitted:
        resp = requests.post(f"{API_URL}/materials/", json={"Name": m_name, "GWP": m_gwp})
        if resp.ok:
            st.success("Material added")
        else:
            st.error(f"Error: {resp.text}")

materials = requests.get(f"{API_URL}/materials/").json()
for mat in materials:
    exp = st.expander(f"{mat['Name']} (ID {mat['Material_ID']})")
    with exp.form(f"update_material_{mat['Material_ID']}"):
        name = st.text_input("Name", value=mat["Name"])
        gwp = st.number_input("GWP", value=mat["GWP"], step=1)
        if st.form_submit_button("Update"):
            requests.put(f"{API_URL}/materials/{mat['Material_ID']}", json={"Name": name, "GWP": gwp})
            st.experimental_rerun()
    if exp.button("Delete", key=f"del_mat_{mat['Material_ID']}"):
        requests.delete(f"{API_URL}/materials/{mat['Material_ID']}")
        st.experimental_rerun()

# ------- Component Section -------
st.header("Components")

with st.form("add_component_form"):
    c_name = st.text_input("Name", key="cname")
    c_ebene = st.number_input("Ebene", value=1, step=1, key="cebene")
    c_material_id = st.number_input("Material ID", value=1, step=1, key="cmat")
    c_parent_id = st.number_input("Parent ID", value=0, step=1, key="cparent")
    c_atomar = st.checkbox("Atomar", value=True)
    c_gewicht = st.number_input("Gewicht (g)", value=0, step=1)
    c_wieder = st.checkbox("Wiederverwendbar", value=True)
    c_verbindung = st.text_input("Verbindungstyp", value="unknown")
    if st.form_submit_button("Add Component"):
        payload = {
            "Name": c_name,
            "Ebene": int(c_ebene),
            "Parent_ID": int(c_parent_id) if c_parent_id else None,
            "Atomar": c_atomar,
            "Gewicht": int(c_gewicht),
            "Komponente_Wiederverwendbar": c_wieder,
            "Verbindungstyp": c_verbindung,
            "Material_ID": int(c_material_id),
        }
        requests.post(f"{API_URL}/components/", json=payload)
        st.experimental_rerun()

components = requests.get(f"{API_URL}/components/").json()
for comp in components:
    exp = st.expander(f"{comp['Name']} (ID {comp['ID']})")
    with exp.form(f"update_component_{comp['ID']}"):
        name = st.text_input("Name", value=comp["Name"], key=f"cname_{comp['ID']}")
        ebene = st.number_input("Ebene", value=comp["Ebene"], step=1, key=f"cebene_{comp['ID']}")
        parent = st.number_input("Parent ID", value=comp["Parent_ID"] or 0, step=1, key=f"cparent_{comp['ID']}")
        atomar = st.checkbox("Atomar", value=comp["Atomar"], key=f"catomar_{comp['ID']}")
        gewicht = st.number_input("Gewicht", value=comp["Gewicht"], step=1, key=f"cgewicht_{comp['ID']}")
        wieder = st.checkbox("Wiederverwendbar", value=comp["Komponente_Wiederverwendbar"], key=f"cwieder_{comp['ID']}")
        verbindung = st.text_input("Verbindungstyp", value=comp["Verbindungstyp"], key=f"cverb_{comp['ID']}")
        material_id = st.number_input("Material ID", value=comp["Material_ID"], step=1, key=f"cmaterial_{comp['ID']}")
        if st.form_submit_button("Update"):
            payload = {
                "Name": name,
                "Ebene": int(ebene),
                "Parent_ID": int(parent) if parent else None,
                "Atomar": atomar,
                "Gewicht": int(gewicht),
                "Komponente_Wiederverwendbar": wieder,
                "Verbindungstyp": verbindung,
                "Material_ID": int(material_id),
            }
            requests.put(f"{API_URL}/components/{comp['ID']}", json=payload)
            st.experimental_rerun()
    if exp.button("Delete", key=f"del_comp_{comp['ID']}"):
        requests.delete(f"{API_URL}/components/{comp['ID']}")
        st.experimental_rerun()
