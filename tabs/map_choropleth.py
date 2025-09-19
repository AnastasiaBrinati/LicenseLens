import branca
import streamlit as st
import pandas as pd
import os
import folium
import plotly.express as px
from streamlit_folium import st_folium
from os.path import getmtime
import streamlit.components.v1 as components
from dotenv import load_dotenv
from utils.utilities import fmt, load_csv_city, list_available_cities, load_geojson

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR")
H3_LAYER = os.path.join(DATA_DIR, "geo", "choropleth_layer.geojson")
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = set([g.strip() for g in gen_prioritari_str.split(",") if g.strip()])
zoom_l = 8


# ===================== Legend helper =====================
def add_continuous_legend(m, cmap, position="bottomleft", title="Priorità (bassa → alta)"):
    import numpy as np
    from branca.element import MacroElement, Template

    STEP = 22
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
def build_map(df_filtered, center_lat, center_lon, geojson_layer, zoom_level=zoom_l, highlight_locale=None):

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_level,
        control_scale=False,
        prefer_canvas=True
    )

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
        return m

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
        cmap_cells = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)
        add_continuous_legend(m, cmap_cells, position="bottomleft", title="Priorità")

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
            lat, lon = r["latitudine"], r["longitudine"]
            ps_locale = r.get("priority_score", None)
            color = cmap_points(float(ps_locale)) if (ps_locale is not None and cmap_points) else "#cccccc"

            try:
                pr_val = int(r.get("priority"))
                pr_label = PRIORITY_LABEL.get(pr_val, "n.d.")
            except Exception:
                pr_label = "n.d."

            popup = folium.Popup(
                f"<b>{r.get('des_locale', 'Senza nome')}</b><br>"
                f"Indirizzo: {r['indirizzo']}<br>"
                f"Genere: {r.get('GENERE_DISPLAY', 'n.d.')}<br>"
                f"Priorità: <b>{pr_label}</b><br>"
                f"Eventi totali: {fmt(r.get('events_total'), 0)}<br>",
                max_width=200,
                show=(highlight_locale == r.get("des_locale"))  # 👈 popup auto aperto
            )

            folium.CircleMarker(
                [lat, lon],
                radius=4,
                color="#333333",
                weight=1,
                fill=True,
                fill_color=color,
                fill_opacity=0.8,
                popup=popup
            ).add_to(m)

    return m


# ===================== Cached renderer =====================
@st.cache_data(show_spinner=False)
def _render_map_html_priority(
    points_payload,
    center_lat: float,
    center_lon: float,
    geojson_layer_path: str,
    geojson_layer_mtime: float,
    base_geojson_mtime: float,
    zoom_level: int,
    highlight_locale: str,
):
    dummy_df = pd.DataFrame(points_payload, columns=[
        "latitudine", "longitudine", "priority_score", "priority", "des_locale", "indirizzo", "GENERE_DISPLAY", "events_total"
    ]) if points_payload else pd.DataFrame(columns=[
        "latitudine", "longitudine", "priority_score", "priority", "des_locale", "indirizzo", "GENERE_DISPLAY", "events_total"
    ])
    m = build_map(dummy_df, center_lat, center_lon, geojson_layer_path, zoom_level, highlight_locale)
    return m.get_root().render()


# ===================== Render =====================
def render():
    st.header("Zone con priorità di attenzione")
    st.info("""
    Questa mappa evidenzia i locali e le aree urbane che **meritano maggiore attenzione nei controlli sugli eventi dichiarati**.

    - I **punti** rappresentano i singoli locali: il colore indica il livello di priorità.  
    - I **poligoni colorati (celle)** mostrano la priorità media della zona.  
    """)

    # --- Session state ---
    if "map_center" not in st.session_state: st.session_state.map_center = (0, 0)
    if "map_zoom" not in st.session_state: st.session_state.map_zoom = zoom_l
    if "last_sede" not in st.session_state: st.session_state.last_sede = None

    available_sedi = list_available_cities()
    available_genres = sorted(GENERI_PRIORITARI) + ["Altro"]

    # --- Riga 1: Sede e Comune ---
    col1, col2 = st.columns(2)
    with col1:
        default_idx = available_sedi.index("Roma") if "Roma" in available_sedi else 0
        selected_sede = st.selectbox("Seleziona sede:", available_sedi, index=default_idx, key="filter_sede_priority")

    df_city = load_csv_city(selected_sede)
    if df_city.empty:
        st.warning("Nessun dato per la sede selezionata.")
        return

    # reset comune se cambio sede
    if st.session_state.last_sede != selected_sede:
        st.session_state["filter_comune_priority"] = "Tutti"
    st.session_state.last_sede = selected_sede

    comuni = ["Tutti"] + sorted(df_city["comune"].dropna().unique())
    with col2:
        selected_comune = st.selectbox("Seleziona comune:", comuni,
                                       index=comuni.index(st.session_state.get("filter_comune_priority", "Tutti")),
                                       key="filter_comune_priority")

    comune_selected = False
    if selected_comune != "Tutti":
        df_city = df_city[df_city["comune"] == selected_comune]
        comune_selected = True

    # --- Riga 2: Generi e Locale ---
    col3, col4 = st.columns(2)
    with col3:
        selected_genres = st.multiselect("Generi:", available_genres,
                                         default=available_genres,
                                         key="filter_genres_priority")

    df_city["GENERE_DISPLAY"] = df_city["locale_genere"].apply(
        lambda g: g if g in GENERI_PRIORITARI else "Altro"
    )
    df_filtered = df_city[df_city["GENERE_DISPLAY"].isin(selected_genres)]

    highlight_locale = None
    with col4:
        if not df_filtered.empty:
            available_locals = ["Tutti"] + sorted(df_filtered["des_locale"].unique().tolist())
            selected_local = st.selectbox("Seleziona locale:", available_locals, index=0, key="filter_local_priority")

            if selected_local != "Tutti":
                df_display = df_filtered[df_filtered["des_locale"] == selected_local]
                if not df_display.empty:
                    st.session_state.map_center = (
                        float(df_display["latitudine"].iloc[0]),
                        float(df_display["longitudine"].iloc[0])
                    )
                    st.session_state.map_zoom = zoom_l
                    df_filtered = df_display
                    highlight_locale = selected_local
        else:
            selected_local = "Tutti"

    if selected_local == "Tutti" and not df_filtered.empty:
        st.session_state.map_center = (
            float(df_filtered["latitudine"].mean()),
            float(df_filtered["longitudine"].mean())
        )
        st.session_state.map_zoom = 12 if comune_selected else zoom_l

    center_lat, center_lon = st.session_state.map_center
    zoom_level = st.session_state.map_zoom

    # --- Mappa e statistiche ---
    if not df_filtered.empty:
        col_map, col_stats = st.columns([2, 1])

        with col_map:
            with st.spinner("⏳ Caricamento mappa..."):
                if not df_filtered.empty:
                    points_payload = tuple(
                        (
                            float(r["latitudine"]),
                            float(r["longitudine"]),
                            float(r.get("priority_score", 0)) if pd.notna(r.get("priority_score", 0)) else 0.0,
                            int(r.get("priority", 0)) if pd.notna(r.get("priority", 0)) else 0,
                            str(r.get("des_locale", "")),
                            str(r.get("indirizzo", "")),
                            str(r.get("GENERE_DISPLAY", "Altro")),
                            float(r.get("events_total", 0)) if pd.notna(r.get("events_total", 0)) else 0.0,
                        )
                        for _, r in df_filtered.iterrows()
                    )
                else:
                    points_payload = tuple()

                geojson_mtime = os.path.getmtime(H3_LAYER) if os.path.exists(H3_LAYER) else 0.0
                base_geojson_path = os.path.join(DATA_DIR, "geo", "seprag.geojson")
                base_mtime = os.path.getmtime(base_geojson_path) if os.path.exists(base_geojson_path) else 0.0

                html = _render_map_html_priority(
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
            points_payload = tuple()
            geojson_mtime = os.path.getmtime(H3_LAYER) if os.path.exists(H3_LAYER) else 0.0
            base_geojson_path = os.path.join(DATA_DIR, "geo", "seprag.geojson")
            base_mtime = os.path.getmtime(base_geojson_path) if os.path.exists(base_geojson_path) else 0.0
            html = _render_map_html_priority(
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

