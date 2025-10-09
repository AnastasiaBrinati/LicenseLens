import streamlit as st
import yaml
from pathlib import Path
from streamlit_option_menu import option_menu
from tabs import metrics, recurrence_analysis, map_h3, map_choropleth

# ===================== Config =====================
st.set_page_config(page_title="Dashboard Eventi", layout="wide")

# ===================== Carica credenziali da YAML =====================
config_path = Path("config/config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

USERS = config["credentials"]["users"]

# ===================== Gestione sessione =====================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ===================== Funzione login =====================
def login_page():
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Accedi"):
        if username in USERS:
            print(username)
            if USERS[username]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.user = username
                st.session_state.regions = USERS[username].get("regions", [])
                st.rerun()
        else:
            st.error("Credenziali non valide")

# ===================== Se non loggato -> mostra login =====================
if not st.session_state.logged_in:
    login_page()
    st.stop()

# ===================== Sidebar con Logout =====================
with st.sidebar:
    st.markdown(f"Utente: **{st.session_state.get('user','?')}**")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()

# ===================== Menu orizzontale moderno =====================
active_tab = option_menu(
    menu_title=None,
    options=["Locali Prioritari", "Analisi Ricorrenze", "Mappa Attività", "Mappa Priorità"],
    icons=["search", "arrow-repeat", "map", "map-fill"],
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
)

# ===================== Caricamento tab selezionata =====================
if active_tab == "Locali Prioritari":
    metrics.render(st.session_state.regions)
elif active_tab == "Analisi Ricorrenze":
    recurrence_analysis.render(st.session_state.regions)
elif active_tab == "Mappa Attività":
    map_h3.render(st.session_state.regions)
elif active_tab == "Mappa Priorità":
    map_choropleth.render(st.session_state.regions)