import folium, os, json
from folium import Element
from streamlit_folium import st_folium
import pandas as pd
from utils.utilities import load_geojson, fmt
import branca

def build_map(
        df_filtered: pd.DataFrame,
        center_lat: float,
        center_lon: float,
        geojson_layer_path: str = None,
        color_env_prefix: str = "FASCIA_COLOR_"
) -> folium.Map:
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, control_scale=True, prefer_canvas=True)

    # --- Confini base ---
    geojson_base = load_geojson()
    if geojson_base:
        folium.GeoJson(
            geojson_base,
            name="Confini Base",
            style_function=lambda x: {"fillColor": "none", "color": "#333333", "weight": 2, "fillOpacity": 0}
        ).add_to(m)

    # --- Layer H3 ---
    if geojson_layer_path:
        geojson_layer = load_geojson(geojson_layer_path)
        if geojson_layer:
            for feat in geojson_layer["features"]:
                props = feat["properties"]
                coords = feat["geometry"]["coordinates"]
                fascia = props.get("fascia", 3)
                color = os.getenv(f"{color_env_prefix}{int(fascia)}", "#d73027")
                tooltip_html = (
                    f"<b>Cella H3</b><br>"
                    f"Fascia: {fascia}<br>"
                    f"Locali: {props.get('count', 0)}<br>"
                    f"Eventi medi: {fmt(props.get('mean_events'))}"
                )
                folium.Polygon(
                    locations=coords,
                    color="#333333",
                    weight=1,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.25,
                    tooltip=tooltip_html
                ).add_to(m)

    # --- Punti locali ---
    if df_filtered is not None and not df_filtered.empty:
        for _, r in df_filtered.iterrows():
            lat, lon = float(r["LATITUDINE"]), float(r["LONGITUDINE"])
            fascia = r.get("fascia_cell", 3)
            color = os.getenv(f"{color_env_prefix}{int(fascia)}", "#d73027")
            popup_html = folium.Popup(
                f"<b>{r.get('DES_LOCALE','Senza nome')}</b><br>"
                f"Città: {r['CITY']}<br>"
                f"Genere: {r.get('GENERE','Altro')}<br>"
                f"Eventi totali: {fmt(r.get('events_total',0))}<br>"
                f"Fascia: {fascia}",
                max_width=320
            )
            folium.CircleMarker(
                [lat, lon],
                radius=5,
                color=color,
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=0.8,
                popup=popup_html
            ).add_to(m)

    return m
