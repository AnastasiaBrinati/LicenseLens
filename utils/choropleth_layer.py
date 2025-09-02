# utils/choropleth_layer_all.py
import os
import json
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from generate_choropleth import generate_choropleth

# ===================== Config =====================
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR", "./data")
OUTPUT_GEOJSON = os.path.join(DATA_DIR, "geo", "choropleth_layer.geojson")

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
    Include: h3_cell, boundary, ps_mean, locali_count, events_sum
    """
    if df_all.empty:
        return pd.DataFrame(columns=["h3_cell", "boundary", "ps_mean", "locali_count", "events_sum"])

    # Genera la griglia completa H3 su tutti i punti
    cell_ps_all, _ = generate_choropleth(df_all)
    if cell_ps_all is None or cell_ps_all.empty:
        return pd.DataFrame(columns=["h3_cell", "boundary", "ps_mean", "locali_count", "events_sum"])

    # Deduplica solo per h3_cell
    base_cells = cell_ps_all.loc[~cell_ps_all.duplicated(subset=["h3_cell"]), ["h3_cell", "boundary"]].reset_index(drop=True)

    # Calcola statistiche su tutti i punti (ps_mean, count, events_sum)
    cell_stats, _ = generate_choropleth(df_all)
    if cell_stats is None:
        cell_stats = pd.DataFrame(columns=["h3_cell", "ps_mean", "locali_count", "events_sum"])

    # Merge sinistro per mantenere tutte le celle
    grid_layer = base_cells.merge(
        cell_stats[["h3_cell", "ps_mean", "locali_count", "events_sum"]],
        on="h3_cell",
        how="left"
    )

    # Riempi valori mancanti
    grid_layer["ps_mean"] = grid_layer["ps_mean"].fillna(np.nan)
    grid_layer["locali_count"] = grid_layer["locali_count"].fillna(0).astype(int)
    grid_layer["events_sum"] = grid_layer["events_sum"].fillna(0).astype(float)

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
                "events_sum": row["events_sum"]
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
