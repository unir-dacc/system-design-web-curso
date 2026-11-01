// ESTREIA DO MAIOR FILME DA HISTÓRIA
//
// As vendas abrem e uma multidão tenta comprar ao mesmo tempo:
//   - fãs: chegam aos montes, abrem o mapa e compram de 1 a 4 ingressos (alguns meia-entrada)
//   - cambistas: robôs com poucos CPFs comprando sem parar, tentando furar o limite
//
// Os fãs continuam chegando mesmo se o site estiver lento. Quem espera mais
// de 30 s desiste. No final, o resultado aparece no terminal e em
// relatorios/estreia.html (para abrir no navegador e mostrar para a turma).
//
//   docker compose run --rm --service-ports k6 run /scripts/estreia.js
//   docker compose run --rm --service-ports k6 run -e FAS=100 /scripts/estreia.js

import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter, Gauge } from 'k6/metrics';
import { gerarHtml } from './relatorio.js';

const INGRESSA = __ENV.BASE_URL || 'http://ingressa:8000';
const CINEMA = 'http://sistema-cinema:8000';
const GATEWAY = 'http://gateway-pagamento:8000';

const ETAPA = __ENV.ETAPA || 'Ingressa';
const FAS_POR_SEGUNDO = Number(__ENV.FAS || 50);
const ROBOS_CAMBISTAS = 20;
const DURACAO_S = 60;
const SESSOES = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]; // todas da estreia, 400 lugares cada
const LIMITE_POR_CPF = 6;
const COTA_MEIA = 160; // 40% de 400

// Três CPFs válidos usados por todos os robôs cambistas
const CPFS_CAMBISTAS = ['11144477735', '52998224725', '39053344705'];

// O caminho do fã (funil)
const fasEntraram = new Counter('fas_entraram');
const fasViramMapa = new Counter('fas_viram_mapa');
const fasTentaramComprar = new Counter('fas_tentaram_comprar');
const fasCompraram = new Counter('fas_compraram');
const desistiram = new Counter('fas_desistiram');
const esgotado = new Counter('fas_encontraram_esgotado');

// Vendas (fãs e robôs)
const comprasConcluidas = new Counter('compras_concluidas');
const ingressosConfirmados = new Counter('ingressos_confirmados');

// Conferidos no final
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
        { duration: `${DURACAO_S - 10}s`, target: FAS_POR_SEGUNDO },
      ],
    },
    cambistas: { executor: 'constant-vus', exec: 'cambista', vus: ROBOS_CAMBISTAS, duration: `${DURACAO_S}s` },
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

function souFa() {
  return exec.scenario.name === 'fas';
}

function abrirMapa(sessao) {
  const r = http.get(`${INGRESSA}/sessoes/${sessao}/assentos`, { timeout: '30s', tags: { name: 'mapa' } });
  if (r.status === 0 && souFa()) desistiram.add(1);
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
    ingressosConfirmados.add(itens.length);
  }
  if (r.status === 0 && souFa()) desistiram.add(1);
  return r.status;
}

// --- Personagens ---

export function fa() {
  fasEntraram.add(1);
  const sessao = sortear(SESSOES)[0];
  const livres = abrirMapa(sessao);
  if (livres === null) return;
  fasViramMapa.add(1);
  if (livres.length === 0) return esgotado.add(1);

  const quantidade = 1 + Math.floor(Math.random() * 4);
  const itens = sortear(livres, quantidade).map((assento) => ({
    assento,
    tipo: Math.random() < 0.4 ? 'meia' : 'inteira',
  }));
  fasTentaramComprar.add(1);
  if (comprar(sessao, gerarCpf(), itens, `tok_fa_${__VU}`) === 201) fasCompraram.add(1); // ~5% dos cartões são recusados
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

// --- Resultado ---

function calcularResultado(data) {
  const m = (nome) => (data.metrics[nome] ? data.metrics[nome].values : {});
  const n = (nome) => m(nome).count || 0;
  const passou = (nome) => {
    if (!data.metrics[nome] || !data.metrics[nome].thresholds) return null;
    return Object.values(data.metrics[nome].thresholds).every((t) => t.ok);
  };
  const espera = (nome) => {
    const v = m(`http_req_duration{name:${nome}}`);
    return { mediana: v.med, p95: v['p(95)'], pior: v.max };
  };

  const naoEntraram = n('dropped_iterations');
  const enviadas = n('http_reqs');
  const comErro = m('http_req_failed').passes || 0;
  const travou = Boolean(m('ingressa_nao_respondeu').value);

  return {
    etapa: ETAPA,
    fasPorSegundo: FAS_POR_SEGUNDO,
    robos: ROBOS_CAMBISTAS,
    duracaoS: DURACAO_S,
    lugares: SESSOES.length * 400,
    travou,
    funil: {
      chegaram: n('fas_entraram') + naoEntraram,
      entraram: n('fas_entraram'),
      viramMapa: n('fas_viram_mapa'),
      tentaramComprar: n('fas_tentaram_comprar'),
      compraram: n('fas_compraram'),
    },
    desistiram: n('fas_desistiram'),
    esgotado: n('fas_encontraram_esgotado'),
    picoSimultaneos: m('vus').max || 0,
    enviadas,
    respondidas: enviadas - comErro,
    comErro,
    compras: n('compras_concluidas'),
    vendidos: m('ingressos_vendidos').value || 0,
    confirmados: n('ingressos_confirmados'),
    espera: { mapa: espera('mapa'), compra: espera('compra') },
    metas: [
      { texto: '95% dos fãs abrem o mapa em até 2 s', ok: passou('http_req_duration{name:mapa}') },
      { texto: '95% dos fãs concluem a compra em até 3 s', ok: passou('http_req_duration{name:compra}') },
      { texto: 'Menos de 1% de requisições com erro', ok: passou('http_req_failed') },
      {
        texto: `No máximo ${LIMITE_POR_CPF} ingressos por CPF`,
        ok: travou ? null : passou('maior_compra_por_cpf'),
        detalhe: travou ? 'não conferido' : `maior compra: ${m('maior_compra_por_cpf').value}`,
      },
      {
        texto: `No máximo ${COTA_MEIA} meias-entradas por sessão`,
        ok: travou ? null : passou('maior_qtd_meia_na_sessao'),
        detalhe: travou ? 'não conferido' : `maior venda: ${m('maior_qtd_meia_na_sessao').value}`,
      },
    ],
  };
}

function gerarTexto(r) {
  const porSeg = (total) => (total / r.duracaoS).toFixed(1);
  const pct = (parte, total) => (total ? `${Math.round((parte / total) * 100)}%` : '0%');
  const seg = (ms) => (ms === undefined ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
  const espera = (e) => `metade em até ${seg(e.mediana)}, 95% em até ${seg(e.p95)}, o pior ${seg(e.pior)}`;
  const icone = (ok) => (ok === null ? '⚠️ ' : ok ? '✅' : '❌');
  const f = r.funil;

  return `
════════════════════════════════════════════════════════════════════
  ESTREIA DO MAIOR FILME DA HISTÓRIA · ${r.etapa}
  ${r.fasPorSegundo} fãs chegando por segundo + ${r.robos} robôs cambistas, por 1 minuto
════════════════════════════════════════════════════════════════════

  O CAMINHO DO FÃ
    Chegaram ........................ ${f.chegaram}
    Conseguiram entrar no site ...... ${f.entraram}  (${pct(f.entraram, f.chegaram)})
    Viram o mapa de assentos ........ ${f.viramMapa}  (${pct(f.viramMapa, f.chegaram)})
    Tentaram comprar ................ ${f.tentaramComprar}  (${pct(f.tentaramComprar, f.chegaram)})
    Compraram ....................... ${f.compraram}  (${pct(f.compraram, f.chegaram)})
    Desistiram depois de 30 s ....... ${r.desistiram}

  O SISTEMA
    Pico de usuários ao mesmo tempo . ${r.picoSimultaneos}
    Requisições por segundo ......... ${porSeg(r.respondidas)} respondidas de ${porSeg(r.enviadas)} enviadas
    Compras por segundo ............. ${porSeg(r.compras)}
    Ingressos vendidos .............. ${r.vendidos} de ${r.lugares}  (confirmados para o cliente: ${r.confirmados})

  A ESPERA
    Abrir o mapa .... ${espera(r.espera.mapa)}
    Comprar ......... ${espera(r.espera.compra)}

  METAS
${r.metas.map((meta) => `    ${icone(meta.ok)} ${meta.texto}${meta.detalhe ? ` (${meta.detalhe})` : ''}`).join('\n')}
${r.travou ? '\n  ⚠️  O Ingressa TRAVOU e não voltou. Para destravar: docker compose restart ingressa\n' : ''}
  Relatório para projetar: relatorios/estreia.html
════════════════════════════════════════════════════════════════════
`;
}

export function handleSummary(data) {
  if (!data.setup_data) {
    return {
      stdout:
        '\n  ⚠️  O Ingressa não está respondendo (provavelmente travou na rodada anterior).\n' +
        '     Para destravar: docker compose restart ingressa\n\n',
    };
  }
  const resultado = calcularResultado(data);
  return {
    stdout: gerarTexto(resultado),
    '/relatorios/estreia.txt': gerarTexto(resultado),
    '/relatorios/estreia.html': gerarHtml(resultado),
  };
}
