import os
import requests
import json
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

logger.info("Modulo di verifica eventi inizializzato")

def check_event_exists(venue: str, city: str, event_date: str):
    q = f"{venue} {city} eventi {event_date}"
    logger.info(f"Eseguo query evento: {q}")

    # --- 1) Ricerca su Google via Serpenter
    try:
        logger.info("Richiesta a Serper API")
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": q, "num": 5, "gl": "it", "hl": "it"},
            timeout=30
        )
        resp.raise_for_status()

        try:
            search = resp.json()
            logger.debug(f"Risposta Serper: {json.dumps(search, indent=2, ensure_ascii=False)}")
        except ValueError as e:
            logger.error(f"JSON non valido da Serper: {e}")
            return {"exists": False, "confidence": 0.0, "evidence": [], "error": f"Invalid JSON: {e}"}

    except requests.RequestException as e:
        logger.error(f"Errore richiesta Serper: {e}")
        return {"exists": False, "confidence": 0.0, "evidence": [], "error": str(e)}

    items = [
        {"title": r.get("title",""), "snippet": r.get("snippet",""), "url": r.get("link","")}
        for r in search.get("organic", [])
    ][:3]

    logger.info(f"Trovati {len(items)} risultati organici da Serper")

    if not items:
        logger.warning("Nessun risultato trovato da Serper")
        return {"exists": False, "confidence": 0.1, "evidence": []}

    # --- 2) Prompt per Gemini
    logger.info("Preparazione payload per Gemini API")
    system_rules = f"""
        Sei un verificatore eventi. Devi stabilire se esiste un evento esattamente nella data richiesta, presso il locale e nella città indicata.

        Regole:
        1. Rispondi '"exists": true' solo se almeno UNA delle fonti fornite conferma in modo chiaro e inequivocabile che l’evento si svolge nella data {event_date}, nella città {city} e nel locale {venue}.
        2. Se la data, la città o il locale non coincidono esattamente (anche con differenze minime, es. altro locale simile o città vicina), rispondi '"exists": false'.
        3. Non fare inferenze o supposizioni: usa esclusivamente le informazioni contenute negli URL forniti.
        4. Usa solo pagine web ufficiali o pagine social del locale.
        5. La risposta deve essere **solo in formato JSON**, senza testo aggiuntivo, con la seguente struttura:
        "exists": true|false,
        "confidence": 0..1,
        "evidence": ["url1","url2", ... ]
    """

    user_payload_text = (
        system_rules
        + "\n\n"
        + f"Query: {q}\n"
        + "Risultati:\n"
        + "\n".join([f"- {it['title']}\n  {it['snippet']}\n  {it['url']}" for it in items])
    )

    payload = {
      "contents": [{"role": "user", "parts": [{"text": user_payload_text}]}],
      "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
    }

    try:
        logger.info("Invio richiesta a Gemini API")
        time.sleep(4)  # throttling: gemini-2.5-flash-lite permette 15 RPM (1 ogni 4s)
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}",
            json=payload,
            timeout=30
        )
        r.raise_for_status()

        data = r.json()
        logger.debug(f"Risposta Gemini: {json.dumps(data, indent=2, ensure_ascii=False)}")

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        logger.info("Risposta Gemini ottenuta correttamente")
        return json.loads(text)

    except Exception as e:
        logger.exception(f"Errore richiesta Gemini: {e}")
        return {"exists": False, "confidence": 0.0, "evidence": [], "error": str(e)}
