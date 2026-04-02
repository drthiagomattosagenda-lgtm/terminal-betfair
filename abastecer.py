import urllib.request
import json
import requests
from datetime import datetime, timedelta, timezone

# Preparando o terreno para o SoccerData (Instalado via Actions)
try:
    import soccerdata as sd
    import pandas as pd
    soccerdata_ready = True
except ImportError:
    soccerdata_ready = False

TOKEN = "f0772d6c4ebf4102b615b3466f97fd4b"

hoje = datetime.now(timezone.utc)
ontem = hoje - timedelta(days=1)
amanha = hoje + timedelta(days=2)

date_from = ontem.strftime('%Y-%m-%d')
date_to = amanha.strftime('%Y-%m-%d')

# BASE: Puxar o "Coração Ao Vivo" da API
url_api = f"https://api.football-data.org/v4/competitions/BSA/matches?dateFrom={date_from}&dateTo={date_to}"
req = urllib.request.Request(url_api, headers={'X-Auth-Token': TOKEN})

# O FILTRO PURIFICADOR: Transforma o lixo da API em nomes de Elite
correcao_nomes = {
    "Mineiro": "Atlético-MG",
    "Clube do Remo": "Remo",
    "Chapecoense AF": "Chapecoense"
}

# MAPA CLUBELO
mapa_clubelo = {
    "Fluminense": "Fluminense",
    "Corinthians": "Corinthians",
    "Palmeiras": "Palmeiras",
    "Flamengo": "Flamengo",
    "Botafogo": "Botafogo",
    "Grêmio": "Gremio",
    "Internacional": "Internacional",
    "Cruzeiro": "Cruzeiro",
    "Atlético-MG": "AtleticoMineiro",
    "São Paulo": "SaoPaulo",
    "Vasco da Gama": "Vasco",
    "Chapecoense": "Chapecoense",
    "Remo": "Remo"
}

def buscar_elo(time_nome):
    time_elo = mapa_clubelo.get(time_nome, time_nome.replace(" ", ""))
    try:
        url = f"http://api.clubelo.com/{time_elo}"
        resposta = requests.get(url, timeout=5)
        if resposta.status_code == 200 and "Elo" in resposta.text:
            linhas = resposta.text.strip().split('\n')
            ultima_linha = linhas[-1].split(',')
            return round(float(ultima_linha[3]))
        return "N/A"
    except:
        return "N/A"

try:
    with urllib.request.urlopen(req) as response:
        dados_originais = json.loads(response.read().decode('utf-8'))
    
    jogos_enriquecidos = []
    
    for match in dados_originais.get('matches', []):
        home_api = match['homeTeam'].get('shortName', match['homeTeam']['name'])
        away_api = match['awayTeam'].get('shortName', match['awayTeam']['name'])
        
        # Passa pelo corretor para arrumar o Chassi visual
        home_oficial = correcao_nomes.get(home_api, home_api)
        away_oficial = correcao_nomes.get(away_api, away_api)
        
        # Devolve o nome purificado para o JSON que o seu HTML vai ler!
        match['homeTeam']['shortName'] = home_oficial
        match['awayTeam']['shortName'] = away_oficial
        match['homeTeam']['name'] = home_oficial
        match['awayTeam']['name'] = away_oficial
        
        print(f"Minerando: {home_oficial} vs {away_oficial}...")
        
        # Injeta a Inteligência
        match['inteligencia'] = {
            'clubelo': {
                'home_elo': buscar_elo(home_oficial),
                'away_elo': buscar_elo(away_oficial)
            },
            'recent_form': {
                'home': ['V', 'V', 'E', 'D', 'V'], # Em breve: alimentado pelo SoccerData
                'away': ['D', 'E', 'V', 'D', 'E']
            }
        }
        jogos_enriquecidos.append(match)
        
    dados_finais = {'matches': jogos_enriquecidos}

    with open('jogos_de_hoje.json', 'w', encoding='utf-8') as f:
        json.dump(dados_finais, f, ensure_ascii=False, indent=2)
        
    print("Tanque Bi-Turbo cheio! Nomes purificados + ClubElo capturado.")

except Exception as e:
    print(f"Erro Fatal no motor V12: {e}")
