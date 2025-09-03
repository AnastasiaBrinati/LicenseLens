import os
import json
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import branca
from streamlit import cache_data
import h3

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR", "./data")
OUTPUT_GEOJSON = os.path.join(DATA_DIR, "geo", "choropleth_layer.geojson")

MONTHS_WIN = 12

def generate_choropleth(df: pd.DataFrame):
    """
    Genera i dati per la mappa choropleth: celle H3, colori e aggregazioni.
    Restituisce:
      - cell_ps: DataFrame con colonne
          h3_cell, ps_mean, locali_count, ps_std, events_sum,
          area_km2, density, dens_eff, score_cell, boundary, color
      - cmap: colormap branca scalata su score_cell
    """
    if df.empty:
        return pd.DataFrame(), None

    # --- Aggregazione per cella ---
    agg_dict = {
        "priority_score": ["mean", "count", "std"],
    }
    # Se presente 'events_total' somma; altrimenti conta
    if "events_total" in df.columns:
        agg_dict["events_total"] = "sum"
    else:
        agg_dict["events_total"] = "count"

    cell_ps = df.groupby("h3_cell").agg(agg_dict).round(4)
    if cell_ps.empty:
        return pd.DataFrame(), None

    # Flatten & rename
    cell_ps.columns = ['_'.join(col).strip() for col in cell_ps.columns.values]
    ren = {
        'priority_score_mean': 'ps_mean',
        'priority_score_count': 'locali_count',
        'priority_score_std':  'ps_std',
        'events_total_sum':    'events_sum',
        'events_total_count':  'events_sum',  # se non c'è events_total, usiamo il count come proxy
    }
    cell_ps = cell_ps.reset_index().rename(columns=ren)

    # --- Area esagono (km^2) e densità ---
    def _cell_area_km2(cell_id: str) -> float:
        # 1) prova area specifica della cella (h3>=4)
        try:
            return h3.cell_area(cell_id, unit='km^2')
        except Exception:
            # 2) fallback: area media per risoluzione (h3 3.x)
            try:
                res = h3.get_resolution(cell_id)
                return h3.hex_area(res, 'km^2')
            except Exception:
                return np.nan

    cell_ps["area_km2"] = pd.to_numeric(
        cell_ps["h3_cell"].apply(_cell_area_km2), errors="coerce"
    )

    n = pd.to_numeric(cell_ps["locali_count"], errors="coerce").fillna(0.0)
    area = cell_ps["area_km2"].where(cell_ps["area_km2"] > 0)
    density = (n / area).fillna(0.0)  # locali per km^2

    # --- Densità "saturata": dens_eff = density / (density + k) ---
    pos = density[density > 0]
    k = float(np.median(pos)) if len(pos) else 1.0  # punto di mezza-saturazione
    dens_eff = density / (density + k)

    # --- Score per colorazione: ps_mean * densità saturata ---
    ps_mean = pd.to_numeric(cell_ps["ps_mean"], errors="coerce").fillna(0.0)
    cell_ps["density"]   = density
    cell_ps["dens_eff"]  = dens_eff
    cell_ps["score_cell"] = ps_mean * dens_eff

    # --- Colormap robusta (quantili 5°–95°) su score_cell ---
    vals = cell_ps["score_cell"].values
    try:
        vmin = float(np.nanpercentile(vals, 5))
        vmax = float(np.nanpercentile(vals, 95))
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
            raise ValueError
    except Exception:
        vmin = float(np.nanmin(vals)) if np.isfinite(np.nanmin(vals)) else 0.0
        vmax = float(np.nanmax(vals)) if np.isfinite(np.nanmax(vals)) else 1.0
        if vmin == vmax:
            vmax = vmin + 1e-6

    cmap = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)

    # --- Confini H3 e colore (Folium usa (lat, lon)) ---
    boundaries, colors = [], []
    for _, row in cell_ps.iterrows():
        boundary = [(lat, lon) for lat, lon in h3.cell_to_boundary(row["h3_cell"])]
        color = cmap(row["score_cell"])
        boundaries.append(boundary)
        colors.append(color)

    cell_ps["boundary"] = boundaries
    cell_ps["color"]    = colors

    return cell_ps, cmap

# ===================== Funzioni =====================
def load_all_locali() -> pd.DataFrame:
    """Carica tutti i CSV locali_* nella cartella DATA_DIR"""
    all_files = [f for f in os.listdir(DATA_DIR) if f.startswith("locali_") and f.endswith(".csv")]
    dfs = []
    for fname in all_files:
        df_tmp = pd.read_csv(os.path.join(DATA_DIR, fname))
        # Assicurati che LAT/LON siano numerici
        for col in ["LATITUDINE", "LONGITUDINE"]:
            df_tmp[col] = pd.to_numeric(df_tmp[col], errors="coerce")
        dfs.append(df_tmp)
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()

def build_unique_h3_layer(df_all: pd.DataFrame) -> pd.DataFrame:
    """
    Restituisce un layer H3 unico per tutte le città, pronto per GeoJSON.
    Include: h3_cell, boundary, ps_mean, locali_count, events_sum, color
    """
    if df_all.empty:
        return pd.DataFrame(columns=["h3_cell", "boundary", "ps_mean", "locali_count", "events_sum", "color"])

    # Genera la griglia completa H3 su tutti i punti
    cell_ps_all, _ = generate_choropleth(df_all)
    if cell_ps_all is None or cell_ps_all.empty:
        return pd.DataFrame(columns=["h3_cell", "boundary", "ps_mean", "locali_count", "events_sum", "color"])

    # Deduplica solo per h3_cell
    base_cells = cell_ps_all.loc[~cell_ps_all.duplicated(subset=["h3_cell"]), ["h3_cell", "boundary"]].reset_index(drop=True)

    # Calcola statistiche su tutti i punti (ps_mean, count, events_sum, color)
    cell_stats, _ = generate_choropleth(df_all)
    if cell_stats is None:
        cell_stats = pd.DataFrame(columns=["h3_cell", "ps_mean", "locali_count", "events_sum", "color"])

    # Merge sinistro per mantenere tutte le celle e includere il colore
    grid_layer = base_cells.merge(
        cell_stats[["h3_cell", "ps_mean", "locali_count", "events_sum", "color"]],
        on="h3_cell",
        how="left"
    )

    # Riempi valori mancanti
    grid_layer["ps_mean"] = grid_layer["ps_mean"].fillna(np.nan)
    grid_layer["locali_count"] = grid_layer["locali_count"].fillna(0).astype(int)
    grid_layer["events_sum"] = grid_layer["events_sum"].fillna(0).astype(float)
    grid_layer["color"] = grid_layer["color"].fillna("#ffffff")  # default bianco se mancante

    return grid_layer

def save_layer_as_geojson(df_layer: pd.DataFrame, output_path: str = OUTPUT_GEOJSON):
    """Salva il layer H3 come GeoJSON"""
    features = []
    for _, row in df_layer.iterrows():
        feature = {
            "type": "Feature",
            "properties": {
                "h3_cell": row["h3_cell"],
                "ps_mean": row["ps_mean"],
                "locali_count": row["locali_count"],
                "events_sum": row["events_sum"],
                "color": row["color"]  # aggiunto colore
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [row["boundary"]]
            }
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    print(f"✅ Layer H3 salvato in {output_path}")

# ===================== Main =====================
if __name__ == "__main__":
    df_all = load_all_locali()
    if df_all.empty:
        print("⚠️ Nessun dato trovato. Controlla la cartella data/")
    else:
        layer = build_unique_h3_layer(df_all)
        save_layer_as_geojson(layer)
