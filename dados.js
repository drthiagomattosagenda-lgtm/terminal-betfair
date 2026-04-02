// dados.js — Motor de dados do site

const API_BASE = "https://api.football-data.org/v4";

// Busca todas as partidas de hoje em todas as ligas configuradas
async function buscarPartidasHoje() {
  const hoje = new Date().toISOString().split("T")[0]; // formato: 2026-04-02
  
  const headers = {
    "X-Auth-Token": CONFIG.API_KEY
  };

  try {
    // Busca partidas de todas as competições configuradas
    const resposta = await fetch(
      `${API_BASE}/matches?date=${hoje}`,
      { headers }
    );

    if (!resposta.ok) {
      throw new Error("Erro ao buscar partidas: " + resposta.status);
    }

    const dados = await resposta.json();
    
    // Organiza as partidas por liga
    const porLiga = {};
    
    dados.matches.forEach(partida => {
      const idLiga = partida.competition.id;
      const nomeLiga = CONFIG.LIGAS[idLiga];
      
      // Só mostra ligas que estão na sua lista
      if (!nomeLiga) return;
      
      if (!porLiga[nomeLiga]) {
        porLiga[nomeLiga] = [];
      }
      
      porLiga[nomeLiga].push({
        id: partida.id,
        horario: new Date(partida.utcDate).toLocaleTimeString("pt-BR", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "America/Sao_Paulo"
        }),
        timeCasa: partida.homeTeam.name,
        timeFora: partida.awayTeam.name,
        escudoCasa: partida.homeTeam.crest,
        escudoFora: partida.awayTeam.crest,
        status: traduzirStatus(partida.status),
        placarCasa: partida.score.fullTime.home,
        placarFora: partida.score.fullTime.away,
        minuto: partida.minute || null
      });
    });
    
    return porLiga;
    
  } catch (erro) {
    console.error("Falha ao carregar partidas:", erro);
    return null;
  }
}

// Traduz os status da API para português
function traduzirStatus(status) {
  const traducoes = {
    "SCHEDULED":  "Agendado",
    "TIMED":      "Agendado",
    "IN_PLAY":    "Ao vivo",
    "PAUSED":     "Intervalo",
    "FINISHED":   "Encerrado",
    "POSTPONED":  "Adiado",
    "CANCELLED":  "Cancelado"
  };
  return traducoes[status] || status;
}
