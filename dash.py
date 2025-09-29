import streamlit as st
import streamlit_authenticator as stauth
from streamlit_option_menu import option_menu
from tabs import metrics, map_h3, map_choropleth
import yaml
from yaml.loader import SafeLoader

# ===================== Config =====================
st.set_page_config(page_title="Dashboard Eventi", layout="wide")

# ===================== Configurazione Authenticator =====================
# Carica la configurazione dell'autenticazione
with open('config/config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Crea l'oggetto authenticator
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# ===================== Login =====================
authenticator.login()

# Controlla se l'utente è autenticato
if st.session_state["authentication_status"]:
    # ===================== Sidebar con logout =====================
    with st.sidebar:
        st.write(f'Benvenuto *{st.session_state["name"]}*')
        authenticator.logout('Logout', 'main', key='unique_key')

    # ===================== Menu orizzontale moderno =====================
    active_tab = option_menu(
        menu_title=None,  # nessun titolo sopra le tab
        options=["Metriche", "Mappa Attività", "Mappa Priorità"],
        icons=["bar-chart-fill", "map", "map-fill"],  # icone opzionali
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
    )

    # ===================== Caricamento tab selezionata =====================
    if active_tab == "Metriche":
        metrics.render()
    elif active_tab == "Mappa Attività":
        # La mappa verrà visualizzata e ricalcolata solo se cambiano i filtri
        map_h3.render()
    elif active_tab == "Mappa Priorità":
        # Stesso principio per la seconda mappa
        map_choropleth.render()

elif st.session_state["authentication_status"] is False:
    st.error('Username/password non corretti')
elif st.session_state["authentication_status"] is None:
    st.warning('Inserisci username e password per accedere')