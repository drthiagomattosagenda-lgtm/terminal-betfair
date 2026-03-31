import os
import requests
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

# Cache leve em memória
elo_cache = None

def carregar_clubelo():
    global elo_cache
    try:
        print("Baixando base de dados do ClubElo...")
        # Busca o CSV oficial do ClubElo direto (super leve)
        url = "http://api.clubelo.com/api/ranking"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        # Converte para DataFrame do Pandas
        df = pd.read_csv(io.StringIO(response.text))
        
        # Filtra apenas a coluna Clube e Elo
        elo_cache = df[['Club', 'Elo']].set_index('Club')
        print("Base ClubElo carregada com sucesso!")
    except Exception as e:
        print(f"Aviso ClubElo: {e}")
        elo_cache = pd.DataFrame()

# ROTA 1: A Grade Rápida
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

# ROTA 2: A Inteligência Profunda
@app.get("/detalhes/{id}")
def buscar_detalhes(id: str):
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/summary?event={id}"
        espn_data = requests.get(url, timeout=10).json()

        # Tratamento da Forma Recente
        form_home, form_away = [], []
        try:
            teams = espn_data['header']['competitions'][0]['competitors']
            home_team = next(t for t in teams if t['homeAway'] == 'home')
            away_team = next(t for t in teams if t['homeAway'] == 'away')
            
            mapa_form = {"W": "V", "D": "E", "L": "D"}
            form_home = [mapa_form.get(f, "?") for f in home_team.get('form', '')[-5:]]
            form_away = [mapa_form.get(f, "?") for f in away_team.get('form', '')[-5:]]
        except:
            form_home, form_away = ["?"], ["?"]

        # Busca do Rating direto na API oficial (Substituindo o soccerdata)
        home_name = espn_data['header']['competitions'][0]['competitors'][0]['team'].get('displayName', '')
        away_name = espn_data['header']['competitions'][0]['competitors'][1]['team'].get('displayName', '')
        home_rating, away_rating = "N/A", "N/A"
        
        global elo_cache
        if elo_cache is None:
            carregar_clubelo()
            
        if not elo_cache.empty:
            try:
                # Tenta casar o começo do nome (Ex: "Arsenal" no ClubElo = "Arsenal" na ESPN)
                h_match = elo_cache[elo_cache.index.str.contains(home_name[:6], case=False, na=False)]
                a_match = elo_cache[elo_cache.index.str.contains(away_name[:6], case=False, na=False)]
                if not h_match.empty: home_rating = str(int(h_match['Elo'].values[0]))
                if not a_match.empty: away_rating = str(int(a_match['Elo'].values[0]))
            except:
                pass

        return {
            "sucesso": True,
            "forma": {"home": form_home, "away": form_away},
            "soccerdata": {"home_elo": home_rating, "away_elo": away_rating}, # Mantive a chave 'soccerdata' pro frontend não quebrar
            "venue": espn_data.get('gameInfo', {}).get('venue', {}).get('fullName', 'N/A'),
            "status": espn_data['header']['competitions'][0]['status']['type']['detail']
        }
    except Exception as e:
        return {"sucesso": False, "erro": "Falha na central de dados"}

if __name__ == "__main__":
    carregar_clubelo()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
