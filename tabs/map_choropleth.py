import branca
import streamlit as st
import pandas as pd
import os
import folium
import plotly.express as px
from streamlit_folium import st_folium
from dotenv import load_dotenv
from utils.utilities import fmt, load_csv_city, list_available_cities, load_geojson

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR")
H3_LAYER = os.path.join(DATA_DIR, "geo", "choropleth_layer.geojson")
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = set([g.strip() for g in gen_prioritari_str.split(",") if g.strip()])


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


# ===================== Map builder =====================
def build_map(df_filtered, center_lat, center_lon, geojson_layer):

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
                "fillOpacity": 0
            }
        ).add_to(m)

    layer = load_geojson(geojson_layer)
    if layer is None:
        return

    # --- Estrai i valori ps_mean dalle celle per definire la colormap ---
    ps_vals = []
    for feat in layer.get("features", []):
        v = feat.get("properties", {}).get("ps_mean", None)
        if v is not None:
            try:
                ps_vals.append(float(v))
            except Exception:
                pass

    if ps_vals:
        vmin, vmax = min(ps_vals), max(ps_vals)
        if vmin == vmax:
            vmax = vmin + 1e-6
        # colormap continua per le celle (match con colori salvati nel geojson)
        cmap_cells = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)
        # legenda continua senza numeri
        add_continuous_legend(m, cmap_cells, position="bottomleft", title="Priorità")

    # --- Disegna poligoni H3 (usiamo il colore già presente nel GeoJSON) ---
    for feat in layer.get("features", []):
        props = feat.get("properties", {})
        color = props.get("color", "#e0e0e0")
        coords = [(lat, lon) for lat, lon in feat["geometry"]["coordinates"][0]]

        folium.Polygon(
            locations=coords,
            color="#333333",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.4 if props.get("ps_mean") is not None else 0.25
        ).add_to(m)

    # --- Punti locali (colore continuo su priority_score, senza legenda numerica) ---
    if df_filtered is not None and not df_filtered.empty:
        ps_vals_loc = df_filtered["priority_score"].dropna()
        if not ps_vals_loc.empty:
            vmin_p, vmax_p = ps_vals_loc.min(), ps_vals_loc.max()
            if vmin_p == vmax_p:
                vmax_p = vmin_p + 1e-6
            cmap_points = branca.colormap.linear.YlOrRd_09.scale(vmin_p, vmax_p)
        else:
            cmap_points = None

        PRIORITY_LABEL = {1: "Alta", 2: "Media", 3: "Bassa"}

        for _, r in df_filtered.iterrows():
            lat, lon = r["LATITUDINE"], r["LONGITUDINE"]
            ps_locale = r.get("priority_score", None)
            color = cmap_points(float(ps_locale)) if (ps_locale is not None and cmap_points) else "#cccccc"

            # etichetta di priorità dalla colonna 'priority'
            try:
                pr_val = int(r.get("priority"))
                pr_label = PRIORITY_LABEL.get(pr_val, "n.d.")
            except Exception:
                pr_label = "n.d."

            folium.CircleMarker(
                [lat, lon],
                radius=4,
                color="#333333",
                weight=1,
                fill=True,
                fill_color=color,
                fill_opacity=0.8,
                popup=folium.Popup(
                    f"<b>{r.get('DES_LOCALE', 'Senza nome')}</b><br>"
                    f"Città: {r['CITY']}<br>"
                    f"Genere: {r.get('GENERE_DISPLAY', 'n.d.')}<br>"
                    f"Priorità: <b>{pr_label}</b><br>"
                    f"Eventi totali: {fmt(r.get('events_total'), 0)}<br>",
                    max_width=320
                )
            ).add_to(m)

    return m


# ===================== Render =====================
def render():
    st.header("Zone con priorità di attenzione")
    st.info("""
    Questa mappa evidenzia i locali e le aree urbane che **meritano maggiore attenzione nei controlli sugli eventi dichiarati**.

    - I **punti** rappresentano i singoli locali: il colore indica il livello di priorità.  
    - I **poligoni colorati (celle)** mostrano la priorità media della zona.  
    """)

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

    # Centro mappa
    center_lat = df_filtered["LATITUDINE"].mean() if not df_filtered.empty else df_city["LATITUDINE"].mean()
    center_lon = df_filtered["LONGITUDINE"].mean() if not df_filtered.empty else df_city["LONGITUDINE"].mean()

    # --- Mappa e statistiche affiancate ---
    if not df_filtered.empty:
        col_map, col_stats = st.columns([2, 1])

        with col_map:
            with st.spinner("⏳ Caricamento mappa..."):
                folium_map = build_map(df_filtered, center_lat, center_lon, H3_LAYER)
                st_folium(folium_map, width=1200, height=800, returned_objects=[])

        with col_stats:
            st.subheader("📊 Statistiche - ultimi 12 mesi")

            total_locali = len(df_filtered)
            total_eventi = df_filtered["events_total"].sum() if "events_total" in df_filtered.columns else 0
            st.metric("Totale Locali", f"{total_locali:,}")
            st.metric("Totale Eventi", f"{int(total_eventi):,}")

            st.subheader("Quota di locali per livello di priorità")
            priority_labels = {1: "Alta priorità", 2: "Media priorità", 3: "Bassa priorità"}
            priority_colors = {1: "#d73027", 2: "#fdae61", 3: "#ffffcc"}

            if 'priority' in df_filtered.columns:
                priority_counts = df_filtered["priority"].value_counts().to_dict()
                for p in [1, 2, 3]:
                    priority_counts.setdefault(p, 0)

                pie_data = pd.DataFrame({
                    "Priorità": [priority_labels[p] for p in priority_counts.keys()],
                    "Locali": [priority_counts[p] for p in priority_counts.keys()]
                })

                fig = px.pie(
                    pie_data,
                    names="Priorità",
                    values="Locali",
                    color="Priorità",
                    color_discrete_map={priority_labels[k]: v for k, v in priority_colors.items()},
                )
                fig.update_traces(hovertemplate="<b>%{label}</b><br>Locali: %{value}<br><extra></extra>")
                fig.update_layout(showlegend=False, margin=dict(l=20, r=20, t=10, b=10), height=320)

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Colonna 'priority' non trovata nei dati.")
    else:
        with st.spinner("⏳ Caricamento mappa..."):
            folium_map = build_map(df_filtered, center_lat, center_lon, H3_LAYER)
            st_folium(folium_map, width=1200, height=800, returned_objects=[])
