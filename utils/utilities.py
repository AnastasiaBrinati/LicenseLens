import os, json
from typing import Optional
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
DATA_DIR = os.getenv("DATA_DIR", "./data")
BASE_MAP_GEOJSON = os.path.join(DATA_DIR, "geo", "seprag.geojson")

@st.cache_data
def load_base_map() -> Optional[dict]:
    """
    Carica il file GeoJSON della mappa base.
    Restituisce un dizionario (parsed JSON) oppure None se il file non esiste.
    Risultato memorizzato in cache per efficienza.
    """
    if not os.path.exists(BASE_MAP_GEOJSON):
        return None
    with open(BASE_MAP_GEOJSON, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def list_available_cities() -> list:
    all_csv = [f for f in os.listdir(DATA_DIR) if f.startswith("locali_") and f.endswith(".csv")]
    return sorted([f.replace("locali_", "").replace(".csv", "") for f in all_csv])


@st.cache_data
def load_csv_city(city: str) -> pd.DataFrame:
    """
    Carica il CSV di una città specifica.
    Restituisce un DataFrame con colonne numeriche convertite e colonna 'CITY' impostata.
    Il risultato è memorizzato in cache per efficienza.
    """
    path = os.path.join(DATA_DIR, f"locali_{city}.csv")
    if not os.path.exists(path):
        st.warning(f"⚠️ CSV non trovato per la città: {city}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    df["CITY"] = city

    # Converti alcune colonne in numerico
    for col in ["LATITUDINE", "LONGITUDINE"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for c in ["events_total", "pct_last6m", "peer_comp", "priority_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

# ===================== Utility =====================
def fmt(x, dec=3, nd="n.d."):
    try:
        v = float(x)
        if v != v:  # check NaN
            return nd
        return f"{v:.{dec}f}" if dec > 0 else f"{v:.0f}"
    except:
        return nd