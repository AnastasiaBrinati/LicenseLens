import os
import json
from typing import Optional
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import math
from datetime import datetime
from pathlib import Path
import glob

load_dotenv()

# Qui definiamo il path di lavoro dei dati
DATA_DIR = os.getenv("DATA_DIR", "/app/data")  # <-- path assoluto nel pod

@st.cache_data
def load_geojson(path: Optional[str] = None) -> Optional[dict]:
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
    path = os.path.join(DATA_DIR, f"Locali_{city}.csv")
    if not os.path.exists(path):
        st.warning(f"⚠️ CSV non trovato per la città: {city}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    df["CITY"] = city

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
    """Carica tutti i file CSV locali_* dalla cartella DATA_DIR"""

    df_cities = []
    cities = list_available_cities()
    for city in cities:
        df_city = load_csv_city(city)
        df_cities.append(df_city)


    if not df_cities:
        st.error(f"Nessun file trovato")
        return pd.DataFrame()

    return pd.concat(df_cities, ignore_index=True)

@st.cache_data
def get_month_columns(df):
    month_cols = []
    for col in df.columns:
        if isinstance(col, str) and '/' in col:
            try:
                datetime.strptime(col, '%m/%Y')
                month_cols.append(col)
            except (ValueError, TypeError):
                continue
    month_cols.sort(key=lambda x: datetime.strptime(x, '%m/%Y'))
    return month_cols

def fmt(x, dec=3, nd="n.d."):
    try:
        v = float(x)
        if math.isnan(v):
            return nd
        return f"{v:.{dec}f}" if dec > 0 else f"{v:.0f}"
    except:
        return nd
