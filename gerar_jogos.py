#!/usr/bin/env python3
"""
============================================================
 QG FUT TRADER — Motor ETL v6 (Sofascore via Playwright)

 Fonte: Sofascore scheduled-events (200-400 jogos/dia)
 Bypass: Playwright headless Chromium (evita 403)
 Fallback: football-data.org se Sofascore falhar

 v6: Limites ampliados (200 times, 80 torneios),
     H2H implementado, venue extraído,
     browser reutilizado para performance
============================================================
"""

import asyncio, json, os, re, sys, time as _time
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

FOOTBALL_API_KEY  = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
OUTPUT_FILE       = "jogos_de_hoje.json"

# ═══════════════════════════════════════════════════
#  LIMITES DE ENRIQUECIMENTO (v6: ampliados)
# ═══════════════════════════════════════════════════
MAX_TEAMS_FORM    = 200   # v5: 50  → v6: 200
MAX_TOURNAMENTS   = 80    # v5: 20  → v6: 80
MAX_H2H_MATCHES   = 100   # v6: novo — busca H2H dos top jogos
FORM_DELAY        = 0.25  # segundos entre requests de form
STANDINGS_DELAY   = 0.4   # segundos entre requests de standings
H2H_DELAY         = 0.3   # segundos entre requests de H2H


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
#  PLAYWRIGHT HELPER — browser reutilizado
# ═══════════════════════════════════════════════════
async def pw_fetch_json(page, url, timeout=15000):
    """Busca URL via Playwright e retorna JSON parsed. Reutiliza a page."""
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if not resp or resp.status != 200:
            return None
        body = await page.content()
        match = re.search(r'<pre[^>]*>(.*?)</pre>', body, re.DOTALL)
        text = match.group(1) if match else re.sub(r'<[^>]+>', '', body).strip()
        return json.loads(text)
    except Exception:
        return None


# ═══════════════════════════════════════════════════
#  SOFASCORE CONVERT — evento → formato interno
# ═══════════════════════════════════════════════════
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
    elif status_code == 31:
        fd_status = "PAUSED"

    # Placar
    sh = hs.get("current")
    sa = aws.get("current")

    # Liga
    league_name = tourn.get("name") or "Futebol"
    country = cat.get("name", "")

    # Venue (v6: extrair do evento)
    venue_data = ev.get("venue", {})
    venue_name = ""
    if isinstance(venue_data, dict):
        venue_name = venue_data.get("stadium", {}).get("name", "") if venue_data.get("stadium") else ""
        if not venue_name:
            venue_name = venue_data.get("city", {}).get("name", "") if venue_data.get("city") else ""
    elif isinstance(venue_data, str):
        venue_name = venue_data

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
    info = " ".join(info_parts) if info_parts else "Dados Sofascore."

    return {
        "id":          ev.get("id", 0),
        "utcDate":     utc_dt.isoformat(),
        "status":      fd_status,
        "minute":      minute,
        "venue":       venue_name,
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
            "homeTeamId":   ht.get("id"),
            "awayTeamId":   at.get("id"),
            "tournamentId": tourn.get("uniqueTournament", {}).get("id"),
            "seasonYear":   ev.get("season", {}).get("year", ""),
            "slug":         ev.get("slug", ""),
            "eventId":      ev.get("id", 0),
            "customId":     ev.get("customId", "")
        }
    }


# ═══════════════════════════════════════════════════
#  ENRIQUECIMENTO BATCH (v6: ampliado + H2H)
# ═══════════════════════════════════════════════════
async def sofascore_enrich_batch(matches, date_str):
    """Enriquece matches com form, standings e H2H via Sofascore."""
    log("  Iniciando enriquecimento v6...")

    # Coletar IDs únicos
    team_ids = set()
    tournament_season = {}
    event_ids_for_h2h = []

    for m in matches:
        meta = m.get("_sofascore", {})
        hid = meta.get("homeTeamId")
        aid = meta.get("awayTeamId")
        tid = meta.get("tournamentId")
        sy = meta.get("seasonYear")
        eid = meta.get("eventId")
        if hid: team_ids.add(hid)
        if aid: team_ids.add(aid)
        if tid and sy:
            tournament_season[tid] = sy
        if eid:
            event_ids_for_h2h.append(eid)

    form_cache = {}
    standings_cache = {}
    h2h_cache = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # ───────────────────────────────────────────
        #  STANDINGS — top 80 torneios
        # ───────────────────────────────────────────
        tourn_list = list(tournament_season.items())[:MAX_TOURNAMENTS]
        log(f"  Buscando classificacao de {len(tourn_list)} torneio(s)...")
        standings_ok = 0

        for tid, sy in tourn_list:
            try:
                seasons_data = await pw_fetch_json(
                    page,
                    f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/seasons"
                )
                if not seasons_data:
                    await asyncio.sleep(STANDINGS_DELAY)
                    continue

                seasons = seasons_data.get("seasons", [])
                if not seasons:
                    await asyncio.sleep(STANDINGS_DELAY)
                    continue

                season_id = seasons[0].get("id")
                if not season_id:
                    await asyncio.sleep(STANDINGS_DELAY)
                    continue

                st_data = await pw_fetch_json(
                    page,
                    f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/{season_id}/standings/total"
                )
                if st_data:
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
                                "sg":  row.get("goalDifference",
                                           row.get("scoresFor", 0) - row.get("scoresAgainst", 0))
                            }
                    standings_ok += 1

                await asyncio.sleep(STANDINGS_DELAY)
            except Exception as e:
                log(f"    standings {tid}: {e}")

        log(f"  Standings: {standings_ok}/{len(tourn_list)} torneios OK, {len(standings_cache)} times mapeados")

        # ───────────────────────────────────────────
        #  FORM — top 200 times
        # ───────────────────────────────────────────
        team_list = list(team_ids)[:MAX_TEAMS_FORM]
        log(f"  Buscando forma de {len(team_list)} time(s)...")
        form_ok = 0

        for tid in team_list:
            try:
                events_data = await pw_fetch_json(
                    page,
                    f"https://api.sofascore.com/api/v1/team/{tid}/events/last/0",
                    timeout=10000
                )
                if not events_data:
                    await asyncio.sleep(FORM_DELAY)
                    continue

                events = events_data.get("events", [])
                form = []
                for ev in reversed(events[-10:]):
                    if len(form) >= 5:
                        break
                    st = ev.get("status", {}).get("type", "")
                    if st != "finished":
                        continue
                    ehs = ev.get("homeScore", {}).get("current")
                    eas = ev.get("awayScore", {}).get("current")
                    if ehs is None or eas is None:
                        continue
                    is_home = ev.get("homeTeam", {}).get("id") == tid
                    if is_home:
                        form.append("V" if ehs > eas else "D" if ehs < eas else "E")
                    else:
                        form.append("V" if eas > ehs else "D" if eas < ehs else "E")

                while len(form) < 5:
                    form.append("-")
                form_cache[tid] = form[:5]
                form_ok += 1
                await asyncio.sleep(FORM_DELAY)
            except Exception:
                pass

        log(f"  Form: {form_ok}/{len(team_list)} times OK")

        # ───────────────────────────────────────────
        #  H2H — top 100 jogos (v6: NOVO)
        # ───────────────────────────────────────────
        h2h_list = event_ids_for_h2h[:MAX_H2H_MATCHES]
        log(f"  Buscando H2H de {len(h2h_list)} jogo(s)...")
        h2h_ok = 0

        for eid in h2h_list:
            try:
                h2h_data = await pw_fetch_json(
                    page,
                    f"https://api.sofascore.com/api/v1/event/{eid}/h2h",
                    timeout=10000
                )
                if not h2h_data:
                    await asyncio.sleep(H2H_DELAY)
                    continue

                # O endpoint retorna teamDuel e managerDuel
                team_duel = h2h_data.get("teamDuel", [])
                if not team_duel and isinstance(h2h_data, list):
                    team_duel = h2h_data

                # Pode vir como objeto com lastEvents
                last_events = []

                # Tentar diferentes formatos de resposta
                if isinstance(team_duel, dict):
                    last_events = team_duel.get("lastEvents", [])
                elif isinstance(h2h_data, dict):
                    # Formato alternativo: h2h_data pode ter várias seções
                    for key in ["teamDuel", "managerDuel"]:
                        section = h2h_data.get(key)
                        if isinstance(section, dict) and "lastEvents" in section:
                            last_events = section["lastEvents"]
                            break
                    # Outro formato: diretamente em events
                    if not last_events:
                        last_events = h2h_data.get("events", [])

                h2h_entries = []
                for ev in last_events[:5]:
                    try:
                        ht_name = ev.get("homeTeam", {}).get("shortName") or ev.get("homeTeam", {}).get("name", "?")
                        at_name = ev.get("awayTeam", {}).get("shortName") or ev.get("awayTeam", {}).get("name", "?")
                        hs_val = ev.get("homeScore", {}).get("current")
                        as_val = ev.get("awayScore", {}).get("current")
                        ts_val = ev.get("startTimestamp", 0)

                        if hs_val is None or as_val is None:
                            continue

                        # Formatar data
                        ev_date = datetime.fromtimestamp(ts_val, tz=timezone.utc)
                        meses = {1:"JAN",2:"FEV",3:"MAR",4:"ABR",5:"MAI",6:"JUN",
                                 7:"JUL",8:"AGO",9:"SET",10:"OUT",11:"NOV",12:"DEZ"}
                        date_str_fmt = f"{ev_date.day:02d} {meses.get(ev_date.month,'?')} {str(ev_date.year)[2:]}"

                        h2h_entries.append({
                            "date": date_str_fmt,
                            "home": ht_name,
                            "score": f"{hs_val} - {as_val}",
                            "away": at_name
                        })
                    except Exception:
                        continue

                if h2h_entries:
                    h2h_cache[eid] = h2h_entries
                    h2h_ok += 1

                await asyncio.sleep(H2H_DELAY)
            except Exception as e:
                log(f"    h2h {eid}: {e}")

        log(f"  H2H: {h2h_ok}/{len(h2h_list)} jogos com historico")

        await browser.close()

    # ───────────────────────────────────────────
    #  MERGE — combinar tudo nos matches
    # ───────────────────────────────────────────
    log("  Merging enrichment data...")
    enriched_count = 0

    for m in matches:
        meta = m.get("_sofascore", {})
        hid = meta.get("homeTeamId")
        aid = meta.get("awayTeamId")
        eid = meta.get("eventId")

        intl = m.get("inteligencia", {})

        # Form
        if hid in form_cache:
            intl["recent_form"]["home"] = form_cache[hid]
        if aid in form_cache:
            intl["recent_form"]["away"] = form_cache[aid]

        # Standings
        if hid in standings_cache:
            intl["standings"]["home"] = standings_cache[hid]
            enriched_count += 1
        if aid in standings_cache:
            intl["standings"]["away"] = standings_cache[aid]

        # H2H (v6: novo)
        if eid in h2h_cache:
            intl["h2h"] = h2h_cache[eid]

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

    log(f"  Enriquecimento final: {len(form_cache)} forms, {len(standings_cache)} standings, {len(h2h_cache)} h2h")
    return matches


# ═══════════════════════════════════════════════════
#  SOFASCORE — coleta multi-dia (ontem + hoje + amanha)
# ═══════════════════════════════════════════════════
async def run_sofascore(today):
    """Fonte principal: Sofascore via Playwright. Busca 3 dias."""
    log(f"  [Sofascore] Buscando jogos (3 dias centrados em {today})...")

    # Calcular ontem e amanha
    today_dt = datetime.strptime(today, "%Y-%m-%d")
    yesterday = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (today_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    all_matches = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for date_str in [yesterday, today, tomorrow]:
            try:
                url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
                data = await pw_fetch_json(page, url, timeout=30000)
                if data:
                    events = data.get("events", [])
                    log(f"  {date_str}: {len(events)} evento(s)")
                    for ev in events:
                        try:
                            all_matches.append(sofascore_convert(ev))
                        except Exception as e:
                            log(f"  Erro convertendo: {e}")
                else:
                    log(f"  {date_str}: sem dados")
            except Exception as e:
                log(f"  {date_str}: erro - {e}")

        await browser.close()

    if not all_matches:
        log("  Sofascore retornou vazio em todos os dias.")
        return None

    log(f"  Total: {len(all_matches)} partida(s) convertida(s)")

    # Enriquecer com standings, form e H2H
    try:
        all_matches = await sofascore_enrich_batch(all_matches, today)
    except Exception as e:
        log(f"  Enriquecimento falhou (dados basicos mantidos): {e}")

    return all_matches


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
    log("QG FUT TRADER — Motor ETL v6 (Sofascore + Playwright)")
    today = today_brazil()
    log(f"Data BR: {today}")
    log("=" * 55)

    # Fonte 1: Sofascore
    matches = await run_sofascore(today)
    if matches:
        save_output(matches, source="sofascore.com")
        log(f"Ferrari abastecida! {len(matches)} jogos via Sofascore.")
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
