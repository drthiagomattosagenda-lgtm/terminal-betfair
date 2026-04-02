import urllib.request
import json
from datetime import datetime, timedelta, timezone

TOKEN = "f0772d6c4ebf4102b615b3466f97fd4b"

# Pega a data de hoje e de amanhã em UTC para garantir os jogos noturnos do Brasil
hoje = datetime.now(timezone.utc)
amanha = hoje + timedelta(days=1)

date_from = hoje.strftime('%Y-%m-%d')
date_to = amanha.strftime('%Y-%m-%d')

# Agora pedimos para a API uma janela de 2 dias
url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"

req = urllib.request.Request(url, headers={'X-Auth-Token': TOKEN})
try:
    with urllib.request.urlopen(req) as response:
        dados = json.loads(response.read().decode('utf-8'))
        
        with open('jogos_de_hoje.json', 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            
        print(f"Combustível abastecido com sucesso! (Janela: {date_from} a {date_to})")
except Exception as e:
    print(f"Erro no motor Python: {e}")
