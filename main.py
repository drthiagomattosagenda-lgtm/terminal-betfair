import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
                    "id": event['id'], "home": home, "away": away, "league": l_name,
                    "score": comp['status']['type']['shortDetail'],
                    "time": comp['status']['type']['shortDetail'],
                    "venue": comp.get('venue', {}).get('fullName', 'Estádio Pro')
                })
        return {"sucesso": True, "dados": jogos}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

# ENDPOINT NOVO: Busca detalhes de um jogo específico para as abas
@app.get("/detalhes/{id}")
def buscar_detalhes(id: str):
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/summary?event={id}"
        return requests.get(url, timeout=10).json()
    except:
        return {"erro": "Falha na central de dados"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
