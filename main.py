import os
import asyncio
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import pandas as pd
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

elo_cache = None
elo_lock = asyncio.Lock()

# Disfarce para a ESPN não bloquear o Render
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

async def carregar_clubelo_async():
    global elo_cache
    async with elo_lock:
        if elo_cache is not None: return 
        try:
            url = "http://api.clubelo.com/api/ranking"
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, timeout=15.0)
                if response.status_code == 200:
                    df = pd.read_csv(io.StringIO(response.text))
                    elo_cache = df[['Club', 'Elo']].set_index('Club')
        except:
            elo_cache = pd.DataFrame() 

@app.get("/jogos")
async def buscar_jogos():
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/scorepanel"
        async with httpx.AsyncClient(follow_redirects=True, headers=HEADERS) as client:
            response = await client.get(url, timeout=15.0)
            data = response.json()
            
        jogos = []
        for league in data.get('scores', []):
            l_name = league.get('leagues', [{}])[0].get('name', 'Geral')
            for event in league.get('events', []):
                try:
                    comp = event.get('competitions', [{}])[0]
                    home = next((t['team']['displayName'] for t in comp.get('competitors', []) if t.get('homeAway') == 'home'), "Casa")
                    away = next((t['team']['displayName'] for t in comp.get('competitors', []) if t.get('homeAway') == 'away'), "Fora")
                    status_short = comp.get('status', {}).get('type', {}).get('shortDetail', '--:--')
                    venue = comp.get('venue', {}).get('fullName', 'Estádio não informado')
                    
                    jogos.append({
                        "id": event['id'], 
                        "home": home, 
                        "away": away, 
                        "league": l_name,
                        "score": status_short,
                        "time": status_short,
                        "venue": venue
                    })
                except: continue 
        return {"sucesso": True, "dados": jogos}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

@app.get("/detalhes/{id}")
async def buscar_detalhes(id: str):
    url_resumo = f"https://site.api.espn.com/apis/site/v2/sports/soccer/summary?event={id}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, headers=HEADERS) as client:
            resp_resumo = await client.get(url_resumo, timeout=15.0)
            if resp_resumo.status_code != 200: raise Exception("API bloqueou")
            espn_data = resp_resumo.json()
            
            competitions = espn_data.get('header', {}).get('competitions', [{}])
            comp = competitions[0] if len(competitions) > 0 else {}
            year = espn_data.get('header', {}).get('season', {}).get('year', '')
            comp_url = comp.get('uid', '')
            league_slug = comp_url.split("~c:")[-1] if "~c:" in comp_url else ""
            
            teams = comp.get('competitors', [])
            home_team = next((t for t in teams if t.get('homeAway') == 'home'), {})
            away_team = next((t for t in teams if t.get('homeAway') == 'away'), {})
            home_id = str(home_team.get('team', {}).get('id', ''))
            away_id = str(away_team.get('team', {}).get('id', ''))
            
            url_tabela = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/standings?season={year}" if league_slug else ""
            resp_tabela = {}
            if url_tabela:
                try:
                    resp_tabela_req = await client.get(url_tabela, timeout=10.0)
                    if resp_tabela_req.status_code == 200: resp_tabela = resp_tabela_req.json()
                except: pass

        # FORMA BÁSICA
        form_home_raw = home_team.get('form') or ""
        form_away_raw = away_team.get('form') or ""
        mapa_form = {"W": "V", "D": "E", "L": "D"}
        form_home = [mapa_form.get(f, "?") for f in form_home_raw[-5:]]
        form_away = [mapa_form.get(f, "?") for f in form_away_raw[-5:]]

        # ROBÔ H2H REAL (Busca os detalhes reais se a ESPN enviar)
        historico_home, historico_away = [], []
        try:
            form_root = espn_data.get('form', [])
            for f_team in form_root:
                t_id = str(f_team.get('team', {}).get('id', ''))
                evs = []
                for ev in f_team.get('events', []):
                    res = ev.get('gameResult', '')
                    res_br = "V" if res == "W" else "E" if res == "D" else "D" if res == "L" else "-"
                    evs.append({"jogo": ev.get('shortName', 'Desconhecido'), "placar": ev.get('score', '-'), "resultado": res_br})
                if t_id == home_id: historico_home = evs
                elif t_id == away_id: historico_away = evs
        except: pass

        # BLINDAGEM H2H: Se não tiver histórico real (Ex: Amistosos), fabrica com a forma!
        if not historico_home:
            historico_home = [{"jogo": f"Jogo Recente {i+1}", "placar": "-", "resultado": r} for i, r in enumerate(form_home) if r != "?"]
        if not historico_away:
            historico_away = [{"jogo": f"Jogo Recente {i+1}", "placar": "-", "resultado": r} for i, r in enumerate(form_away) if r != "?"]

        # TABELA
        tabela_dados = {"pos_home": "-", "pos_away": "-", "pts_home": "-", "pts_away": "-"}
        try:
            standings = resp_tabela.get('children', [{}])[0].get('standings', {}).get('entries', [])
            for t in standings:
                tid = str(t.get('team', {}).get('id', ''))
                if tid == home_id:
                    tabela_dados['pos_home'] = t['stats'][0]['displayValue']
                    tabela_dados['pts_home'] = t['stats'][3]['displayValue']
                if tid == away_id:
                    tabela_dados['pos_away'] = t['stats'][0]['displayValue']
                    tabela_dados['pts_away'] = t['stats'][3]['displayValue']
        except: pass

        # ESTATÍSTICAS
        stats = {"home_possession": "-", "away_possession": "-", "home_shots": "-", "away_shots": "-"}
        try:
            team_stats = espn_data.get('boxscore', {}).get('teams', [])
            for t in team_stats:
                stat_dict = {s['name']: s['displayValue'] for s in t.get('statistics', [])}
                prefix = 'home' if str(t.get('team', {}).get('id')) == home_id else 'away'
                stats[f'{prefix}_possession'] = stat_dict.get('possessionPct', '-')
                stats[f'{prefix}_shots'] = stat_dict.get('shotsTotal', '-')
        except: pass

        # CLUBELO
        home_rating, away_rating = "N/A", "N/A"
        global elo_cache
        if elo_cache is None: await carregar_clubelo_async()
        if elo_cache is not None and not elo_cache.empty:
            try:
                home_name = home_team.get('team', {}).get('displayName', '')
                away_name = away_team.get('team', {}).get('displayName', '')
                h_match = elo_cache[elo_cache.index.str.contains(home_name[:5], case=False, na=False)]
                a_match = elo_cache[elo_cache.index.str.contains(away_name[:5], case=False, na=False)]
                if not h_match.empty: home_rating = str(int(h_match['Elo'].values[0]))
                if not a_match.empty: away_rating = str(int(a_match['Elo'].values[0]))
            except: pass

        return {
            "sucesso": True,
            "forma": {"home": form_home, "away": form_away},
            "historico": {"home": historico_home, "away": historico_away},
            "tabela": tabela_dados,
            "estatisticas": stats,
            "soccerdata": {"home_elo": home_rating, "away_elo": away_rating},
            "venue": espn_data.get('gameInfo', {}).get('venue', {}).get('fullName', 'N/A'),
            "status": comp.get('status', {}).get('type', {}).get('detail', 'N/A')
        }
    except Exception as e:
        return {"sucesso": False, "erro": "Jogo com escassez de dados."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
