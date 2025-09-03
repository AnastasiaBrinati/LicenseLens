import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.sonar import perform_sonar_search
import os


def render():
    st.header("🔍 Deep Search Eventi con Sonar")

    col1, col2 = st.columns([3, 1])

    with col1:
        locale_name = st.text_input("Nome Locale", placeholder="Es: Teatro dell'Opera di Roma")

    with col2:
        st.write("")
        st.write("")
        search_button = st.button("🔍 Cerca Eventi", type="primary")

    if locale_name and search_button:
        filepath = os.getenv("DEEP_SEARCH_DATA")

        try:
            df_existing = pd.read_csv(filepath)
            if locale_name in df_existing["nome_locale"].unique():
                 st.info(f"✅ Il locale '{locale_name}' è già presente nel file. Caricando eventi salvati...")
                 df_locale = df_existing[df_existing["nome_locale"] == locale_name]
                 display_events_table(df_locale, locale_name)
                 return
        except Exception as e:
            st.warning(f"⚠️ Errore nel controllo del file: {str(e)}")

        # Se non presente, esegue la ricerca
        with st.spinner("🔍 Ricerca in corso..."):
            try:
                df_results = perform_sonar_search(locale_name)
                st.success(f"✅ {len(df_results)} eventi trovati e salvati.")
                display_events_table(df_results, locale_name)
            except Exception as e:
                st.error(f"❌ Errore durante la ricerca: {str(e)}")

    show_saved_searches()

def display_events_table(df, locale_name):
    """Visualizza la tabella degli eventi"""
    st.subheader(f"📅 Eventi per: {locale_name}")

    if df.empty:
        st.info("Nessun evento trovato")
        return

    # Filtri
    col1, col2 = st.columns(2)

    with col1:
        date_filter = st.selectbox(
            "Filtra per periodo:",
            ["Tutti", "Prossimi 7 giorni", "Prossimo mese", "Eventi passati"],
            key=f"date_filter_{locale_name}"
        )

    with col2:
        text_filter = st.text_input(
            "Cerca nell'evento:",
            placeholder="Es: concerto, teatro...",
            key=f"text_filter_{locale_name}"
        )

    # Applica filtri
    df_filtered = df.copy()

    if text_filter:
        df_filtered = df_filtered[df_filtered["evento"].str.contains(text_filter, case=False, na=False)]

    if date_filter != "Tutti":
        try:
            df_temp = df_filtered.copy()
            df_temp["data_evento_dt"] = pd.to_datetime(df_temp["data_evento"], errors="coerce")
            today = datetime.now().date()

            if date_filter == "Prossimi 7 giorni":
                end_date = today + timedelta(days=7)
                df_filtered = df_temp[
                    (df_temp["data_evento_dt"].dt.date >= today) & (df_temp["data_evento_dt"].dt.date <= end_date)]
            elif date_filter == "Prossimo mese":
                end_date = today + timedelta(days=30)
                df_filtered = df_temp[
                    (df_temp["data_evento_dt"].dt.date >= today) & (df_temp["data_evento_dt"].dt.date <= end_date)]
            elif date_filter == "Eventi passati":
                df_filtered = df_temp[df_temp["data_evento_dt"].dt.date < today]

            if "data_evento_dt" in df_filtered.columns:
                df_filtered = df_filtered.drop("data_evento_dt", axis=1)

        except Exception as e:
            st.warning(f"Errore nel filtro date: {str(e)}")

    # Mostra statistiche
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Eventi totali", len(df))
    with col2:
        st.metric("Eventi filtrati", len(df_filtered))
    with col3:
        try:
            future_events = pd.to_datetime(df["data_evento"], errors="coerce")
            future_count = sum(future_events.dt.date >= datetime.now().date())
            st.metric("Eventi futuri", future_count)
        except:
            st.metric("Eventi futuri", "N/A")

    # Mostra la tabella
    if not df_filtered.empty:
        st.dataframe(df_filtered, width='Stretch', hide_index=True)

        csv = df_filtered.to_csv(index=False)
        st.download_button(
            "📥 Scarica CSV filtrato",
            data=csv,
            file_name=f"eventi_{locale_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("Nessun evento corrisponde ai filtri selezionati")


def show_saved_searches():
    """Mostra le ricerche salvate dal file unico research.csv"""

    filepath = os.getenv("DEEP_SEARCH_DATA")
    if os.path.exists(filepath):
        try:
            df = pd.read_csv(filepath)

            if df.empty:
                st.info("Il file delle ricerche è vuoto.")
                return

            st.subheader("📂 Ricerche Salvate")

            # Raggruppa per nome_locale
            for locale_name in sorted(df["nome_locale"].unique()):
                df_locale = df[df["nome_locale"] == locale_name]
                last_search = df_locale["data_research"].max()

                with st.expander(f"📍 {locale_name} (ultima ricerca: {last_search})"):
                    st.write(f"**Eventi salvati:** {len(df_locale)}")

                    if not df_locale.empty:
                        st.write("**Ultimi eventi:**")
                        st.dataframe(df_locale.head(), use_container_width=True, hide_index=True)

                        if st.button(f"Visualizza tutti gli eventi", key=f"show_all_{locale_name}"):
                            display_events_table(df_locale, locale_name)

        except Exception as e:
            st.error(f"📍 Errore nel caricamento del file: {str(e)}")