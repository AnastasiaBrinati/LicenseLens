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
    import folium
    import branca

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True)

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

    # --- Estrai i valori ps_mean dalle celle per definire la colormap ---
    ps_vals = []
    for feat in geojson_layer["features"]:
        v = feat["properties"].get("ps_mean", None)
        if v is not None:
            try:
                ps_vals.append(float(v))
            except:
                pass

    cmap_cells = None
    if ps_vals:
        vmin, vmax = min(ps_vals), max(ps_vals)
        if vmin == vmax:
            vmax = vmin + 1e-6
        cmap_cells = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)
        cmap_cells.caption = "Priority Score medio (celle H3)"
        # 👉 Aggiunge la legenda in modo nativo (affidabile nell'iframe)
        cmap_cells.add_to(m)

    # --- Disegna poligoni H3 ---
    for feat in geojson_layer["features"]:
        props = feat["properties"]
        color = props.get("color", "#e0e0e0")
        coords = [(lat, lon) for lat, lon in feat["geometry"]["coordinates"][0]]

        tooltip_html = (
            f"<b>Cella H3</b><br>"
            f"Priority Score medio: {fmt(props.get('ps_mean'))}<br>"
            f"Locali: {props.get('locali_count',0)}<br>"
            f"Eventi Totali: {fmt(props.get('events_sum'),0)}"
        )

        folium.Polygon(
            locations=coords,
            color="#333333",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.4 if props.get("ps_mean") is not None else 0.25,
            tooltip=tooltip_html
        ).add_to(m)

    # --- Punti locali (senza legenda separata) ---
    if df_filtered is not None and not df_filtered.empty:
        # se vuoi, puoi mantenere lo stesso schema colori dei poligoni (non è obbligatorio)
        ps_vals_loc = df_filtered["priority_score"].dropna()
        if not ps_vals_loc.empty:
            vmin_p, vmax_p = ps_vals_loc.min(), ps_vals_loc.max()
            if vmin_p == vmax_p:
                vmax_p = vmin_p + 1e-6
            cmap_points = branca.colormap.linear.YlOrRd_09.scale(vmin_p, vmax_p)
        else:
            cmap_points = None

        for _, r in df_filtered.iterrows():
            lat, lon = r["LATITUDINE"], r["LONGITUDINE"]
            ps_locale = r.get("priority_score", None)
            color = cmap_points(float(ps_locale)) if (ps_locale is not None and cmap_points) else "#cccccc"

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
                    f"Eventi totali: {fmt(r.get('events_total'),0)}<br>",
                    max_width=320
                )
            ).add_to(m)

    return m



def render():
    st.header("Zone con priorità di attenzione")
    st.info(
        "⚠️ **Cos'è il Priority Score?**\n"
        "Il Priority Score aiuta a identificare i locali e le aree potenzialmente anomale rispetto agli eventi dichiarati."
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
