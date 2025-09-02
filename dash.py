import streamlit as st
from streamlit_option_menu import option_menu
from tabs import metrics, map_h3, map_choropleth

st.set_page_config(page_title="Dashboard Eventi", layout="wide")

# Menu orizzontale moderno tipo tab
active_tab = option_menu(
    menu_title=None,  # nessun titolo sopra le tab
    options=["Mappa Attività", "Mappa Priorità", "Metriche"],
    icons=["map", "map-fill", "bar-chart"],  # icone opzionali
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
)

# Caricamento solo della tab attiva (indipendente)
if active_tab == "Mappa Attività":
    map_h3.render()
elif active_tab == "Mappa Priorità":
    map_choropleth.render()
elif active_tab == "Metriche":
    metrics.render()
