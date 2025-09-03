import os
import pandas as pd
from datetime import datetime


def perform_sonar_search(locale_name):
    """Esegue la ricerca tramite API Sonar e salva i risultati in append su CSV"""

    search_queries = [
        f"{locale_name} eventi",
        f"{locale_name} concerti",
        f"{locale_name} spettacoli"
    ]

    all_events = []

    for query in search_queries:
        events = call_sonar_api(query)
        all_events.extend(events)

    # Processa i dati
    df_events = process_events_data(locale_name, all_events)


    filepath = os.getenv("DEEP_SEARCH_DATA")
    # Crea la directory se non esiste
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Salva in append
    if os.path.exists(filepath):
        df_events.to_csv(filepath, mode='a', header=False, index=False)
    else:
        df_events.to_csv(filepath, mode='w', header=True, index=False)

    return df_events


def call_sonar_api(query: str) -> list:
    """
    Simula una chiamata API Sonar per ottenere eventi in base alla query.
    Restituisce una lista di dizionari con dati evento.
    """
    # Simulazione di risultati
    simulated_results = [
        {
            "evento": f"Evento speciale: {query}",
            "data": "2025-09-10",
            "descrizione": f"Descrizione dell'evento relativo a '{query}'."
        },
        {
            "evento": f"Altro evento: {query}",
            "data": "2025-09-15",
            "descrizione": f"Un altro evento interessante su '{query}'."
        }
    ]
    return simulated_results

def process_events_data(locale_name: str, events: list) -> pd.DataFrame:
    df_events = pd.DataFrame(events)

    # Aggiunge colonne richieste
    df_events["data_research"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_events["nome_locale"] = locale_name

    # Rinomina colonne per uniformità
    df_events = df_events.rename(columns={
        "data": "data_evento",
        "descrizione": "descrizione_evento"
    })

    # Seleziona e ordina le colonne
    df_events = df_events[[
        "data_research",
        "nome_locale",
        "evento",
        "data_evento",
        "descrizione_evento"
    ]]

    return df_events
