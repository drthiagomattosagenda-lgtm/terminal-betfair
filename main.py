import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import pandas as pd
import soccerdata as sd

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache em memória para o SoccerData (Evita travar o Render baixando toda hora)
elo_cache = None

def carregar_soccerdata():
    global elo_cache
    try:
        # Inicializa o módulo ClubElo do soccerdata (Leve e poderoso para Power Rating)
        elo = sd.ClubElo()
        elo_cache = elo.read_by_date()
    except Exception as e:
        print(f"Aviso SoccerData: {e}")
        elo_cache = pd.DataFrame() # DataFrame vazio em caso de falha

# ROTA 1: A Grade Rápida (Mantém o site voando)
@app.get("/jogos")
def buscar_jogos():
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/scorepanel"
        data = requests.get(url, timeout=10).json()
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

# ROTA 2: A Inteligência Profunda (H2H da ESPN + Power Rating do SoccerData)
@app.get("/detalhes/{id}")
def buscar_detalhes(id: str):
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/summary?event={id}"
        espn_data = requests.get(url, timeout=10).json()

        # 1. Tratamento da Forma Recente (W/D/L -> V/E/D)
        form_home, form_away = [], []
        try:
            teams = espn_data['header']['competitions'][0]['competitors']
            home_team = next(t for t in teams if t['homeAway'] == 'home')
            away_team = next(t for t in teams if t['homeAway'] == 'away')
            
            # Tradutor de Resultados
            mapa_form = {"W": "V", "D": "E", "L": "D"}
            form_home = [mapa_form.get(f, "?") for f in home_team.get('form', '')[-5:]]
            form_away = [mapa_form.get(f, "?") for f in away_team.get('form', '')[-5:]]
        except:
            form_home, form_away = ["?"], ["?"]

        # 2. Integração SOCCERDATA (Buscando Força Elo do time)
        home_name = home_team['team'].get('displayName', '')
        away_name = away_team['team'].get('displayName', '')
        home_rating, away_rating = "N/A", "N/A"
        
        global elo_cache
        if elo_cache is None:
            carregar_soccerdata()
            
        if not elo_cache.empty:
            # Fuzzy match simples (Como a ESPN e o Soccerdata usam nomes diferentes, pegamos o mais próximo)
            try:
                # Exemplo: Filtra times no ClubElo que contenham parte do nome da ESPN
                h_match = elo_cache[elo_cache.index.str.contains(home_name[:5], case=False, na=False)]
                a_match = elo_cache[elo_cache.index.str.contains(away_name[:5], case=False, na=False)]
                if not h_match.empty: home_rating = str(int(h_match['Elo'].values[0]))
                if not a_match.empty: away_rating = str(int(a_match['Elo'].values[0]))
            except:
                pass

        return {
            "sucesso": True,
            "forma": {"home": form_home, "away": form_away},
            "soccerdata": {"home_elo": home_rating, "away_elo": away_rating},
            "venue": espn_data.get('gameInfo', {}).get('venue', {}).get('fullName', 'N/A'),
            "status": espn_data['header']['competitions'][0]['status']['type']['detail']
        }
    except Exception as e:
        return {"sucesso": False, "erro": "Falha na central de dados"}

if __name__ == "__main__":
    # Inicia o cache do soccerdata ao ligar o servidor
    carregar_soccerdata()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
