#!/usr/bin/env python3
import os
import json
import pandas as pd
import numpy as np
import h3
from dotenv import load_dotenv

# Carica le variabili dal .env (che sta nella root del progetto)
load_dotenv()

# Percorsi da .env (con fallback di sicurezza)
DATA_DIR = os.getenv("DATA_DIR", "./data")
OUTPUT_DIR = os.path.join(DATA_DIR, "geo")

# Colori per fascia (da .env oppure default)
FASCIA_COLOR = {
    1: os.getenv("FASCIA_COLOR_1", "#d73027"),
    2: os.getenv("FASCIA_COLOR_2", "#fc8d59"),
    3: os.getenv("FASCIA_COLOR_3", "#2b8cbe"),
}

def fmt_float(x, dec=1):
    try:
        return round(float(x), dec)
    except:
        return None

def main():
    all_csv = [f for f in os.listdir(DATA_DIR) if f.startswith("Locali_") and f.endswith(".csv")]
    if not all_csv:
        raise RuntimeError(f"Nessun CSV trovato in {DATA_DIR}")

    dfs = []
    for f in all_csv:
        city = f.replace("Locali_", "").replace(".csv", "")
        df_city = pd.read_csv(os.path.join(DATA_DIR, f))
        df_city["CITY"] = city
        dfs.append(df_city)

    df = pd.concat(dfs, ignore_index=True)

    # Conversioni
    for col in ["latitudine", "longitudine"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for c in ["events_total", "pct_last6m", "peer_comp", "priority_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["latitudine", "longitudine", "h3_cell", "fascia_cell"])\
           .query("latitudine!=0 & longitudine!=0")\
           .copy()

    if df.empty:
        raise RuntimeError("DataFrame vuoto dopo la pulizia, impossibile creare GeoJSON")

    # Statistiche per cella H3
    features = []
    for cell, grp in df.groupby("h3_cell"):
        fascia = int(grp["fascia_cell"].iloc[0])
        boundary = h3.cell_to_boundary(cell)

        # GeoJSON vuole [lon, lat]
        coords = [[lon, lat] for lat, lon in boundary] + [[boundary[0][1], boundary[0][0]]]  # chiusura poligono

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords]
            },
            "properties": {
                "h3_cell": cell,
                "fascia": fascia,
                "count": int(len(grp)),
                "mean_events": fmt_float(np.nanmean(grp.get("events_total", 0))),
                "color": FASCIA_COLOR.get(fascia, "#555555")
            }
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR, "h3_polygons.geojson")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"✅ File salvato in {out_file} con {len(features)} poligoni")

if __name__ == "__main__":
    main()