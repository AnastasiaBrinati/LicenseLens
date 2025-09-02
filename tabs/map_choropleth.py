import streamlit as st
import pandas as pd
import numpy as np
import folium
import os, json
from streamlit_folium import st_folium
from dotenv import load_dotenv
from utils.generate_choropleth import generate_choropleth
from folium import Element

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR", "./data")
BASE_MAP_GEOJSON = os.path.join(DATA_DIR, "geo", "seprag.geojson")
MONTHS_WIN = int(os.getenv("MONTHS_WIN", "12"))
ROMA_LAT, ROMA_LON = 41.9027835, 12.4963655
GENERI_PRIORITARI = {"Bar", "Discoteca", "Ristorante", "All'aperto", "Circolo", "Albergo/Hotel"}

# ===================== Utility =====================
def fmt(x, dec=3, nd="n.d."):
    try:
        v = float(x)
        if np.isnan(v): return nd
        return f"{v:.{dec}f}" if dec > 0 else f"{v:.0f}"
    except:
        return nd

# ===================== Caching =====================
@st.cache_data
def load_csv_files():
    all_files = [f for f in os.listdir(DATA_DIR) if f.startswith("locali_") and f.endswith(".csv")]
    dfs = []
    for fname in all_files:
        city_name = fname.replace("locali_", "").replace(".csv", "")
        df_tmp = pd.read_csv(os.path.join(DATA_DIR, fname))
        for col in ["LATITUDINE", "LONGITUDINE"]:
            df_tmp[col] = pd.to_numeric(df_tmp[col], errors="coerce")
        df_tmp["CITY"] = city_name
        dfs.append(df_tmp)
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()

@st.cache_data
def load_base_map():
    if os.path.exists(BASE_MAP_GEOJSON):
        with open(BASE_MAP_GEOJSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# ===================== Map builder =====================
def build_choropleth_map(df_filtered, cell_ps, cmap, center_lat, center_lon):
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, control_scale=True)

    # Confini base
    geojson_base = load_base_map()
    if geojson_base:
        folium.GeoJson(
            geojson_base,
            name="Confini Base",
            style_function=lambda x: {
                'fillColor': 'none',
                'color': '#333333',
                'weight': 2,
                'fillOpacity': 0
            }
        ).add_to(m)

    # Legenda cmap
    legend_html = cmap._repr_html_().replace(
        'position: absolute;',
        'position: absolute; bottom: 10px; left: 10px;'
    )
    Element(legend_html).add_to(m)

    # Poligoni H3
    for _, row in cell_ps.iterrows():
        boundary = row['boundary']
        tooltip_html = f"""
        <b>Cella H3</b><br>
        Priority Score: {row['ps_mean']:.3f}<br>
        Locali: {row['locali_count']}<br>
        Eventi Totali: {row['events_sum']}
        """
        folium.Polygon(
            locations=boundary,
            color="#333333",
            weight=1,
            fill=True,
            fill_color=row['color'],
            fill_opacity=0.7,
            tooltip=tooltip_html
        ).add_to(m)

    # Punti locali
    for _, r in df_filtered.iterrows():
        lat, lon = float(r["LATITUDINE"]), float(r["LONGITUDINE"])
        ps_locale = r.get("priority_score", np.nan)
        color = cmap(ps_locale) if not np.isnan(ps_locale) else "#cccccc"

        popup_html = folium.Popup(
            f"<b>{r.get('DES_LOCALE','Senza nome')}</b><br>"
            f"Città: {r['CITY']}<br>"
            f"Genere: {r['GENERE_DISPLAY']}<br>"
            f"Priority Score: {fmt(ps_locale)}<br>"
            f"Eventi totali: {fmt(r.get('events_total'),0)}<br>",
            max_width=320
        )

        folium.CircleMarker(
            [lat, lon],
            radius=4,
            color="#333333",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=popup_html
        ).add_to(m)

    return m

# ===================== Render =====================
def render():
    st.header("Zone con priorità di attenzione")
    st.info(
        "⚠️ **Cos'è il Priority Score?**\n"
        "Il Priority Score aiuta a identificare le aree potenzialmente anomale rispetto agli eventi dichiarati dai locali."
    )

    # ===================== Session state =====================
    if 'last_filters_choropleth' not in st.session_state:
        st.session_state.last_filters_choropleth = None
    if 'df_choropleth' not in st.session_state:
        st.session_state.df_choropleth = None
    if 'cell_ps' not in st.session_state:
        st.session_state.cell_ps = None
    if 'cmap' not in st.session_state:
        st.session_state.cmap = None

    # ===================== Filtri =====================
    df = load_csv_files()
    if df.empty:
        st.error("⚠️ Nessun file valido trovato in data/locali_*.csv")
        return

    available_cities = sorted(df["CITY"].unique())
    available_genres = sorted(GENERI_PRIORITARI) + ["Altro"]

    col1, col2 = st.columns(2)
    with col1:
        selected_city = st.selectbox("Seleziona città:", available_cities, index=0, key="filter_city_c_auto")
    with col2:
        selected_genres = st.multiselect("Seleziona genere:", available_genres, default=available_genres, key="filter_genre_c_auto")

    if not selected_city or not selected_genres:
        st.warning("Seleziona almeno una città e un genere.")
        return

    filters_key = (selected_city, tuple(sorted(selected_genres)))
    needs_update = (st.session_state.last_filters_choropleth != filters_key
                    or st.session_state.df_choropleth is None)

    if needs_update:
        # Filtra dati
        df_filtered = df[df["CITY"] == selected_city].copy()
        df_filtered["GENERE_DISPLAY"] = df_filtered["GENERE"].apply(lambda g: g if g in GENERI_PRIORITARI else "Altro")
        df_filtered = df_filtered[df_filtered["GENERE_DISPLAY"].isin(selected_genres)]

        if df_filtered.empty:
            st.warning("Nessun punto soddisfa i filtri selezionati.")
            return

        # Genera choropleth
        cell_ps, cmap = generate_choropleth(df_filtered)
        if cell_ps.empty:
            st.warning("Nessuna cella H3 disponibile per la mappa.")
            return

        # Salva in session state
        st.session_state.df_choropleth = df_filtered
        st.session_state.cell_ps = cell_ps
        st.session_state.cmap = cmap
        st.session_state.last_filters_choropleth = filters_key

    # ===================== Render mappa =====================
    if st.session_state.df_choropleth is not None:
        folium_map = build_choropleth_map(
            st.session_state.df_choropleth,
            st.session_state.cell_ps,
            st.session_state.cmap,
            st.session_state.df_choropleth["LATITUDINE"].mean(),
            st.session_state.df_choropleth["LONGITUDINE"].mean()
        )

        st_folium(folium_map, width=1200, height=800, returned_objects=[])
