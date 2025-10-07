import streamlit as st
import pandas as pd
import folium, os, logging
from typing import Tuple
import streamlit.components.v1 as components
import plotly.express as px
from utils.persistence import load_csv_city, list_available_cities, load_geojson
from utils.utilities import fmt
from dotenv import load_dotenv

# ===================== Config logging =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR")
H3_LAYER = os.path.join(DATA_DIR, "geo", "h3_polygons.geojson")
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = set([g.strip() for g in gen_prioritari_str.split(",") if g.strip()])
ROMA_LAT, ROMA_LON = float(os.getenv("ROMA_LAT", 0)), float(os.getenv("ROMA_LON", 0))
zoom_l = 8

logger.info(f"Configurazione iniziale: DATA_DIR={DATA_DIR}, GENERI_PRIORITARI={GENERI_PRIORITARI}")

# ===================== Map builder =====================
def build_map(df_filtered, center_lat, center_lon, geojson_layer, zoom_level=zoom_l, highlight_locale=None):
    logger.info(f"build_map: centro=({center_lat},{center_lon}), zoom={zoom_level}, punti={len(df_filtered)}")
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_level,
        control_scale=False,
        prefer_canvas=True
    )

    try:
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
        logger.info("GeoJson base caricato con successo.")
    except Exception as e:
        logger.error(f"Errore caricamento GeoJson base: {e}")

    try:
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
        logger.info("GeoJson layer H3 caricato con successo.")
    except Exception as e:
        logger.error(f"Errore caricamento GeoJson H3 layer: {e}")

    if df_filtered is not None and not df_filtered.empty:
        logger.info(f"Aggiunta di {len(df_filtered)} punti sulla mappa.")
        for _, r in df_filtered.iterrows():
            try:
                lat, lon = float(r["latitudine"]), float(r["longitudine"])
                fascia = int(r.get("fascia_cell", 3))
                popup_html = folium.Popup(
                    f"<b>{r.get('des_locale', 'Senza nome')}</b><br>"
                    f"Indirizzo: {r['indirizzo']}<br>"
                    f"Genere: {r.get('locale_genere', 'Altro')}<br>"
                    f"Eventi totali (12 mesi): {fmt(r.get('events_total',0),0)}<br>"
                    f"Fascia: {fascia}",
                    max_width=200,
                    show=(highlight_locale == r.get("des_locale"))
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
            except Exception as e:
                logger.warning(f"Errore aggiunta punto: {e}")
    else:
        logger.info("Nessun punto da aggiungere sulla mappa.")

    return m

# ===================== Cached renderer =====================
@st.cache_data(show_spinner=False)
def _render_map_html(
    points_payload: Tuple[Tuple[float, float, int, str, str, str, float], ...],
    center_lat: float,
    center_lon: float,
    geojson_layer_path: str,
    geojson_layer_mtime: float,
    base_geojson_mtime: float,
    zoom_level: int,
    highlight_locale: str,
) -> str:
    logger.info(f"_render_map_html: punti={len(points_payload)}, centro=({center_lat},{center_lon}), zoom={zoom_level}")
    dummy_df = pd.DataFrame(points_payload, columns=[
        "latitudine", "longitudine", "fascia_cell", "des_locale", "indirizzo", "locale_genere", "events_total"
    ]) if points_payload else pd.DataFrame(columns=[
        "latitudine", "longitudine", "fascia_cell", "des_locale", "indirizzo", "locale_genere", "events_total"
    ])
    m = build_map(dummy_df, center_lat, center_lon, geojson_layer_path, zoom_level, highlight_locale)
    return m.get_root().render()


def render(allowed_regions=None):
    logger.info("Render della pagina avviato.")
    st.header("Zone per livello di attività")

    if allowed_regions is None:
        st.warning("Nessuna regione assegnata. Nessun dato da mostrare.")
        return

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
    if "map_zoom" not in st.session_state: st.session_state.map_zoom = zoom_l
    if "last_sede" not in st.session_state: st.session_state.last_sede = None

    # =================== LAYOUT PRINCIPALE ===================
    col_filters, col_map = st.columns([1, 4])  # filtri a sinistra, mappa a destra

    with col_filters:
        st.subheader("🔍 Filtri")

        # --- Filtro sede ---
        available_sedi = list_available_cities()
        default_idx = available_sedi.index("Roma") if "Roma" in available_sedi else 0
        selected_sede = st.selectbox("Seleziona sede:", available_sedi, index=default_idx, key="filter_sede")

        df_base = load_csv_city(selected_sede).copy()
        df_base["GENERE_NORM"] = df_base["locale_genere"].apply(lambda g: g if g in GENERI_PRIORITARI else "Altro")
        df_filtered = df_base.copy()

        if st.session_state.get("last_sede") != selected_sede:
            st.session_state["filter_my_cod"] = "Tutti"
        st.session_state.last_sede = selected_sede

        # --- NUOVO filtro per my_cod (al posto di comune) ---
        available_seprag_cod = ["Tutti"] + sorted(df_filtered["seprag_cod"].dropna().unique())
        selected_seprag_cod = st.selectbox(
            "Seleziona seprag cod:",
            available_seprag_cod,
            index=available_seprag_cod.index(st.session_state.get("filter_my_cod", "Tutti")),
            key="filter_my_cod"
        )

        sepragcod_selected = False
        if selected_seprag_cod != "Tutti":
            df_filtered = df_filtered[df_filtered["seprag_cod"] == selected_seprag_cod]
            sepragcod_selected = True

        # --- Filtro generi ---
        available_genres = sorted(GENERI_PRIORITARI) + ["Altro"]
        selected_genres = st.multiselect("Generi:", available_genres, default=available_genres, key="filter_genre")
        if selected_genres:
            df_filtered = df_filtered[df_filtered["GENERE_NORM"].isin(selected_genres)]

        # --- Filtro locale ---
        available_locals = ["Tutti"] + sorted(df_filtered["des_locale"].unique().tolist())
        selected_local = st.selectbox("Seleziona locale:", available_locals, index=0, key="filter_local")
        highlight_locale = None
        if selected_local != "Tutti":
            df_filtered = df_filtered[df_filtered["des_locale"] == selected_local]
            highlight_locale = selected_local

    # ======= MAPPA =======
    with col_map:
        if not df_filtered.empty:
            st.subheader("🗺️ Mappa")
        else:
            st.subheader("🗺️ Mappa (nessun risultato)")

        center_lat, center_lon = (
            float(df_filtered["latitudine"].mean()),
            float(df_filtered["longitudine"].mean())
        ) if not df_filtered.empty else (ROMA_LAT, ROMA_LON)
        zoom_level = 12 if sepragcod_selected else zoom_l

        with st.spinner("⏳ Caricamento mappa..."):
            points_payload = tuple(
                (
                    float(r["latitudine"]),
                    float(r["longitudine"]),
                    int(r.get("fascia_cell", 3) if not pd.isna(r.get("fascia_cell", 3)) else 3),
                    str(r.get("des_locale", "")),
                    str(r.get("indirizzo", "")),
                    str(r.get("locale_genere", "Altro")),
                    float(r.get("events_total", 0) if not pd.isna(r.get("events_total", 0)) else 0.0),
                )
                for _, r in df_filtered.iterrows()
            ) if not df_filtered.empty else tuple()

            geojson_mtime = os.path.getmtime(H3_LAYER) if os.path.exists(H3_LAYER) else 0.0
            base_geojson_path = os.path.join(DATA_DIR, "geo", "seprag.geojson")
            base_mtime = os.path.getmtime(base_geojson_path) if os.path.exists(base_geojson_path) else 0.0

            html = _render_map_html(
                points_payload,
                center_lat,
                center_lon,
                H3_LAYER,
                geojson_mtime,
                base_mtime,
                int(zoom_level),
                highlight_locale or "",
            )
            components.html(html, height=800)

    # ======= STATISTICHE SOTTO =======
    if not df_filtered.empty:
        st.subheader("📊 Statistiche - ultimi 12 mesi")

        col1, col2, col3 = st.columns([1, 1, 2])  # due colonne piccole per metriche, una più larga per grafico

        with col1:
            total_locali = len(df_filtered)
            st.metric("Totale Locali", f"{total_locali:,}")

        with col2:
            total_eventi = df_filtered["events_total"].sum() if "events_total" in df_filtered.columns else 0
            st.metric("Totale Eventi", f"{int(total_eventi):,}")

        with col3:
            st.subheader("Quota per livello di attività")
            fasce_labels = {1: "Alta attività", 2: "Media attività", 3: "Bassa attività"}
            fasce_colors = {
                1: os.getenv("FASCIA_COLOR_1"),
                2: os.getenv("FASCIA_COLOR_2"),
                3: os.getenv("FASCIA_COLOR_3")
            }

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
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

