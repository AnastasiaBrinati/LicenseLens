import streamlit as st
from tabs import metrics, map_h3, map_choropleth

import streamlit as st

# Configurazione pagina Streamlit
st.set_page_config(
    page_title="Dashboard Eventi",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Crea le tab orizzontali - ora 4 tab separate
tab1, tab2, tab3  = st.tabs(["Mappa Attività", "Mappa Priorità", "Metriche"])

with tab1:
    map_h3.render()

with tab2:
    map_choropleth.render()

with tab3:
    metrics.render()