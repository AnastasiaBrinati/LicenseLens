import datetime
import streamlit as st
import pandas as pd
import os
import plotly.express as px
from utils.deep_search import check_event_exists
from utils.utilities import get_month_columns, load_locali_data
from dotenv import load_dotenv
import re

def extract_links(text: str):
    """
    Estrae tutti i link (URL) da un testo evitando di inglobare parentesi o punteggiatura
    che non fanno parte del link.
    """
    # Matcha http/https, poi prende caratteri validi per URL
    # e si ferma prima di punteggiatura/chiusure non url-safe
    url_pattern = r'https?://[^\s\)\]\}\>\\"\'<>]+'
    return re.findall(url_pattern, text)

load_dotenv()
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = [g.strip() for g in gen_prioritari_str.split(",") if g.strip()]

@st.cache_data()
def get_today_events(df_top, today):
    print(today)
    table_data = []
    for _, row in df_top.iterrows():
        result = check_event_exists(row.get("des_locale", ""), row.get("comune", ""), today)
        table_data.append({
            "Nome Locale": row.get("des_locale", ""),
            "Evento Oggi": "✅ Sì" if result.get("exists") else "❌ No",
            "Link": ", ".join(
                [f"[{i+1}]({url})" for i, url in enumerate(result.get("evidence", []))]
            ) if result.get("evidence") else "-"
        })
    return pd.DataFrame(table_data)


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

    st.plotly_chart(fig, width=400)


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
        col_f1, col_f2 = st.columns(2)

        with col_f1:
            sedi = sorted(df['sede'].dropna().unique().tolist())
            roma_option = next((s for s in sedi if isinstance(s, str) and s.strip().lower() == 'roma'), None)
            default_selection = [roma_option] if roma_option else ([sedi[0]] if sedi else [])
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
                default=[],
                key="metrics_comuni_tab"
            )

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

        if selected_sedi:
            df = df[df['sede'].isin(selected_sedi)]
        else:
            st.warning("Seleziona almeno una sede.")
            return

        if selected_comuni:
            df = df[df['comune'].isin(selected_comuni)]

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
    col_left, col_right = st.columns([2, 1])  # left wider for tables

    # ---------- LEFT COLUMN (Tables) ----------
    with col_left:
        top_n = st.slider("Top N locali:", min_value=5, max_value=50, value=10, key="metrics_top_n")

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

        selected_row = st.dataframe(
            df_to_display,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="metrics_table"
        )
        # ----------------- Eventi per date selezionate -----------------

        # Dizionario mesi in italiano
        mesi = {
            1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile",
            5: "maggio", 6: "giugno", 7: "luglio", 8: "agosto",
            9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"
        }

        st.subheader("📅 Eventi per date selezionate (Top N)")
        today_dt = datetime.datetime.now().date()

        if "df_events_by_day" not in st.session_state:
            st.session_state.df_events_by_day = {}

        # Stile pulsante
        st.markdown("""
            <style>
            div.stButton > button:first-child {
                background: linear-gradient(90deg, #667eea, #764ba2);
                color: white;
                border: none;
                border-radius: 12px;
                padding: 0.8em 2em;
                font-size: 1.1em;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: 0px 4px 12px rgba(0,0,0,0.2);
            }
            div.stButton > button:first-child:hover {
                transform: translateY(-2px);
                box-shadow: 0px 6px 16px rgba(0,0,0,0.25);
                background: linear-gradient(90deg, #5a67d8, #6b46c1);
            }
            div.stButton > button:first-child:active {
                transform: translateY(0px);
                box-shadow: 0px 3px 8px rgba(0,0,0,0.2);
            }
            </style>
        """, unsafe_allow_html=True)

        # Calendario: singolo giorno o intervallo
        date_selection = st.date_input(
            "Seleziona giorno o intervallo",
            value=(today_dt, today_dt),
            min_value=today_dt - datetime.timedelta(days=0),
            max_value=today_dt + datetime.timedelta(days=365),
            key="events_date_selection"
        )

        if st.button("🔍 Cerca eventi per le date selezionate", key="search_selected_days_events"):
            with st.spinner("Ricerca eventi in corso..."):
                st.session_state.df_events_by_day = {}

                # Normalizza la selezione in lista di date
                if isinstance(date_selection, tuple) and len(date_selection) == 2:
                    start_date, end_date = date_selection
                    if start_date and end_date and start_date <= end_date:
                        delta_days = (end_date - start_date).days
                        selected_dates = [start_date + datetime.timedelta(days=i) for i in range(delta_days + 1)]
                    else:
                        selected_dates = [today_dt]
                elif hasattr(date_selection, "strftime"):
                    selected_dates = [date_selection]
                else:
                    selected_dates = [today_dt]

                for d in selected_dates:
                    # Costruzione data in italiano
                    day_str = f"{d.day:02d} {mesi[d.month]} {d.year}"
                    st.session_state.df_events_by_day[day_str] = get_today_events(df_top, day_str)

        # Mostra risultati come CARD separati per giorno
        if st.session_state.df_events_by_day:
            for day, df_day in st.session_state.df_events_by_day.items():
                st.markdown(f"---\n### 📅 Eventi per **{day}**", unsafe_allow_html=True)

                if df_day is not None and not df_day.empty:
                    for _, row in df_day.iterrows():
                        if row['Link'] and row['Link'].strip() != "-":
                            st.markdown(f"""
                            <div style="padding:16px; margin-bottom:12px; border-radius:12px; 
                                        box-shadow:0 2px 10px rgba(0,0,0,0.08); 
                                        background-color:#ffffff; border:1px solid #eee;">
                                <div style="font-size:1.1em; font-weight:600; margin-bottom:6px; color:#222;">
                                    📍 {row['Nome Locale']}
                                </div>
                                <div style="color:#555; margin-bottom:10px;">
                                    🗓️ {day}
                                </div>
                                <div>
                            """, unsafe_allow_html=True)

                            links = extract_links(row['Link'])
                            for i, link in enumerate(links):
                                st.markdown(f"""
                                <a href="{link.strip()}" target="_blank" 
                                   style="text-decoration:none; 
                                          color:white; 
                                          background:linear-gradient(90deg, #667eea, #764ba2); 
                                          padding:6px 12px; 
                                          border-radius:8px; 
                                          font-weight:500;
                                          font-size:0.9em;
                                          margin-right:6px;
                                          box-shadow:0px 2px 6px rgba(0,0,0,0.2); 
                                          display:inline-block;">
                                    🔗 Link {i + 1}
                                </a>
                                """, unsafe_allow_html=True)

                            st.markdown("</div></div>", unsafe_allow_html=True)
                else:
                    st.info(f"Nessun evento trovato per **{day}**.")

    # ---------- RIGHT COLUMN (Charts) ----------
    with col_right:
        st.subheader("📈 Andamento Eventi Mensili")
        if selected_row.selection and len(selected_row.selection['rows']) > 0:
            selected_idx = selected_row.selection['rows'][0]
            selected_locale_data = df_top.iloc[[selected_idx]]
            locale_name = selected_locale_data.iloc[0].get('des_locale', f'Locale #{selected_idx + 1}')
            priority_score = selected_locale_data.iloc[0].get('priority_score', 'N/A')
            st.info(f"📍 **Locale selezionato:** {locale_name} | **Priority Score:** {priority_score}")
            create_events_timeline_chart(selected_locale_data)
        else:
            st.info("👆 Seleziona una riga nella tab")

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
                hovertemplate="<b>%{label}</b> Locali: %{value} Percentuale: %{percent}<extra></extra>"
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

            st.plotly_chart(fig, width=400)
        else:
            st.info("Colonna 'locale_genere' non disponibile")