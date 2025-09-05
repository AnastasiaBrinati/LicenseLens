# utils/build_map.py
import os
import folium
import branca
from branca.element import MacroElement
from jinja2 import Template
from utils.utilities import load_geojson  # se hai già la funzione separata
from utils.utilities import fmt  # formattazione numeri
import streamlit as st

# ===================== Legend helper =====================
def add_continuous_legend(m, cmap, position="bottomleft", title="Priorità (bassa → alta)"):
    """
    Aggiunge a `m` una legenda verticale continua senza numeri basata su `cmap` (branca.colormap).
    position: 'topleft' | 'topright' | 'bottomleft' | 'bottomright'
    """
    import numpy as np
    from branca.element import MacroElement, Template

    STEP = 22  # numero di tappe per il gradiente
    vmin, vmax = float(cmap.vmin), float(cmap.vmax)
    vals = np.linspace(vmin, vmax, STEP)

    stops = []
    for i, v in enumerate(vals):
        pct = int(100 * i / (STEP - 1))
        stops.append(f"{cmap(v)} {pct}%")
    gradient_css = ", ".join(stops)

    pos_css = {
        "topleft":      "top: 20px; left: 20px;",
        "topright":     "top: 20px; right: 20px;",
        "bottomleft":   "bottom: 20px; left: 20px;",
        "bottomright":  "bottom: 20px; right: 20px;",
    }.get(position, "bottom: 20px; left: 20px;")

    template = f"""
    {{% macro html(this, kwargs) %}}
    <div style="
        position: fixed; {pos_css}
        z-index:9999;
        background: rgba(255,255,255,0.92);
        border: 1px solid #888;
        border-radius: 6px;
        padding: 10px 12px;
        font-size: 13px;
        color: #111;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    ">
      <div style="font-weight:600; margin-bottom:6px;">{title}</div>
      <div style="display:flex; align-items:center; gap:10px;">
        <div style="
            width: 20px; height: 120px;
            background: linear-gradient(to top, {gradient_css});
            border: 1px solid #999;
        "></div>
        <div style="display:flex; flex-direction:column; height:120px; justify-content:space-between;">
          <div style="margin:0;">Alta</div>
          <div style="margin:0; opacity:0.8;">Media</div>
          <div style="margin:0;">Bassa</div>
        </div>
      </div>
    </div>
    {{% endmacro %}}
    """
    legend = MacroElement()
    legend._template = Template(template)
    m.get_root().add_child(legend)

@st.cache_resource
def build_map(df_filtered, center_lat, center_lon, mode="fasce", geojson_layer_path=None):
    """
    Mappa unica per fasce discrete o priority continua.
    """
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True, prefer_canvas=True)

    # Layer base
    geojson_base = load_geojson()
    if geojson_base:
        folium.GeoJson(
            geojson_base,
            name="Confini Base",
            style_function=lambda x: {"fillColor":"none","color":"#333333","weight":2,"fillOpacity":0},
        ).add_to(m)

    # Layer H3
    layer = load_geojson(geojson_layer_path) if geojson_layer_path else None
    if layer:
        if mode == "fasce":
            folium.GeoJson(
                layer,
                name="Fasce H3",
                style_function=lambda f: {
                    "color": f["properties"].get("color", "#e0e0e0"),
                    "weight": 2,
                    "fill": True,
                    "fillColor": f["properties"].get("color", "#e0e0e0"),
                    "fillOpacity": 0.4,
                },
            ).add_to(m)
        elif mode == "priority":
            ps_vals = [float(f["properties"]["ps_mean"]) for f in layer["features"]
                       if f["properties"].get("ps_mean") is not None]
            if ps_vals:
                vmin, vmax = min(ps_vals), max(ps_vals)
                if vmin == vmax: vmax = vmin + 1e-6
                cmap_cells = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)
                add_continuous_legend(m, cmap_cells, position="bottomleft", title="Priorità")
            for f in layer["features"]:
                props = f["properties"]
                color = props.get("color", "#e0e0e0")
                coords = [(lat, lon) for lat, lon in f["geometry"]["coordinates"][0]]
                folium.Polygon(
                    locations=coords,
                    color="#333333",
                    weight=1,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.4 if props.get("ps_mean") is not None else 0.25,
                ).add_to(m)

    # Punti filtrati
    if df_filtered is not None and not df_filtered.empty:
        for _, r in df_filtered.iterrows():
            lat, lon = r["LATITUDINE"], r["LONGITUDINE"]
            if mode == "fasce":
                fascia = int(r.get("fascia_cell",3))
                color = os.getenv(f"FASCIA_COLOR_{fascia}", "#d73027")
                popup_text = (
                    f"<b>{r.get('DES_LOCALE','Senza nome')}</b><br>"
                    f"Città: {r['CITY']}<br>"
                    f"Genere: {r.get('GENERE','Altro')}<br>"
                    f"Eventi totali: {fmt(r.get('events_total',0),0)}<br>"
                    f"Fascia: {fascia}"
                )
                radius=5
            elif mode == "priority":
                ps_locale = r.get("priority_score")
                ps_vals_loc = df_filtered["priority_score"].dropna()
                cmap_points = None
                if not ps_vals_loc.empty:
                    vmin_p, vmax_p = ps_vals_loc.min(), ps_vals_loc.max()
                    if vmin_p == vmax_p: vmax_p = vmin_p + 1e-6
                    cmap_points = branca.colormap.linear.YlOrRd_09.scale(vmin_p, vmax_p)
                color = cmap_points(float(ps_locale)) if (ps_locale is not None and cmap_points) else "#cccccc"
                pr_label = {1:"Alta",2:"Media",3:"Bassa"}.get(int(r.get("priority",0)),"n.d.")
                popup_text = (
                    f"<b>{r.get('DES_LOCALE','Senza nome')}</b><br>"
                    f"Città: {r['CITY']}<br>"
                    f"Genere: {r.get('GENERE_DISPLAY','n.d.')}<br>"
                    f"Priorità: <b>{pr_label}</b><br>"
                    f"Eventi totali: {fmt(r.get('events_total',0),0)}<br>"
                )
                radius=4

            folium.CircleMarker(
                [lat, lon],
                radius=4,
                color="#333333" if mode=="priority" else "#333333",
                weight=1 if mode=="priority" else 2,
                fill=True,
                fill_color="#333333",
                fill_opacity=0.8,
                popup=folium.Popup("popup_text", max_width=320)
            ).add_to(m)

    # Legenda statica per fasce
    if mode == "fasce":
        template = """
        {% macro html(this, kwargs) %}
        <div style="
            position: fixed; bottom: 50px; left: 50px; width: 180px; height: 120px;
            z-index:9999; background-color:white;
            border:2px solid grey; border-radius:5px;
            padding: 10px; font-size:14px; color: black;">
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