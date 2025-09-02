import streamlit as st
from streamlit_option_menu import option_menu
from tabs import metrics, map_h3, map_choropleth

# ===================== Config =====================
st.set_page_config(page_title="Dashboard Eventi", layout="wide")

# ===================== Menu orizzontale moderno =====================
active_tab = option_menu(
    menu_title=None,  # nessun titolo sopra le tab
    options=["Mappa Attività", "Mappa Priorità", "Metriche"],
    icons=["map", "map-fill", "bar-chart"],  # icone opzionali
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
)

# ===================== Caricamento tab selezionata =====================
if active_tab == "Mappa Attività":
    # La mappa verrà visualizzata e ricalcolata solo se cambiano i filtri
    map_h3.render()

elif active_tab == "Mappa Priorità":
    # Stesso principio per la seconda mappa
    map_choropleth.render()

elif active_tab == "Metriche":
    metrics.render()
