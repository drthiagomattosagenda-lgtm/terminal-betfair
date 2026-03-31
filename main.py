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

@app.get("/jogos")
def buscar_jogos():
    try:
        # Endpoint público da ESPN (Grade Global)
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/scorepanel"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        jogos = []
        for league in data.get('scores', []):
            l_name = league.get('leagues', [{}])[0].get('name', 'Outros')
            for event in league.get('events', []):
                comp = event.get('competitions', [{}])[0]
                home = next((t['team']['displayName'] for t in comp['competitors'] if t['homeAway'] == 'home'), "Casa")
                away = next((t['team']['displayName'] for t in comp['competitors'] if t['homeAway'] == 'away'), "Fora")
                
                jogos.append({
                    "id": event['id'],
                    "home": home,
                    "away": away,
                    "league": l_name,
                    "score": comp.get('status', {}).get('type', {}).get('shortDetail', '0-0'),
                    "time": event.get('status', {}).get('type', {}).get('shortDetail', '--'),
                    "venue": comp.get('venue', {}).get('fullName', 'N/A')
                })
        return {"sucesso": True, "dados": jogos}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
