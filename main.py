import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import soccerdata as sd
import uvicorn
import pandas as pd

app = FastAPI()

# Liberação de CORS para o seu site no GitHub Pages conversar com o Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"status": "Motor Real Online e Turbinado"}

@app.get("/jogos")
def buscar_jogos():
    try:
        # Buscando dados reais de ranking/jogos via ClubElo (Leve e estável)
        elo = sd.ClubElo()
        df = elo.read_by_date() 
        
        # Pegamos os 10 primeiros registros para garantir velocidade
        top_jogos = df.head(10).reset_index()
        
        dados_reais = []
        for _, row in top_jogos.iterrows():
            # Mapeamos as colunas do SoccerData para o que o seu site espera
            dados_reais.append({
                "home_team": row['team'],
                "away_team": f"Elo: {int(row['elo'])}", # Mostra o nível de força do time
                "home_score": "-", 
                "away_score": "-"
            })
            
        return {"sucesso": True, "dados": dados_reais}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    # Ajuste automático de porta para o servidor do Render
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
