import streamlit as st
import pandas as pd
import os
import plotly.express as px
from fontTools.feaLib.ast import fea_keywords

from utils.utilities import get_month_columns, load_locali_data
import webbrowser
from utils.sonar import perform_sonar_search
from dotenv import load_dotenv

load_dotenv()
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = [g.strip() for g in gen_prioritari_str.split(",") if g.strip()]

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
    st.header("Locali ad alta priorità")
    st.info(
        """
        Il **livello di priorità** misura quanto un locale merita attenzione in base ai dati disponibili.  
        Viene calcolato combinando diversi fattori, tra cui:  
        - l’andamento degli eventi dichiarati negli ultimi mesi,  
        - il confronto con locali simili nella stessa area,  
        - e altre caratteristiche storiche.  

        Un valore più alto indica una probabilità maggiore che il locale presenti **comportamenti anomali o irregolarità**.
        """
    )

    with st.spinner("Caricamento dati..."):
        df = load_locali_data()

    if df.empty:
        st.error("Impossibile caricare i dati. Verifica la presenza dei file CSV.")
        return

    # ------------------ Filtri ------------------
    if 'sede' in df.columns and 'comune' in df.columns:
        # Prima riga: sede + comune
        col_f1, col_f2 = st.columns(2)

        with col_f1:
            sedi = sorted(df['sede'].dropna().unique().tolist())
            # Trova 'Roma' in modo robusto (case/whitespace insensitive)
            roma_option = next((s for s in sedi if isinstance(s, str) and s.strip().lower() == 'roma'), None)
            default_selection = [roma_option] if roma_option else ([sedi[0]] if sedi else [])
            # Imposta sessione solo se vuota o non coerente con le opzioni
            if (
                'metrics_sedi_tab' not in st.session_state or
                not st.session_state['metrics_sedi_tab'] or
                any(sel not in sedi for sel in st.session_state['metrics_sedi_tab'])
            ):
                st.session_state['metrics_sedi_tab'] = default_selection
            selected_sedi = st.multiselect(
                "Seleziona sede",
                options=sedi,
                key="metrics_sedi_tab"
            )

        with col_f2:
            comuni_options = (
                df[df['sede'].isin(selected_sedi)]['comune'].dropna().unique().tolist()
                if selected_sedi else []
            )
            comuni_options = sorted(comuni_options)
            selected_comuni = st.multiselect(
                "Seleziona comune (opzionale)",
                options=comuni_options,
                default=[],   # 🔹 vuoto = tutti i comuni
                key="metrics_comuni_tab"
            )

        # Seconda riga: genere + locale
        col_f3, col_f4 = st.columns(2)

        with col_f3:
            if 'locale_genere' in df.columns:
                df['GENERE_CAT'] = df['locale_genere'].apply(
                    lambda g: g if g in GENERI_PRIORITARI else "Altro"
                )
                default_genres = [v for v in GENERI_PRIORITARI if v != 'Altro'][:3]
                selected_genres = st.multiselect(
                    "Generi:",
                    options=df['GENERE_CAT'].unique(),
                    default=default_genres,
                    key="metrics_genres_tab"
                )
            else:
                selected_genres = None

        with col_f4:
            df_for_locals = df[
                (df['sede'].isin(selected_sedi)) &
                (df['comune'].isin(selected_comuni) if selected_comuni else True)
            ]
            if selected_genres:
                df_for_locals = df_for_locals[df_for_locals['GENERE_CAT'].isin(selected_genres)]
            locali_options = df_for_locals['des_locale'].dropna().unique().tolist()
            locali_options = sorted(locali_options)
            selected_locali = st.multiselect(
                "Seleziona locale (opzionale)",
                options=locali_options,
                default=[],
                key="metrics_locali_tab"
            )

        # Applica i filtri
        if selected_sedi:
            df = df[df['sede'].isin(selected_sedi)]
        else:
            st.warning("Seleziona almeno una sede.")
            return

        if selected_comuni:
            df = df[df['comune'].isin(selected_comuni)]
        # 🔹 altrimenti nessun filtro → tutti i comuni della sede

        if selected_genres:
            df = df[df['GENERE_CAT'].isin(selected_genres)]
        elif 'locale_genere' in df.columns:
            st.warning("Seleziona almeno un locale_genere.")
            return

        if selected_locali:
            df = df[df['des_locale'].isin(selected_locali)]

    if df.empty:
        st.warning("Nessun dato disponibile con i filtri selezionati")
        return

    # ------------------ Layout principale ------------------
    col1, col2 = st.columns([2, 1])

    with col1:
        # ------------------ Slider Top N locale ------------------
        top_n = st.slider("Top N locali:", min_value=5, max_value=50, value=10, key="metrics_top_n")

        # Assicura colonna TOTALE_EVENTI per tabella (fallback da events_total)
        if 'TOTALE_EVENTI' not in df.columns:
            if 'events_total' in df.columns:
                try:
                    df['TOTALE_EVENTI'] = pd.to_numeric(df['events_total'], errors='coerce').fillna(0).astype(int)
                except Exception:
                    df['TOTALE_EVENTI'] = 0
            else:
                df['TOTALE_EVENTI'] = 0

        if 'priority_score' in df.columns:
            df_top = df.nlargest(top_n, 'priority_score').reset_index(drop=True)
        else:
            st.error("Colonna 'priority_score' non trovata nei dati")
            return

        display_columns = ["des_locale", "locale_genere", "indirizzo", "TOTALE_EVENTI",
                           "priority_score", "fascia_cell", "peer_comp", "pct_last6m", "irregularity_score"]
        column_mapping = {
            "des_locale": "Nome Locale",
            "locale_genere": "Genere",
            "indirizzo": "Indirizzo",
            "TOTALE_EVENTI": "Eventi Totali",
            "priority_score": "Priority Score",
            "fascia_cell": "Livello Attività",
            "peer_comp": "Indice di Concorrenza",
            "pct_last6m": "% Eventi vs Storico",
            "irregularity_score": "Irregularity Score",
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

            locale_name = selected_locale_data.iloc[0].get('des_locale', f'Locale #{selected_idx + 1}')
            priority_score = selected_locale_data.iloc[0].get('priority_score', 'N/A')

            st.info(f"📍 **Locale selezionato:** {locale_name} | **Priority Score:** {priority_score}")
            create_events_timeline_chart(selected_locale_data)

            # ----------------- Bottoni affiancati -----------------
            col_b1, col_b2 = st.columns(2)

            with col_b1:
                button_key = f"deep_search_{selected_idx}"
                research_file = "./data/deep/sonar.csv"
                if st.button(f"🔍 Deep Research: {locale_name}", key=button_key):
                    if os.path.exists(research_file):
                        try:
                            df_research = pd.read_csv(research_file)
                        except Exception as e:
                            st.error(f"Impossibile leggere {research_file}: {e}")
                            df_research = pd.DataFrame(columns=['data_deep_search', 'nome_locale', 'descrizione'])
                    else:
                        df_research = pd.DataFrame(columns=['data_deep_search', 'nome_locale', 'descrizione'])

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
        import plotly.express as px
        st.subheader("\n")
        st.subheader("\n")
        st.subheader("Quota di locali per genere")

        if 'locale_genere' in df_top.columns:
            genre_counts_top = df_top['locale_genere'].value_counts()
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

            fig.update_traces(
                textinfo='percent',
                hovertemplate="<b>%{label}</b><br>Locali: %{value}<br>Percentuale: %{percent}<extra></extra>"
            )

            fig.update_layout(
                showlegend=True,
                margin=dict(l=10, r=10, t=10, b=10),
                height=320,
                legend_itemclick=False,
                legend_itemdoubleclick=False,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Colonna 'locale_genere' non disponibile")
