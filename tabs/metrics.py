import datetime
import streamlit as st
import pandas as pd
import os
import logging
from logging.handlers import RotatingFileHandler
from utils.persistence import load_csv_city
from utils.utilities import create_events_timeline_chart, get_today_events, extract_links
from dotenv import load_dotenv
import re
import csv

# ==========================
# 🔐 Config Logging
# ==========================
LOG_FILE = "logs/dashboard_metrics.log"

# Rotazione log: max 5 MB, 3 backup
handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
handler.setFormatter(formatter)

logger = logging.getLogger("metrics")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Per vedere anche in console/streamlit logs
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

load_dotenv()
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = [g.strip() for g in gen_prioritari_str.split(",") if g.strip()]

logger.info("Avvio modulo metrics. Generi prioritari: %s", GENERI_PRIORITARI)


def render(allowed_regions=None):
    st.header("Locali ad alta priorità")

    # Inizializza set dei locali nascosti e tracciamento ultimo click
    if "hidden_locales" not in st.session_state:
        st.session_state.hidden_locales = set()
    if "last_selected_row" not in st.session_state:
        st.session_state.last_selected_row = None

    if allowed_regions is None:
        st.warning("Nessuna regione assegnata. Nessun dato da mostrare.")
        return

    st.info(
        """
        Il **livello di priorità** misura quanto un locale merita attenzione in base ai dati disponibili.  
        Viene calcolato combinando diversi fattori, tra cui:  
        - l'andamento degli eventi dichiarati negli ultimi mesi,  
        - il confronto con locali simili nella stessa area,  
        - e altre caratteristiche storiche.  

        Un valore più alto indica una probabilità maggiore che il locale presenti **comportamenti anomali o irregolarità**.
        """
    )

    logger.info("Caricamento dati locali...")
    with st.spinner("Caricamento dati..."):
        df_cities = []
        for sede in allowed_regions:
            print(f"Loading locali per: {sede}")
            df_city = load_csv_city(sede)
            if not df_city.empty:
                df_cities.append(df_city)

        if not df_cities:
            logger.error("Nessun dato caricato per le regioni assegnate.")
            st.error("Nessun dato disponibile per le regioni assegnate.")
            return

        df = pd.concat(df_cities, ignore_index=True)

    if df.empty:
        logger.error("Dati non caricati o DataFrame vuoto.")
        st.error("Impossibile caricare i dati. Verifica la presenza dei file CSV.")
        return
    logger.info("Dati caricati: %d righe, %d colonne", df.shape[0], df.shape[1])

    # ------------------ Layout principale ------------------
    col_filters, col_table = st.columns([0.5, 3])  # Solo filtri e tabella

    # ------------------ Filtri ------------------
    with col_filters:
        st.subheader("Filtri")
        try:
            if 'sede' in df.columns and 'seprag_cod' in df.columns:

                sedi = sorted(df['sede'].dropna().unique().tolist())
                logger.info("Sedi disponibili: %s", sedi)
                roma_option = next((s for s in sedi if isinstance(s, str) and s.strip().lower() == 'roma'), None)
                default_selection = [roma_option] if roma_option else ([sedi[0]] if sedi else [])
                if (
                            'metrics_sedi_tab' not in st.session_state or
                            not st.session_state['metrics_sedi_tab'] or
                            any(sel not in sedi for sel in st.session_state['metrics_sedi_tab'])
                    ):
                    st.session_state['metrics_sedi_tab'] = default_selection
                selected_sedi = st.multiselect("Seleziona sede", options=sedi, key="metrics_sedi_tab")
                logger.info("Sedi selezionate: %s", selected_sedi)

                comuni_options = (
                    df[df['sede'].isin(selected_sedi)]['seprag_cod'].dropna().unique().tolist()
                    if selected_sedi else []
                )
                comuni_options = sorted(comuni_options)
                selected_comuni = st.multiselect("Seleziona seprag (opzionale)", options=comuni_options, default=[],
                                                     key="metrics_comuni_tab")
                logger.info("Comuni selezionati: %s", selected_comuni)

                if 'locale_genere' in df.columns:
                    df['GENERE_CAT'] = df['locale_genere'].apply(lambda g: g if g in GENERI_PRIORITARI else "Altro")
                    default_genres = [v for v in GENERI_PRIORITARI if v != 'Altro'][:3]
                    selected_genres = st.multiselect("Generi:", options=df['GENERE_CAT'].unique(),
                                                         default=default_genres, key="metrics_genres_tab")
                    logger.info("Generi selezionati: %s", selected_genres)
                else:
                    selected_genres = None
                    logger.warning("Colonna locale_genere non trovata nei dati.")

                df_for_locals = df[(df['sede'].isin(selected_sedi)) & (
                    df['seprag_cod'].isin(selected_comuni) if selected_comuni else True)]
                if selected_genres:
                    df_for_locals = df_for_locals[df_for_locals['GENERE_CAT'].isin(selected_genres)]
                locali_options = sorted(df_for_locals['des_locale'].dropna().unique().tolist())
                selected_locali = st.multiselect("Seleziona locale (opzionale)", options=locali_options, default=[],
                                                     key="metrics_locali_tab")
                logger.info("Locali selezionati: %s", selected_locali)

            # Filtri applicati al DataFrame
            if selected_sedi:
                df = df[df['sede'].isin(selected_sedi)]
            else:
                st.warning("Seleziona almeno una sede.")
                logger.warning("Nessuna sede selezionata, stop render().")
                return

            if selected_comuni:
                df = df[df['seprag_cod'].isin(selected_comuni)]

            if selected_genres:
                df = df[df['GENERE_CAT'].isin(selected_genres)]
            elif 'locale_genere' in df.columns:
                st.warning("Seleziona almeno un locale_genere.")
                logger.warning("Nessun genere selezionato, stop render().")
                return

            if selected_locali:
                df = df[df['des_locale'].isin(selected_locali)]

        except Exception as e:
            logger.exception("Errore durante l'applicazione dei filtri: %s", str(e))
            st.error("Errore nell'applicazione dei filtri.")
            return

    if df.empty:
        st.warning("Nessun dato disponibile con i filtri selezionati")
        logger.warning("DataFrame vuoto dopo i filtri.")
        return

    # ---------- LEFT COLUMN (Tables) ----------
    with col_table:
        st.subheader("Tabella locali in ordine di priorità")
        top_n = st.slider("Top N locali:", min_value=5, max_value=50, value=10, key="metrics_top_n")
        logger.info(f"Slider 'Top N locali' selezionato: {top_n}")

        if 'TOTALE_EVENTI' not in df.columns:
            logger.warning("'TOTALE_EVENTI' non trovato in df.columns")
            if 'events_total' in df.columns:
                try:
                    df['TOTALE_EVENTI'] = pd.to_numeric(df['events_total'], errors='coerce').fillna(0).astype(int)
                    logger.info("Creata colonna 'TOTALE_EVENTI' a partire da 'events_total'")
                except Exception as e:
                    logger.error(f"Errore durante la conversione 'events_total' → 'TOTALE_EVENTI': {e}", exc_info=True)
                    df['TOTALE_EVENTI'] = 0
            else:
                logger.error("Nessuna colonna 'events_total' trovata → imposto 'TOTALE_EVENTI' = 0")
                df['TOTALE_EVENTI'] = 0

        # Filtra locali nascosti
        if st.session_state.hidden_locales:
            df = df[~df['des_locale'].isin(st.session_state.hidden_locales)]
            logger.info(f"Filtrati {len(st.session_state.hidden_locales)} locali nascosti")

        if 'priority_score' in df.columns:
            df_top = df.nlargest(top_n, 'priority_score').reset_index(drop=True)
            logger.info(f"Generata top {top_n} righe ordinate per 'priority_score'")
        else:
            st.error("Colonna 'priority_score' non trovata nei dati")
            logger.error("Colonna 'priority_score' mancante: impossibile generare df_top")
            return

        # Aggiungi colonna checkbox per nascondere
        df_top_copy = df_top.copy()
        df_top_copy.insert(0, "Nascondi", False)

        display_columns = ["Nascondi", "des_locale", "locale_genere", "indirizzo", "TOTALE_EVENTI","priority_score"]
        column_mapping = {
            "Nascondi": "❌",
            "des_locale": "Nome Locale",
            "locale_genere": "Genere",
            "indirizzo": "Indirizzo",
            "TOTALE_EVENTI": "Eventi Totali",
            "priority_score": "Priority Score"
        }
        df_to_display = df_top_copy[display_columns].rename(columns=column_mapping)

        # Riga con azioni sopra la tabella
        action_col1, action_col2 = st.columns([5, 1])
        with action_col1:
            st.caption("Spunta la checkbox per nascondere un locale")
            if st.session_state.hidden_locales:
                st.caption(f"{len(st.session_state.hidden_locales)} locale/i nascosto/i")
        with action_col2:
            if st.session_state.hidden_locales:
                if st.button("Reset", key="reset_hidden"):
                    st.session_state.hidden_locales.clear()
                    st.rerun()

        edited_df = st.data_editor(
            df_to_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "❌": st.column_config.CheckboxColumn(
                    "❌",
                    help="Seleziona per nascondere",
                    default=False,
                    width="small"
                )
            },
            disabled=[col for col in df_to_display.columns if col != "❌"],
            key="metrics_table"
        )

        # Controlla quali righe hanno la checkbox spuntata
        checked_rows = edited_df[edited_df["❌"] == True]
        if not checked_rows.empty:
            for idx in checked_rows.index:
                locale_to_hide = checked_rows.loc[idx, "Nome Locale"]
                if locale_to_hide not in st.session_state.hidden_locales:
                    st.session_state.hidden_locales.add(locale_to_hide)
                    logger.info(f"Locale nascosto: {locale_to_hide}")
            st.rerun()

    # ----------------- Eventi per date selezionate -----------------
    mesi = {
                1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile",
                5: "maggio", 6: "giugno", 7: "luglio", 8: "agosto",
                9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"
    }

    st.subheader("Eventi per date selezionate (Top N)")
    today_dt = datetime.datetime.now().date()

    if "df_events_by_day" not in st.session_state:
        st.session_state.df_events_by_day = {}

    # ============= CSS STYLING =============
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

                /* Card styling per eventi */
                .venue-card {
                    background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
                    border: 1px solid #e0e7ff;
                    border-radius: 16px;
                    padding: 1.2rem;
                    margin-bottom: 1rem;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.07);
                    transition: all 0.3s ease;
                }
                .venue-card:hover {
                    transform: translateY(-3px);
                    box-shadow: 0 8px 16px rgba(102, 126, 234, 0.2);
                }
                .venue-head {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: 1rem;
                    flex-wrap: wrap;
                    margin-bottom: 0.8rem;
                }
                .venue-name {
                    font-size: 1.1rem;
                    font-weight: 700;
                    color: var(--text-color);
                    flex: 1;
                }
                .venue-status {
                    padding: 0.3rem 0.8rem;
                    border-radius: 8px;
                    font-size: 0.75rem;
                    font-weight: 500;
                    letter-spacing: 0.3px;
                    border: 1px solid #10b981;
                    color: #10b981;
                    background: transparent;
                }

                /* Compact card per evidenze */
                .compact-card {
                    background: white;
                    border: 1px solid #e2e8f0;
                    border-radius: 12px;
                    padding: 1rem;
                    margin: 0.8rem 0;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                    transition: all 0.3s ease;
                }
                .compact-card:hover {
                    box-shadow: 0 6px 12px rgba(0,0,0,0.1);
                    border-color: #cbd5e1;
                }
                .compact-card .header {
                    display: flex;
                    align-items: center;
                    gap: 0.6rem;
                    margin-bottom: 0.6rem;
                }
                .compact-card .favicon {
                    font-size: 1.2rem;
                }
                .compact-card .title {
                    font-weight: 600;
                    color: #0f172a;
                    font-size: 0.95rem;
                    line-height: 1.4;
                }
                .compact-card .meta {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    flex-wrap: wrap;
                    margin-bottom: 0.6rem;
                    font-size: 0.8rem;
                    color: #64748b;
                }
                .badge {
                    padding: 0.2rem 0.6rem;
                    border-radius: 6px;
                    font-weight: 600;
                    font-size: 0.75rem;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                .badge-ev {
                    background: linear-gradient(135deg, #f59e0b, #d97706);
                    color: white;
                }
                .domain {
                    color: #475569;
                    font-weight: 500;
                }
                .time-dot {
                    width: 3px;
                    height: 3px;
                    background: #94a3b8;
                    border-radius: 50%;
                }
                .compact-card .snippet {
                    color: #475569;
                    font-size: 0.85rem;
                    line-height: 1.5;
                    margin: 0.6rem 0;
                    display: -webkit-box;
                    -webkit-line-clamp: 3;
                    -webkit-box-orient: vertical;
                    overflow: hidden;
                }
                .compact-card .actions {
                    margin-top: 0.8rem;
                    padding-top: 0.8rem;
                    border-top: 1px solid #f1f5f9;
                }
                .link-btn {
                    display: inline-block;
                    padding: 0.5rem 1.2rem;
                    background: linear-gradient(135deg, #3b82f6, #2563eb);
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 0.85rem;
                    transition: all 0.3s ease;
                    box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
                }
                .link-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 10px rgba(59, 130, 246, 0.4);
                    background: linear-gradient(135deg, #2563eb, #1d4ed8);
                }

                /* Links wrap - rimuovere perché i link vanno nelle card */
                .venue-card .links-wrap {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 0.5rem;
                    padding-top: 0.8rem;
                    border-top: 1px solid rgba(102, 126, 234, 0.2);
                }
                .venue-card .chip-link {
                    display: inline-block;
                    padding: 0.5rem 1rem;
                    background: linear-gradient(135deg, #8b5cf6, #7c3aed);
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-size: 0.85rem;
                    font-weight: 600;
                    transition: all 0.3s ease;
                    box-shadow: 0 2px 6px rgba(139, 92, 246, 0.3);
                }
                .venue-card .chip-link:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 10px rgba(139, 92, 246, 0.4);
                    background: linear-gradient(135deg, #7c3aed, #6d28d9);
                }

                /* Day wrap */
                .day-wrap {
                    background: linear-gradient(45deg, #5b21b6, #5b21b6); /* viola chiaro sfumato */
                    border-radius: 16px;
                    margin-bottom: 1rem;
                }
                .day-title {
                    font-size: 1.1rem;
                    font-weight: 700;
                    color: var(--text-color);
                    padding: 0.8rem 1rem;
                    background: linear-gradient(135deg, rgba(248,250,252,0.6), rgba(241,245,249,0.6));
                    border-radius: 12px;
                    border-left: 4px solid #667eea;
                    margin-bottom: 1rem;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
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
    logger.info(f"Selezione date: {date_selection}")

    # --- BLOCCO CONTROLLO INTERVALLO ---
    block_search = False
    if isinstance(date_selection, tuple) and len(date_selection) == 2:
        start_date, end_date = date_selection
        logger.info(f"Intervallo selezionato: start_date={start_date}, end_date={end_date}")
        if start_date and end_date and start_date <= end_date:
            delta_days = (end_date - start_date).days
            logger.info(f"Delta giorni calcolato: {delta_days}")
            if delta_days > 6:  # oltre 7 giorni
                block_search = True
                logger.warning(f"Intervallo troppo lungo: {delta_days + 1} giorni selezionati")
    else:
        delta_days = 0
        logger.warning("date_selection non è un tuple di due date valide")

    if block_search:
        st.warning("⚠️ Puoi selezionare al massimo 7 giorni consecutivi.")
        logger.info("Ricerca disabilitata: intervallo > 7 giorni")
        search_disabled = True
    else:
        logger.info("Ricerca abilitata")
        search_disabled = False

    if st.button("Cerca eventi per le date selezionate", key="search_selected_days_events",
                         disabled=search_disabled):

        logger.info("Bottone 'Cerca eventi' premuto")
        logger.info(f"search_disabled={search_disabled}, date_selection={date_selection}")

        with st.spinner("Ricerca eventi in corso..."):
            st.session_state.df_events_by_day = {}
            selected_dates = []

            if isinstance(date_selection, tuple) and len(date_selection) == 2:
                start_date, end_date = date_selection
                logger.info(f"Intervallo selezionato: start_date={start_date}, end_date={end_date}")
                if start_date and end_date and start_date <= end_date:
                    delta_days = (end_date - start_date).days
                    logger.info(f"Delta giorni: {delta_days}")
                    selected_dates = [start_date + datetime.timedelta(days=i) for i in range(delta_days + 1)]
                else:
                    logger.warning("Intervallo date non valido, uso today_dt")
                    selected_dates = [today_dt]
            elif hasattr(date_selection, "strftime"):
                logger.info(f"Singola data selezionata: {date_selection}")
                selected_dates = [date_selection]
            else:
                logger.warning("Formato date_selection inatteso, uso today_dt")
                selected_dates = [today_dt]

            logger.info(f"Date selezionate per ricerca: {selected_dates}")

            # --- ciclo sui giorni con layout a 3 colonne ---
            for i, d in enumerate(selected_dates):
                day_str = f"{d.day:02d} {mesi[d.month]} {d.year}"
                logger.info(f"Ricerca eventi per giorno: {day_str}")
                df_day = get_today_events(df_top, day_str)  # recupero eventi per il giorno
                st.session_state.df_events_by_day[day_str] = df_day

                # nuova riga ogni 3 giorni
                if i % 3 == 0:
                    cols = st.columns(3)

                with cols[i % 3]:
                    st.markdown(f"<div class='day-wrap'><div class='day-title'>{day_str}</div></div>",
                                        unsafe_allow_html=True)

                    if df_day is not None and not df_day.empty:
                        logger.info(f"Trovati {len(df_day)} eventi per {day_str}")
                        for _, row in df_day.iterrows():
                            has_links = row['Link'] and row['Link'].strip() != "-"
                            logger.info(f"Locale: {row['Nome Locale']}, has_links={has_links}")

                            if has_links:
                                links = extract_links(row['Link'])

                                # Rendering card con i link dentro
                                st.markdown(
                                        f"""
                                            <div class="venue-card">
                                              <div class="venue-head">
                                                <div class="venue-name">{row['Nome Locale']}</div>
                                              </div>
                                              <div class="links-wrap">
                                                {''.join([f"<a href='{l.strip()}' target='_blank' class='chip-link'>Link {i + 1}</a>" for i, l in enumerate(links)])}
                                              </div>
                                            </div>
                                            """,
                                            unsafe_allow_html=True
                                        )

                                evidenze_meta = row.get('EVIDENZE_META') if isinstance(row, pd.Series) else None
                                if evidenze_meta:
                                    for ev in evidenze_meta:
                                        title = ev.get('title') or 'Evento trovato'
                                        url = ev.get('url') or ''
                                        snippet = ev.get('snippet') or ''
                                        time_info = ev.get('time') or ''
                                        domain = re.sub(r"^https?://", "", url).split("/")[0] if url else ''
                                        st.markdown(
                                                    f"""
                                                    <div class="compact-card">
                                                      <div class="header">
                                                        <div class="title">{title}</div>
                                                      </div>
                                                      <div class="meta">
                                                        <span class="badge badge-ev">Evidenza</span>
                                                        <span class="domain">{domain}</span>
                                                        <span class="time-dot"></span><span>{time_info}</span>
                                                      </div>
                                                      <p class="snippet">{snippet}</p>
                                                      <div class="actions"><a class="link-btn" href="{url}" target="_blank">Link</a></div>
                                                    </div>
                                                    """,
                                                    unsafe_allow_html=True)

                                    # Apri il file in append mode
                                    csv_filename = "output.csv"
                                    with open(csv_filename, mode="a", newline="", encoding="utf-8") as csvfile:
                                        writer = csv.writer(csvfile)

                                        # Scrivi la riga
                                        writer.writerow([row['Nome Locale'], d])