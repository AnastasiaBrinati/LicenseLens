import streamlit as st
import pandas as pd
import os
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import glob
from datetime import datetime
import webbrowser
from utils.sonar import perform_sonar_search
from dotenv import load_dotenv

load_dotenv()
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = set([g.strip() for g in gen_prioritari_str.split(",") if g.strip()])

@st.cache_data
def load_locali_data():
    """Carica tutti i file CSV locali_* dalla cartella DATA_DIR e aggiunge la colonna 'citta' dal nome file"""
    pattern = f"./data/locali_*.csv"
    csv_files = glob.glob(pattern)

    if not csv_files:
        st.error(f"Nessun file trovato con pattern {pattern}")
        return pd.DataFrame()

    dataframes = []
    for file in csv_files:
        try:
            df = pd.read_csv(file)
            city_name = Path(file).stem.replace("locali_", "")
            df['citta'] = city_name
            dataframes.append(df)
        except Exception as e:
            st.warning(f"Errore nel caricamento di {file}: {e}")

    if not dataframes:
        return pd.DataFrame()

    combined_df = pd.concat(dataframes, ignore_index=True)
    return combined_df


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


import plotly.express as px

def create_events_timeline_chart(df_row):
    month_columns = get_month_columns(df_row)
    row_data = df_row.iloc[0]

    months, events = [], []
    for month_col in month_columns:
        months.append(month_col)
        value = row_data.get(month_col, 0)
        events.append(float(value) if pd.notna(value) else 0)

    if not months:
        st.info("Nessun dato mensile trovato")
        return

    df_plot = pd.DataFrame({"Mese": months, "Eventi": events})

    fig = px.line(
        df_plot,
        x="Mese",
        y="Eventi",
        markers=True,
        text="Eventi"
    )

    fig.update_traces(
        line=dict(color="#1f77b4", width=2),
        marker=dict(size=8),
        textposition="top center"
    )

    fig.update_layout(
        xaxis_title="Mese",
        yaxis_title="Numero di Eventi",
        margin=dict(l=40, r=40, t=40, b=40),
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color='white' if st.get_option("theme.base") == "dark" else "black"
    )

    st.plotly_chart(fig, use_container_width=True)



def render():
    st.header("Top priority venues")

    with st.spinner("Caricamento dati..."):
        df = load_locali_data()

    if df.empty:
        st.error("Impossibile caricare i dati. Verifica la presenza dei file CSV.")
        return

    # ------------------ Filtri affiancati ------------------
    if 'citta' in df.columns:
        col_f1, col_f2 = st.columns(2)

        with col_f1:
            cities = sorted(df['citta'].dropna().unique().tolist())
            selected_cities = st.multiselect(
                "Seleziona città",
                options=cities,
                default=cities[0],
                key="metrics_cities_tab"
            )

        with col_f2:
            if 'GENERE' in df.columns:
                df['GENERE_CAT'] = df['GENERE'].apply(lambda g: g if g in GENERI_PRIORITARI else "Altro")
                selected_genres = st.multiselect(
                    "Generi:",
                    options=df['GENERE_CAT'].unique(),
                    default=df['GENERE_CAT'].unique(),
                    key="metrics_genres_tab"
                )
            else:
                selected_genres = None

        # Applica i filtri
        if selected_cities:
            df = df[df['citta'].isin(selected_cities)]
        else:
            st.warning("Seleziona almeno una città.")
            return

        if selected_genres:
            df = df[df['GENERE_CAT'].isin(selected_genres)]
        elif 'GENERE' in df.columns:
            st.warning("Seleziona almeno un genere.")
            return

    if df.empty:
        st.warning("Nessun dato disponibile con i filtri selezionati")
        return

    # ------------------ Layout principale ------------------
    col1, col2 = st.columns([2, 1])

    with col1:
        # ------------------ Slider Top N locale ------------------
        top_n = st.slider("Top N locali:", min_value=5, max_value=50, value=10, key="metrics_top_n")

        if 'priority_score' in df.columns:
            df_top = df.nlargest(top_n, 'priority_score').reset_index(drop=True)
        else:
            st.error("Colonna 'priority_score' non trovata nei dati")
            return

        display_columns = ["DES_LOCALE", "GENERE", "INDIRIZZO", "TOTALE_EVENTI",
                           "priority_score", "fascia_cell", "peer_comp", "pct_last6m"]
        column_mapping = {
            "DES_LOCALE": "Nome Locale",
            "GENERE": "Genere",
            "INDIRIZZO": "Indirizzo",
            "TOTALE_EVENTI": "Eventi Totali",
            "priority_score": "Priority Score",
            "fascia_cell": "Livello Attività",
            "peer_comp": "Indice di Concorrenza",
            "pct_last6m": "% Eventi vs Storico"
        }
        df_to_display = df_top[display_columns].rename(columns=column_mapping)

        # ------------------ Tabella interattiva ------------------
        selected_row = st.dataframe(
            df_to_display,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="metrics_table"
        )

        # ------------------ Grafico timeline ------------------
        st.subheader("📈 Andamento Eventi Mensili")

        if selected_row.selection and len(selected_row.selection['rows']) > 0:
            selected_idx = selected_row.selection['rows'][0]
            selected_locale_data = df_top.iloc[[selected_idx]]

            locale_name = selected_locale_data.iloc[0].get('DES_LOCALE', f'Locale #{selected_idx + 1}')
            priority_score = selected_locale_data.iloc[0].get('priority_score', 'N/A')

            st.info(f"📍 **Locale selezionato:** {locale_name} | **Priority Score:** {priority_score}")
            create_events_timeline_chart(selected_locale_data)

            # ----------------- Bottoni affiancati -----------------
            col_b1, col_b2 = st.columns(2)

            with col_b1:
                button_key = f"deep_search_{selected_idx}"
                research_file = "./data/deep/sonar.csv"
                if st.button(f"🔍 Deep Research: {locale_name}", key=button_key):
                    # Leggi il file CSV se esiste
                    if os.path.exists(research_file):
                        try:
                            df_research = pd.read_csv(research_file)
                        except Exception as e:
                            st.error(f"Impossibile leggere {research_file}: {e}")
                            df_research = pd.DataFrame(columns=['data_deep_search', 'nome_locale', 'descrizione'])
                    else:
                        df_research = pd.DataFrame(columns=['data_deep_search', 'nome_locale', 'descrizione'])

                    # Controlla se il locale è già presente
                    existing_entry = df_research[df_research['nome_locale'] == locale_name]

                    if not existing_entry.empty:
                        descrizione = existing_entry.iloc[0]['descrizione']
                        st.info(f"✅ Il locale **{locale_name}** è già stato ricercato.")
                        st.markdown(f"**Descrizione trovata:**\n\n{descrizione}")
                    else:
                        with st.spinner(f"Ricerca in corso su Sonar per {locale_name}..."):
                            try:
                                result = perform_sonar_search(locale_name)
                                st.markdown(f"**Descrizione deep search:**\n\n{result}")
                            except Exception as e:
                                st.error(f"Errore durante la ricerca Sonar: {str(e)}")

            with col_b2:
                google_url = f"https://www.google.com/search?q={locale_name.replace(' ', '+')}+eventi"
                if st.button(f"🌐 Google Search: {locale_name}", key=f"google_{selected_idx}"):
                    webbrowser.open(google_url)

        else:
            st.info("👆 Seleziona una riga nella tabella sopra per visualizzare l'andamento degli eventi mensili")

    # ------------------ Colonna laterale ------------------
    with col2:
        st.subheader("📊 Statistiche")

        if 'priority_score' in df_top.columns:
            avg_score = df_top['priority_score'].mean()
            max_score = df_top['priority_score'].max()
            min_score = df_top['priority_score'].min()

            st.metric("Priority Score Medio", f"{avg_score:.2f}")
            st.metric("Priority Score Max", f"{max_score:.2f}")
            st.metric("Priority Score Min", f"{min_score:.2f}")

        import plotly.express as px

        st.subheader("Distribuzione Generi")

        if 'GENERE' in df_top.columns:
            genre_counts_top = df_top['GENERE'].value_counts()
            pie_data = pd.DataFrame({
                "Genere": genre_counts_top.index,
                "Locali": genre_counts_top.values
            })

            colors = px.colors.qualitative.Set3

            fig = px.pie(
                pie_data,
                names="Genere",
                values="Locali",
                color="Genere",
                color_discrete_sequence=colors
            )

            # Mostra solo percentuale sugli spicchi, hover con dettagli completi
            fig.update_traces(
                textinfo='percent',
                hovertemplate="<b>%{label}</b><br>Locali: %{value}<br>Percentuale: %{percent}<extra></extra>"
            )

            fig.update_layout(
                showlegend=True,
                margin=dict(l=10, r=10, t=10, b=10),
                height=320,
                legend_itemclick=False,  # disabilita il click singolo sulla legenda
                legend_itemdoubleclick=False,  # disabilita doppio click
                paper_bgcolor='rgba(0,0,0,0)',  # trasparente per dark mode
                plot_bgcolor='rgba(0,0,0,0)'
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Colonna 'GENERE' non disponibile")
