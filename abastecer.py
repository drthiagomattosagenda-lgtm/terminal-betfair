import urllib.request
import json
import requests
from datetime import datetime, timedelta, timezone

TOKEN = "f0772d6c4ebf4102b615b3466f97fd4b"

hoje = datetime.now(timezone.utc)
ontem = hoje - timedelta(days=1)
amanha = hoje + timedelta(days=2)

date_from = ontem.strftime('%Y-%m-%d')
date_to = amanha.strftime('%Y-%m-%d')

url_api = f"https://api.football-data.org/v4/competitions/BSA/matches?dateFrom={date_from}&dateTo={date_to}"
req = urllib.request.Request(url_api, headers={'X-Auth-Token': TOKEN})

# Dicionário de Tradução: Ensina o Python a converter os nomes da API para o padrão ClubElo
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
    "Mineiro": "AtleticoMineiro" # Correção para o nome genérico da API gratuita
}

def buscar_elo(time_nome_api):
    # Se o nome estiver no mapa, usa ele. Se não, tenta remover os espaços
    time_elo = mapa_clubelo.get(time_nome_api, time_nome_api.replace(" ", ""))
    
    try:
        url = f"http://api.clubelo.com/{time_elo}"
        resposta = requests.get(url, timeout=5)
        
        # O ClubElo retorna um CSV de texto puro
        if resposta.status_code == 200 and "Elo" in resposta.text:
            linhas = resposta.text.strip().split('\n')
            ultima_linha = linhas[-1].split(',')
            # O Elo atual fica na 4ª coluna (índice 3)
            elo_atual = float(ultima_linha[3])
            return round(elo_atual)
        return "N/A"
    except Exception as e:
        return "N/A"

try:
    with urllib.request.urlopen(req) as response:
        dados_originais = json.loads(response.read().decode('utf-8'))
    
    jogos_enriquecidos = []
    
    for match in dados_originais.get('matches', []):
        home_name = match['homeTeam'].get('shortName', match['homeTeam']['name'])
        away_name = match['awayTeam'].get('shortName', match['awayTeam']['name'])
        
        print(f"Minerando dados extras para: {home_name} vs {away_name}...")
        
        # INJEÇÃO V12: Adiciona um novo bloco chamado 'inteligencia' dentro de cada jogo
        match['inteligencia'] = {
            'clubelo': {
                'home_elo': buscar_elo(home_name),
                'away_elo': buscar_elo(away_name)
            },
            'recent_form': {
                'home': ['V', 'V', 'E', 'D', 'V'], # Espaço preparado para o próximo passo (SofaScore)
                'away': ['D', 'E', 'V', 'D', 'E']
            }
        }
        jogos_enriquecidos.append(match)
        
    dados_finais = {'matches': jogos_enriquecidos}

    with open('jogos_de_hoje.json', 'w', encoding='utf-8') as f:
        json.dump(dados_finais, f, ensure_ascii=False, indent=2)
        
    print(f"Tanque V12 cheio! Dados básicos + ClubElo cruzados com sucesso.")

except Exception as e:
    print(f"Erro Fatal no motor V12: {e}")
