import os, json
from typing import Optional
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import math
from datetime import datetime
from pathlib import Path
import glob

load_dotenv()
DATA_DIR = os.getenv("DATA_DIR", "./data")

@st.cache_data
def load_geojson(path: Optional[str] = None) -> Optional[dict]:
    """
    Carica un file GeoJSON da disco.
    Se path non è fornito, carica il file della mappa base (BASE_MAP_GEOJSON).
    Restituisce:
    - dict: contenuto del JSON se il file esiste
    - None: se il file non esiste, mostra st.error
    """
    if path is None:
        path = os.path.join(DATA_DIR, "geo", "seprag.geojson")

    if not os.path.exists(path):
        st.error(f"⚠️ File GeoJSON non trovato: {path}")
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def list_available_cities() -> list:
    all_csv = [f for f in os.listdir(DATA_DIR) if f.startswith("Locali_") and f.endswith(".csv")]
    return sorted([f.replace("Locali_", "").replace(".csv", "") for f in all_csv])

@st.cache_data
def load_csv_city(city: str) -> pd.DataFrame:
    """
    Carica il CSV di una città specifica.
    Restituisce un DataFrame con colonne numeriche convertite e colonna 'CITY' impostata.
    Il risultato è memorizzato in cache per efficienza.
    """
    path = os.path.join(DATA_DIR, f"Locali_{city}.csv")
    if not os.path.exists(path):
        st.warning(f"⚠️ CSV non trovato per la città: {city}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    df["CITY"] = city

    # Converti alcune colonne in numerico
    for col in ["latitudine", "longitudine"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.dropna(subset=["latitudine", "longitudine"]).query(
        "latitudine!=0 & longitudine!=0"
    )

    for c in ["events_total", "pct_last6m", "peer_comp", "priority_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

@st.cache_data
def load_locali_data():
    """Carica tutti i file CSV locali_* dalla cartella DATA_DIR e aggiunge la colonna 'citta' dal nome file"""
    pattern = f"./data/Locali_*.csv"
    csv_files = glob.glob(pattern)

    if not csv_files:
        st.error(f"Nessun file trovato con pattern {pattern}")
        return pd.DataFrame()

    dataframes = []
    for file in csv_files:
        try:
            df = pd.read_csv(file)
            city_name = Path(file).stem.replace("Locali_", "")
            df['citta'] = city_name
            dataframes.append(df)
        except Exception as e:
            st.warning(f"Errore nel caricamento di {file}: {e}")

    if not dataframes:
        return pd.DataFrame()

    combined_df = pd.concat(dataframes, ignore_index=True)
    return combined_df

@st.cache_data
def get_month_columns(df):
    """Identifica le colonne dei mesi nel formato MM/YYYY"""
    month_cols = []
    for col in df.columns:
        if isinstance(col, str) and '/' in col:
            try:
                month, year = col.split('/')
                if len(month) == 2 and len(year) == 4:
                    datetime.strptime(col, '%m/%Y')
                    month_cols.append(col)
            except (ValueError, TypeError):
                continue
    month_cols.sort(key=lambda x: datetime.strptime(x, '%m/%Y'))
    return month_cols

# ===================== Utility =====================
def fmt(x, dec=3, nd="n.d."):
    try:
        v = float(x)
        if math.isnan(v):
            return nd
        return f"{v:.{dec}f}" if dec > 0 else f"{v:.0f}"
    except:
        return nd