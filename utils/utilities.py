import logging
import streamlit as st
import pandas as pd
import math
import re
import plotly.express as px
from datetime import datetime
from utils.deep_search import check_event_exists
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@st.cache_data
def get_month_columns(df):
    logger.info("Chiamata a get_month_columns")
    month_cols = []
    for col in df.columns:
        if isinstance(col, str) and '/' in col:
            try:
                datetime.strptime(col, '%m/%Y')
                month_cols.append(col)
            except (ValueError, TypeError):
                logger.debug(f"Colonna ignorata: {col}")
                continue
    month_cols.sort(key=lambda x: datetime.strptime(x, '%m/%Y'))
    logger.info(f"Colonne mesi trovate: {month_cols}")
    return month_cols

def create_events_timeline_chart(df_row):
    logger.info("Creazione grafico eventi mensili")
    month_columns = get_month_columns(df_row)
    row_data = df_row.iloc[0]

    months, events = [], []
    for month_col in month_columns:
        months.append(month_col)
        value = row_data.get(month_col, 0)
        events.append(float(value) if pd.notna(value) else 0)

    logger.info(f"Mesi: {months}")
    logger.info(f"Eventi: {events}")

    if not months:
        st.info("Nessun dato mensile trovato")
        logger.warning("Nessun dato mensile disponibile per il grafico")
        return

    df_plot = pd.DataFrame({"Mese": months, "Eventi": events})

    fig = px.line(
        df_plot,
        x="Mese",
        y="Eventi",
        markers=True,
        text="Eventi"
    )

    fig.update_traces(
        line=dict(color="#1f77b4", width=2),
        marker=dict(size=8),
        textposition="top center"
    )

    fig.update_layout(
        xaxis_title="Mese",
        yaxis_title="Numero di Eventi",
        margin=dict(l=40, r=40, t=40, b=40),
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color='white' if st.get_option("theme.base") == "dark" else "black"
    )

    st.plotly_chart(fig, width=400)
    logger.info("Grafico eventi mensili renderizzato")

def fmt(x, dec=3, nd="n.d."):
    try:
        v = float(x)
        if math.isnan(v):
            return nd
        return f"{v:.{dec}f}" if dec > 0 else f"{v:.0f}"
    except Exception as e:
        logger.error(f"Errore in fmt: {e}")
        return nd

def extract_links(text: str):
    logger.debug(f"Estrazione link dal testo: {text}")
    url_pattern = r'https?://[^\s\)\]\}\>\\"\'<>]+'
    links = re.findall(url_pattern, text)
    logger.debug(f"Link trovati: {links}")
    return links

def _check_single_venue(row, today):
    """Helper function per parallelizzare le chiamate API"""
    logger.debug(f"Controllo evento per: {row.get('des_locale', '')}, {row.get('comune', '')}")
    result = check_event_exists(row.get("des_locale", ""), row.get("comune", ""), today)
    evidence_meta = result.get("evidence_meta") if isinstance(result, dict) else None
    return {
        "Nome Locale": row.get("des_locale", ""),
        "Evento Oggi": "✅ Sì" if result.get("exists") else "❌ No",
        "Link": ", ".join(
            [f"[{i+1}]({url})" for i, url in enumerate(result.get("evidence", []))]
        ) if result.get("evidence") else "-",
        "EVIDENZE_META": evidence_meta if evidence_meta else None,
    }

def get_today_events(df_top, today):
    logger.info(f"Recupero eventi per: {today}")
    table_data = []

    # Parallelizza le chiamate API con max 3 worker per rispettare rate limit 15 RPM
    # 3 worker con sleep di 4s = ~12-15 richieste al minuto
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for _, row in df_top.iterrows():
            future = executor.submit(_check_single_venue, row, today)
            futures.append(future)

        # Raccogli i risultati man mano che arrivano
        for future in as_completed(futures):
            try:
                result = future.result()
                table_data.append(result)
            except Exception as e:
                logger.exception(f"Errore durante controllo evento: {e}")

    logger.info(f"Eventi trovati: {len(table_data)}")
    return pd.DataFrame(table_data)
