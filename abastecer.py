import urllib.request
import json
import requests
from datetime import datetime, timedelta, timezone
import traceback
import re

# Acionando o Cérebro Avançado
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

# 1. RELÓGIO AO VIVO (Mantém a pulsação do site sem ser banido)
url_api = f"https://api.football-data.org/v4/competitions/BSA/matches?dateFrom={date_from}&dateTo={date_to}"
req = urllib.request.Request(url_api, headers={'X-Auth-Token': TOKEN})

# 2. O SUPER TRADUTOR V12 (Retorna: Nome Tela, Nome ClubElo, Nome FBref)
def padronizar_time(nome_sujo):
    n = nome_sujo.upper()
    if "MINEIRO" in n: return "Atlético-MG", "AtleticoMineiro", "Atlético Mineiro"
    if "CHAPECO" in n: return "Chapecoense", "Chapecoense", "Chapecoense"
    if "REMO" in n: return "Remo", "Remo", "Remo"
    if "SANTOS" in n: return "Santos", "Santos", "Santos"
    if "FLAMENGO" in n: return "Flamengo", "Flamengo", "Flamengo"
    if "FLUMINENSE" in n: return "Fluminense", "Fluminense", "Fluminense"
    if "CORINTHIANS" in n: return "Corinthians", "Corinthians", "Corinthians"
    if "PALMEIRAS" in n: return "Palmeiras", "Palmeiras", "Palmeiras"
    if "BOTAFOGO" in n: return "Botafogo", "Botafogo", "Botafogo"
    if "GREMIO" in n or "GRÊMIO" in n: return "Grêmio", "Gremio", "Grêmio"
    if "INTER" in n: return "Internacional", "Internacional", "Internacional"
    if "CRUZEIRO" in n: return "Cruzeiro", "Cruzeiro", "Cruzeiro"
    if "PAULO" in n: return "São Paulo", "SaoPaulo", "São Paulo"
    if "VASCO" in n: return "Vasco", "Vasco", "Vasco"
    # Fallback triplo de segurança
    return nome_sujo.title(), nome_sujo.replace(" ", ""), nome_sujo.title()

def buscar_elo(nome_clubelo):
    try:
        url = f"http://api.clubelo.com/{nome_clubelo}"
        resposta = requests.get(url, timeout=5)
        if resposta.status_code == 200 and "Elo" in resposta.text:
            return round(float(resposta.text.strip().split('\n')[-1].split(',')[3]))
        return "N/A"
    except:
        return "N/A"

# 3. MÁQUINA DE CALCULAR MOMENTO RECENTE (Lê o FBref e gera V/E/D)
def calcular_forma_fbref(nome_fbref, df_schedule):
    try:
        if df_schedule is None or df_schedule.empty:
            return ['-','-','-','-','-']
        
        # Filtra os jogos do time que já possuem placar na temporada
        mask_team = (df_schedule['home_team'].str.contains(nome_fbref, case=False, na=False)) | (df_schedule['away_team'].str.contains(nome_fbref, case=False, na=False))
        mask_score = df_schedule['score'].notna()
        df_team = df_schedule[mask_team & mask_score].tail(5) # Pega as 5 últimas partidas
        
        forma = []
        for _, row in df_team.iterrows():
            home = str(row['home_team'])
            score = str(row['score']).replace('–', '-') # Limpa a tipografia do FBref
            
            # Puxa os gols exatos usando Regex (segurança máxima)
            gols = re.findall(r'\d+', score)
            if len(gols) >= 2:
                gh = int(gols[0])
                ga = int(gols[1])
                
                is_home = nome_fbref.lower() in home.lower()
                if gh == ga:
                    forma.append('E')
                elif (gh > ga and is_home) or (ga > gh and not is_home):
                    forma.append('V')
                else:
                    forma.append('D')
                    
        # Se o time jogou menos de 5 partidas na temporada, preenche com "-"
        while len(forma) < 5:
            forma.insert(0, '-')
            
        return forma[-5:]
    except Exception as e:
        print(f"Erro ao calcular forma para {nome_fbref}: {e}")
        return ['-','-','-','-','-']

# 4. CARREGANDO A INTELIGÊNCIA EM MEMÓRIA
df_schedule = None
if soccerdata_ready:
    try:
        print("Lendo Cache do SoccerData (FBref)...")
        fbref = sd.FBref(leagues="BRA-Serie A", seasons="2024")
        df_schedule = fbref.read_schedule()
        print("Base de dados do FBref pronta!")
    except Exception as e:
        print(f"Aviso FBref: {e}")

# 5. CRUZAMENTO DE DADOS E ABASTECIMENTO DO TANQUE
try:
    with urllib.request.urlopen(req) as response:
        dados_originais = json.loads(response.read().decode('utf-8'))
    
    jogos_enriquecidos = []
    
    for match in dados_originais.get('matches', []):
        home_raw = match['homeTeam'].get('shortName', match['homeTeam']['name'])
        away_raw = match['awayTeam'].get('shortName', match['awayTeam']['name'])
        
        # O Chassi HTML recebe os nomes perfeitos
        home_tela, home_elo_name, home_fbref = padronizar_time(home_raw)
        away_tela, away_elo_name, away_fbref = padronizar_time(away_raw)
        
        match['homeTeam']['shortName'] = home_tela
        match['homeTeam']['name'] = home_tela
        match['awayTeam']['shortName'] = away_tela
        match['awayTeam']['name'] = away_tela
        
        print(f"Injetando cálculos matemáticos: {home_tela} vs {away_tela}...")
        
        # Aqui a mágica acontece: O Python gera a forma e o seu HTML lê na tela
        match['inteligencia'] = {
            'clubelo': {
                'home_elo': buscar_elo(home_elo_name),
                'away_elo': buscar_elo(away_elo_name)
            },
            'recent_form': {
                'home': calcular_forma_fbref(home_fbref, df_schedule),
                'away': calcular_forma_fbref(away_fbref, df_schedule)
            }
        }
        jogos_enriquecidos.append(match)
        
    dados_finais = {'matches': jogos_enriquecidos}

    with open('jogos_de_hoje.json', 'w', encoding='utf-8') as f:
        json.dump(dados_finais, f, ensure_ascii=False, indent=2)
        
    print("Sucesso! O caminhão tanque agora carrega dados 100% reais do SoccerData.")

except Exception as e:
    print(f"Erro Fatal no motor: {e}")
    traceback.print_exc()
