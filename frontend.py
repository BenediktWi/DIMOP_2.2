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

    # Tiles list
    tiles = projs_sorted

    # Create Project dialog
    @st.dialog("Create Project")
    def create_project_dialog():
        new_name = st.text_input("Project name")
        r_opts = {
            "Refuse (R0)": "R0",
            "Rethink (R1)": "R1",
            "Reduce (R2)": "R2",
            "Reuse (R3)": "R3",
            "Repair (R4)": "R4",
            "Refurbish (R5)": "R5",
            "Remanufacture (R6)": "R6",
            "Repurpose (R7)": "R7",
            "Recycle (R8)": "R8",
            "Recover (R9)": "R9",
        }
        selected_strats = [
            code
            for label, code in r_opts.items()
            if st.checkbox(label, key=f"dlg_{code}")
        ]
        c1, c2 = st.columns(2)
        if c1.button("Create"):
            if not new_name:
                st.error("Please enter a name")
            else:
                try:
                    res = requests.post(
                        f"{BACKEND_URL}/projects",
                        json={"name": new_name, "r_strategies": selected_strats},
                        headers=AUTH_HEADERS,
                    )
                    res.raise_for_status()
                    st.success("Project created")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        if c2.button("Cancel"):
            st.rerun()

    # Grid: 3 columns, fill left-to-right
    N_COLS = 3
    cols = st.columns(N_COLS)

    for i, proj in enumerate(tiles):
        col = cols[i % N_COLS]
        with col:
            # Tile: fixed-height name area + buttons -> consistent tile heights
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div style="
                        height:64px;
                        overflow:hidden;
                        display:-webkit-box;
                        -webkit-line-clamp:2;
                        -webkit-box-orient:vertical;
                        font-weight:600;
                        font-size:1.1rem;
                        line-height:1.2;">{proj['name']}</div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Select", key=f"proj_select_{proj['id']}", use_container_width=True):
                    st.session_state["project_id"] = proj["id"]
                    st.session_state["r_strategies"] = proj.get("r_strategies") or []
                    navigate("Components")  # jump to Components when selecting a Project
                st.write("")
                st.button("Delete", key=f"proj_delete_{proj['id']}", use_container_width=True)

    # Centered Create Project tile
    create_cols = st.columns(N_COLS)
    with create_cols[1]:
        with st.container(border=True):
            if st.button(
                "➕ Create Project",
                use_container_width=True,
                key="create_project_main",
            ):
                create_project_dialog()

    from streamlit.components.v1 import html
    html(
        """
        <script>
        const doc = window.parent.document;
        Array.from(doc.getElementsByTagName('button')).forEach(btn => {
            const txt = btn.innerText.trim();
            if (txt === 'Select') btn.classList.add('btn-select');
            else if (txt === 'Delete') btn.classList.add('btn-delete');
            else if (txt === '➕ Create Project') btn.classList.add('btn-create');
        });
        </script>
        <style>
        .btn-select:hover { background-color: #00B050 !important; }
        .btn-delete:hover { background-color: #FF0000 !important; }
        .btn-create:hover { filter: brightness(1.05); }
        </style>
        """,
        height=0,
    )

# ---------- Misc ----------
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

# ---------- Title ----------
st.title("DIMOP 2.2")

# ---------- Sidebar: Page select (no warning, no direct state writes) ----------
page_options = ["Projects", "Materials", "Components", "Export/Import"]
pending_nav = st.session_state.pop("_nav_to", None)

if pending_nav and pending_nav in page_options:
    # Programmatic navigation this run: set default index via widget (no direct session write)
    st.sidebar.selectbox("Page", page_options, index=page_options.index(pending_nav), key="page_select")
elif "page_select" in st.session_state:
    # Let existing widget value stand; don't pass index explicitly to avoid warning
    st.sidebar.selectbox("Page", page_options, key="page_select")
else:
    # First run: default to Projects
    st.sidebar.selectbox("Page", page_options, index=page_options.index("Projects"), key="page_select")

# ---------- Sidebar: Project dropdown + R tags + Logout ----------
if "token" in st.session_state:
    # Project dropdown (kept as requested)
    projects = get_projects()
    if projects:
        proj_options = {f"{p['name']} (id:{p['id']})": p['id'] for p in projects}
        proj_map = {p['id']: p for p in projects}
        if "project_id" not in st.session_state and proj_options:
            st.session_state.project_id = next(iter(proj_options.values()))
        selected = st.sidebar.selectbox(
            "Project",
            list(proj_options.keys()),
            index=list(proj_options.values()).index(st.session_state.project_id) if proj_options else 0,
        )
        st.session_state.project_id = proj_options[selected]
        st.session_state.r_strategies = (
            proj_map[st.session_state.project_id].get("r_strategies") or []
        )
    else:
        st.sidebar.write("No projects available")

    # R strategy tags under the dropdown
    codes = st.session_state.get("r_strategies") or []
    labels = [LABELS.get(c, c) for c in codes]
    if labels:
        st.sidebar.markdown(
            " ".join(
                [
                    f"<span style='padding:2px 6px;border:1px solid #ccc;border-radius:8px;"
                    f"font-size:12px;margin-right:4px'>{lbl}</span>"
                    for lbl in labels
                ]
            ),
            unsafe_allow_html=True,
        )

    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        st.session_state.pop("token", None)
        navigate("Projects")

# ---------- Page renderers ----------

def render_materials():
    require_auth()
    st.header("Create material")
    with st.form("create_material"):
        name = st.text_input("Name")
        description = st.text_input("Description")
        total_gwp = st.number_input("Total - GWP", value=0.0)
        fossil_gwp = st.number_input("Fossil - GWP", value=0.0)
        biogenic_gwp = st.number_input("Biogenic - GWP", value=0.0)
        adpf = st.number_input("ADPF", value=0.0)
        density = st.number_input("Density", value=0.0)
        is_dangerous = st.checkbox("Dangerous")
        submitted = st.form_submit_button("Create")
        if submitted and name:
            res = requests.post(
                f"{BACKEND_URL}/materials",
                json={
                    "name": name,
                    "description": description,
                    "total_gwp": total_gwp,
                    "fossil_gwp": fossil_gwp,
                    "biogenic_gwp": biogenic_gwp,
                    "adpf": adpf,
                    "density": density,
                    "is_dangerous": is_dangerous,
                    "project_id": st.session_state.get("project_id"),
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
            up_total = st.number_input(
                "Total - GWP",
                value=mat.get("total_gwp", 0.0) or 0.0,
            )
            up_fossil = st.number_input(
                "Fossil - GWP",
                value=mat.get("fossil_gwp", 0.0) or 0.0,
            )
            up_bio = st.number_input(
                "Biogenic - GWP",
                value=mat.get("biogenic_gwp", 0.0) or 0.0,
            )
            up_adpf = st.number_input(
                "ADPF",
                value=mat.get("adpf", 0.0) or 0.0,
            )
            up_density = st.number_input(
                "Density",
                value=mat.get("density", 0.0) or 0.0,
            )
            up_danger = st.checkbox(
                "Dangerous",
                value=mat.get("is_dangerous", False),
            )
            updated = st.form_submit_button("Update")
            if updated:
                res = requests.put(
                    f"{BACKEND_URL}/materials/{mat['id']}",
                    json={
                        "name": up_name,
                        "description": up_desc,
                        "total_gwp": up_total,
                        "fossil_gwp": up_fossil,
                        "biogenic_gwp": up_bio,
                        "adpf": up_adpf,
                        "density": up_density,
                        "is_dangerous": up_danger,
                        "project_id": st.session_state.get("project_id"),
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
        info = (
            f"Total: {m.get('total_gwp', '')}, "
            f"Fossil: {m.get('fossil_gwp', '')}, "
            f"Biogenic: {m.get('biogenic_gwp', '')}, "
            f"ADPF: {m.get('adpf', '')}, "
            f"Danger: {m.get('is_dangerous', '')}"
        )
        col1.write(
            f"{m['name']} ({m['id']}) - {m.get('description', '')} | {info}"
        )
        if col2.button("Delete", key=f"del_mat_{m['id']}"):
            requests.delete(
                f"{BACKEND_URL}/materials/{m['id']}",
                params={"project_id": st.session_state.get("project_id")},
                headers=AUTH_HEADERS,
            )
            rerun()

def render_components():
    require_auth()
    materials = get_materials()
    mat_dict = {m['name']: m['id'] for m in materials}
    components = get_components()
    r_strats = st.session_state.get("r_strategies") or []

    @st.dialog("Create from existing component")
    def copy_component_dialog():
        comp_options = {f"{c['name']} (id:{c['id']})": c for c in components}
        sel = st.selectbox(
            "Select component",
            list(comp_options.keys()),
            key="copy_component_select",
        )
        new_name = st.text_input("New name")
        col1, col2 = st.columns(2)
        if col1.button("Create") and new_name:
            orig = comp_options[sel]
            fields = [
                "material_id",
                "level",
                "parent_id",
                "is_atomic",
                "reusable",
                "systemability",
                "r_factor",
                "trenn_eff",
                "sort_eff",
                "mv_bonus",
                "mv_abzug",
            ]
            if orig.get("is_atomic"):
                fields.append("volume")
            payload = {k: orig.get(k) for k in fields}
            payload.update(
                {
                    "name": new_name,
                    "project_id": st.session_state.get("project_id"),
                }
            )
            res = requests.post(
                f"{BACKEND_URL}/components",
                json=payload,
                headers=AUTH_HEADERS,
            )
            if res.ok:
                st.success("Component created")
                rerun()
            else:
                st.error(res.text)
        if col2.button("Cancel"):
            rerun()

    st.header("Create component")
    level = int(
        st.number_input(
            "Level",
            value=st.session_state.get("create_level", 0),
            step=1,
            key="create_level",
        )
    )
    name = st.text_input("Name")
    is_atomic = st.checkbox("Atomic", key="create_is_atomic")
    mat_name = (
        st.selectbox("Material", list(mat_dict.keys()), key="create_material")
        if is_atomic and mat_dict
        else ""
    )
    volume = (
        st.number_input("Volume", value=0.0, key="create_volume")
        if is_atomic
        else None
    )
    parent_candidates = [c for c in components if c.get("level") == level - 1]
    parent_map = {
        "None": None,
        **{f"{c['name']} (id:{c['id']})": c["id"] for c in parent_candidates},
    }
    parent_sel = st.selectbox("Parent component", list(parent_map.keys()))
    reusable = st.checkbox("Reusable", key="create_reusable")

    # Standardwerte
    systemability = None
    r_factor = None
    trenn_eff = None
    sort_eff = None
    mv_bonus = 0.0
    mv_abzug = 0.0
    if "R8" in r_strats:
        sys_map = {
            "system-compatible": 1.0,
            "potentially system-compatible": 1.0,
            "not system-compatible": 0.0,
        }
        systemability = sys_map[
            st.selectbox("System ability", list(sys_map.keys()), key="create_systemability")
        ]
        r_map = {
            "Recycling as a high-quality material for the same product category": 1.0,
            "Down-Cycling as a material with material input for other product categories": 0.9,
            "Down-Cycling as filler for other applications": 0.3,
            "waste-to-energy": 0.0,
        }
        r_factor = r_map[
            st.selectbox(
                "recyclability potential",
                list(r_map.keys()),
                key="create_r_factor",
            )
        ]
        tr_map = {
            "mono-material and free from additives or usage residues": 1.0,
            "Components are completely separated by hand": 0.95,
            "Mechanically separable by impact or shock": 0.90,
            "separable by using shredding machines (shredder, mill)": 0.85,
            "composite materials, inseparable within the product": 0.0,
        }
        trenn_eff = tr_map[
            st.selectbox(
                "Separation efficiency",
                list(tr_map.keys()),
                key="create_trenn_eff",
            )
        ]
        sort_eff = {
            "Sorting exclusion (criteria fulfilled)": 0.0,
            "unreliably sortable": 0.7,
            "Sorting with 2 MK": 0.95,
            "Sorting with 3 MK": 0.9,
            "No sorting necessary / pure": 1.0,
        }[
            st.selectbox(
                "Sorting efficiency",
                list(
                    {
                        "Sorting exclusion (criteria fulfilled)": 0.0,
                        "unreliably sortable": 0.7,
                        "Sorting with 2 MK": 0.95,
                        "Sorting with 3 MK": 0.9,
                        "No sorting necessary / pure": 1.0,
                    }.keys()
                ),
                key="create_sort_eff",
            )
        ]
        mv_bonus = {
            "None": 0.0,
            "MV 0.25 → 2.5": 2.5,
            "MV 0.50 → 5.0": 5.0,
            "MV 0.75 → 7.5": 7.5,
            "MV 1.00 → 10.0": 10.0,
        }[
            st.selectbox(
                "Material compatibility bonus",
                [
                    "None",
                    "MV 0.25 → 2.5",
                    "MV 0.50 → 5.0",
                    "MV 0.75 → 7.5",
                    "MV 1.00 → 10.0",
                ],
                key="create_mv_bonus",
            )
        ]
        mv_abzug = {
            "no deduction": 0.0,
            "incompatible": -2.0,
            "contaminating (MV-2 or MV-3)": -3.0,
        }[
            st.selectbox(
                "Contaminants / deduction",
                [
                    "no deduction",
                    "incompatible",
                    "contaminating (MV-2 or MV-3)",
                ],
                key="create_mv_abzug",
            )
        ]

    if st.button("Create", key="create_submit") and name:
        if is_atomic and (not mat_dict or not mat_name):
            st.error("Material required for atomic component")
        else:
            # erst Extra-Block bauen, dann mergen - so weniger fehleranfällig
            extra_r8 = (
                {
                    "systemability": systemability,
                    "r_factor": r_factor,
                    "trenn_eff": trenn_eff,
                    "sort_eff": sort_eff,
                    "mv_bonus": mv_bonus,
                    "mv_abzug": mv_abzug,
                }
                if "R8" in r_strats
                else {}
            )

            payload = {
                "name": name,
                "project_id": st.session_state.get("project_id"),
                "level": level,
                "parent_id": parent_map[parent_sel],
                "is_atomic": is_atomic,
                "reusable": reusable,
                **extra_r8,
            }
            if is_atomic:
                payload["material_id"] = mat_dict[mat_name]
                payload["volume"] = volume

            res = requests.post(
                f"{BACKEND_URL}/components",
                json=payload,
                headers=AUTH_HEADERS,
            )
            if res.ok:
                st.success("Component created")
                rerun()
            else:
                st.error(res.text)

    if st.button("From existing Component"):
        copy_component_dialog()

    st.header("Update component")
    if components:
        comp_options = {f"{c['name']} (id:{c['id']})": c for c in components}
        selected = st.selectbox(
            "Select component",
            list(comp_options.keys()),
            key="update_component_select",
        )
        comp = comp_options[selected]
        with st.form("update_component"):
            up_name = st.text_input("Name", comp["name"])
            up_level = int(
                st.number_input(
                    "Level",
                    value=comp.get("level", 0) or 0,
                    step=1,
                )
            )
            up_atomic = st.checkbox(
                "Atomic",
                value=comp.get("is_atomic", False),
            )
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
                if mat_dict and comp.get("material_id") in mat_dict.values()
                else 0
            )
            up_mat = (
                st.selectbox("Material", mat_names, index=mat_idx)
                if up_atomic and mat_dict
                else ""
            )
            up_volume = (
                st.number_input(
                    "Volume",
                    value=comp.get("volume", 0.0) or 0.0,
                )
                if up_atomic
                else None
            )
            parent_candidates = [
                c
                for c in components
                if c["id"] != comp["id"] and c.get("level") == up_level - 1
            ]
            parent_map = {
                "None": None,
                **{
                    f"{c['name']} (id:{c['id']})": c["id"]
                    for c in parent_candidates
                },
            }
            current_parent = comp.get("parent_id")
            if current_parent in parent_map.values():
                parent_idx = list(parent_map.values()).index(current_parent)
            else:
                parent_idx = 0
            up_parent = st.selectbox(
                "Parent component",
                list(parent_map.keys()),
                index=parent_idx,
            )
            up_reusable = st.checkbox(
                "Reusable",
                value=comp.get("reusable", False),
            )
            up_systemability = comp.get("systemability")
            up_r_factor = comp.get("r_factor")
            up_trenn_eff = comp.get("trenn_eff")
            up_sort_eff = comp.get("sort_eff")
            up_mv_bonus = comp.get("mv_bonus")
            up_mv_abzug = comp.get("mv_abzug")
            if "R8" in r_strats:
                sys_map = {
                    "system-compatible": 1.0,
                    "potentially system-compatible": 1.0,
                    "not system-compatible": 0.0,
                }
                sys_vals = list(sys_map.values())
                sys_idx = (
                    sys_vals.index(up_systemability)
                    if up_systemability in sys_vals
                    else 0
                )
                up_systemability = sys_map[
                    st.selectbox("System ability", list(sys_map.keys()), index=sys_idx)
                ]
                r_map = {
                    "Recycling as a high-quality material for the same product category": 1.0,
                    "Down-Cycling as a material with material input for other product categories": 0.9,
                    "Down-Cycling as filler for other applications": 0.3,
                    "waste-to-energy": 0.0,
                }
                r_vals = list(r_map.values())
                r_idx = (
                    r_vals.index(up_r_factor)
                    if up_r_factor in r_vals
                    else 0
                )
                up_r_factor = r_map[
                    st.selectbox(
                        "recyclability potential",
                        list(r_map.keys()),
                        index=r_idx,
                    )
                ]
                tr_map = {
                    "mono-material and free from additives or usage residues": 1.0,
                    "Components are completely separated by hand": 0.95,
                    "Mechanically separable by impact or shock": 0.90,
                    "separable by using shredding machines (shredder, mill)": 0.85,
                    "composite materials, inseparable within the product": 0.0,
                }
                tr_vals = list(tr_map.values())
                tr_idx = (
                    tr_vals.index(up_trenn_eff)
                    if up_trenn_eff in tr_vals
                    else 0
                )
                up_trenn_eff = tr_map[
                    st.selectbox(
                        "Separation efficiency",
                        list(tr_map.keys()),
                        index=tr_idx,
                    )
                ]
                sort_map = {
                    "Sorting exclusion (criteria fulfilled)": 0.0,
                    "unreliably sortable": 0.7,
                    "Sorting with 2 MK": 0.95,
                    "Sorting with 3 MK": 0.9,
                    "No sorting necessary / pure": 1.0,
                }
                sort_vals = list(sort_map.values())
                sort_idx = (
                    sort_vals.index(up_sort_eff)
                    if up_sort_eff in sort_vals
                    else 0
                )
                up_sort_eff = sort_map[
                    st.selectbox(
                        "Sorting efficiency",
                        list(sort_map.keys()),
                        index=sort_idx,
                    )
                ]
                mv_bonus_map = {
                    "None": 0.0,
                    "MV 0.25 → 2.5": 2.5,
                    "MV 0.50 → 5.0": 5.0,
                    "MV 0.75 → 7.5": 7.5,
                    "MV 1.00 → 10.0": 10.0,
                }
                mv_bonus_vals = list(mv_bonus_map.values())
                mv_bonus_idx = (
                    mv_bonus_vals.index(up_mv_bonus)
                    if up_mv_bonus in mv_bonus_vals
                    else 0
                )
                up_mv_bonus = mv_bonus_map[
                    st.selectbox(
                        "Material compatibility bonus",
                        list(mv_bonus_map.keys()),
                        index=mv_bonus_idx,
                    )
                ]
                mv_abzug_map = {
                    "no deduction": 0.0,
                    "incompatible": -2.0,
                    "contaminating (MV-2 or MV-3)": -3.0,
                }
                mv_abzug_vals = list(mv_abzug_map.values())
                mv_abzug_idx = (
                    mv_abzug_vals.index(up_mv_abzug)
                    if up_mv_abzug in mv_abzug_vals
                    else 0
                )
                up_mv_abzug = mv_abzug_map[
                    st.selectbox(
                        "Contaminants / deduction",
                        list(mv_abzug_map.keys()),
                        index=mv_abzug_idx,
                    )
                ]
            updated = st.form_submit_button("Update")

            if updated:
                payload = {
                    "name": up_name,
                    "project_id": st.session_state.get("project_id"),
                    "material_id": mat_dict.get(up_mat),
                    "level": up_level,
                    "parent_id": parent_map[up_parent],
                    "is_atomic": up_atomic,
                    "reusable": up_reusable,
                    **(
                        {
                            "systemability": up_systemability,
                            "r_factor": up_r_factor,
                            "trenn_eff": up_trenn_eff,
                            "sort_eff": up_sort_eff,
                            "mv_bonus": up_mv_bonus,
                            "mv_abzug": up_mv_abzug,
                        }
                        if "R8" in r_strats
                        else {},
                    ),
                }
                if up_atomic:
                    payload["volume"] = up_volume
                res = requests.put(
                    f"{BACKEND_URL}/components/{comp['id']}",
                    json=payload,
                    headers=AUTH_HEADERS,
                )
                if res.ok:
                    st.success("Component updated")
                    rerun()
                else:
                    st.error(res.text)
    else:
        st.info("No components available")

    st.header("Existing components")
    for c in components:
        mat = next((m for m in materials if m['id'] == c['material_id']), None)
        mat_name = mat['name'] if mat else 'N/A'
        mat_density = mat.get('density') if mat else None
        vol = c.get('volume')
        weight = c.get('weight')
        info = (
            f"Material: {mat_name}, "
            f"Volume: {vol if vol is not None else 'N/A'}, "
            f"Density: {mat_density if mat_density is not None else 'N/A'}"
        )
        if weight is not None:
            info += f", Weight: {weight}"
        col1, col2 = st.columns([4, 1])
        col1.write(f"{c['name']} ({c['id']}) - {info}")
        if col2.button("Delete", key=f"del_comp_{c['id']}"):
            requests.delete(
                f"{BACKEND_URL}/components/{c['id']}",
                params={"project_id": st.session_state.get("project_id")},
                headers=AUTH_HEADERS,
            )
            rerun()

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

    @st.dialog("Calculate sustainability assessment")
    def sustainability_dialog():
        st.write("Calculate sustainability assessment?")
        col1, col2 = st.columns(2)
        if col1.button("Yes, calculate"):
            try:
                res = requests.post(
                    f"{BACKEND_URL}/sustainability/calculate",
                    params={"project_id": st.session_state.get("project_id")},
                )
                res.raise_for_status()
                st.session_state.sustainability = res.json()
            except Exception as e:
                st.session_state.sustainability = []
                st.error(str(e))
            rerun()
        if col2.button("Cancel"):
            rerun()

    st.header("Component hierarchy")
    st.graphviz_chart(build_graphviz_tree(components))
    tree = build_tree(components)
    display_tree(tree)

    if st.button("Finish"):
        sustainability_dialog()

    if st.session_state.get("sustainability"):
        st.header("Sustainability scores")
        for entry in st.session_state.sustainability:
            st.write(f"{entry['name']}: {entry['score']:.2f}")

    st.header("Evaluate component")
    if components:
        eval_map = {f"{c['name']} (id:{c['id']})": c['id'] for c in components}
        sel_eval = st.selectbox("Component to evaluate", list(eval_map.keys()))
        if st.button("Run evaluation"):
            try:
                res = requests.post(
                    f"{BACKEND_URL}/evaluation/{eval_map[sel_eval]}",
                    params={"project_id": st.session_state.get("project_id")},
                    headers=AUTH_HEADERS,
                )
                res.raise_for_status()
                st.session_state.evaluation = res.json()
            except Exception as e:
                st.error(str(e))
        if st.session_state.get("evaluation"):
            ev = st.session_state.evaluation
            st.write(f"RV: {ev['rv']:.2f}")
            st.write(f"Grade: {ev['grade']}")
            st.write(
                f"Total GWP: {ev['total_gwp']:.2f}, Fossil: {ev['fossil_gwp']:.2f}, "
                f"Biogenic: {ev['biogenic_gwp']:.2f}, ADPf: {ev['adpf']:.2f}"
            )

def render_export_import():
    require_auth()
    st.header("Export database")
    if st.button("Download CSV"):
        try:
            res = requests.get(
                f"{BACKEND_URL}/export",
                params={"project_id": st.session_state.get("project_id")},
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
                params={"project_id": st.session_state.get("project_id")},
                headers=AUTH_HEADERS,
            )
            resp.raise_for_status()
            st.success("Import successful")
        except Exception as e:
            st.error(str(e))


# ---------- Router ----------
page = st.session_state.get("page_select", "Projects")
if page == "Projects":
    render_projects()
elif page == "Materials":
    render_materials()
elif page == "Components":
    render_components()
elif page == "Export/Import":
    render_export_import()
