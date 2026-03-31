import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import soccerdata as sd
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
    return {"status": "Ferrari Online no Render"}

@app.get("/jogos")
def buscar_jogos():
    try:
        # Usando ClubElo para o primeiro teste (mais leve para o Render)
        elo = sd.ClubElo()
        jogos = elo.read_by_date()
        resultado = jogos.reset_index().fillna("").to_dict(orient="records")
        return {"sucesso": True, "dados": resultado}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
