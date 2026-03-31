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

def carregar_clubelo():
    global elo_cache
    try:
        url = "http://api.clubelo.com/api/ranking"
        response = httpx.get(url, timeout=15)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        elo_cache = df[['Club', 'Elo']].set_index('Club')
        print("Base ClubElo carregada com sucesso!")
    except Exception as e:
        print(f"Aviso ClubElo: {e}")
        elo_cache = pd.DataFrame()

@app.get("/jogos")
async def buscar_jogos():
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/scorepanel"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
            data = response.json()
            
        jogos = []
        for league in data.get('scores', []):
            l_name = league.get('leagues', [{}])[0].get('name', 'Geral')
            for event in league.get('events', []):
                comp = event['competitions'][0]
                home = next(t['team']['displayName'] for t in comp['competitors'] if t['homeAway'] == 'home')
                away = next(t['team']['displayName'] for t in comp['competitors'] if t['homeAway'] == 'away')
                jogos.append({
                    "id": event['id'], 
                    "home": home, 
                    "away": away, 
                    "league": l_name,
                    "score": comp['status']['type']['shortDetail'],
                    "time": comp['status']['type']['shortDetail'],
                    "venue": comp.get('venue', {}).get('fullName', 'Estádio não informado')
                })
        return {"sucesso": True, "dados": jogos}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

# ROTA REESCRITA (Busca Assíncrona Tripla para encher as 4 abas)
@app.get("/detalhes/{id}")
async def buscar_detalhes(id: str):
    url_resumo = f"https://site.api.espn.com/apis/site/v2/sports/soccer/summary?event={id}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp_resumo = await client.get(url_resumo, timeout=10)
            espn_data = resp_resumo.json()
            
            # Precisamos do ID da liga e ano para buscar classificação
            league_id = espn_data.get('header', {}).get('competitions', [{}])[0].get('season', {}).get('type', {}).get('id')
            year = espn_data.get('header', {}).get('season', {}).get('year')
            # Extraindo a sigla do campeonato (ex: eng.1, bra.1) da URL da competição
            comp_url = espn_data.get('header', {}).get('competitions', [{}])[0].get('uid', '')
            league_slug = comp_url.split(':')[-2] if ':' in comp_url else ''

            # Bate na API de Classificação e Estatísticas simultaneamente se tiver a liga
            url_tabela = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/standings?season={year}" if league_slug else url_resumo
            url_stats = f"https://site.api.espn.com/apis/site/v2/sports/soccer/summary?event={id}" # ESPN repete stats aqui, mas em outra chave

            reqs = await asyncio.gather(
                client.get(url_tabela, timeout=10) if league_slug else asyncio.sleep(0),
                client.get(url_stats, timeout=10)
            )
            resp_tabela = reqs[0].json() if reqs[0] else {}

        # 1. TRATANDO ABA GERAL (Forma e Status)
        form_home, form_away = [], []
        home_id, away_id = "", ""
        try:
            teams = espn_data['header']['competitions'][0]['competitors']
            home_team = next(t for t in teams if t['homeAway'] == 'home')
            away_team = next(t for t in teams if t['homeAway'] == 'away')
            home_id = home_team['team']['id']
            away_id = away_team['team']['id']
            
            mapa_form = {"W": "V", "D": "E", "L": "D"}
            form_home = [mapa_form.get(f, "?") for f in home_team.get('form', '')[-5:]]
            form_away = [mapa_form.get(f, "?") for f in away_team.get('form', '')[-5:]]
        except:
            pass

        # 2. TRATANDO ABA CLASSIFICAÇÃO (Tabela)
        tabela_dados = {"pos_home": "-", "pos_away": "-", "pts_home": "-", "pts_away": "-"}
        try:
            # Varre a tabela para achar os dois times
            standings = resp_tabela.get('children', [{}])[0].get('standings', {}).get('entries', [])
            for t in standings:
                if t['team']['id'] == home_id:
                    tabela_dados['pos_home'] = t['stats'][0]['displayValue'] # Ranking
                    tabela_dados['pts_home'] = t['stats'][3]['displayValue'] # Pontos
                if t['team']['id'] == away_id:
                    tabela_dados['pos_away'] = t['stats'][0]['displayValue']
                    tabela_dados['pts_away'] = t['stats'][3]['displayValue']
        except:
            pass

        # 3. TRATANDO ABA DESTAQUES (Estatísticas do Jogo, se já começou/acabou)
        stats = {"home_possession": "-", "away_possession": "-", "home_shots": "-", "away_shots": "-"}
        try:
            team_stats = espn_data.get('boxscore', {}).get('teams', [])
            for t in team_stats:
                stat_dict = {s['name']: s['displayValue'] for s in t.get('statistics', [])}
                prefix = 'home' if t['team']['id'] == home_id else 'away'
                stats[f'{prefix}_possession'] = stat_dict.get('possessionPct', '-')
                stats[f'{prefix}_shots'] = stat_dict.get('shotsTotal', '-')
        except:
            pass

        # 4. ClubElo (A velha dica do mestre)
        home_name = home_team['team'].get('displayName', '')
        away_name = away_team['team'].get('displayName', '')
        home_rating, away_rating = "N/A", "N/A"
        global elo_cache
        if elo_cache is None: carregar_clubelo()
        if not elo_cache.empty:
            try:
                h_match = elo_cache[elo_cache.index.str.contains(home_name[:6], case=False, na=False)]
                a_match = elo_cache[elo_cache.index.str.contains(away_name[:6], case=False, na=False)]
                if not h_match.empty: home_rating = str(int(h_match['Elo'].values[0]))
                if not a_match.empty: away_rating = str(int(a_match['Elo'].values[0]))
            except: pass

        return {
            "sucesso": True,
            "forma": {"home": form_home, "away": form_away},
            "tabela": tabela_dados,
            "estatisticas": stats,
            "soccerdata": {"home_elo": home_rating, "away_elo": away_rating},
            "venue": espn_data.get('gameInfo', {}).get('venue', {}).get('fullName', 'N/A'),
            "status": espn_data['header']['competitions'][0]['status']['type']['detail']
        }
    except Exception as e:
        print("Erro Detalhes:", str(e))
        return {"sucesso": False, "erro": "Falha na central de dados"}

if __name__ == "__main__":
    carregar_clubelo()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
