#!/usr/bin/env python3
"""
============================================================
 QG FUT TRADER — Motor ETL v2  (blindado contra erros)

 Correções v2:
  - Melhor tratamento de rate limit
  - Fallback robusto para cada chamada
  - Logs detalhados para debug no GitHub Actions
  - Salva arquivo mesmo com 0 partidas (JSON vazio válido)
============================================================
"""

import json, os, sys, time
from datetime import datetime, timedelta, timezone
import requests

FOOTBALL_API_KEY  = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
FOOTBALL_API_BASE = "https://api.football-data.org/v4"
OUTPUT_FILE       = "jogos_de_hoje.json"
RATE_DELAY        = 7  # segundos (free tier = max 10 req/min)


def log(msg):
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}", flush=True)

def today_brazil():
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")

def api_get(endpoint, params=None):
    url = f"{FOOTBALL_API_BASE}{endpoint}"
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"X-Auth-Token": FOOTBALL_API_KEY},
                             params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("X-RequestCounter-Reset", 60))
                log(f"  ⏳ Rate limit. Aguardando {wait}s...")
                time.sleep(wait + 2)
                continue
            if r.status_code in (403, 401):
                log("  ❌ HTTP 403/401 — API Key inválida ou sem permissão!")
                return {}
            if r.status_code == 404:
                return {}
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log(f"  ⚠️  Erro tentativa {attempt+1}/3: {e}")
            time.sleep(5)
    return {}

def get_recent_form(team_id):
    data = api_get(f"/teams/{team_id}/matches", {"limit": 10, "status": "FINISHED"})
    time.sleep(RATE_DELAY)
    form = []
    for m in reversed(data.get("matches", [])):
        if len(form) >= 5: break
        ft = (m.get("score") or {}).get("fullTime", {})
        sh, sa = ft.get("home"), ft.get("away")
        if sh is None or sa is None: continue
        is_home = (m.get("homeTeam") or {}).get("id") == team_id
        if is_home: form.append("V" if sh>sa else "D" if sh<sa else "E")
        else:       form.append("V" if sa>sh else "D" if sa<sh else "E")
    while len(form) < 5: form.insert(0, "-")
    return form[-5:]

def get_standings(comp_id, home_id, away_id):
    empty = {"pos":"-","pts":"-","p":"-","sg":"-"}
    data  = api_get(f"/competitions/{comp_id}/standings")
    time.sleep(RATE_DELAY)
    table = []
    for s in data.get("standings", []):
        if s.get("type") == "TOTAL": table = s.get("table", []); break
    if not table and data.get("standings"):
        table = data["standings"][0].get("table", [])
    h, a = dict(empty), dict(empty)
    for row in table:
        tid = (row.get("team") or {}).get("id")
        e = {"pos":row.get("position","-"),"pts":row.get("points","-"),
             "p":row.get("playedGames","-"),"sg":row.get("goalDifference","-")}
        if tid == home_id: h = e
        if tid == away_id: a = e
    return {"home": h, "away": a}

def get_h2h(match_id):
    data = api_get(f"/matches/{match_id}/head2head", {"limit": 5})
    time.sleep(RATE_DELAY)
    h2h = []
    for m in data.get("matches", []):
        mh = (m.get("homeTeam") or {}).get("shortName") or (m.get("homeTeam") or {}).get("name","?")
        ma = (m.get("awayTeam") or {}).get("shortName") or (m.get("awayTeam") or {}).get("name","?")
        ft = (m.get("score") or {}).get("fullTime", {})
        sh, sa = ft.get("home"), ft.get("away")
        h2h.append({"date":m.get("utcDate","")[:10],"home":mh,
                    "score":f"{sh}-{sa}" if sh is not None else "?-?","away":ma})
    return h2h

def get_clubelo(name):
    slug = "".join(c for c in name if c.isalnum())
    try:
        r = requests.get(f"http://api.clubelo.com/{slug}", timeout=10)
        if r.status_code == 200 and r.text.strip():
            lines = [l for l in r.text.strip().split("\n") if l and not l.startswith("Rank")]
            if lines:
                parts = lines[-1].split(",")
                if len(parts) >= 5:
                    return str(round(float(parts[4])))
    except Exception: pass
    return "N/A"

def enrich(match):
    hid = match["homeTeam"]["id"]
    aid = match["awayTeam"]["id"]
    cid = match["competition"]["id"]
    mid = match["id"]
    hn  = match["homeTeam"].get("shortName") or match["homeTeam"]["name"]
    an  = match["awayTeam"].get("shortName") or match["awayTeam"]["name"]
    st  = match.get("status","SCHEDULED")

    log(f"    ↳ Forma: {hn}..."); fh = get_recent_form(hid)
    log(f"    ↳ Forma: {an}..."); fa = get_recent_form(aid)
    log(f"    ↳ Classificação..."); standings = get_standings(cid, hid, aid)
    log(f"    ↳ H2H..."); h2h = get_h2h(mid)
    log(f"    ↳ ClubElo...")
    eh, ea = get_clubelo(hn), get_clubelo(an)
    time.sleep(2)

    if st == "FINISHED":
        sh = match["score"]["fullTime"].get("home","?")
        sa = match["score"]["fullTime"].get("away","?")
        info = f"Partida encerrada. Placar final: {sh}-{sa}."
    elif st in ("IN_PLAY","PAUSED"):
        info = f"Partida em andamento ({match.get('minute','?')}')."
    else:
        info = f"Dados coletados às {datetime.utcnow().strftime('%H:%M UTC')}."

    match["inteligencia"] = {
        "clubelo":     {"home_elo": eh, "away_elo": ea},
        "recent_form": {"home": fh, "away": fa},
        "standings":   standings,
        "h2h":         h2h,
        "stats":       {"info": info, "reliability": "8.5"}
    }
    return match

def main():
    log("=" * 50)
    log("🔥 QG FUT TRADER — Motor ETL v2")
    log(f"📅 Data BR: {today_brazil()}")
    log("=" * 50)

    if not FOOTBALL_API_KEY:
        log("❌ FOOTBALL_DATA_API_KEY não encontrada!")
        log("   GitHub: Settings → Secrets and variables → Actions")
        log("   Crie: FOOTBALL_DATA_API_KEY = <sua_chave>")
        sys.exit(1)

    log(f"🔑 Key: {'*'*20}{FOOTBALL_API_KEY[-4:]}")

    today = today_brazil()
    log(f"\n📡 Buscando partidas de {today}...")
    data    = api_get("/matches", {"dateFrom": today, "dateTo": today})
    matches = data.get("matches", [])
    log(f"✅ {len(matches)} partida(s) encontrada(s)")

    if not matches:
        log("ℹ️  Nenhuma partida hoje. Salvando JSON vazio válido.")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump({"matches":[], "_gerado_em": datetime.utcnow().isoformat()+"Z"}, f)
        return

    enriched = []
    for i, match in enumerate(matches):
        hn = match["homeTeam"].get("shortName") or match["homeTeam"]["name"]
        an = match["awayTeam"].get("shortName") or match["awayTeam"]["name"]
        log(f"\n  [{i+1}/{len(matches)}] {match['competition']['name']}: {hn} x {an}")
        try:
            enriched.append(enrich(match))
        except Exception as e:
            log(f"  ⚠️  Falha: {e}")
            match.setdefault("inteligencia", {
                "clubelo":     {"home_elo":"N/A","away_elo":"N/A"},
                "recent_form": {"home":["-","-","-","-","-"],"away":["-","-","-","-","-"]},
                "standings":   {"home":{"pos":"-","pts":"-","p":"-","sg":"-"},
                                "away":{"pos":"-","pts":"-","p":"-","sg":"-"}},
                "h2h":  [],
                "stats": {"info":"Dados indisponíveis.","reliability":"0.0"}
            })
            enriched.append(match)

    output = {"matches": enriched, "_gerado_em": datetime.utcnow().isoformat()+"Z",
              "_total": len(enriched)}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log(f"\n✅ {OUTPUT_FILE} gerado — {len(enriched)} partida(s)!")
    log("🏁 A Ferrari está abastecida.")

if __name__ == "__main__":
    main()
