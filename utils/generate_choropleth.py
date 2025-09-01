# generate_choropleth.py
import pandas as pd
import numpy as np
import h3
import branca
from streamlit import cache_data

MONTHS_WIN = 12

@cache_data
def generate_choropleth(df: pd.DataFrame):
    """
    Genera i dati per la mappa choropleth: celle H3, colori e aggregazioni.
    Restituisce:
      - cell_ps: DataFrame con colonne h3_cell, ps_mean, locali_count, events_sum, boundary, color
      - cmap: colormap branca già scalata
    """
    if df.empty:
        return pd.DataFrame(), None

    # Aggregazione per cella
    agg_dict = {
        "priority_score": ["mean", "count", "std"],
        "events_total": "sum" if "events_total" in df.columns else "count"
    }
    cell_ps = df.groupby("h3_cell").agg(agg_dict).round(4)

    if cell_ps.empty:
        return pd.DataFrame(), None

    # Rinominazione colonne
    cell_ps.columns = ['_'.join(col).strip() for col in cell_ps.columns.values]
    cell_ps = cell_ps.reset_index().rename(columns={
        'priority_score_mean': 'ps_mean',
        'priority_score_count': 'locali_count',
        'priority_score_std': 'ps_std',
        'events_total_sum': 'events_sum' if 'events_total_sum' in cell_ps.columns else 'events_sum'
    })

    # Calcolo confini H3 e colore
    vals = cell_ps['ps_mean'].values
    vmin, vmax = float(np.nanmin(vals)), float(np.nanmax(vals))
    if vmin == vmax:
        vmax = vmin + 1e-6
    cmap = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)

    boundaries = []
    colors = []

    for _, row in cell_ps.iterrows():
        # Restituisce lista di tuple [(lat, lon), ...] adatta a Folium
        boundary = [(lat, lon) for lat, lon in h3.cell_to_boundary(row['h3_cell'])]
        color = cmap(row['ps_mean'])
        boundaries.append(boundary)
        colors.append(color)

    cell_ps['boundary'] = boundaries
    cell_ps['color'] = colors

    return cell_ps, cmap
