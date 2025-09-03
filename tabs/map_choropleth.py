import streamlit as st
import os
from streamlit_folium import st_folium
from dotenv import load_dotenv
from utils.utilities import fmt, load_csv_city, list_available_cities, load_geojson

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR")
H3_LAYER = os.path.join(DATA_DIR, "geo", "choropleth_layer.geojson")
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = set([g.strip() for g in gen_prioritari_str.split(",") if g.strip()])

# ===================== Caching =====================
def build_map(df_filtered, geojson_layer, center_lat, center_lon):
    """
    Costruisce una mappa Folium centrata su center_lat, center_lon.
    Mostra:
      - Poligoni H3 colorati secondo 'color' dal GeoJSON
      - Punti dei locali filtrati con colore basato su priority_score
    """
    import folium
    import branca
    from folium import Element

    # Crea mappa base
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, control_scale=True)

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
                "fillOpacity": 0
            }
        ).add_to(m)

    # Poligoni H3 con colore dal GeoJSON
    for feat in geojson_layer["features"]:
        props = feat["properties"]
        color = props.get("color", "#e0e0e0")
        coords = [(lat, lon) for lat, lon in feat["geometry"]["coordinates"][0]]

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

    # Colormap per punti locali basata su priority_score
    ps_vals = df_filtered["priority_score"].dropna()
    if not ps_vals.empty:
        vmin, vmax = ps_vals.min(), ps_vals.max()
        cmap = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)
    else:
        cmap = lambda x: "#1f77b4"

    # Punti dei locali filtrati
    if df_filtered is not None and not df_filtered.empty:
        for _, r in df_filtered.iterrows():
            lat, lon = r["LATITUDINE"], r["LONGITUDINE"]
            ps_locale = r.get("priority_score", None)
            color = cmap(float(ps_locale)) if ps_locale is not None else "#cccccc"

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

    # Aggiungi legenda colormap
    if hasattr(cmap, "caption"):
        Element(cmap._repr_html_().replace("position: absolute;", "position: absolute; bottom: 10px; left: 10px;")).add_to(m)

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
    geojson_layer = load_geojson(H3_LAYER)
    if geojson_layer is None:
        return

    # Centro mappa
    center_lat = df_filtered["LATITUDINE"].mean() if not df_filtered.empty else df_city["LATITUDINE"].mean()
    center_lon = df_filtered["LONGITUDINE"].mean() if not df_filtered.empty else df_city["LONGITUDINE"].mean()

    with st.spinner("⏳ Caricamento mappa..."):
        folium_map = build_map(df_filtered, geojson_layer, center_lat, center_lon)
        st_folium(folium_map, width=1200, height=800, returned_objects=[])
