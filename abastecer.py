import urllib.request
import json

TOKEN = "f0772d6c4ebf4102b615b3466f97fd4b" # Sua chave
url = "https://api.football-data.org/v4/matches"

req = urllib.request.Request(url, headers={'X-Auth-Token': TOKEN})
try:
    with urllib.request.urlopen(req) as response:
        dados = json.loads(response.read().decode('utf-8'))
        # Salva a gasolina no nosso próprio galão
        with open('jogos_de_hoje.json', 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        print("Combustível abastecido com sucesso!")
except Exception as e:
    print(f"Erro no motor Python: {e}")
