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
        # O motor ESPN é o segredo: ele traz a grade global de hoje muito rápido
        espn = sd.ESPN(leagues=None, seasons='2025-2026') # 'None' busca o que estiver disponível
        schedule = espn.read_schedule()
        
        # Resetamos o index para facilitar a leitura das colunas
        df = schedule.reset_index()
        
        # Filtramos apenas jogos de HOJE para não sobrecarregar
        hoje = datetime.now().strftime('%Y-%m-%d')
        jogos_hoje = df[df['date'].astype(str).str.contains(hoje)]
        
        # Se não houver jogos de hoje no log, pegamos os próximos 20 da lista
        if jogos_hoje.empty:
            jogos_hoje = df.head(20)

        dados_finais = []
        for _, row in jogos_hoje.iterrows():
            dados_finais.append({
                "home_team": str(row['home_team']),
                "away_team": str(row['away_team']),
                "league": str(row.get('league', 'International')),
                "time": str(row.get('time', 'A definir')),
                "id": str(row.get('game_id', '0'))
            })
            
        return {"sucesso": True, "dados": dados_finais}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
