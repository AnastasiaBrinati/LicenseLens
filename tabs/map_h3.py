import streamlit as st
import pandas as pd
import numpy as np
import folium, os, json
from streamlit_folium import st_folium
from dotenv import load_dotenv

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
        if np.isnan(v):
            return nd
        return f"{v:.{dec}f}" if dec > 0 else f"{v:.0f}"
    except:
        return nd

# ===================== Caching =====================
@st.cache_data
def load_h3_polygons():
    geo_file = os.path.join(DATA_DIR, "geo", "h3_polygons.geojson")
    with open(geo_file, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_base_map(geojson_path: str = BASE_MAP_GEOJSON):
    if not os.path.exists(geojson_path):
        return None
    with open(geojson_path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_csv(city: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f"locali_{city}.csv")
    df_city = pd.read_csv(path)
    df_city["CITY"] = city
    for col in ["LATITUDINE", "LONGITUDINE"]:
        df_city[col] = pd.to_numeric(df_city[col], errors="coerce")
    for c in ["events_total", "pct_last6m", "peer_comp", "priority_score"]:
        if c in df_city.columns:
            df_city[c] = pd.to_numeric(df_city[c], errors="coerce")
    return df_city

@st.cache_data
def list_available_cities() -> list:
    all_csv = [f for f in os.listdir(DATA_DIR) if f.startswith("locali_") and f.endswith(".csv")]
    return sorted([f.replace("locali_", "").replace(".csv", "") for f in all_csv])

# ===================== Map builder =====================
def build_map(df_filtered, center_lat, center_lon):
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, control_scale=False, prefer_canvas=True)
    geojson_base = load_base_map()
    if geojson_base:
        folium.GeoJson(
            geojson_base,
            name="Confini Base",
            style_function=lambda feature: {
                "fillColor": "none",
                "color": "#333333",
                "weight": 2,
                "fillOpacity": 0,
            }
        ).add_to(m)

    geojson_h3 = load_h3_polygons()
    folium.GeoJson(
        geojson_h3,
        name="Fasce H3",
        style_function=lambda feature: {
            "color": feature["properties"]["color"],
            "weight": 2,
            "fill": True,
            "fillColor": feature["properties"]["color"],
            "fillOpacity": 0.25,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["fascia", "count", "mean_events"],
            aliases=["Fascia", "Locali", "Eventi medi"],
            sticky=False
        ),
    ).add_to(m)

    if not df_filtered.empty:
        for _, r in df_filtered.iterrows():
            lat, lon = float(r["LATITUDINE"]), float(r["LONGITUDINE"])
            fascia = int(r.get("fascia_cell", 3))
            popup_html = folium.Popup(
                f"<b>{r.get('DES_LOCALE', 'Senza nome')}</b><br>"
                f"Città: {r['CITY']}<br>"
                f"Genere: {r.get('GENERE', 'Altro')}<br>"
                f"Eventi totali ({MONTHS_WIN} mesi): {fmt(r.get('events_total',0),0)}<br>"
                f"Fascia: {fascia}",
                max_width=320
            )
            folium.CircleMarker(
                [lat, lon],
                radius=5,
                color=os.getenv('FASCIA_COLOR_' + str(fascia), "#d73027"),
                weight=2,
                fill=True,
                fill_color=os.getenv('FASCIA_COLOR_' + str(fascia), "#d73027"),
                fill_opacity=0.8,
                popup=popup_html
            ).add_to(m)
    return m

# ===================== Render =====================
def render():
    st.header("Zone per livello di attività")
    st.info(
        "⚠️ **Cos'è il livello di attività?**\n"
        "Classificazione automatica delle zone basata sulla media di eventi registrati negli ultimi 12 mesi."
    )

    # --- Session state ---
    if "last_filters" not in st.session_state: st.session_state.last_filters = None
    if "df_filtered_h3" not in st.session_state: st.session_state.df_filtered_h3 = None
    if "map_center" not in st.session_state: st.session_state.map_center = (ROMA_LAT, ROMA_LON)

    # --- Filtri affiancati ---
    col1, col2 = st.columns(2)
    available_cities = list_available_cities()
    with col1:
        selected_city = st.selectbox("Seleziona città:", available_cities, index=0, key="filter_city_auto")
    available_genres = sorted(GENERI_PRIORITARI) + ["Altro"]
    with col2:
        selected_genres = st.multiselect("Seleziona genere:", available_genres, default=available_genres, key="filter_genre_auto")

    filters_key = (selected_city, tuple(sorted(selected_genres)))
    needs_update = st.session_state.last_filters != filters_key

    if needs_update:
        df = load_csv(selected_city).dropna(subset=["LATITUDINE", "LONGITUDINE"]).query(
            "LATITUDINE!=0 & LONGITUDINE!=0"
        ).copy()
        df_filtered = df.copy()
        df_filtered["GENERE_NORM"] = df_filtered["GENERE"].apply(lambda g: g if g in GENERI_PRIORITARI else "Altro")
        if selected_genres:
            df_filtered = df_filtered[df_filtered["GENERE_NORM"].isin(selected_genres)]

        mean_lat = df_filtered["LATITUDINE"].mean() if not df_filtered.empty else ROMA_LAT
        mean_lon = df_filtered["LONGITUDINE"].mean() if not df_filtered.empty else ROMA_LON

        st.session_state.df_filtered_h3 = df_filtered
        st.session_state.map_center = (mean_lat, mean_lon)
        st.session_state.last_filters = filters_key

    # --- Mappa e metriche affiancate ---
    df_filtered = st.session_state.df_filtered_h3
    center_lat, center_lon = st.session_state.map_center
    if df_filtered is not None:
        col_map, col_stats = st.columns([2,1])
        with col_map:
            folium_map = build_map(df_filtered, center_lat, center_lon)
            st_folium(folium_map, width=1200, height=800, returned_objects=[])
        with col_stats:
            if not df_filtered.empty:
                st.subheader("📊 Statistiche - ultimi 12 mesi")
                total_locali = len(df_filtered)
                total_eventi = df_filtered["events_total"].sum() if "events_total" in df_filtered.columns else 0
                st.metric("Totale Locali", total_locali)
                st.metric("Totale Eventi", total_eventi)
                for fascia in sorted(df_filtered["fascia_cell"].unique()):
                    fascia_data = df_filtered[df_filtered["fascia_cell"] == fascia]
                    count = len(fascia_data)
                    pct = (count / total_locali * 100) if total_locali > 0 else 0
                    labels = {1: "🔴 Alta attività", 2: "🟡 Media attività", 3: "🔵 Bassa attività"}
                    st.metric(labels.get(int(fascia), f"Fascia {fascia}"), f"{count} ({pct:.1f}%)")
