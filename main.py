from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import soccerdata as sd

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
        # Buscando os dados da Premier League
        ws = sd.WhoScored(leagues=['ENG-Premier League'], seasons='2023')
        jogos = ws.read_schedule()
        
        # --- A LINHA MÁGICA ESTÁ AQUI ---
        # O .fillna("") preenche os campos vazios (NaN) para o navegador não dar erro
        resultado = jogos.reset_index().fillna("").to_dict(orient="records")
        
        return {"sucesso": True, "dados": resultado}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

if __name__ == "__main__":
    import uvicorn
    print("🚀 FERRARI REVISADA: Agora com limpeza de dados automática.")
    uvicorn.run(app, host="0.0.0.0", port=8000)