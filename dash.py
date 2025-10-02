import streamlit as st
import streamlit_authenticator as stauth
from streamlit_option_menu import option_menu
from tabs import metrics, map_h3, map_choropleth
import yaml
from yaml.loader import SafeLoader
import logging
import sys

# ===================== Logging Config =====================
logger = logging.getLogger("dashboard_logger")
logger.setLevel(logging.DEBUG)  # livello minimo

# Handler su file
file_handler = logging.FileHandler("dashboard.log")
file_handler.setLevel(logging.INFO)

# Handler su console
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)

# Formattazione
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    "%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Aggiunta handler
if not logger.handlers:  # evita duplicati in Streamlit
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# ===================== Config =====================
st.set_page_config(page_title="Dashboard Eventi", layout="wide")

# ===================== Configurazione Authenticator =====================
try:
    with open('config/config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
    logger.info("Configurazione caricata con successo")
except Exception as e:
    logger.exception("Errore durante il caricamento della configurazione")
    st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# ===================== Login =====================
authenticator.login()

# ===================== Controllo autenticazione =====================
if st.session_state["authentication_status"]:
    user = st.session_state["username"]
    logger.info(f"Login effettuato: {user}")

    with st.sidebar:
        st.write(f'Benvenuto *{st.session_state["name"]}*')
        if st.button("Logout"):
            authenticator.logout('Logout', 'main', key='unique_key')
            logger.info(f"Logout effettuato: {user}")

    # ===================== Menu orizzontale =====================
    active_tab = option_menu(
        menu_title=None,
        options=["Metriche", "Mappa Attività", "Mappa Priorità"],
        icons=["bar-chart-fill", "map", "map-fill"],
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
    )
    logger.debug(f"Tab attiva: {active_tab}")

    # ===================== Caricamento tab =====================
    try:
        if active_tab == "Metriche":
            metrics.render()
        elif active_tab == "Mappa Attività":
            map_h3.render()
        elif active_tab == "Mappa Priorità":
            map_choropleth.render()
    except Exception as e:
        logger.exception(f"Errore durante il rendering della tab {active_tab}")
        st.error("Si è verificato un errore. Controlla i log.")

elif st.session_state["authentication_status"] is False:
    logger.warning("Tentativo di login con credenziali errate")
    st.error('Username/password non corretti')
elif st.session_state["authentication_status"] is None:
    logger.info("Utente non autenticato, in attesa di credenziali")
    st.warning('Inserisci username e password per accedere')
