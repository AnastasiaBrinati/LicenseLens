import os
import pandas as pd
from datetime import datetime


def perform_sonar_search(locale_name: str) -> str:
    """Esegue la ricerca tramite API Sonar e salva il risultato sintetico in research.csv"""

    result = call_sonar_api(locale_name)

    # Se non ci sono eventi trovati
    if not result:
        descrizione = "Nessun evento trovato."
    else:
        descrizione = result

    # Costruisci DataFrame con formato standardizzato
    df_result = pd.DataFrame([{
        "data_deep_search": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nome_locale": locale_name,
        "descrizione": descrizione
    }])

    # Percorso file
    filepath = os.getenv("DEEP_SEARCH_DATA", "./data/deep/sonar.csv")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Salvataggio append
    if os.path.exists(filepath):
        df_result.to_csv(filepath, mode="a", header=False, index=False)
    else:
        df_result.to_csv(filepath, mode="w", header=True, index=False)

    return result


def call_sonar_api(query: str) -> list:
    """
    Simula una chiamata API Sonar per ottenere eventi in base alla query.
    Restituisce una lista di dizionari con dati evento.
    """
    simulated_results = [
        {
            "evento": f"Evento speciale: {query}",
            "data": "2025-09-11",
            "descrizione": f"Descrizione dell'evento relativo a '{query}'."
        }
    ]
    return simulated_results
