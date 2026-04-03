#!/usr/bin/env python3
"""
============================================================
 QG FUT TRADER — Motor ETL v5 (Sofascore via Playwright)

 Fonte: Sofascore scheduled-events (200-400 jogos/dia)
 Bypass: Playwright headless Chromium (evita 403)
 Fallback: football-data.org se Sofascore falhar

 Output: jogos_de_hoje.json no formato do inicio.html
============================================================
"""

import asyncio, json, os, re, sys, time as _time
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

FOOTBALL_API_KEY  = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
OUTPUT_FILE       = "jogos_de_hoje.json"

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
    log(f"  {OUTPUT_FILE} salvo — {len(matches)} partida(s) via {source}")


# ═══════════════════════════════════════════════════
#  SOFASCORE via Playwright
# ═══════════════════════════════════════════════════
async def sofascore_fetch(url):
    """Busca URL via Playwright headless Chromium (bypass 403)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if resp.status != 200:
            await browser.close()
            return None
        body = await page.content()
        await browser.close()

        # Extrai JSON do body HTML
        match = re.search(r'<pre[^>]*>(.*?)</pre>', body, re.DOTALL)
        text = match.group(1) if match else re.sub(r'<[^>]+>', '', body).strip()
        return json.loads(text)


def sofascore_convert(ev):
    """Converte evento Sofascore para formato interno do inicio.html."""
    ht = ev.get("homeTeam", {})
    at = ev.get("awayTeam", {})
    st = ev.get("status", {})
    hs = ev.get("homeScore", {})
    aws = ev.get("awayScore", {})
    tourn = ev.get("tournament", {})
    cat = tourn.get("category", {})
    ts = ev.get("startTimestamp", 0)

    # Horário BRT
    utc_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    brt = utc_dt.astimezone(timezone(timedelta(hours=-3)))
    horario = brt.strftime("%H:%M")

    # Status
    status_type = (st.get("type") or "").lower()
    status_code = st.get("code", 0)
    fd_status = "SCHEDULED"
    minute = None

    if status_type == "inprogress":
        fd_status = "IN_PLAY"
        minute = st.get("description", "")
    elif status_type == "finished":
        fd_status = "FINISHED"
    elif status_type == "canceled":
        fd_status = "CANCELLED"
    elif status_type == "postponed":
        fd_status = "POSTPONED"
    elif status_code == 31:  # Halftime
        fd_status = "PAUSED"

    # Placar
    sh = hs.get("current")
    sa = aws.get("current")

    # Liga
    league_name = tourn.get("name") or "Futebol"
    country = cat.get("name", "")
    if country and country.lower() not in league_name.lower():
        league_name = f"{league_name}"

    # Round info
    round_info = ev.get("roundInfo", {})
    round_name = round_info.get("name") or ""
    round_num = round_info.get("round")

    # Info text
    info_parts = []
    if round_name:
        info_parts.append(f"{round_name}.")
    elif round_num:
        info_parts.append(f"Rodada {round_num}.")
    if country:
        info_parts.append(f"Pais: {country}.")
    info = " ".join(info_parts) if info_parts else f"Dados Sofascore."

    return {
        "id":          ev.get("id", 0),
        "utcDate":     utc_dt.isoformat(),
        "status":      fd_status,
        "minute":      minute,
        "venue":       "",
        "competition": {
            "id":   tourn.get("uniqueTournament", {}).get("id", ""),
            "name": league_name
        },
        "homeTeam": {
            "id":        ht.get("id", ""),
            "name":      ht.get("name", "?"),
            "shortName": ht.get("shortName") or ht.get("name", "?")
        },
        "awayTeam": {
            "id":        at.get("id", ""),
            "name":      at.get("name", "?"),
            "shortName": at.get("shortName") or at.get("name", "?")
        },
        "score": {
            "fullTime": {
                "home": sh,
                "away": sa
            }
        },
        "inteligencia": {
            "clubelo":     {"home_elo": "N/A", "away_elo": "N/A"},
            "recent_form": {"home": ["-"] * 5, "away": ["-"] * 5},
            "standings":   {
                "home": {"pos": "-", "pts": "-", "p": "-", "sg": "-"},
                "away": {"pos": "-", "pts": "-", "p": "-", "sg": "-"}
            },
            "h2h":  [],
            "stats": {"info": info, "reliability": "8.0"}
        },
        "_sofascore": {
            "homeTeamId": ht.get("id"),
            "awayTeamId": at.get("id"),
            "tournamentId": tourn.get("uniqueTournament", {}).get("id"),
            "seasonYear": ev.get("season", {}).get("year", ""),
            "slug": ev.get("slug", "")
        }
    }


async def sofascore_enrich_batch(matches, date_str):
    """Enriquece matches com form e standings via Sofascore (batch)."""
    log("  Buscando dados de enriquecimento...")

    # Coletar IDs de times e torneios unicos
    team_ids = set()
    tournament_season = {}
    for m in matches:
        meta = m.get("_sofascore", {})
        hid = meta.get("homeTeamId")
        aid = meta.get("awayTeamId")
        tid = meta.get("tournamentId")
        sy = meta.get("seasonYear")
        if hid: team_ids.add(hid)
        if aid: team_ids.add(aid)
        if tid and sy:
            tournament_season[tid] = sy

    form_cache = {}
    standings_cache = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Standings por torneio (top 20 torneios por volume)
        tourn_list = list(tournament_season.items())[:20]
        log(f"  Buscando classificacao de {len(tourn_list)} torneio(s)...")
        for tid, sy in tourn_list:
            try:
                # Buscar seasons para achar o season ID
                resp = await page.goto(
                    f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/seasons",
                    wait_until="domcontentloaded", timeout=15000
                )
                if resp.status == 200:
                    body = await page.content()
                    match = re.search(r'<pre[^>]*>(.*?)</pre>', body, re.DOTALL)
                    text = match.group(1) if match else re.sub(r'<[^>]+>', '', body).strip()
                    seasons_data = json.loads(text)
                    seasons = seasons_data.get("seasons", [])
                    if seasons:
                        season_id = seasons[0].get("id")
                        if season_id:
                            resp2 = await page.goto(
                                f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/{season_id}/standings/total",
                                wait_until="domcontentloaded", timeout=15000
                            )
                            if resp2.status == 200:
                                body2 = await page.content()
                                m2 = re.search(r'<pre[^>]*>(.*?)</pre>', body2, re.DOTALL)
                                t2 = m2.group(1) if m2 else re.sub(r'<[^>]+>', '', body2).strip()
                                st_data = json.loads(t2)
                                rows = []
                                for group in st_data.get("standings", []):
                                    rows.extend(group.get("rows", []))
                                for row in rows:
                                    team = row.get("team", {})
                                    team_id = team.get("id")
                                    if team_id:
                                        standings_cache[team_id] = {
                                            "pos": row.get("position", "-"),
                                            "pts": row.get("points", "-"),
                                            "p":   row.get("matches", "-"),
                                            "sg":  row.get("goalDifference", row.get("scoresFor", 0) - row.get("scoresAgainst", 0))
                                        }
                await asyncio.sleep(0.5)
            except Exception as e:
                log(f"    standings {tid}: {e}")

        # Form por time (top 50 times, batch)
        team_list = list(team_ids)[:50]
        log(f"  Buscando forma de {len(team_list)} time(s)...")
        for i, tid in enumerate(team_list):
            try:
                resp = await page.goto(
                    f"https://api.sofascore.com/api/v1/team/{tid}/events/last/0",
                    wait_until="domcontentloaded", timeout=10000
                )
                if resp.status == 200:
                    body = await page.content()
                    match = re.search(r'<pre[^>]*>(.*?)</pre>', body, re.DOTALL)
                    text = match.group(1) if match else re.sub(r'<[^>]+>', '', body).strip()
                    events_data = json.loads(text)
                    events = events_data.get("events", [])

                    form = []
                    for ev in reversed(events[-10:]):
                        if len(form) >= 5: break
                        st = ev.get("status", {}).get("type", "")
                        if st != "finished": continue
                        ehs = ev.get("homeScore", {}).get("current")
                        eas = ev.get("awayScore", {}).get("current")
                        if ehs is None or eas is None: continue
                        is_home = ev.get("homeTeam", {}).get("id") == tid
                        if is_home:
                            form.append("V" if ehs > eas else "D" if ehs < eas else "E")
                        else:
                            form.append("V" if eas > ehs else "D" if eas < ehs else "E")

                    while len(form) < 5: form.append("-")
                    form_cache[tid] = form[:5]
                await asyncio.sleep(0.3)
            except Exception:
                pass

        await browser.close()

    # Merge enrichment
    enriched_count = 0
    for m in matches:
        meta = m.get("_sofascore", {})
        hid = meta.get("homeTeamId")
        aid = meta.get("awayTeamId")

        intl = m.get("inteligencia", {})

        if hid in form_cache:
            intl["recent_form"]["home"] = form_cache[hid]
        if aid in form_cache:
            intl["recent_form"]["away"] = form_cache[aid]

        empty_std = {"pos": "-", "pts": "-", "p": "-", "sg": "-"}
        if hid in standings_cache:
            intl["standings"]["home"] = standings_cache[hid]
            enriched_count += 1
        if aid in standings_cache:
            intl["standings"]["away"] = standings_cache[aid]

        # Update info text
        sh = intl["standings"]["home"]
        sa = intl["standings"]["away"]
        parts = []
        if sh.get("pos") != "-" and sa.get("pos") != "-":
            hn = m["homeTeam"]["shortName"]
            an = m["awayTeam"]["shortName"]
            parts.append(f"{hn} em {sh['pos']}o ({sh['pts']}pts) vs {an} em {sa['pos']}o ({sa['pts']}pts).")
        fh = [x for x in intl["recent_form"]["home"] if x != "-"]
        fa = [x for x in intl["recent_form"]["away"] if x != "-"]
        if len(fh) >= 3:
            pct = round((fh.count("V") / len(fh)) * 100)
            parts.append(f"{m['homeTeam']['shortName']}: {pct}% vitorias recentes.")
        if len(fa) >= 3:
            pct = round((fa.count("V") / len(fa)) * 100)
            parts.append(f"{m['awayTeam']['shortName']}: {pct}% vitorias recentes.")
        if parts:
            intl["stats"]["info"] = " ".join(parts)
            intl["stats"]["reliability"] = "8.5"

    log(f"  Enriquecimento: {len(form_cache)} forms, {len(standings_cache)} standings")
    return matches


async def run_sofascore(today):
    """Fonte principal: Sofascore via Playwright."""
    log(f"  [Sofascore] Buscando jogos de {today}...")

    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}"
    data = await sofascore_fetch(url)

    if not data:
        log("  Sofascore retornou vazio ou erro.")
        return None

    events = data.get("events", [])
    log(f"  {len(events)} evento(s) encontrado(s) via Sofascore")

    if not events:
        return None

    # Converter todos os eventos
    matches = []
    for ev in events:
        try:
            matches.append(sofascore_convert(ev))
        except Exception as e:
            log(f"  Erro convertendo: {e}")

    log(f"  {len(matches)} partida(s) convertida(s)")

    # Enriquecer com standings e form (top times/torneios)
    try:
        matches = await sofascore_enrich_batch(matches, today)
    except Exception as e:
        log(f"  Enriquecimento falhou (dados basicos mantidos): {e}")

    return matches


# ═══════════════════════════════════════════════════
#  FOOTBALL-DATA.ORG (fallback)
# ═══════════════════════════════════════════════════
def fd_api_get(endpoint, params=None):
    import requests
    url = f"https://api.football-data.org/v4{endpoint}"
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"X-Auth-Token": FOOTBALL_API_KEY},
                             params=params, timeout=20)
            if r.status_code == 429:
                _time.sleep(int(r.headers.get("X-RequestCounter-Reset", 60)) + 2)
                continue
            if r.status_code in (403, 401, 404):
                return {}
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log(f"  fd_api tentativa {attempt+1}: {e}")
            _time.sleep(5)
    return {}

def run_football_data(today):
    if not FOOTBALL_API_KEY:
        return None
    log(f"  [football-data.org] Buscando partidas de {today}...")
    data = fd_api_get("/matches", {"dateFrom": today, "dateTo": today})
    matches = data.get("matches", [])
    log(f"  {len(matches)} partida(s) via football-data.org")
    if not matches:
        return None
    # Converter para formato minimo (sem enriquecimento completo)
    result = []
    for m in matches:
        m.setdefault("inteligencia", {
            "clubelo": {"home_elo": "N/A", "away_elo": "N/A"},
            "recent_form": {"home": ["-"]*5, "away": ["-"]*5},
            "standings": {"home": {"pos":"-","pts":"-","p":"-","sg":"-"},
                          "away": {"pos":"-","pts":"-","p":"-","sg":"-"}},
            "h2h": [],
            "stats": {"info": "Dados football-data.org.", "reliability": "7.0"}
        })
        result.append(m)
    return result


# ═══════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════
async def async_main():
    log("=" * 55)
    log("QG FUT TRADER — Motor ETL v5 (Sofascore + Playwright)")
    today = today_brazil()
    log(f"Data BR: {today}")
    log("=" * 55)

    # Fonte 1: Sofascore
    matches = await run_sofascore(today)
    if matches:
        save_output(matches, source="sofascore.com")
        log(f"A Ferrari esta abastecida! {len(matches)} jogos via Sofascore.")
        return

    # Fonte 2: football-data.org
    log("\nTentando fallback: football-data.org...")
    matches = run_football_data(today)
    if matches:
        save_output(matches, source="football-data.org")
        log(f"Fallback OK: {len(matches)} jogos via football-data.org.")
        return

    # Nenhuma fonte
    log("Nenhuma partida encontrada. JSON vazio salvo.")
    save_output([], source="empty")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
