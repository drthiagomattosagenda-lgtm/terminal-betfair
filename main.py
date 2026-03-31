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
        # Buscando dados globais da ESPN
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/scorepanel"
        response = requests.get(url, timeout=15)
        data = response.json()
        
        jogos_formatados = []
        
        for league_data in data.get('scores', []):
            league_info = league_data.get('leagues', [{}])[0]
            league_name = league_info.get('name', 'Outras Competições')
            country = league_info.get('midsizeName', 'Global')

            for event in league_data.get('events', []):
                comp = event.get('competitions', [{}])[0]
                teams = comp.get('competitors', [])
                
                home = next((t for t in teams if t['homeAway'] == 'home'), {})
                away = next((t for t in teams if t['homeAway'] == 'away'), {})
                
                # Dados REAIS para as abas
                jogos_formatados.append({
                    "id": event.get('id'),
                    "league": league_name,
                    "country": country,
                    "home": home.get('team', {}).get('displayName'),
                    "away": away.get('team', {}).get('displayName'),
                    "time": event.get('status', {}).get('type', {}).get('shortDetail', '--:--'),
                    "status": event.get('status', {}).get('type', {}).get('name'),
                    "venue": comp.get('venue', {}).get('fullName', 'Estádio Indisponível'),
                    "score": f"{home.get('score', 0)} - {away.get('score', 0)}",
                    # Dados reais para abas (se disponíveis na API)
                    "standings": f"Verificar tabela da {league_name}",
                    "h2h_summary": f"Confronto histórico entre {home.get('team', {}).get('shortDisplayName')} e {away.get('team', {}).get('shortDisplayName')}"
                })
        
        return {"sucesso": True, "dados": jogos_formatados}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
