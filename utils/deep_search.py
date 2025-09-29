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
    ][:8]

    if not items:
        return {"exists": False, "confidence": 0.1, "evidence": []}

    # --- 2) Prompt per Gemini
    system_rules = f"""
    Sei un verificatore eventi. Decidi se esiste un evento esattamente nella data/città richieste.
    Rispondi "si" solo se almeno una delle fonti fornite indica chiaramente che l'evento esiste in data {event_date} a {city}.
    Se la data non coincide esattamente, rispondi "no".
    Usa SOLO gli URL forniti.
    Output SOLO in JSON:
    {{"exists": true|false, "confidence": 0..1, "evidence": ["url1","url2"...]}}
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
        time.sleep(15)
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
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
