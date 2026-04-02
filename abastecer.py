import urllib.request
import json
from datetime import datetime, timedelta, timezone

TOKEN = "f0772d6c4ebf4102b615b3466f97fd4b"

# Pegando uma janela larga (Ontem até Amanhã) para o fuso horário (UTC) não engolir os jogos noturnos
hoje = datetime.now(timezone.utc)
ontem = hoje - timedelta(days=1)
amanha = hoje + timedelta(days=2)

date_from = ontem.strftime('%Y-%m-%d')
date_to = amanha.strftime('%Y-%m-%d')

# Filtro cirúrgico: Puxa APENAS o Campeonato Brasileiro Série A (BSA) nessa janela de datas
url = f"https://api.football-data.org/v4/competitions/BSA/matches?dateFrom={date_from}&dateTo={date_to}"

req = urllib.request.Request(url, headers={'X-Auth-Token': TOKEN})
try:
    with urllib.request.urlopen(req) as response:
        dados = json.loads(response.read().decode('utf-8'))
        
        # Salva no galão
        with open('jogos_de_hoje.json', 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            
        print(f"Tanque cheio! Brasileirão Série A capturado. (Janela: {date_from} a {date_to})")
except Exception as e:
    print(f"Erro no motor Python: {e}")
