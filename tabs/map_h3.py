import streamlit as st
import pandas as pd
import folium, os
import plotly.express as px
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
def build_map(df_filtered, center_lat, center_lon, geojson_layer, zoom_level=12, highlight_locale=None):

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_level,
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

    layer = load_geojson(geojson_layer)
    if layer is not None:
        folium.GeoJson(
            layer,
            name="Livelli Attività",
            style_function=lambda feature: {
                 "color": feature["properties"].get("color", "#e0e0e0"),
                 "weight": 2,
                 "fill": True,
                 "fillColor": feature["properties"].get("color", "#e0e0e0"),
                 "fillOpacity": 0.4,
            },
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
                max_width=320,
                show=(highlight_locale == r.get("DES_LOCALE"))  # 👈 popup aperto se locale selezionato
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
        color: black;
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
        """
        Le aree della città sono state suddivise in **tre livelli di attività** sulla base del numero di eventi dichiarati negli ultimi 12 mesi. 

        - I **punti** rappresentano i singoli locali.  
        - I **poligoni colorati (celle)** suddividono la mappa in aree che vengono classificate in tre diversi livelli di attività: bassa, media e alta. 
        """
    )

    # --- Session state ---
    if "last_filters" not in st.session_state: st.session_state.last_filters = None
    if "df_base" not in st.session_state: st.session_state.df_base = None
    if "df_filtered_h3" not in st.session_state: st.session_state.df_filtered_h3 = None
    if "map_center" not in st.session_state: st.session_state.map_center = (ROMA_LAT, ROMA_LON)
    if "map_zoom" not in st.session_state: st.session_state.map_zoom = 12

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
        df_base = load_csv_city(selected_city).copy()
        df_base["GENERE_NORM"] = df_base["GENERE"].apply(lambda g: g if g in GENERI_PRIORITARI else "Altro")
        if selected_genres:
            df_base = df_base[df_base["GENERE_NORM"].isin(selected_genres)]

        st.session_state.df_base = df_base
        st.session_state.df_filtered_h3 = df_base
        st.session_state.last_filters = filters_key

    # --- Filtro per locale ---
    df_base = st.session_state.df_base
    df_filtered = st.session_state.df_filtered_h3
    highlight_locale = None

    if df_base is not None and not df_base.empty:
        available_locals = ["Tutti"] + sorted(df_base["DES_LOCALE"].unique().tolist())
        selected_local = st.selectbox("Seleziona locale:", available_locals, index=0, key="filter_local")

        if selected_local != "Tutti":
            df_display = df_base[df_base["DES_LOCALE"] == selected_local]
            if not df_display.empty:
                st.session_state.map_center = (
                    float(df_display["LATITUDINE"].iloc[0]),
                    float(df_display["LONGITUDINE"].iloc[0])
                )
                st.session_state.map_zoom = 15
                df_filtered = df_display
                highlight_locale = selected_local
        else:
            df_display = df_base
            st.session_state.map_center = (
                float(df_display["LATITUDINE"].mean()) if not df_display.empty else ROMA_LAT,
                float(df_display["LONGITUDINE"].mean()) if not df_display.empty else ROMA_LON
            )
            st.session_state.map_zoom = 12
            df_filtered = df_display

        st.session_state.df_filtered_h3 = df_filtered

    # --- Mappa e metriche affiancate ---
    df_filtered = st.session_state.df_filtered_h3
    center_lat, center_lon = st.session_state.map_center
    zoom_level = st.session_state.map_zoom

    if df_filtered is not None:
        col_map, col_stats = st.columns([2, 1])
        with col_map:
            with st.spinner("⏳ Caricamento mappa..."):
                folium_map = build_map(
                    df_filtered,
                    center_lat,
                    center_lon,
                    H3_LAYER,
                    zoom_level=zoom_level,
                    highlight_locale=highlight_locale
                )
                st_folium(folium_map, width=1200, height=800, returned_objects=[])

        with col_stats:
            if not df_filtered.empty:
                st.subheader("📊 Statistiche - ultimi 12 mesi")
                total_locali = len(df_filtered)
                total_eventi = df_filtered["events_total"].sum() if "events_total" in df_filtered.columns else 0
                st.metric("Totale Locali", f"{total_locali:,}")
                st.metric("Totale Eventi", f"{int(total_eventi):,}")

                # --- Subheader ---
                st.subheader("Quota locali per livello di attività")

                # --- Dati per il pie chart ---
                fasce_labels = {1: "Alta attività", 2: "Media attività", 3: "Bassa attività"}
                fasce_colors = {1: os.getenv("FASCIA_COLOR_1"), 2: os.getenv("FASCIA_COLOR_2"), 3: os.getenv("FASCIA_COLOR_3")}

                counts = df_filtered["fascia_cell"].value_counts().to_dict()
                for fascia in [1, 2, 3]:
                    counts.setdefault(fascia, 0)

                pie_data = pd.DataFrame({
                    "Fascia": [fasce_labels[f] for f in counts.keys()],
                    "Locali": [counts[f] for f in counts.keys()]
                })

                fig = px.pie(
                    pie_data,
                    names="Fascia",
                    values="Locali",
                    color="Fascia",
                    color_discrete_map={fasce_labels[k]: v for k, v in fasce_colors.items()},
                )
                fig.update_traces(
                    hovertemplate="<b>%{label}</b><br>Locali: %{value}<br><extra></extra>"
                )
                fig.update_layout(
                    showlegend=False,
                    margin=dict(l=20, r=20, t=10, b=10),
                    height=320
                )

                st.plotly_chart(fig, use_container_width=True)
