import streamlit as st
import pandas as pd
import numpy as np
import folium, os, json
from branca.element import Template, MacroElement
from streamlit_folium import st_folium
from utils.utilities import fmt, load_csv_city, list_available_cities, load_geojson
from dotenv import load_dotenv

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR")
H3_LAYER = os.path.join(DATA_DIR, "geo", "h3_polygons.geojson")
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = set([g.strip() for g in gen_prioritari_str.split(",") if g.strip()])
ROMA_LAT, ROMA_LON = os.getenv("ROMA_LAT", 0), os.getenv("ROMA_LON", 0)

# ===================== Map builder =====================
def build_map(df_filtered, center_lat, center_lon):
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        control_scale=False,
        prefer_canvas=True
    )

    # Layer base
    geojson_base = load_geojson()
    if geojson_base:
        folium.GeoJson(
            geojson_base,
            name="Confini Base",
            style_function=lambda x: {
                "fillColor": "none",
                "color": "#333333",
                "weight": 2,
                "fillOpacity": 0,
            }
        ).add_to(m)

    # Layer H3
    geojson_layer = load_geojson(H3_LAYER)
    if geojson_layer:
        folium.GeoJson(
            geojson_layer,
            name="Fasce H3",
            style_function=lambda feature: {
                "color": feature["properties"].get("color", "#e0e0e0"),
                "weight": 2,
                "fill": True,
                "fillColor": feature["properties"].get("color", "#e0e0e0"),
                "fillOpacity": 0.4,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["count", "mean_events"],
                aliases=["Locali", "Media Eventi"],
                sticky=False
            ),
        ).add_to(m)

    # Punti filtrati
    if df_filtered is not None and not df_filtered.empty:
        for _, r in df_filtered.iterrows():
            lat, lon = float(r["LATITUDINE"]), float(r["LONGITUDINE"])
            fascia = int(r.get("fascia_cell", 3))
            popup_html = folium.Popup(
                f"<b>{r.get('DES_LOCALE', 'Senza nome')}</b><br>"
                f"Città: {r['CITY']}<br>"
                f"Genere: {r.get('GENERE', 'Altro')}<br>"
                f"Eventi totali (12 mesi): {fmt(r.get('events_total',0),0)}<br>"
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

    # ---------------------- Legenda ----------------------
    template = """
    {% macro html(this, kwargs) %}
    <div style="
        position: fixed; 
        bottom: 50px; left: 50px; width: 180px; height: 120px; 
        z-index:9999; 
        background-color:white;
        border:2px solid grey;
        border-radius:5px;
        padding: 10px;
        font-size:14px;
        ">
        <b>Legenda Fasce Attività</b><br>
        <i class="fa fa-circle" style="color:#d73027"></i> Alta attività<br>
        <i class="fa fa-circle" style="color:#fc8d59"></i> Media attività<br>
        <i class="fa fa-circle" style="color:#4575b4"></i> Bassa attività
    </div>
    {% endmacro %}
    """
    macro = MacroElement()
    macro._template = Template(template)
    m.get_root().add_child(macro)

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
        selected_genres = st.multiselect("Generi:", available_genres, default=available_genres, key="filter_genre_auto")

    filters_key = (selected_city, tuple(sorted(selected_genres)))
    needs_update = st.session_state.last_filters != filters_key

    if needs_update:
        df_filtered = load_csv_city(selected_city).copy()
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
        col_map, col_stats = st.columns([2, 1])
        with col_map:
            # Spinner durante il caricamento della mappa
            with st.spinner("⏳ Caricamento mappa..."):
                folium_map = build_map(df_filtered, center_lat, center_lon)
                st_folium(folium_map, width=1200, height=800, returned_objects=[])

        with col_stats:
            if not df_filtered.empty:
                st.subheader("📊 Statistiche - ultimi 12 mesi")
                total_locali = len(df_filtered)
                total_eventi = df_filtered["events_total"].sum() if "events_total" in df_filtered.columns else 0
                st.metric("Totale Locali", f"{total_locali:,}")
                st.metric("Totale Eventi", f"{int(total_eventi):,}")

                for fascia in sorted(df_filtered["fascia_cell"].unique()):
                    fascia_data = df_filtered[df_filtered["fascia_cell"] == fascia]
                    count = len(fascia_data)
                    pct = (count / total_locali * 100) if total_locali > 0 else 0
                    labels = {1: "🔴 Alta attività", 2: "🟡 Media attività", 3: "🔵 Bassa attività"}
                    st.metric(
                        labels.get(int(fascia), f"Fascia {fascia}"),
                        f"{count:,} ({pct:.1f}%)"
                    )

