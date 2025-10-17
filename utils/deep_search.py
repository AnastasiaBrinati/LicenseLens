import os
import requests
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Cache settings
CACHE_DIR = Path("data/cache/events")
CACHE_EXPIRY_HOURS = 24

logger.info("Modulo di verifica eventi inizializzato")

def _get_cache_key(venue: str, city: str, event_date: str) -> str:
    """Genera una chiave univoca per la cache"""
    key_string = f"{venue}|{city}|{event_date}".lower()
    return hashlib.md5(key_string.encode()).hexdigest()

def _get_cache_path(cache_key: str) -> Path:
    """Ottiene il percorso del file di cache"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{cache_key}.json"

def _load_from_cache(cache_key: str) -> dict:
    """Carica risultato dalla cache se valido"""
    cache_path = _get_cache_path(cache_key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cached_data = json.load(f)

        # Verifica se la cache è ancora valida
        cached_time = datetime.fromisoformat(cached_data.get('timestamp', ''))
        expiry_time = cached_time + timedelta(hours=CACHE_EXPIRY_HOURS)

        if datetime.now() < expiry_time:
            logger.info(f"Cache hit per chiave {cache_key}")
            return cached_data.get('result')
        else:
            logger.info(f"Cache expired per chiave {cache_key}")
            cache_path.unlink()
            return None

    except Exception as e:
        logger.warning(f"Errore lettura cache: {e}")
        return None

def _save_to_cache(cache_key: str, result: dict):
    """Salva risultato nella cache"""
    cache_path = _get_cache_path(cache_key)

    try:
        cached_data = {
            'timestamp': datetime.now().isoformat(),
            'result': result
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cached_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Risultato salvato in cache: {cache_key}")
    except Exception as e:
        logger.warning(f"Errore salvataggio cache: {e}")

def check_event_exists(venue: str, city: str, event_date: str):
    # Controlla cache prima di fare le chiamate API
    cache_key = _get_cache_key(venue, city, event_date)
    cached_result = _load_from_cache(cache_key)

    if cached_result is not None:
        logger.info(f"Risultato trovato in cache per {venue}, {city}, {event_date}")
        return cached_result

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
            result = {"exists": False, "confidence": 0.0, "evidence": [], "error": f"Invalid JSON: {e}"}
            _save_to_cache(cache_key, result)
            return result

    except requests.RequestException as e:
        logger.error(f"Errore richiesta Serper: {e}")
        result = {"exists": False, "confidence": 0.0, "evidence": [], "error": str(e)}
        _save_to_cache(cache_key, result)
        return result

    items = [
        {"title": r.get("title",""), "snippet": r.get("snippet",""), "url": r.get("link","")}
        for r in search.get("organic", [])
    ][:3]

    logger.info(f"Trovati {len(items)} risultati organici da Serper")

    if not items:
        logger.warning("Nessun risultato trovato da Serper")
        result = {"exists": False, "confidence": 0.1, "evidence": []}
        _save_to_cache(cache_key, result)
        return result

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
        result = json.loads(text)
        _save_to_cache(cache_key, result)
        return result

    except Exception as e:
        logger.exception(f"Errore richiesta Gemini: {e}")
        result = {"exists": False, "confidence": 0.0, "evidence": [], "error": str(e)}
        _save_to_cache(cache_key, result)
        return result
