import os, requests, json
from dotenv import load_dotenv
import time

load_dotenv()
SERPER_API_KEY = os.environ["SERPER_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

def check_event_exists(venue: str, city: str, event_date: str):

    q = f"{venue} {city} eventi {event_date}"
    print(q)

    # --- 1) Ricerca su Google via Serpenter
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": q, "num": 8, "gl": "it", "hl": "it"},
            timeout=20
        )
        resp.raise_for_status()
        try:
            search = resp.json()
        except ValueError as e:  # invalid JSON
            return {"exists": False, "confidence": 0.0, "evidence": [], "error": f"Invalid JSON: {e}"}
    except requests.RequestException as e:
        print(f"exception ricerca serpenter {e}")
        return {"exists": False, "confidence": 0.0, "evidence": [], "error": str(e)}

    items = [
        {"title": r.get("title",""), "snippet": r.get("snippet",""), "url": r.get("link","")}
        for r in search.get("organic", [])
    ][:3]

    if not items:
        return {"exists": False, "confidence": 0.1, "evidence": []}

    # --- 2) Prompt per Gemini
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
        time.sleep(10)
        r = requests.post(
            # gemini-pro-latest: bloccato ogni tanto  503 Server Error: Service Unavailable
            # gemini-2.5-flash-lite-preview-09-2025
            # gemini-2.5-flash-preview-09-2025 too many requests
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}",
            json=payload,
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as e:
        print(f"exception ricerca gemini {e}")
        return {"exists": False, "confidence": 0.0, "evidence": [], "error": str(e)}
