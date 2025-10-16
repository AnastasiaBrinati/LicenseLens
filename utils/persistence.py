import os
import json
import logging
from typing import Optional
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
LOCALI_CSV_DIR = os.getenv("LOCALI_CSV_DIR", DATA_DIR)
logger.info(f"DATA_DIR impostato a: {DATA_DIR}")
logger.info(f"LOCALI_CSV_DIR impostato a: {LOCALI_CSV_DIR}")

@st.cache_data
def load_geojson(path: Optional[str] = None) -> Optional[dict]:
    logger.info("Caricamento GeoJSON")
    if path is None:
        path = os.path.join(DATA_DIR, "geo", "seprag.geojson")
    logger.debug(f"Percorso GeoJSON: {path}")

    if not os.path.exists(path):
        st.error(f"⚠️ File GeoJSON non trovato: {path}")
        logger.error(f"File GeoJSON non trovato: {path}")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        logger.info("GeoJSON caricato correttamente")
        return geojson_data
    except Exception as e:
        logger.exception(f"Errore caricamento GeoJSON: {e}")
        st.error(f"Errore caricamento GeoJSON: {e}")
        return None

@st.cache_data
def list_available_cities() -> list:
    logger.info("Lista delle città disponibili")
    try:
        all_csv = [f for f in os.listdir(LOCALI_CSV_DIR) if f.startswith("Locali_") and f.endswith(".csv")]
        cities = sorted([f.replace("Locali_", "").replace(".csv", "") for f in all_csv])
        logger.info(f"Città trovate: {cities}")
        return cities
    except Exception as e:
        logger.exception(f"Errore durante listing città: {e}")
        return []

@st.cache_data
def load_csv_city(city: str) -> pd.DataFrame:
    logger.info(f"Caricamento CSV per città: {city}")
    path = os.path.join(LOCALI_CSV_DIR, f"Locali_{city}.csv")
    logger.debug(f"Percorso CSV: {path}")

    if not os.path.exists(path):
        st.warning(f"⚠️ CSV non trovato per la città: {city}")
        logger.warning(f"CSV non trovato: {path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(path)
        df["CITY"] = city
        logger.info(f"CSV caricato: {city}, righe: {len(df)}")

        for col in ["latitudine", "longitudine"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["latitudine", "longitudine"]).query(
            "latitudine!=0 & longitudine!=0"
        )

        for c in ["events_total", "pct_last6m", "peer_comp", "priority_score"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        return df
    except Exception as e:
        logger.exception(f"Errore caricamento CSV città {city}: {e}")
        return pd.DataFrame()

@st.cache_data
def load_locali_data() -> pd.DataFrame:
    logger.info("Caricamento dati di tutti i locali")
    df_cities = []
    cities = list_available_cities()

    if not cities:
        st.error("⚠️ Nessuna città trovata")
        logger.warning("Nessuna città disponibile")
        return pd.DataFrame()

    for city in cities:
        df_city = load_csv_city(city)
        if not df_city.empty:
            df_cities.append(df_city)

    if not df_cities:
        st.error("⚠️ Nessun file trovato")
        logger.error("Nessun file CSV caricato correttamente")
        return pd.DataFrame()

    logger.info(f"Dati caricati per {len(df_cities)} città")
    return pd.concat(df_cities, ignore_index=True)
