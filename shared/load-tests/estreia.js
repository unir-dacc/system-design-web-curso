// ESTREIA DO MAIOR FILME DA HISTÓRIA
//
// As vendas abrem e uma multidão tenta comprar ao mesmo tempo:
//   - fãs: chegam aos montes, abrem o mapa e compram de 1 a 4 ingressos (alguns meia-entrada)
//   - cambistas: robôs com poucos CPFs comprando sem parar, tentando furar o limite
//
// Os fãs continuam chegando mesmo se o site estiver lento. Quem espera mais
// de 30 s desiste. No final, o resumo mostra o que aconteceu.
//
//   docker compose run --rm --service-ports k6 run /scripts/estreia.js
//   docker compose run --rm --service-ports k6 run -e FAS=100 /scripts/estreia.js

import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter, Gauge } from 'k6/metrics';

const INGRESSA = __ENV.BASE_URL || 'http://ingressa:8000';
const CINEMA = 'http://sistema-cinema:8000';
const GATEWAY = 'http://gateway-pagamento:8000';

const FAS_POR_SEGUNDO = Number(__ENV.FAS || 50);
const ROBOS_CAMBISTAS = 20;
const SESSOES = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]; // todas da estreia, 400 lugares cada
const LIMITE_POR_CPF = 6;
const COTA_MEIA = 160; // 40% de 400

// Três CPFs válidos usados por todos os robôs cambistas
const CPFS_CAMBISTAS = ['11144477735', '52998224725', '39053344705'];

const fasChegaram = new Counter('fas_chegaram');
const viramConfirmacao = new Counter('ingressos_confirmados_para_o_fa');
const comprasConcluidas = new Counter('compras_concluidas');
const desistiram = new Counter('desistiram');
const esgotado = new Counter('encontraram_esgotado');
const vendidos = new Gauge('ingressos_vendidos');
const maiorCompraPorCpf = new Gauge('maior_compra_por_cpf');
const maiorQtdMeia = new Gauge('maior_qtd_meia_na_sessao');
const naoRespondeu = new Gauge('ingressa_nao_respondeu');

http.setResponseCallback(http.expectedStatuses(200, 201, 402, 409, 422)); // erros de negócio não são falhas

export const options = {
  scenarios: {
    fas: {
      executor: 'ramping-arrival-rate',
      exec: 'fa',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 1500,
      stages: [
        { duration: '10s', target: FAS_POR_SEGUNDO }, // as vendas abrem
        { duration: '50s', target: FAS_POR_SEGUNDO },
      ],
    },
    cambistas: { executor: 'constant-vus', exec: 'cambista', vus: ROBOS_CAMBISTAS, duration: '60s' },
  },
  thresholds: {
    'http_req_duration{name:mapa}': ['p(95)<2000'],
    'http_req_duration{name:compra}': ['p(95)<3000'],
    http_req_failed: ['rate<0.01'],
    maior_compra_por_cpf: [`value<=${LIMITE_POR_CPF}`],
    maior_qtd_meia_na_sessao: [`value<=${COTA_MEIA}`],
  },
  summaryTrendStats: ['med', 'p(95)', 'p(99)', 'max'],
  teardownTimeout: '90s',
};

// --- Ações de um usuário ---

function gerarCpf() {
  const d = Array.from({ length: 9 }, () => Math.floor(Math.random() * 10));
  for (const n of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < n; i++) soma += d[i] * (n + 1 - i);
    d.push(((soma * 10) % 11) % 10);
  }
  return d.join('');
}

function sortear(lista, quantidade = 1) {
  return [...lista].sort(() => Math.random() - 0.5).slice(0, quantidade);
}

function abrirMapa(sessao) {
  const r = http.get(`${INGRESSA}/sessoes/${sessao}/assentos`, { timeout: '30s', tags: { name: 'mapa' } });
  if (r.status === 0 && exec.scenario.name === 'fas') desistiram.add(1); // só fãs desistem
  if (r.status !== 200) return null;
  return r.json('assentos').filter((a) => a.status === 'livre').map((a) => a.codigo);
}

function comprar(sessao, cpf, itens, cartao) {
  const corpo = { sessao_id: sessao, nome: 'Cliente', cpf, email: `${cpf}@exemplo.com`, cartao_token: cartao, itens };
  const r = http.post(`${INGRESSA}/pedidos`, JSON.stringify(corpo), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '30s',
    tags: { name: 'compra' },
  });
  if (r.status === 201) {
    comprasConcluidas.add(1);
    viramConfirmacao.add(itens.length);
  }
  if (r.status === 0 && exec.scenario.name === 'fas') desistiram.add(1); // só fãs desistem
}

// --- Personagens ---

export function fa() {
  fasChegaram.add(1);
  const sessao = sortear(SESSOES)[0];
  const livres = abrirMapa(sessao);
  if (livres === null) return;
  if (livres.length === 0) return esgotado.add(1);

  const quantidade = 1 + Math.floor(Math.random() * 4);
  const itens = sortear(livres, quantidade).map((assento) => ({
    assento,
    tipo: Math.random() < 0.4 ? 'meia' : 'inteira',
  }));
  comprar(sessao, gerarCpf(), itens, `tok_fa_${__VU}`); // ~5% dos cartões são recusados
}

export function cambista() {
  const cpf = CPFS_CAMBISTAS[__VU % CPFS_CAMBISTAS.length];
  const livres = abrirMapa(1);
  if (livres && livres.length >= 2) {
    comprar(1, cpf, sortear(livres, 2).map((assento) => ({ assento, tipo: 'inteira' })), 'tok_aprovado');
  }
  sleep(0.2);
}

// --- Antes e depois ---

export function setup() {
  if (http.get(`${INGRESSA}/health`, { timeout: '10s' }).status !== 200) {
    exec.test.abort('O Ingressa não está respondendo');
  }
  // Toda rodada parte do zero (a configuração dos simuladores é mantida)
  for (const url of [INGRESSA, CINEMA, GATEWAY]) http.post(`${url}/admin/reset`);
  return { comecou: true };
}

export function teardown() {
  // Quem desiste vai embora, mas o servidor continua processando o pedido dele.
  // Espera até 30 s o sistema do cinema terminar antes de conferir.
  let estado = null;
  for (let i = 0; i < 30; i++) {
    const r = http.get(`${CINEMA}/admin/estado`);
    if (r.status === 200) estado = r.json();
    if (estado && estado.fila.na_fila + estado.fila.em_atendimento === 0) break;
    sleep(1);
  }

  // Quem sabe quantos assentos foram vendidos é o cinema
  if (estado) vendidos.add(SESSOES.reduce((total, s) => total + estado.sessoes[s].vendido, 0));

  // As regras de negócio (CPF e meia) só o Ingressa sabe
  let maiorCpf = 0;
  let maiorMeia = 0;
  for (const sessao of SESSOES) {
    const r = http.get(`${INGRESSA}/sessoes/${sessao}/resumo`, { timeout: '10s' });
    if (r.status !== 200) {
      naoRespondeu.add(1);
      return;
    }
    maiorCpf = Math.max(maiorCpf, r.json('maior_compra_por_cpf'));
    maiorMeia = Math.max(maiorMeia, r.json('meia_vendidas'));
  }
  maiorCompraPorCpf.add(maiorCpf);
  maiorQtdMeia.add(maiorMeia);
}

// --- Resumo ---

const DURACAO_S = 60; // duração da venda (setup e teardown não contam)
const COMO_REINICIAR = '    Para destravar: docker compose restart ingressa';

export function handleSummary(data) {
  if (!data.setup_data) {
    const texto = `\n  ⚠️  O Ingressa não está respondendo (provavelmente travou na rodada anterior).\n${COMO_REINICIAR}\n\n`;
    return { stdout: texto };
  }

  const m = (nome) => (data.metrics[nome] ? data.metrics[nome].values : {});
  const n = (nome) => m(nome).count || 0;
  const porSeg = (total) => (total / DURACAO_S).toFixed(1);
  const pct = (parte, total) => (total ? `${Math.round((parte / total) * 100)}%` : '0%');
  const seg = (ms) => (ms === undefined ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
  const meta = (nome) => {
    if (!data.metrics[nome] || !data.metrics[nome].thresholds) return '⚠️ ';
    return Object.values(data.metrics[nome].thresholds).every((t) => t.ok) ? '✅' : '❌';
  };
  const espera = (nome) => {
    const v = m(`http_req_duration{name:${nome}}`);
    return `metade em até ${seg(v.med)}, 95% em até ${seg(v['p(95)'])}, o pior ${seg(v.max)}`;
  };

  const naoEntraram = n('dropped_iterations');
  const entraram = n('fas_chegaram');
  const fas = entraram + naoEntraram;
  const enviadas = n('http_reqs');
  const falhas = m('http_req_failed').passes || 0;
  const respondidas = enviadas - falhas;
  const compras = n('compras_concluidas');

  const regras = m('ingressa_nao_respondeu').value
    ? `  ⚠️  Não deu para conferir as regras: o Ingressa TRAVOU e não respondeu
      nem depois que o público foi embora.
  ${COMO_REINICIAR}`
    : `  ${meta('maior_compra_por_cpf')} No máximo ${LIMITE_POR_CPF} ingressos por CPF ................ maior compra: ${m('maior_compra_por_cpf').value}
  ${meta('maior_qtd_meia_na_sessao')} No máximo ${COTA_MEIA} meias por sessão (40%) ........ maior venda: ${m('maior_qtd_meia_na_sessao').value}`;

  const texto = `
════════════════════════════════════════════════════════════════════
  ESTREIA DO MAIOR FILME DA HISTÓRIA: 1 minuto de vendas
════════════════════════════════════════════════════════════════════

  1. A CARGA (o que o teste mandou para o Ingressa)

  Fãs que chegaram ............................ ${fas}
     ${FAS_POR_SEGUNDO} novos por segundo, mais ${ROBOS_CAMBISTAS} robôs cambistas comprando sem parar
  Pico de usuários ao mesmo tempo ............. ${m('vus').max || 0}
     fãs e robôs esperando uma resposta no mesmo instante
  Requisições enviadas ........................ ${enviadas}  (${porSeg(enviadas)} por segundo)
     até 2 por fã (abrir o mapa e comprar), mais as dos robôs

  2. O QUE O INGRESSA CONSEGUIU ATENDER

  Requisições respondidas ..................... ${respondidas}  (${porSeg(respondidas)} por segundo)
     é a VAZÃO real do sistema; as outras ${falhas} ficaram sem resposta ou deram erro
  Compras concluídas .......................... ${compras}  (${porSeg(compras)} por segundo)
  Ingressos vendidos .......................... ${m('ingressos_vendidos').value || 0} de ${SESSOES.length * 400}
     contados no sistema do cinema, que é o dono dos assentos
  ...e o fã recebeu a confirmação ............. ${n('ingressos_confirmados_para_o_fa')}
     se for menor que o número acima, houve venda para quem já tinha desistido

  3. O QUE O FÃ SENTIU

  Abrir o mapa de assentos .... ${espera('mapa')}
  Concluir a compra ........... ${espera('compra')}
  Desistiram (esperaram 30 s) ................. ${n('desistiram')}  (${pct(n('desistiram'), entraram)} dos que entraram)
  Nem conseguiram entrar ...................... ${naoEntraram}  (${pct(naoEntraram, fas)} dos fãs)
     o site não respondeu nem para começar a carregar
  Encontraram a sessão esgotada ............... ${n('encontraram_esgotado')}

  4. METAS

  ${meta('http_req_duration{name:mapa}')} 95% dos fãs abrem o mapa em até 2 s
  ${meta('http_req_duration{name:compra}')} 95% dos fãs concluem a compra em até 3 s
  ${meta('http_req_failed')} Menos de 1% de requisições com erro ......... ${pct(falhas, enviadas)} com erro
     409 (assento ocupado), 402 (cartão recusado) e 422 (regra) não são
     erros: são respostas corretas do sistema
${regras}
════════════════════════════════════════════════════════════════════
`;
  return { stdout: texto, '/relatorios/estreia.txt': texto };
}
