#!/usr/bin/env python3
"""
============================================================
 QG FUT TRADER — Motor ETL v4  (multi-source, corrigido)

 FIX: eventsday.php retornava dados de 2014 (bug TheSportsDB)
      Substituido por eventsnextleague + eventspastleague
      com filtro por data e deduplicacao

 Fontes em cascata:
  1. football-data.org (se API key configurada)
  2. TheSportsDB (gratuito, sem key, multi-liga)

 Enriquecimento: Form, Classificacao, H2H, ClubElo
 Nunca falha — sempre gera JSON valido.
============================================================
"""

import json, os, sys, time
from datetime import datetime, timedelta, timezone
import requests

FOOTBALL_API_KEY  = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
FOOTBALL_API_BASE = "https://api.football-data.org/v4"
TSDB_BASE         = "https://www.thesportsdb.com/api/v1/json/3"
OUTPUT_FILE       = "jogos_de_hoje.json"
RATE_DELAY        = 7   # football-data.org free tier
TSDB_DELAY        = 0.5 # TheSportsDB é mais permissivo


def log(msg):
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}", flush=True)

def today_brazil():
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")

def save_output(matches, source="unknown"):
    output = {
        "matches": matches,
        "_gerado_em": datetime.utcnow().isoformat() + "Z",
        "_total": len(matches),
        "_fonte": source
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"💾 {OUTPUT_FILE} salvo — {len(matches)} partida(s) via {source}")


# ═══════════════════════════════════════════════════
#  FOOTBALL-DATA.ORG (fonte primária)
# ═══════════════════════════════════════════════════
def fd_api_get(endpoint, params=None):
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

def fd_get_recent_form(team_id):
    data = fd_api_get(f"/teams/{team_id}/matches", {"limit": 10, "status": "FINISHED"})
    time.sleep(RATE_DELAY)
    form = []
    for m in reversed(data.get("matches", [])):
        if len(form) >= 5: break
        ft = (m.get("score") or {}).get("fullTime", {})
        sh, sa = ft.get("home"), ft.get("away")
        if sh is None or sa is None: continue
        is_home = (m.get("homeTeam") or {}).get("id") == team_id
        if is_home: form.append("V" if sh > sa else "D" if sh < sa else "E")
        else:       form.append("V" if sa > sh else "D" if sa < sh else "E")
    while len(form) < 5: form.insert(0, "-")
    return form[-5:]

def fd_get_standings(comp_id, home_id, away_id):
    empty = {"pos": "-", "pts": "-", "p": "-", "sg": "-"}
    data = fd_api_get(f"/competitions/{comp_id}/standings")
    time.sleep(RATE_DELAY)
    table = []
    for s in data.get("standings", []):
        if s.get("type") == "TOTAL": table = s.get("table", []); break
    if not table and data.get("standings"):
        table = data["standings"][0].get("table", [])
    h, a = dict(empty), dict(empty)
    for row in table:
        tid = (row.get("team") or {}).get("id")
        e = {"pos": row.get("position", "-"), "pts": row.get("points", "-"),
             "p": row.get("playedGames", "-"), "sg": row.get("goalDifference", "-")}
        if tid == home_id: h = e
        if tid == away_id: a = e
    return {"home": h, "away": a}

def fd_get_h2h(match_id):
    data = fd_api_get(f"/matches/{match_id}/head2head", {"limit": 5})
    time.sleep(RATE_DELAY)
    h2h = []
    for m in data.get("matches", []):
        mh = (m.get("homeTeam") or {}).get("shortName") or (m.get("homeTeam") or {}).get("name", "?")
        ma = (m.get("awayTeam") or {}).get("shortName") or (m.get("awayTeam") or {}).get("name", "?")
        ft = (m.get("score") or {}).get("fullTime", {})
        sh, sa = ft.get("home"), ft.get("away")
        h2h.append({"date": m.get("utcDate", "")[:10], "home": mh,
                     "score": f"{sh}-{sa}" if sh is not None else "?-?", "away": ma})
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
    except Exception:
        pass
    return "N/A"

def fd_enrich(match):
    hid = match["homeTeam"]["id"]
    aid = match["awayTeam"]["id"]
    cid = match["competition"]["id"]
    mid = match["id"]
    hn = match["homeTeam"].get("shortName") or match["homeTeam"]["name"]
    an = match["awayTeam"].get("shortName") or match["awayTeam"]["name"]
    st = match.get("status", "SCHEDULED")

    log(f"    ↳ Forma: {hn}..."); fh = fd_get_recent_form(hid)
    log(f"    ↳ Forma: {an}..."); fa = fd_get_recent_form(aid)
    log(f"    ↳ Classificação..."); standings = fd_get_standings(cid, hid, aid)
    log(f"    ↳ H2H..."); h2h = fd_get_h2h(mid)
    log(f"    ↳ ClubElo...")
    eh, ea = get_clubelo(hn), get_clubelo(an)
    time.sleep(2)

    if st == "FINISHED":
        sh = match["score"]["fullTime"].get("home", "?")
        sa = match["score"]["fullTime"].get("away", "?")
        info = f"Partida encerrada. Placar final: {sh}-{sa}."
    elif st in ("IN_PLAY", "PAUSED"):
        info = f"Partida em andamento ({match.get('minute', '?')}')."
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

def run_football_data(today):
    """Fonte 1: football-data.org — retorna lista de matches enriquecidos ou None."""
    if not FOOTBALL_API_KEY:
        log("⚠️  FOOTBALL_DATA_API_KEY não configurada. Pulando football-data.org.")
        return None

    log(f"🔑 Key: {'*' * 20}{FOOTBALL_API_KEY[-4:]}")
    log(f"📡 [football-data.org] Buscando partidas de {today}...")
    data = fd_api_get("/matches", {"dateFrom": today, "dateTo": today})
    matches = data.get("matches", [])
    log(f"✅ {len(matches)} partida(s) encontrada(s) via football-data.org")

    if not matches:
        return None

    enriched = []
    for i, match in enumerate(matches):
        hn = match["homeTeam"].get("shortName") or match["homeTeam"]["name"]
        an = match["awayTeam"].get("shortName") or match["awayTeam"]["name"]
        log(f"\n  [{i + 1}/{len(matches)}] {match['competition']['name']}: {hn} x {an}")
        try:
            enriched.append(fd_enrich(match))
        except Exception as e:
            log(f"  ⚠️  Falha no enriquecimento: {e}")
            match.setdefault("inteligencia", {
                "clubelo":     {"home_elo": "N/A", "away_elo": "N/A"},
                "recent_form": {"home": ["-"] * 5, "away": ["-"] * 5},
                "standings":   {"home": {"pos": "-", "pts": "-", "p": "-", "sg": "-"},
                                "away": {"pos": "-", "pts": "-", "p": "-", "sg": "-"}},
                "h2h":  [],
                "stats": {"info": "Dados indisponíveis.", "reliability": "0.0"}
            })
            enriched.append(match)
    return enriched


# ═══════════════════════════════════════════════════
#  THESPORTSDB (fonte secundária — gratuita, sem key)
# ═══════════════════════════════════════════════════
def tsdb_get(endpoint):
    url = f"{TSDB_BASE}{endpoint}"
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            log(f"  ⚠️  TheSportsDB HTTP {r.status_code}")
            return {}
        except Exception as e:
            log(f"  ⚠️  TheSportsDB tentativa {attempt + 1}/3: {e}")
            time.sleep(3)
    return {}

def tsdb_get_team_form(team_id):
    """Últimos 5 resultados de um time via TheSportsDB."""
    if not team_id:
        return ["-"] * 5
    data = tsdb_get(f"/eventslast.php?id={team_id}")
    time.sleep(TSDB_DELAY)
    results = data.get("results") or []
    form = []
    tid = str(team_id)
    for ev in results:
        if len(form) >= 5:
            break
        try:
            sh = int(ev.get("intHomeScore", ""))
            sa = int(ev.get("intAwayScore", ""))
        except (ValueError, TypeError):
            continue
        is_home = str(ev.get("idHomeTeam", "")) == tid
        if is_home:
            form.append("V" if sh > sa else "D" if sh < sa else "E")
        else:
            form.append("V" if sa > sh else "D" if sa < sh else "E")
    while len(form) < 5:
        form.append("-")
    return form[:5]

def tsdb_get_standings(league_id, season):
    """Classificação da liga via TheSportsDB."""
    if not league_id or not season:
        return {}
    data = tsdb_get(f"/lookuptable.php?l={league_id}&s={season}")
    time.sleep(TSDB_DELAY)
    table = data.get("table") or []
    standings = {}
    for row in table:
        tid = str(row.get("idTeam", ""))
        gf = int(row.get("intGoalsFor", 0) or 0)
        ga = int(row.get("intGoalsAgainst", 0) or 0)
        gd = row.get("intGoalDifference")
        if gd is None or gd == "":
            gd = str(gf - ga)
        standings[tid] = {
            "pos": row.get("intRank", "-"),
            "pts": row.get("intPoints", "-"),
            "p":   row.get("intPlayed", "-"),
            "sg":  gd
        }
    return standings

def tsdb_convert_match(ev, standings_cache, form_cache):
    """Converte um evento TheSportsDB para o formato interno do inicio.html."""
    ts = ev.get("strTimestamp") or (ev.get("dateEvent", "") + "T" + (ev.get("strTime") or "12:00:00") + "+00:00")

    status_raw = (ev.get("strStatus") or "").strip()
    status_lower = status_raw.lower()
    fd_status = "SCHEDULED"
    minute = None

    if status_lower in ("in progress", "1h", "2h"):
        fd_status = "IN_PLAY"
    elif status_lower == "ht":
        fd_status = "PAUSED"
    elif status_lower in ("ft", "finished", "match finished", "aet", "pen"):
        fd_status = "FINISHED"
    elif status_lower == "postponed":
        fd_status = "POSTPONED"
    elif status_lower == "cancelled":
        fd_status = "CANCELLED"

    sh = ev.get("intHomeScore")
    sa = ev.get("intAwayScore")
    sh_int = None if sh is None or sh == "" else int(sh)
    sa_int = None if sa is None or sa == "" else int(sa)

    htid = str(ev.get("idHomeTeam", ""))
    atid = str(ev.get("idAwayTeam", ""))
    lid  = str(ev.get("idLeague", ""))

    # Form
    fh = form_cache.get(htid, ["-"] * 5)
    fa = form_cache.get(atid, ["-"] * 5)

    # Standings
    empty_std = {"pos": "-", "pts": "-", "p": "-", "sg": "-"}
    std_table = standings_cache.get(lid, {})
    std_home = std_table.get(htid, empty_std)
    std_away = std_table.get(atid, empty_std)

    # ClubElo
    elo_home = form_cache.get(f"elo_{htid}", "N/A")
    elo_away = form_cache.get(f"elo_{atid}", "N/A")

    home_name = ev.get("strHomeTeam", "?")
    away_name = ev.get("strAwayTeam", "?")

    # Info text
    info_parts = []
    if std_home.get("pos") != "-" and std_away.get("pos") != "-":
        info_parts.append(f"{home_name} em {std_home['pos']}° ({std_home['pts']}pts) vs {away_name} em {std_away['pos']}° ({std_away['pts']}pts).")
    fh_valid = [x for x in fh if x != "-"]
    fa_valid = [x for x in fa if x != "-"]
    if len(fh_valid) >= 3:
        pct = round((fh_valid.count("V") / len(fh_valid)) * 100)
        info_parts.append(f"{home_name}: {pct}% vitórias recentes.")
    if len(fa_valid) >= 3:
        pct = round((fa_valid.count("V") / len(fa_valid)) * 100)
        info_parts.append(f"{away_name}: {pct}% vitórias recentes.")
    info = " ".join(info_parts) if info_parts else f"Dados coletados às {datetime.utcnow().strftime('%H:%M UTC')}."

    return {
        "id":          int(ev.get("idEvent", 0)),
        "utcDate":     ts,
        "status":      fd_status,
        "minute":      minute,
        "venue":       (ev.get("strVenue") or "ESTÁDIO").upper(),
        "competition": {
            "id":   ev.get("idLeague", ""),
            "name": ev.get("strLeague") or "Futebol"
        },
        "homeTeam": {
            "id":        ev.get("idHomeTeam", ""),
            "name":      home_name,
            "shortName": home_name
        },
        "awayTeam": {
            "id":        ev.get("idAwayTeam", ""),
            "name":      away_name,
            "shortName": away_name
        },
        "score": {
            "fullTime": {
                "home": sh_int,
                "away": sa_int
            }
        },
        "inteligencia": {
            "clubelo":     {"home_elo": elo_home, "away_elo": elo_away},
            "recent_form": {"home": fh, "away": fa},
            "standings":   {"home": std_home, "away": std_away},
            "h2h":         [],
            "stats":       {"info": info, "reliability": "7.5"}
        }
    }

TSDB_LEAGUE_IDS = [
    4328, 4329, 4330, 4331, 4332, 4334, 4335, 4336, 4337, 4338,
    4340, 4344, 4346, 4347, 4351, 4355, 4356, 4358, 4359, 4396,
    4480, 4482, 4484, 4485, 4497, 4501, 4504, 4505, 4506, 4507
]

def tsdb_fetch_todays_events(today):
    """
    Busca eventos do dia usando eventsnextleague + eventspastleague
    por liga, filtrando por data. eventsday.php retorna dados de 2014.
    """
    seen = set()
    all_events = []

    for lid in TSDB_LEAGUE_IDS:
        for endpoint in [f"/eventsnextleague.php?id={lid}", f"/eventspastleague.php?id={lid}"]:
            data = tsdb_get(endpoint)
            events = data.get("events") or []
            for ev in events:
                ev_date = ev.get("dateEvent", "")
                ev_id = str(ev.get("idEvent", ""))
                if ev_date == today and ev_id and ev_id not in seen:
                    seen.add(ev_id)
                    all_events.append(ev)
            time.sleep(TSDB_DELAY)

    return all_events

def run_thesportsdb(today):
    """Fonte 2: TheSportsDB — gratuita. Usa eventsnextleague + eventspastleague."""
    log(f"\n📡 [TheSportsDB] Buscando partidas de {today} em {len(TSDB_LEAGUE_IDS)} ligas...")
    events = tsdb_fetch_todays_events(today)
    log(f"✅ {len(events)} partida(s) encontrada(s) via TheSportsDB")

    if not events:
        return None

    # Fase 1: Coletar IDs únicos de times e ligas
    team_ids = set()
    league_seasons = {}
    for ev in events:
        htid = ev.get("idHomeTeam")
        atid = ev.get("idAwayTeam")
        lid  = ev.get("idLeague")
        ssn  = ev.get("strSeason")
        if htid: team_ids.add(str(htid))
        if atid: team_ids.add(str(atid))
        if lid and ssn: league_seasons[str(lid)] = ssn

    # Fase 2: Buscar classificações por liga
    log(f"\n📊 Buscando classificação de {len(league_seasons)} liga(s)...")
    standings_cache = {}
    for lid, ssn in league_seasons.items():
        log(f"    ↳ Liga {lid} (temporada {ssn})...")
        standings_cache[lid] = tsdb_get_standings(lid, ssn)

    # Fase 3: Buscar forma de cada time
    log(f"\n📈 Buscando forma de {len(team_ids)} time(s)...")
    form_cache = {}
    team_list = list(team_ids)
    for i, tid in enumerate(team_list):
        if (i + 1) % 10 == 0 or i == 0:
            log(f"    ↳ Time {i + 1}/{len(team_list)}...")
        form_cache[tid] = tsdb_get_team_form(tid)

    # Fase 4: ClubElo para times (nomes únicos)
    log(f"\n🏆 Buscando ClubElo ratings...")
    team_names = {}
    for ev in events:
        htid = str(ev.get("idHomeTeam", ""))
        atid = str(ev.get("idAwayTeam", ""))
        if htid and htid not in team_names:
            team_names[htid] = ev.get("strHomeTeam", "")
        if atid and atid not in team_names:
            team_names[atid] = ev.get("strAwayTeam", "")

    elo_done = set()
    for tid, name in team_names.items():
        if tid in elo_done or not name:
            continue
        elo = get_clubelo(name)
        form_cache[f"elo_{tid}"] = elo
        elo_done.add(tid)
        if elo != "N/A":
            log(f"    ↳ {name}: ELO {elo}")
        time.sleep(0.3)

    # Fase 5: Converter para formato interno
    log(f"\n🔧 Convertendo {len(events)} evento(s)...")
    matches = []
    for ev in events:
        try:
            matches.append(tsdb_convert_match(ev, standings_cache, form_cache))
        except Exception as e:
            log(f"  ⚠️  Erro convertendo {ev.get('strEvent', '?')}: {e}")
            continue

    return matches


# ═══════════════════════════════════════════════════
#  MAIN — Cascata de fontes
# ═══════════════════════════════════════════════════
def main():
    log("=" * 55)
    log("🔥 QG FUT TRADER — Motor ETL v4 (multi-source, corrigido)")
    today = today_brazil()
    log(f"📅 Data BR: {today}")
    log("=" * 55)

    # ── FONTE 1: football-data.org ──
    matches = run_football_data(today)
    if matches:
        save_output(matches, source="football-data.org")
        log("🏁 A Ferrari está abastecida (football-data.org)!")
        return

    # ── FONTE 2: TheSportsDB ──
    log("\n🔄 Tentando fonte alternativa: TheSportsDB...")
    matches = run_thesportsdb(today)
    if matches:
        save_output(matches, source="thesportsdb.com")
        log("🏁 A Ferrari está abastecida (TheSportsDB)!")
        return

    # ── Nenhuma fonte retornou dados ──
    log("ℹ️  Nenhuma partida encontrada em nenhuma fonte hoje.")
    save_output([], source="empty")
    log("🏁 JSON vazio salvo. O frontend usará fallback.")

if __name__ == "__main__":
    main()
