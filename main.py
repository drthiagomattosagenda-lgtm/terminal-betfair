import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# Configuração de Segurança (CORS) - LIBERADO TOTAL
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"status": "Motor Ferrari Online"}

@app.get("/jogos")
def buscar_jogos():
    try:
        # Dados simplificados e rápidos para garantir que o Render não dê Erro 500
        # Em breve voltaremos com o SoccerData assim que o túnel estiver estável
        dados_vips = [
            {"home_team": "Real Madrid", "away_team": "Man City", "home_score": "3", "away_score": "3"},
            {"home_team": "Arsenal", "away_team": "Bayern", "home_score": "2", "away_score": "2"},
            {"home_team": "Inter", "away_team": "Milan", "home_score": "1", "away_score": "0"},
            {"home_team": "Flamengo", "away_team": "Palmeiras", "home_score": "0", "away_score": "0"}
        ]
        return {"sucesso": True, "dados": dados_vips}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
