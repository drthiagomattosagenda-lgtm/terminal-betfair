import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"status": "Motor ESPN Ativo"}

@app.get("/jogos")
def buscar_jogos():
    try:
        # API Direta da ESPN - Grade Global (Leve e estável no Render)
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/scorepanel"
        response = requests.get(url, timeout=15)
        data = response.json()
        
        jogos_formatados = []
        
        # Percorrendo as ligas e jogos disponíveis hoje
        for league in data.get('scores', []):
            league_name = league.get('leagues', [{}])[0].get('name', 'Outros')
            for event in league.get('events', []):
                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                home_team = next((c['team']['displayName'] for c in competitors if c['homeAway'] == 'home'), "Casa")
                away_team = next((c['team']['displayName'] for c in competitors if c['homeAway'] == 'away'), "Fora")
                
                jogos_formatados.append({
                    "home_team": home_team,
                    "away_team": away_team,
                    "league": league_name,
                    "time": event.get('status', {}).get('type', {}).get('shortDetail', 'HOJE'),
                    "id": event.get('id', '0')
                })
        
        return {"sucesso": True, "dados": jogos_formatados}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
