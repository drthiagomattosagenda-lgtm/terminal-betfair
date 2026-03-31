import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import soccerdata as sd
import uvicorn
import pandas as pd
from datetime import datetime

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
        # Usaremos o FBRef para pegar o calendário de jogos
        # É leve e traz dados de ligas tops (Premier League, La Liga, etc.)
        fbref = sd.FBRef(leagues=['ENG-Premier League', 'ESP-La Liga', 'BRA-Serie A'], seasons='2025-2026')
        schedule = fbref.read_schedule()
        
        # Filtramos apenas os jogos que ainda não aconteceram (futuros)
        hoje = datetime.now().strftime('%Y-%m-%d')
        jogos_hoje = schedule[schedule.index.get_level_values('date') >= hoje].head(10).reset_index()

        dados_finais = []
        for _, row in jogos_hoje.iterrows():
            dados_finais.append({
                "home_team": row['home_team'],
                "away_team": row['away_team'],
                "league": row.get('league', 'Elite League'),
                "time": row['time'] if pd.notna(row['time']) else "A definir",
                "stadium": row.get('venue', 'Estádio Principal')
            })
            
        return {"sucesso": True, "dados": dados_finais}
    except Exception as e:
        # Se o SoccerData falhar por timeout, mandamos um sinal para o site não travar
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
