import datetime
import streamlit as st
import pandas as pd
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ==========================
# 🔐 Config Logging
# ==========================
LOG_FILE = "logs/recurrence_analysis.log"

handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
handler.setFormatter(formatter)

logger = logging.getLogger("recurrence_analysis")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

load_dotenv()
gen_prioritari_str = os.getenv("GENERI_PRIORITARI", "")
GENERI_PRIORITARI = [g.strip() for g in gen_prioritari_str.split(",") if g.strip()]
DATA_DIR = os.getenv("DATA_DIR", "data")

logger.info("Avvio modulo recurrence_analysis. Generi prioritari: %s", GENERI_PRIORITARI)


def load_events_data(allowed_regions):
    """
    Carica tutti i file Eventi_{città}_{anno}.csv disponibili per le regioni autorizzate.
    Ritorna un DataFrame unificato con colonna 'anno' aggiunta.
    """
    logger.info(f"Caricamento dati eventi per regioni: {allowed_regions}")

    all_events = []
    available_years = set()

    for region in allowed_regions:
        # Cerca tutti i file Eventi_{region}_{anno}.csv
        pattern = f"Eventi_{region}_*.csv"
        event_files = list(Path(DATA_DIR).glob(pattern))

        logger.info(f"Trovati {len(event_files)} file eventi per {region}")

        for file_path in event_files:
            try:
                # Estrai anno dal nome file
                filename = file_path.stem  # Eventi_Roma_2025
                parts = filename.split("_")
                if len(parts) >= 3:
                    year = int(parts[-1])
                else:
                    logger.warning(f"Impossibile estrarre anno da {filename}")
                    continue

                # Carica CSV
                df = pd.read_csv(file_path)
                df['anno'] = year
                df['sede'] = region

                # Parse data
                if 'data_ora_inizio' in df.columns:
                    df['data_ora_inizio'] = pd.to_datetime(df['data_ora_inizio'], errors='coerce')
                    df['giorno'] = df['data_ora_inizio'].dt.day
                    df['mese'] = df['data_ora_inizio'].dt.month
                    df['data'] = df['data_ora_inizio'].dt.date

                all_events.append(df)
                available_years.add(year)

                logger.info(f"Caricato {file_path.name}: {len(df)} eventi")

            except Exception as e:
                logger.error(f"Errore caricamento {file_path}: {e}")

    if not all_events:
        logger.warning("Nessun file eventi caricato")
        return pd.DataFrame(), []

    df_combined = pd.concat(all_events, ignore_index=True)
    available_years = sorted(list(available_years))

    logger.info(f"Totale eventi caricati: {len(df_combined)}, anni disponibili: {available_years}")

    return df_combined, available_years


def load_locali_priority_scores(allowed_regions):
    """
    Carica i file Locali_{città}.csv per ottenere i priority_score.
    Ritorna un DataFrame con des_locale, sede, priority_score.
    """
    logger.info(f"Caricamento priority scores per regioni: {allowed_regions}")

    all_locali = []

    for region in allowed_regions:
        file_path = Path(DATA_DIR) / f"Locali_{region}.csv"

        if not file_path.exists():
            logger.warning(f"File {file_path} non trovato")
            continue

        try:
            df = pd.read_csv(file_path)

            # Verifica presenza colonne necessarie
            if 'des_locale' not in df.columns:
                logger.warning(f"Colonna 'des_locale' non trovata in {file_path}")
                continue

            if 'priority_score' not in df.columns:
                logger.warning(f"Colonna 'priority_score' non trovata in {file_path}")
                df['priority_score'] = 1.0  # Default se manca

            # Converti priority_score a numerico
            df['priority_score'] = pd.to_numeric(df['priority_score'], errors='coerce')

            # Seleziona solo le colonne necessarie
            df_subset = df[['des_locale', 'priority_score']].copy()
            df_subset['sede'] = region

            all_locali.append(df_subset)

            logger.info(f"Caricati {len(df_subset)} locali da {file_path.name}")

        except Exception as e:
            logger.error(f"Errore caricamento {file_path}: {e}")

    if not all_locali:
        logger.warning("Nessun file Locali caricato")
        return pd.DataFrame()

    df_combined = pd.concat(all_locali, ignore_index=True)

    # Rimuovi duplicati (in caso ci siano)
    df_combined = df_combined.drop_duplicates(subset=['des_locale', 'sede'])

    logger.info(f"Totale locali caricati: {len(df_combined)}")

    return df_combined


def calculate_recurrence_score(df_events, df_priority_scores, day, month, filters):
    """
    Calcola il punteggio di ricorrenza per ogni locale dal file Locali_{città}.csv
    che ha eventi nel giorno/mese selezionato.

    IMPORTANTE: Considera SOLO eventi passati (data <= oggi)

    Score finale = score_ricorrenza * priority_score
    dove:
    - score_ricorrenza = numero_anni_con_evento / totale_anni_passati
    - priority_score = punteggio dal file Locali_{città}.csv

    Ritorna DataFrame con colonne:
    - des_locale, locale_genere, indirizzo, sede, seprag_cod
    - score_ricorrenza, priority_score, score (finale)
    - anni_con_evento, totale_anni
    - eventi_dettaglio (lista di eventi)
    """
    logger.info(f"Calcolo score ricorrenza per {day:02d}/{month:02d}")

    if df_priority_scores.empty:
        logger.error("Nessun locale caricato da Locali_{città}.csv")
        return pd.DataFrame()

    # Data odierna
    oggi = datetime.datetime.now().date()

    # Filtra eventi per il giorno/mese selezionato E data <= oggi
    df_filtered_events = df_events[
        (df_events['giorno'] == day) &
        (df_events['mese'] == month) &
        (df_events['data'] <= oggi)  # SOLO eventi passati
        ].copy()

    logger.info(f"Eventi passati trovati per {day:02d}/{month:02d}: {len(df_filtered_events)}")

    # Applica filtri agli eventi
    if filters.get('sedi'):
        df_filtered_events = df_filtered_events[df_filtered_events['sede'].isin(filters['sedi'])]
    if filters.get('comuni'):
        df_filtered_events = df_filtered_events[df_filtered_events['seprag_cod'].isin(filters['comuni'])]
    if filters.get('generi'):
        df_filtered_events = df_filtered_events[df_filtered_events['locale_genere'].isin(filters['generi'])]
    if filters.get('locali'):
        df_filtered_events = df_filtered_events[df_filtered_events['des_locale'].isin(filters['locali'])]

    logger.info(f"Eventi dopo filtri: {len(df_filtered_events)}")

    # Calcola anni passati: solo gli anni in cui il giorno/mese selezionato è già passato
    anno_corrente = oggi.year
    mese_corrente = oggi.month
    giorno_corrente = oggi.day

    # Se la data selezionata è già passata quest'anno, includi l'anno corrente
    data_selezionata_anno_corrente = datetime.date(anno_corrente, month,
                                                   min(day, 28))  # min per evitare errori con febbraio
    try:
        data_selezionata_anno_corrente = datetime.date(anno_corrente, month, day)
    except ValueError:
        # Gestisce date invalide come 31 febbraio
        pass

    if data_selezionata_anno_corrente <= oggi:
        anni_passati = [y for y in filters['available_years'] if y <= anno_corrente]
    else:
        anni_passati = [y for y in filters['available_years'] if y < anno_corrente]

    totale_anni_passati = len(anni_passati)
    logger.info(f"Anni passati considerati: {anni_passati}, totale: {totale_anni_passati}")

    # Applica filtri ai locali
    df_filtered_locali = df_priority_scores.copy()
    if filters.get('sedi'):
        df_filtered_locali = df_filtered_locali[df_filtered_locali['sede'].isin(filters['sedi'])]

    results = []

    # Itera sui locali dal file Locali_{città}.csv
    for _, locale_row in df_filtered_locali.iterrows():
        locale_name = locale_row['des_locale']
        sede = locale_row['sede']
        priority_score = locale_row['priority_score']

        # Cerca eventi per questo locale (solo passati)
        locale_events = df_filtered_events[
            (df_filtered_events['des_locale'] == locale_name) &
            (df_filtered_events['sede'] == sede)
            ]

        # Se non ha eventi in questa data, skippa
        if locale_events.empty:
            continue

        # Anni in cui il locale ha avuto eventi (solo passati)
        anni_con_evento = sorted(locale_events['anno'].unique())

        score_ricorrenza = len(anni_con_evento) / totale_anni_passati if totale_anni_passati > 0 else 0

        # Score finale = prodotto
        score_finale = score_ricorrenza * priority_score

        # Prendi info del locale (prima riga eventi per dati aggiuntivi)
        first_event = locale_events.iloc[0]

        # Crea lista eventi dettagliata
        eventi_dettaglio = []
        for _, event in locale_events.iterrows():
            eventi_dettaglio.append({
                'anno': event['anno'],
                'data': event['data'],
                'data_ora_inizio': event['data_ora_inizio'],
                'sede': event.get('sede', ''),
                'comune': event.get('comune', '')
            })

        results.append({
            'des_locale': locale_name,
            'locale_genere': first_event.get('locale_genere', 'N/D'),
            'indirizzo': first_event.get('indirizzo', 'N/D'),
            'sede': sede,
            'seprag_cod': first_event.get('seprag_cod', 'N/D'),
            'comune': first_event.get('comune', 'N/D'),
            'score_ricorrenza': score_ricorrenza,
            'priority_score': priority_score,
            'score': score_finale,
            'anni_con_evento': anni_con_evento,
            'totale_anni': totale_anni_passati,
            'num_eventi_totali': len(locale_events),
            'eventi_dettaglio': eventi_dettaglio
        })

    df_results = pd.DataFrame(results)

    if not df_results.empty:
        df_results = df_results.sort_values('score', ascending=False).reset_index(drop=True)

    logger.info(f"Locali con eventi: {len(df_results)}")

    return df_results


def show_event_details(eventi_dettaglio):
    """
    Mostra i dettagli degli eventi in card compatte.
    """
    st.markdown("""
        <style>
        .event-detail-card {
            background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
            border: 1px solid #e0e7ff;
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 0.8rem;
            box-shadow: 0 2px 6px rgba(0,0,0,0.07);
        }
        .event-year {
            font-size: 1.2rem;
            font-weight: 700;
            color: #667eea;
            margin-bottom: 0.5rem;
        }
        .event-info {
            font-size: 0.9rem;
            color: #475569;
            line-height: 1.6;
        }
        </style>
    """, unsafe_allow_html=True)

    for evento in sorted(eventi_dettaglio, key=lambda x: x['anno'], reverse=True):
        data_formatted = evento['data'].strftime("%d/%m/%Y") if pd.notna(evento['data']) else 'N/D'
        ora_formatted = evento['data_ora_inizio'].strftime("%H:%M") if pd.notna(evento['data_ora_inizio']) else 'N/D'

        st.markdown(f"""
            <div class="event-detail-card">
                <div class="event-year">{evento['anno']}</div>
                <div class="event-info">
                    <strong>Data:</strong> {data_formatted}<br>
                    <strong>Orario:</strong> {ora_formatted}<br>
                    <strong>Sede:</strong> {evento.get('sede', 'N/D')}<br>
                    <strong>Comune:</strong> {evento.get('comune', 'N/D')}
                </div>
            </div>
        """, unsafe_allow_html=True)


def render(allowed_regions=None):
    """
    Rendering principale del modulo Analisi Ricorrenze.
    """
    st.header("Analisi Ricorrenze Eventi")

    if allowed_regions is None:
        st.warning("Nessuna regione assegnata. Nessun dato da mostrare.")
        return

    st.info(
        """
        Analizza la **ricorrenza degli eventi** nei locali attraverso gli anni.  
        Seleziona un giorno e il sistema calcola uno **score finale** che combina:
        - **Score di ricorrenza**: % di anni in cui il locale ha fatto eventi in quella data
        - **Priority score**: priorità generale del locale

        I locali sono ordinati per score finale decrescente.
        """
    )

    # ========== Caricamento dati ==========
    with st.spinner("Caricamento dati..."):
        df_events, available_years = load_events_data(allowed_regions)
        df_priority_scores = load_locali_priority_scores(allowed_regions)

    if df_events.empty:
        st.error("Nessun file eventi trovato. Verifica la presenza dei file Eventi_{città}_{anno}.csv")
        return

    # ========== Layout principale ==========
    col_filters, col_table, col_details = st.columns([1, 2, 1.5])

    # ========== FILTRI ==========
    with col_filters:
        st.subheader("Filtri")

        # Toggle Priority Score
        use_priority_score = st.toggle(
            "Usa Priority Score",
            value=True,
            help="Disattiva per ordinare solo per ricorrenza",
            key="use_priority_score"
        )
        # Calcola domani come default
        domani = datetime.datetime.now().date() + datetime.timedelta(days=1)
        default_day = domani.day
        default_month = domani.month

        col_day, col_month = st.columns(2)
        with col_day:
            selected_day = st.number_input(
                "Giorno",
                min_value=1,
                max_value=31,
                value=default_day,
                key="recurrence_day"
            )
        with col_month:
            mesi = {
                1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
                5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
                9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
            }
            selected_month_name = st.selectbox(
                "Mese",
                options=list(mesi.values()),
                index=default_month - 1,  # Index è 0-based
                key="recurrence_month"
            )
            selected_month = list(mesi.keys())[list(mesi.values()).index(selected_month_name)]

        st.divider()

        # Filtro sedi
        sedi = sorted(df_events['sede'].dropna().unique().tolist())

        # Default: Roma se disponibile, altrimenti prima sede
        roma_option = next((s for s in sedi if isinstance(s, str) and s.strip().lower() == 'roma'), None)
        if roma_option:
            default_sedi = [roma_option]
        elif sedi:
            default_sedi = [sedi[0]]
        else:
            default_sedi = []

        selected_sedi = st.multiselect(
            "Sedi",
            options=sedi,
            default=default_sedi,
            key="recurrence_sedi"
        )

        # Filtro comuni (basato su sedi selezionate)
        df_for_comuni = df_events[df_events['sede'].isin(selected_sedi)] if selected_sedi else df_events
        comuni_options = sorted(df_for_comuni['seprag_cod'].dropna().unique().tolist())

        selected_comuni = st.multiselect(
            "SEPRAG (opzionale)",
            options=comuni_options,
            default=[],
            key="recurrence_comuni"
        )

        # Filtro generi
        if 'locale_genere' in df_events.columns:
            generi_options = sorted(df_events['locale_genere'].dropna().unique().tolist())

            # Default: "Bar" e "Discoteca" (case-insensitive match)
            default_genres = []
            for genere in generi_options:
                if isinstance(genere, str) and genere.strip().lower() in ['bar', 'discoteca']:
                    default_genres.append(genere)

            selected_genres = st.multiselect(
                "Generi",
                options=generi_options,
                default=default_genres,
                key="recurrence_genres"
            )
        else:
            selected_genres = None

        # Filtro locali
        df_for_locali = df_events[df_events['sede'].isin(selected_sedi)] if selected_sedi else df_events
        if selected_comuni:
            df_for_locali = df_for_locali[df_for_locali['seprag_cod'].isin(selected_comuni)]
        if selected_genres:
            df_for_locali = df_for_locali[df_for_locali['locale_genere'].isin(selected_genres)]

        locali_options = sorted(df_for_locali['des_locale'].dropna().unique().tolist())
        selected_locali = st.multiselect(
            "Locali (opzionale)",
            options=locali_options,
            default=[],
            key="recurrence_locali"
        )

    # ========== CALCOLO RICORRENZE ==========
    filters = {
        'sedi': selected_sedi,
        'comuni': selected_comuni,
        'generi': selected_genres,
        'locali': selected_locali,
        'available_years': available_years
    }

    with st.spinner("Calcolo ricorrenze..."):
        df_results = calculate_recurrence_score(df_events, df_priority_scores, selected_day, selected_month, filters)

    # ========== TABELLA RISULTATI ==========
    with col_table:
        st.subheader(f"Locali - {selected_day:02d}/{selected_month_name}")

        if df_results.empty:
            st.warning("Nessun locale trovato con i filtri selezionati")
            logger.warning("Nessun risultato dopo filtri")
            return

        st.info(f"**{len(df_results)} locali** hanno organizzato eventi in questa data")

        # Prepara DataFrame per visualizzazione
        df_display = df_results[[
            'des_locale', 'locale_genere', 'sede',
            'score_ricorrenza', 'priority_score', 'score',
            'anni_con_evento', 'totale_anni', 'num_eventi_totali'
        ]].copy()

        # Formatta score ricorrenza come percentuale e frazione
        df_display['Score Ric.'] = df_display.apply(
            lambda row: f"{row['score_ricorrenza']:.0%} ({len(row['anni_con_evento'])}/{row['totale_anni']})",
            axis=1
        )

        # Formatta priority score
        df_display['Priority'] = df_display['priority_score'].apply(lambda x: f"{x:.3f}")

        # Formatta score finale
        df_display['Score Finale'] = df_display['score'].apply(lambda x: f"{x:.3f}")

        df_display = df_display.rename(columns={
            'des_locale': 'Nome Locale',
            'locale_genere': 'Genere',
            'sede': 'Sede',
            'num_eventi_totali': 'Tot. Eventi'
        })

        df_display = df_display[[
            'Nome Locale', 'Genere', 'Sede', 'Score Ric.', 'Priority', 'Score Finale', 'Tot. Eventi'
        ]]

        # Tabella interattiva
        selected_row = st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="recurrence_table"
        )

    # ========== DETTAGLI LOCALE SELEZIONATO ==========
    with col_details:
        st.subheader("Dettagli Locale")

        if selected_row.selection and len(selected_row.selection['rows']) > 0:
            selected_idx = selected_row.selection['rows'][0]
            locale_data = df_results.iloc[selected_idx]

            # Info generale
            st.markdown(f"""
                **{locale_data['des_locale']}**

                - **Genere:** {locale_data['locale_genere']}
                - **Sede:** {locale_data['sede']}
                - **Comune:** {locale_data.get('comune', 'N/D')}
                - **Indirizzo:** {locale_data.get('indirizzo', 'N/D')}
            """)

            # Metriche
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.metric("Score Ricorrenza", f"{locale_data['score_ricorrenza']:.0%}")
            with col_m2:
                st.metric("Priority Score", f"{locale_data['priority_score']:.3f}")

            col_m3, col_m4 = st.columns(2)
            with col_m3:
                st.metric("Score Finale", f"{locale_data['score']:.3f}")
            with col_m4:
                st.metric("Anni attivi", f"{len(locale_data['anni_con_evento'])}/{locale_data['totale_anni']}")

            st.divider()

            # Dettagli eventi
            st.markdown("### Dettagli Eventi")
            show_event_details(locale_data['eventi_dettaglio'])

        else:
            st.info("Seleziona una riga nella tabella per vedere i dettagli")

    # ========== STATISTICHE GLOBALI ==========
    st.divider()
    st.subheader("Statistiche Globali")

    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)

    with col_stat1:
        st.metric("Totale Locali", len(df_results))

    with col_stat2:
        avg_score = df_results['score'].mean() if not df_results.empty else 0
        score_metric_label = "Score Medio" if not use_priority_score else "Score Finale Medio"
        st.metric(score_metric_label, f"{avg_score:.3f}")

    with col_stat3:
        locali_100_ric = len(df_results[df_results['score_ricorrenza'] == 1.0])
        st.metric("Ricorrenza 100%", locali_100_ric)

    with col_stat4:
        tot_eventi = df_results['num_eventi_totali'].sum()
        st.metric("Eventi Totali", tot_eventi)

    # ========== DISTRIBUZIONE EVENTI NELL'ANNO ==========
    st.divider()
    st.subheader("Distribuzione Eventi nell'Anno")

    # Selettore anno
    col_anno, col_space = st.columns([1, 3])
    with col_anno:
        selected_year = st.selectbox(
            "Seleziona anno",
            options=sorted(available_years, reverse=True),
            key="distribution_year"
        )

    # Calcola distribuzione per l'anno selezionato
    df_events_filtered = df_events.copy()

    # Filtra per anno selezionato
    df_events_filtered = df_events_filtered[df_events_filtered['anno'] == selected_year]

    # Applica gli stessi filtri usati per i risultati
    if selected_sedi:
        df_events_filtered = df_events_filtered[df_events_filtered['sede'].isin(selected_sedi)]
    if selected_comuni:
        df_events_filtered = df_events_filtered[df_events_filtered['seprag_cod'].isin(selected_comuni)]
    if selected_genres:
        df_events_filtered = df_events_filtered[df_events_filtered['locale_genere'].isin(selected_genres)]
    if selected_locali:
        df_events_filtered = df_events_filtered[df_events_filtered['des_locale'].isin(selected_locali)]

    # Filtra solo locali presenti in Locali_{città}.csv
    if not df_priority_scores.empty:
        locali_validi = df_priority_scores['des_locale'].unique()
        df_events_filtered = df_events_filtered[df_events_filtered['des_locale'].isin(locali_validi)]

    # Solo eventi passati
    oggi = datetime.datetime.now().date()
    df_events_filtered = df_events_filtered[df_events_filtered['data'] <= oggi]

    if not df_events_filtered.empty:
        # Assicurati che giorno e mese siano int
        df_events_filtered = df_events_filtered.copy()
        df_events_filtered['giorno'] = pd.to_numeric(df_events_filtered['giorno'], errors='coerce')
        df_events_filtered['mese'] = pd.to_numeric(df_events_filtered['mese'], errors='coerce')
        df_events_filtered = df_events_filtered.dropna(subset=['giorno', 'mese'])
        df_events_filtered['giorno'] = df_events_filtered['giorno'].astype(int)
        df_events_filtered['mese'] = df_events_filtered['mese'].astype(int)

        # Raggruppa per giorno/mese e conta eventi
        eventi_per_giorno = df_events_filtered.groupby(['mese', 'giorno']).size().reset_index(name='num_eventi')

        # Converti a int e gestisci eventuali NaN
        eventi_per_giorno = eventi_per_giorno.dropna(subset=['mese', 'giorno'])
        eventi_per_giorno['mese'] = eventi_per_giorno['mese'].astype(int)
        eventi_per_giorno['giorno'] = eventi_per_giorno['giorno'].astype(int)

        # Crea etichetta per l'asse X usando operazioni vettoriali
        eventi_per_giorno['data_label'] = (
                eventi_per_giorno['giorno'].astype(str).str.zfill(2) + '/' +
                eventi_per_giorno['mese'].astype(str).str.zfill(2)
        )

        # Ordina per data
        eventi_per_giorno = eventi_per_giorno.sort_values(['mese', 'giorno'])

        # Crea line chart
        fig_dist = go.Figure()

        fig_dist.add_trace(go.Scatter(
            x=eventi_per_giorno['data_label'],
            y=eventi_per_giorno['num_eventi'],
            mode='lines',
            fill='tozeroy',
            line=dict(color='#667eea', width=2),
            fillcolor='rgba(102, 126, 234, 0.2)',
            name='Eventi',
            hovertemplate='<b>%{x}</b><br>Eventi: %{y}<extra></extra>'
        ))

        fig_dist.update_layout(
            title=f"Distribuzione eventi nel {selected_year}",
            xaxis_title="Giorno/Mese",
            yaxis_title="Numero eventi",
            height=400,
            showlegend=False,
            hovermode='x unified',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(
                tickangle=-45,
                tickmode='array',
                tickvals=eventi_per_giorno['data_label'][::15],  # Mostra ogni 15 giorni
                ticktext=eventi_per_giorno['data_label'][::15]
            )
        )

        st.plotly_chart(fig_dist, use_container_width=True)

        # Info aggiuntiva
        giorno_max = eventi_per_giorno.loc[eventi_per_giorno['num_eventi'].idxmax()]
        col_info1, col_info2, col_info3 = st.columns(3)

        with col_info1:
            st.metric("Giorno con più eventi", giorno_max['data_label'])
        with col_info2:
            st.metric(f"Eventi quel giorno ({selected_year})", f"{giorno_max['num_eventi']:.0f}")
        with col_info3:
            st.metric(f"Totale eventi {selected_year}", f"{eventi_per_giorno['num_eventi'].sum():.0f}")
    else:
        st.info(f"Nessun evento disponibile per l'anno {selected_year} con i filtri selezionati")