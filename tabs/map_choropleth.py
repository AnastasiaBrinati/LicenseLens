# tabs/map_choropleth_static.py
import streamlit as st
import pandas as pd
import folium, os, json
from folium import Element
from streamlit_folium import st_folium
from dotenv import load_dotenv
import branca
from utils.utilities import fmt, load_base_map, load_csv_city, list_available_cities

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR", "./data")
LAYER_GEOJSON = os.path.join(DATA_DIR, "geo", "choropleth_layer.geojson")
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = set([g.strip() for g in gen_prioritari_str.split(",") if g.strip()])

# ===================== Caching =====================
def load_h3_layer():
    if not os.path.exists(LAYER_GEOJSON):
        st.error(f"⚠️ Layer H3 non trovato: {LAYER_GEOJSON}")
        return None
    with open(LAYER_GEOJSON, "r", encoding="utf-8") as f:
        return json.load(f)

def build_map(df_filtered, geojson_layer, center_lat, center_lon):
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, control_scale=True)
    geojson_base = load_base_map()
    if geojson_base:
        folium.GeoJson(
            geojson_base,
            name="Confini Base",
            style_function=lambda x: {
                "fillColor": "none",
                "color": "#333333",
                "weight": 2,
                "fillOpacity": 0}
        ).add_to(m)

    # Colormap
    ps_vals = [f.get("properties", {}).get("ps_mean") for f in geojson_layer["features"] if f.get("properties", {}).get("ps_mean") is not None]
    vmin, vmax = (0,1) if not ps_vals else (min(ps_vals), max(ps_vals))
    cmap = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)
    Element(cmap._repr_html_().replace("position: absolute;", "position: absolute; bottom: 10px; left: 10px;")).add_to(m)

    # Poligoni H3
    for feat in geojson_layer["features"]:
        props = feat["properties"]
        coords = feat["geometry"]["coordinates"]
        # Usa dati filtrati per colore dinamico
        if df_filtered is not None and not df_filtered.empty:
            ps = props.get("ps_mean", None)
            color = "#e0e0e0" if ps is None else cmap(float(ps))
        else:
            color = "#e0e0e0"

        tooltip_html = (
            f"<b>Cella H3</b><br>"
            f"Priority Score: {fmt(props.get('ps_mean'))}<br>"
            f"Locali: {props.get('locali_count',0)}<br>"
            f"Eventi Totali: {fmt(props.get('events_sum'),0)}"
        )
        folium.Polygon(
            locations=coords,
            color="#333333",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.5 if props.get("ps_mean") is not None else 0.25,
            tooltip=tooltip_html
        ).add_to(m)

    # Punti filtrati
    for _, r in df_filtered.iterrows():
        lat, lon = r["LATITUDINE"], r["LONGITUDINE"]
        ps_locale = r.get("priority_score", None)
        color = cmap(ps_locale) if ps_locale is not None else "#cccccc"
        folium.CircleMarker(
            [lat, lon],
            radius=4,
            color="#333333",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=folium.Popup(
                f"<b>{r.get('DES_LOCALE','Senza nome')}</b><br>"
                f"Città: {r['CITY']}<br>"
                f"Genere: {r.get('GENERE_DISPLAY','n.d.')}<br>"
                f"Priority Score: {fmt(ps_locale)}<br>"
                f"Eventi totali: {fmt(r.get('events_total'),0)}<br>", max_width=320
            )
        ).add_to(m)

    return m

def render():
    st.header("Zone con priorità di attenzione")
    st.info(
        "⚠️ **Cos'è il Priority Score?**\n"
        "Il Priority Score aiuta a identificare le aree potenzialmente anomale rispetto agli eventi dichiarati dai locali."
    )

    available_cities = list_available_cities()
    available_genres = sorted(GENERI_PRIORITARI) + ["Altro"]

    col1, col2 = st.columns(2)
    with col1:
        selected_city = st.selectbox("Seleziona città:", available_cities, index=0)
    with col2:
        selected_genres = st.multiselect("Generi:", available_genres, default=available_genres)

    # Filtra punti
    df_city = load_csv_city(selected_city)
    if df_city.empty:
        st.warning("Nessun dato per la città selezionata.")
        return
    df_city["GENERE_DISPLAY"] = df_city["GENERE"].apply(lambda g: g if g in GENERI_PRIORITARI else "Altro")
    df_filtered = df_city[df_city["GENERE_DISPLAY"].isin(selected_genres)]

    # Carica layer H3
    geojson_layer = load_h3_layer()
    if geojson_layer is None:
        return

    # Centro mappa
    center_lat = df_filtered["LATITUDINE"].mean() if not df_filtered.empty else df_city["LATITUDINE"].mean()
    center_lon = df_filtered["LONGITUDINE"].mean() if not df_filtered.empty else df_city["LONGITUDINE"].mean()

    with st.spinner("⏳ Caricamento mappa..."):
        folium_map = build_map(df_filtered, geojson_layer, center_lat, center_lon)
        st_folium(folium_map, width=1200, height=800, returned_objects=[])
