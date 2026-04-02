import urllib.request
import json
import requests
from datetime import datetime, timedelta, timezone

# Deixando a porta aberta para o SoccerData (Estatísticas Avançadas)
try:
    import soccerdata as sd
    soccerdata_ready = True
except ImportError:
    soccerdata_ready = False

TOKEN = "f0772d6c4ebf4102b615b3466f97fd4b"

hoje = datetime.now(timezone.utc)
ontem = hoje - timedelta(days=1)
amanha = hoje + timedelta(days=2)

date_from = ontem.strftime('%Y-%m-%d')
date_to = amanha.strftime('%Y-%m-%d')

# RELÓGIO AO VIVO: Mantemos a API oficial APENAS para os minutos e placar real-time.
# Isso evita que o GitHub Actions seja banido pelos bloqueios do Sofascore/FBref.
url_api = f"https://api.football-data.org/v4/competitions/BSA/matches?dateFrom={date_from}&dateTo={date_to}"
req = urllib.request.Request(url_api, headers={'X-Auth-Token': TOKEN})

# O SUPER TRADUTOR V12: Identifica times mesmo se a API mandar o nome bagunçado
def padronizar_time(nome_sujo):
    n = nome_sujo.upper()
    if "MINEIRO" in n: return "Atlético-MG", "AtleticoMineiro"
    if "CHAPECO" in n: return "Chapecoense", "Chapecoense"
    if "REMO" in n: return "Remo", "Remo"
    if "SANTOS" in n: return "Santos", "Santos"
    if "FLAMENGO" in n: return "Flamengo", "Flamengo"
    if "FLUMINENSE" in n: return "Fluminense", "Fluminense"
    if "CORINTHIANS" in n: return "Corinthians", "Corinthians"
    if "PALMEIRAS" in n: return "Palmeiras", "Palmeiras"
    if "BOTAFOGO" in n: return "Botafogo", "Botafogo"
    if "GREMIO" in n or "GRÊMIO" in n: return "Grêmio", "Gremio"
    if "INTER" in n: return "Internacional", "Internacional"
    if "CRUZEIRO" in n: return "Cruzeiro", "Cruzeiro"
    if "PAULO" in n: return "São Paulo", "SaoPaulo"
    if "VASCO" in n: return "Vasco", "Vasco"
    if "PARANAENSE" in n: return "Athletico-PR", "Athletico"
    if "BAHIA" in n: return "Bahia", "Bahia"
    if "VITORIA" in n or "VITÓRIA" in n: return "Vitória", "Vitoria"
    if "FORTALEZA" in n: return "Fortaleza", "Fortaleza"
    if "JUVENTUDE" in n: return "Juventude", "Juventude"
    if "CRICI" in n: return "Criciúma", "Criciuma"
    if "BRAGANTINO" in n: return "Bragantino", "Bragantino"
    if "GOIANIENSE" in n: return "Atlético-GO", "AtleticoGO"
    if "CUIAB" in n: return "Cuiabá", "Cuiaba"
    
    # Fallback caso seja um time que não mapeamos
    return nome_sujo.title(), nome_sujo.replace(" ", "")

def buscar_elo(nome_clubelo):
    try:
        url = f"http://api.clubelo.com/{nome_clubelo}"
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
        home_raw = match['homeTeam'].get('shortName', match['homeTeam']['name'])
        away_raw = match['awayTeam'].get('shortName', match['awayTeam']['name'])
        
        # O Chassi HTML vai receber os nomes perfeitos, independentemente da API
        home_tela, home_elo_name = padronizar_time(home_raw)
        away_tela, away_elo_name = padronizar_time(away_raw)
        
        match['homeTeam']['shortName'] = home_tela
        match['homeTeam']['name'] = home_tela
        match['awayTeam']['shortName'] = away_tela
        match['awayTeam']['name'] = away_tela
        
        print(f"Minerando Inteligência: {home_tela} vs {away_tela}...")
        
        # Injeta a Inteligência (Cérebro) sem quebrar o HTML (Chassi)
        match['inteligencia'] = {
            'clubelo': {
                'home_elo': buscar_elo(home_elo_name),
                'away_elo': buscar_elo(away_elo_name)
            },
            'recent_form': {
                'home': ['V', 'V', 'E', 'D', 'V'], # Espaço exato que o SoccerData FBref vai preencher a seguir
                'away': ['D', 'E', 'V', 'D', 'E']
            }
        }
        jogos_enriquecidos.append(match)
        
    dados_finais = {'matches': jogos_enriquecidos}

    with open('jogos_de_hoje.json', 'w', encoding='utf-8') as f:
        json.dump(dados_finais, f, ensure_ascii=False, indent=2)
        
    print("Tanque Bi-Turbo cheio! Nomes purificados + ClubElo capturado com sucesso.")

except Exception as e:
    print(f"Erro Fatal no motor V12: {e}")
