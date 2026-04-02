#!/usr/bin/env python3
"""
============================================================
 QG FUT TRADER — Motor ETL de Combustível Real
 Gera jogos_de_hoje.json com dados enriquecidos
 
 Fontes:
   - football-data.org  → partidas, placar, status
   - football-data.org  → forma recente, classificação, H2H
   - api.clubelo.com    → ratings Elo (sem chave, API pública)
============================================================
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# ──────────────────────────────────────────────
#  CONFIGURAÇÃO
# ──────────────────────────────────────────────
FOOTBALL_API_KEY  = os.environ.get("FOOTBALL_DATA_API_KEY", "")
FOOTBALL_API_BASE = "https://api.football-data.org/v4"
OUTPUT_FILE       = "jogos_de_hoje.json"

HEADERS_FOOTBALL = {
    "X-Auth-Token": FOOTBALL_API_KEY,
}

# Delay entre chamadas para respeitar o rate limit (10 req/min no tier free)
RATE_DELAY = 6  # segundos


# ──────────────────────────────────────────────
#  UTILITÁRIOS
# ──────────────────────────────────────────────
def today_brazil() -> str:
    """Retorna YYYY-MM-DD no fuso de Brasília (UTC-3)."""
    br_tz = timezone(timedelta(hours=-3))
    return datetime.now(br_tz).strftime("%Y-%m-%d")


def safe_get(url: str, params: dict = None, retries: int = 3) -> dict:
    """GET com retry e tratamento de rate-limit."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS_FOOTBALL, params=params, timeout=15)
            if r.status_code == 429:
                print(f"  ⏳ Rate limit atingido, aguardando 60s...")
                time.sleep(60)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"  ⚠️  Erro na tentativa {attempt+1}: {e}")
            time.sleep(5)
    return {}


# ──────────────────────────────────────────────
#  1. PARTIDAS DO DIA
# ──────────────────────────────────────────────
def fetch_today_matches() -> list:
    """Busca todas as partidas do dia pelo fuso brasileiro."""
    today = today_brazil()
    print(f"📅 Buscando partidas para: {today}")
    data = safe_get(f"{FOOTBALL_API_BASE}/matches", {"dateFrom": today, "dateTo": today})
    matches = data.get("matches", [])
    print(f"✅ {len(matches)} partidas encontradas.")
    return matches


# ──────────────────────────────────────────────
#  2. FORMA RECENTE  (últimas 5 partidas)
# ──────────────────────────────────────────────
def get_recent_form(team_id: int) -> list:
    """Retorna lista com V/E/D das últimas 5 partidas do time."""
    data = safe_get(
        f"{FOOTBALL_API_BASE}/teams/{team_id}/matches",
        {"limit": 10, "status": "FINISHED"}
    )
    time.sleep(RATE_DELAY)

    matches = data.get("matches", [])
    form = []

    for m in reversed(matches):
        if len(form) >= 5:
            break
        # Verifica se o jogo já tem placar
        sh = m.get("score", {}).get("fullTime", {}).get("home")
        sa = m.get("score", {}).get("fullTime", {}).get("away")
        if sh is None or sa is None:
            continue

        is_home = m["homeTeam"]["id"] == team_id
        if is_home:
            if sh > sa:   form.append("V")
            elif sh < sa: form.append("D")
            else:          form.append("E")
        else:
            if sa > sh:   form.append("V")
            elif sa < sh: form.append("D")
            else:          form.append("E")

    # Preenche até 5 se necessário
    while len(form) < 5:
        form.insert(0, "-")

    return form[-5:]


# ──────────────────────────────────────────────
#  3. CLASSIFICAÇÃO  (posição, pontos, jogos, SG)
# ──────────────────────────────────────────────
def get_standings(competition_id: int, home_team_id: int, away_team_id: int) -> dict:
    """Retorna dados de classificação dos dois times."""
    empty = {"pos": "-", "pts": "-", "p": "-", "sg": "-"}
    default = {"home": dict(empty), "away": dict(empty)}

    data = safe_get(f"{FOOTBALL_API_BASE}/competitions/{competition_id}/standings")
    time.sleep(RATE_DELAY)

    standings_list = data.get("standings", [])
    if not standings_list:
        return default

    # Prefere tabela TOTAL; caso não exista, usa a primeira
    table = next(
        (s.get("table", []) for s in standings_list if s.get("type") == "TOTAL"),
        standings_list[0].get("table", [])
    )

    home_data = dict(empty)
    away_data = dict(empty)

    for row in table:
        t_id = row.get("team", {}).get("id")
        entry = {
            "pos": row.get("position", "-"),
            "pts": row.get("points", "-"),
            "p":   row.get("playedGames", "-"),
            "sg":  row.get("goalDifference", "-")
        }
        if t_id == home_team_id:
            home_data = entry
        if t_id == away_team_id:
            away_data = entry

    return {"home": home_data, "away": away_data}


# ──────────────────────────────────────────────
#  4. CONFRONTOS DIRETOS  (H2H)
# ──────────────────────────────────────────────
def get_h2h(match_id: int, home_name: str, away_name: str) -> list:
    """Retorna lista de últimos 5 confrontos diretos."""
    data = safe_get(
        f"{FOOTBALL_API_BASE}/matches/{match_id}/head2head",
        {"limit": 5}
    )
    time.sleep(RATE_DELAY)

    h2h = []
    for m in data.get("matches", []):
        date_str = m.get("utcDate", "")[:10]
        mh = m["homeTeam"].get("shortName") or m["homeTeam"]["name"]
        ma = m["awayTeam"].get("shortName") or m["awayTeam"]["name"]
        sh = m["score"]["fullTime"].get("home")
        sa = m["score"]["fullTime"].get("away")
        score = f"{sh}-{sa}" if (sh is not None and sa is not None) else "?-?"
        h2h.append({"date": date_str, "home": mh, "score": score, "away": ma})

    return h2h


# ──────────────────────────────────────────────
#  5. CLUBELO  (API pública, sem chave)
# ──────────────────────────────────────────────
def get_club_elo(team_name: str) -> str:
    """Busca rating Elo atual do clube em api.clubelo.com."""
    # ClubElo aceita o nome do clube sem espaços, capitalizado
    slug = team_name.replace(" ", "").replace("-", "")
    url  = f"http://api.clubelo.com/{slug}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.text.strip():
            lines = [l for l in r.text.strip().split("\n") if l and not l.startswith("Rank")]
            if lines:
                last = lines[-1].split(",")
                if len(last) >= 5:
                    return str(round(float(last[4])))
    except Exception:
        pass
    return "N/A"


# ──────────────────────────────────────────────
#  6. ENRIQUECIMENTO COMPLETO  por partida
# ──────────────────────────────────────────────
def enrich_match(match: dict) -> dict:
    """Adiciona bloco `inteligencia` à partida."""
    home_id   = match["homeTeam"]["id"]
    away_id   = match["awayTeam"]["id"]
    comp_id   = match["competition"]["id"]
    match_id  = match["id"]

    home_name = match["homeTeam"].get("shortName") or match["homeTeam"]["name"]
    away_name = match["awayTeam"].get("shortName") or match["awayTeam"]["name"]

    print(f"    🔄 Forma recente → {home_name}...")
    form_home = get_recent_form(home_id)

    print(f"    🔄 Forma recente → {away_name}...")
    form_away = get_recent_form(away_id)

    print(f"    🔄 Classificação...")
    standings = get_standings(comp_id, home_id, away_id)

    print(f"    🔄 H2H...")
    h2h = get_h2h(match_id, home_name, away_name)

    print(f"    🔄 ClubElo → {home_name} & {away_name}...")
    elo_home = get_club_elo(home_name)
    elo_away = get_club_elo(away_name)
    time.sleep(2)  # Pequeno delay para ClubElo

    # Monta bloco stats com contexto
    status = match.get("status", "SCHEDULED")
    if status == "FINISHED":
        sh = match["score"]["fullTime"].get("home", "?")
        sa = match["score"]["fullTime"].get("away", "?")
        info_text = f"Partida encerrada. Placar final: {sh}-{sa}."
    elif status in ("IN_PLAY", "PAUSED"):
        minute = match.get("minute", "?")
        info_text = f"Partida em andamento ({minute}')."
    else:
        info_text = f"Jogo agendado. Dados coletados às {datetime.utcnow().strftime('%H:%M UTC')}."

    match["inteligencia"] = {
        "clubelo":     {"home_elo": elo_home, "away_elo": elo_away},
        "recent_form": {"home": form_home, "away": form_away},
        "standings":   standings,
        "h2h":         h2h,
        "stats": {
            "info":        info_text,
            "reliability": "8.5"
        }
    }

    return match


# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────
def main():
    if not FOOTBALL_API_KEY:
        print("❌ FOOTBALL_DATA_API_KEY não configurada!")
        print("   Configure o secret no GitHub: Settings → Secrets → Actions")
        sys.exit(1)

    print("=" * 55)
    print("  🔥 QG FUT TRADER — Motor ETL iniciado")
    print(f"  🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    # 1. Busca partidas
    matches = fetch_today_matches()
    if not matches:
        print("ℹ️  Nenhuma partida hoje. Gerando JSON vazio.")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump({"matches": []}, f, ensure_ascii=False, indent=2)
        return

    # 2. Enriquece cada partida
    enriched = []
    total = len(matches)
    for i, match in enumerate(matches):
        home = match["homeTeam"].get("shortName") or match["homeTeam"]["name"]
        away = match["awayTeam"].get("shortName") or match["awayTeam"]["name"]
        comp = match["competition"]["name"]
        print(f"\n  [{i+1}/{total}] {comp}: {home} x {away}")

        try:
            enriched.append(enrich_match(match))
        except Exception as e:
            print(f"  ⚠️  Erro no enriquecimento: {e}. Usando dados básicos.")
            # Garante que o campo inteligencia existe mesmo sem enriquecimento
            if "inteligencia" not in match:
                match["inteligencia"] = {
                    "clubelo":     {"home_elo": "N/A", "away_elo": "N/A"},
                    "recent_form": {"home": ["-","-","-","-","-"], "away": ["-","-","-","-","-"]},
                    "standings":   {
                        "home": {"pos": "-", "pts": "-", "p": "-", "sg": "-"},
                        "away": {"pos": "-", "pts": "-", "p": "-", "sg": "-"}
                    },
                    "h2h":  [],
                    "stats": {"info": "Dados indisponíveis temporariamente.", "reliability": "0.0"}
                }
            enriched.append(match)

    # 3. Salva JSON
    output = {"matches": enriched, "_gerado_em": datetime.utcnow().isoformat() + "Z"}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 55}")
    print(f"  ✅ {OUTPUT_FILE} salvo com {len(enriched)} partidas!")
    print(f"  🏁 Pronto para o jogo.")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
