// O DIA EM QUE O ENCURTADOR BOMBOU
//
// O encurtador já tem 1 milhão de links quando um evento faz todo mundo
// compartilhar links ao mesmo tempo. Uma rodada, duas partes:
//
//   1. A SUBIDA: as requisições chegam em degraus (5 por segundo, 10, 20...).
//      Em cada degrau conferimos se o encurtador continua viável. É assim
//      que descobrimos quantas requisições por segundo ele aguenta.
//
//   2. O PICO: por 1 minuto chegam de uma vez:
//      - quem clica em links (95%). A procura pelos links segue uma curva
//        normal (um sino): poucos links muito acessados no centro, a maioria
//        no meio-termo, e nas pontas links muito raramente acessados.
//        Quem clica espera no máximo 5 s; depois, desiste.
//      - quem cria links (4%) e quem abre as estatísticas de um link (1%)
//      - robôs tentando códigos aleatórios, que quase nunca existem
//
// No final: relatorios/viral.html (para projetar) e um resumo no terminal.
//
//   docker compose run --rm --service-ports k6 run /scripts/viral.js

import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter, Gauge, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import { gerarHtml } from './relatorio.js';

const BASE = __ENV.BASE_URL || 'http://app:8000';
const ETAPA = __ENV.ETAPA || 'Encurtador';
// O hardware do encurtador nesta etapa (aparece na comparação entre etapas)
const HARDWARE = __ENV.HARDWARE || '2 CPUs / 2 GB';

// Cada rodada salva um resumo em relatorios/viral.json. O relatório compara a
// rodada atual com o último resumo das etapas ANTERIORES. As seguintes ficam de
// fora: o resultado de uma aula que ainda não aconteceu não pode aparecer.
const PASTAS_DAS_ETAPAS = ['01-monolito'];
const ETAPAS_ANTERIORES = new SharedArray('etapas anteriores', () =>
  PASTAS_DAS_ETAPAS.flatMap((pasta) => {
    try {
      return [JSON.parse(open(`/curso/${pasta}/relatorios/viral.json`))];
    } catch (e) {
      return []; // essa etapa ainda não rodou o teste
    }
  }).filter((resumo) => resumo.etapa.localeCompare(ETAPA) < 0),
);

// O pico: requisições por segundo durante 1 minuto
const PICO = Number(__ENV.PICO || 2000);
const PICO_S = 60;
const ROBOS_POR_SEGUNDO = 100;

// A subida: cada degrau tem ~1,5× o anterior, sempre abaixo do pico
const DEGRAUS = (__ENV.DEGRAUS || '5,10,20,30,50,75,100,150,200,300,500,750,1000,1500')
  .split(',')
  .map(Number)
  .filter((d) => d < PICO);
const DURACAO_DEGRAU_S = 15;
const SUBIDA_S = DEGRAUS.length * DURACAO_DEGRAU_S;

// O público: de cada 100 requisições, 95 são cliques, 4 criam um link e 1 abre as estatísticas
const FRACAO_CRIAR = 0.04;
const FRACAO_ESTATISTICAS = 0.01;
// A procura pelos links segue uma curva normal sobre uma amostra de links que
// existem: o centro da amostra é o mais acessado, e as pontas, muito raramente
const AMOSTRA = 1000;
// Curva estreita: os links do centro concentram os cliques (o do meio recebe
// ~0,8% de todos), e a mais de 3 desvios do centro eles quase nunca são acessados
const DESVIO = 50;

// Quanto tempo cada um espera antes de desistir
const PACIENCIA_S = 5;
const PACIENCIA = `${PACIENCIA_S}s`;

// O que é um encurtador "viável"
const META_REDIRECIONAR_MS = 300;
const META_CRIAR_MS = 1000;
const META_ERROS = 0.01;

const ENDPOINTS = {
  redirecionar: 'GET /{codigo}',
  criar: 'POST /links',
  estatisticas: 'GET /links/{codigo}/estatisticas',
  robo: 'GET /{codigo} (robôs, inexistente)',
};
const PARTES = ['subida', 'pico'];
const RESULTADOS = ['ok', 'erro', 'barrada'];

// --- Métricas ---

const tempo = new Trend('tempo', true); // só de quem foi atendido
const requisicoes = new Counter('requisicoes');
const cliquesRedirecionados = new Counter('cliques_redirecionados'); // redirecionados com sucesso
const cliquesContados = new Gauge('cliques_contados'); // o que o encurtador registrou, somando todos os links
const naoRespondeu = new Gauge('nao_respondeu');

// Não são falhas do sistema: o redirecionamento (302), o código que não existe
// (404, os robôs), a URL inválida (422) e a recusa na porta (429)
http.setResponseCallback(http.expectedStatuses(200, 201, 302, 404, 422, 429));

// --- Cenários ---

// Cada requisição esperando ocupa um usuário virtual do k6, criados ANTES do
// teste. No pior caso, todos esperam até desistir: chegada × paciência.
function chegada(funcao, stages, porSegundoNoMaximo, extras = {}) {
  const vus = Math.ceil(porSegundoNoMaximo * (PACIENCIA_S + 1));
  return {
    executor: 'ramping-arrival-rate',
    exec: funcao,
    startRate: 0,
    timeUnit: '1s',
    preAllocatedVUs: vus,
    maxVUs: vus,
    stages,
    gracefulStop: '30s',
    ...extras,
  };
}

function guardar(metricas, condicao = 'count>=0') {
  return Object.fromEntries(metricas.map((m) => [m, [condicao]]));
}

export const options = {
  scenarios: {
    subida: chegada(
      'acesso',
      DEGRAUS.flatMap((d) => [
        { duration: '2s', target: d },
        { duration: `${DURACAO_DEGRAU_S - 2}s`, target: d },
      ]),
      Math.max(...DEGRAUS),
    ),
    pico: chegada(
      'acesso',
      [
        { duration: '10s', target: PICO }, // o influenciador posta o link
        { duration: `${PICO_S - 10}s`, target: PICO },
      ],
      PICO,
      { startTime: `${SUBIDA_S}s` },
    ),
    robos: chegada('robo', [{ duration: `${PICO_S}s`, target: ROBOS_POR_SEGUNDO }], ROBOS_POR_SEGUNDO, {
      startTime: `${SUBIDA_S}s`,
      startRate: ROBOS_POR_SEGUNDO,
    }),
  },
  thresholds: {
    [`tempo{endpoint:redirecionar,parte:pico}`]: [`p(95)<${META_REDIRECIONAR_MS}`],
    ...guardar(
      PARTES.flatMap((parte) =>
        Object.keys(ENDPOINTS).flatMap((endpoint) =>
          RESULTADOS.map((resultado) => `requisicoes{endpoint:${endpoint},parte:${parte},resultado:${resultado}}`),
        ),
      ),
    ),
    ...guardar(PARTES.flatMap((parte) => Object.keys(ENDPOINTS).map((endpoint) => `tempo{endpoint:${endpoint},parte:${parte}}`)), 'max>=0'),
    ...guardar(
      DEGRAUS.flatMap((d) => [
        ...RESULTADOS.map((resultado) => `requisicoes{degrau:${d},resultado:${resultado}}`),
      ]),
    ),
    ...guardar(
      DEGRAUS.flatMap((d) => [`tempo{degrau:${d},endpoint:redirecionar}`, `tempo{degrau:${d},endpoint:criar}`]),
      'max>=0',
    ),
    ...guardar(['dropped_iterations{scenario:pico}', 'dropped_iterations{scenario:subida}', 'cliques_redirecionados']),
  },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  teardownTimeout: '60s',
};

// --- Ações ---

function degrauAtual() {
  const segundos = (Date.now() - exec.scenario.startTime) / 1000;
  return DEGRAUS[Math.min(Math.floor(segundos / DURACAO_DEGRAU_S), DEGRAUS.length - 1)];
}

// Conta a requisição no seu endpoint. Um 429 é contado à parte e não entra no
// tempo, para uma recusa instantânea não parecer "rápida".
function medir(endpoint, r, esperados) {
  const parte = exec.scenario.name === 'subida' ? 'subida' : 'pico';
  const tags = { endpoint, parte };
  if (parte === 'subida') tags.degrau = String(degrauAtual());
  const resultado = r.status === 429 ? 'barrada' : esperados.includes(r.status) ? 'ok' : 'erro';
  requisicoes.add(1, { ...tags, resultado });
  if (resultado === 'ok') tempo.add(r.timings.duration, tags);
  return resultado === 'ok';
}

// Um número de uma curva normal (média 0, desvio 1), pelo método de Box-Muller
function normal() {
  const u = 1 - Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * Math.random());
}

// O link do clique: a posição na amostra segue a curva normal. Os do centro
// são muito acessados; os das pontas, muito raramente.
function codigoParaClicar(links) {
  for (;;) {
    const posicao = Math.round(AMOSTRA / 2 + normal() * DESVIO);
    if (posicao >= 0 && posicao < links.codigos.length) return links.codigos[posicao];
  }
}

const ALFABETO = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';
function codigoAleatorio() {
  let c = '';
  for (let i = 0; i < 7; i++) c += ALFABETO[Math.floor(Math.random() * ALFABETO.length)];
  return c;
}

// --- Personagens ---

export function acesso(links) {
  const sorteio = Math.random();
  if (sorteio < FRACAO_CRIAR) {
    const r = http.post(`${BASE}/links`, JSON.stringify({ url: `https://exemplo.com/novo/${exec.vu.idInTest}-${Date.now()}` }), {
      headers: { 'Content-Type': 'application/json' },
      timeout: '10s',
      tags: { name: 'criar' },
    });
    return medir('criar', r, [201]);
  }
  if (sorteio < FRACAO_CRIAR + FRACAO_ESTATISTICAS) {
    const r = http.get(`${BASE}/links/${codigoParaClicar(links)}/estatisticas`, { timeout: PACIENCIA, tags: { name: 'estatisticas' } });
    return medir('estatisticas', r, [200]);
  }
  const codigo = codigoParaClicar(links);
  // redirects: 0 — o k6 não vai até o site de destino, só mede o encurtador
  const r = http.get(`${BASE}/${codigo}`, { redirects: 0, timeout: PACIENCIA, tags: { name: 'redirecionar' } });
  if (medir('redirecionar', r, [302])) cliquesRedirecionados.add(1);
}

export function robo() {
  const r = http.get(`${BASE}/${codigoAleatorio()}`, { redirects: 0, timeout: PACIENCIA, tags: { name: 'robo' } });
  // Raríssimo: o código aleatório existe, e o clique conta como qualquer outro
  if (r.status === 302) cliquesRedirecionados.add(1);
  medir('robo', r, [404, 302]);
}

// --- Antes e depois ---

export function setup() {
  if (http.get(`${BASE}/health`, { timeout: '10s' }).status !== 200) exec.test.abort('O encurtador não está respondendo');
  // Toda rodada parte do zero: apaga os links criados e zera os cliques
  http.post(`${BASE}/admin/reset`, null, { timeout: '120s' });
  // Códigos que existem, em ordem aleatória: a curva normal escolhe entre eles
  const codigos = http.get(`${BASE}/admin/amostra?quantidade=${AMOSTRA}`, { timeout: '60s' }).json('codigos');
  return { codigos };
}

export function teardown(links) {
  sleep(2);
  // O encurtador ainda responde depois que o público foi embora?
  if (http.get(`${BASE}/health`, { timeout: '10s' }).status !== 200) {
    naoRespondeu.add(1);
    return;
  }
  // Quantos cliques o encurtador contou, somando todos os links?
  const r = http.get(`${BASE}/admin/cliques`, { timeout: '60s' });
  if (r.status === 200) cliquesContados.add(r.json('total'));
}

// --- Resultado ---

function calcularResultado(data) {
  const v = (nome) => (data.metrics[nome] ? data.metrics[nome].values : {});
  const n = (nome) => v(nome).count || 0;
  const p95 = (nome) => v(nome)['p(95)'] || undefined;

  // 1. A subida
  const degraus = DEGRAUS.map((d) => {
    const conta = (resultado) => n(`requisicoes{degrau:${d},resultado:${resultado}}`);
    const total = conta('ok') + conta('erro') + conta('barrada');
    const p95Redirecionar = p95(`tempo{degrau:${d},endpoint:redirecionar}`);
    const p95Criar = p95(`tempo{degrau:${d},endpoint:criar}`);
    const erros = total ? (conta('erro') + conta('barrada')) / total : undefined;
    return {
      porSegundo: d,
      atendidasPorSegundo: conta('ok') / DURACAO_DEGRAU_S,
      p95Redirecionar,
      p95Criar,
      erros,
      viavel:
        p95Redirecionar !== undefined && p95Redirecionar <= META_REDIRECIONAR_MS &&
        (p95Criar === undefined || p95Criar <= META_CRIAR_MS) &&
        erros !== undefined && erros < META_ERROS,
    };
  });
  const viaveis = degraus.filter((d) => d.viavel);
  const capacidade = viaveis.length ? viaveis[viaveis.length - 1] : null;
  const quebrou = degraus.find((d) => !d.viavel && (!capacidade || d.porSegundo > capacidade.porSegundo)) || null;

  // Velocidade por endpoint em cada parte
  const porEndpoint = (parte, duracaoS) =>
    Object.entries(ENDPOINTS)
      .map(([endpoint, nome]) => {
        const conta = (resultado) => n(`requisicoes{endpoint:${endpoint},parte:${parte},resultado:${resultado}}`);
        const total = conta('ok') + conta('erro') + conta('barrada');
        const t = v(`tempo{endpoint:${endpoint},parte:${parte}}`);
        return {
          nome,
          porSegundo: total / duracaoS,
          mediana: t.med || undefined,
          p95: t['p(95)'] || undefined,
          pior: t.max || undefined,
          atendidas: total ? conta('ok') / total : 0,
          erros: total ? conta('erro') / total : 0,
          barradas: total ? conta('barrada') / total : 0,
          total,
          ok: conta('ok'),
        };
      })
      .filter((e) => e.total > 0);
  const noPico = porEndpoint('pico', PICO_S);
  const doPublico = noPico.filter((e) => e.nome !== ENDPOINTS.robo);
  const enviadasNoPico = doPublico.reduce((s, e) => s + e.total, 0);
  const atendidasNoPico = doPublico.reduce((s, e) => s + e.ok, 0);
  const naoEnviadas = n('dropped_iterations{scenario:pico}');

  // A progressão: degrau a degrau, e o pico como último ponto
  const progressao = [
    ...degraus.map((d) => ({ rotulo: `${d.porSegundo}/s`, procura: d.porSegundo, atendidas: d.atendidasPorSegundo, viavel: d.viavel })),
    { rotulo: `pico ${PICO}/s`, procura: PICO, atendidas: atendidasNoPico / PICO_S, viavel: null, pico: true },
  ];

  const redirecionar = noPico.find((e) => e.nome === ENDPOINTS.redirecionar);
  return {
    etapa: ETAPA,
    travou: Boolean(v('nao_respondeu').value),
    subida: {
      degraus,
      duracaoDegrauS: DURACAO_DEGRAU_S,
      capacidade,
      quebrou,
      caiuEm: degraus.find((d) => d.erros !== undefined && d.erros >= 0.5) || null,
    },
    pico: {
      porSegundo: PICO,
      robosPorSegundo: ROBOS_POR_SEGUNDO,
      duracaoS: PICO_S,
      enviadas: enviadasNoPico + naoEnviadas,
      atendidas: atendidasNoPico,
      naoEnviadas,
      espera: redirecionar ? { mediana: redirecionar.mediana, p95: redirecionar.p95, pior: redirecionar.pior } : {},
    },
    // Os cliques: quantos foram redirecionados, e quantos o encurtador contou
    cliques: { redirecionados: n('cliques_redirecionados'), contados: v('cliques_contados').value },
    progressao,
    endpoints: { subida: porEndpoint('subida', SUBIDA_S), pico: noPico },
    metas: {
      redirecionarMs: META_REDIRECIONAR_MS,
      criarMs: META_CRIAR_MS,
      erros: META_ERROS,
      lista: [
        {
          texto: `95% dos redirecionamentos no pico em até ${META_REDIRECIONAR_MS} ms`,
          ok: redirecionar && redirecionar.p95 !== undefined ? redirecionar.p95 <= META_REDIRECIONAR_MS : null,
          detalhe: redirecionar && redirecionar.p95 !== undefined ? undefined : 'nenhum redirecionamento respondeu',
        },
        {
          texto: 'Menos de 1% das requisições do pico sem resposta',
          ok: enviadasNoPico + naoEnviadas ? 1 - atendidasNoPico / (enviadasNoPico + naoEnviadas) < META_ERROS : null,
          detalhe: enviadasNoPico + naoEnviadas ? `${((1 - atendidasNoPico / (enviadasNoPico + naoEnviadas)) * 100).toFixed(1)}% sem resposta` : 'nenhuma requisição',
        },
      ],
    },
  };
}

function resumir(r) {
  return {
    etapa: r.etapa,
    hardware: HARDWARE,
    quando: new Date().toISOString(),
    capacidade: r.subida.capacidade ? r.subida.capacidade.porSegundo : 0,
    atendidasNoPico: r.pico.enviadas ? r.pico.atendidas / r.pico.enviadas : 0,
    p95RedirecionarNoPico: r.pico.espera.p95 === undefined ? null : r.pico.espera.p95,
    cliquesContados: r.cliques.redirecionados ? (r.cliques.contados || 0) / r.cliques.redirecionados : null,
    caiuNaSubida: Boolean(r.subida.caiuEm),
    travou: r.travou,
  };
}

function gerarTexto(r) {
  const seg = (ms) => (ms === undefined || ms === null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
  const pct = (x) => (x === undefined || x === null ? '—' : `${(x * 100).toFixed(1)}%`);
  const col = (texto, largura) => String(texto).padStart(largura);
  const linha = (texto, largura) => String(texto).padEnd(largura);
  const icone = (ok) => (ok === null ? '⚠️ ' : ok ? '✅' : '❌');
  const s = r.subida;
  const p = r.pico;

  let capacidade;
  if (!s.capacidade) capacidade = `Não aguentou nem ${s.degraus[0].porSegundo} requisições por segundo.`;
  else if (!s.quebrou) capacidade = `Aguentou todos os degraus (até ${s.capacidade.porSegundo} requisições por segundo).`;
  else capacidade = `Aguenta até ${s.capacidade.porSegundo} requisições por segundo. Com ${s.quebrou.porSegundo}/s, fica inviável.`;

  const degraus = s.degraus.map(
    (d) =>
      `    ${col(`${d.porSegundo}/s`, 8)}${col(d.atendidasPorSegundo.toFixed(1), 13)}${col(seg(d.p95Redirecionar), 15)}` +
      `${col(seg(d.p95Criar), 11)}${col(pct(d.erros), 15)}    ${d.viavel ? '✅' : '❌'}`,
  );
  const tabelaDeEndpoints = (lista) =>
    [
      `    ${linha('endpoint', 36)}${col('req/s', 8)}${col('metade em', 11)}${col('95% em', 9)}${col('o pior', 9)}${col('erros', 8)}${col('barradas', 10)}`,
      ...lista.map(
        (e) =>
          `    ${linha(e.nome, 36)}${col(e.porSegundo.toFixed(1), 8)}${col(seg(e.mediana), 11)}${col(seg(e.p95), 9)}` +
          `${col(seg(e.pior), 9)}${col(pct(e.erros), 8)}${col(pct(e.barradas), 10)}`,
      ),
    ].join('\n');
  const comparacao = r.comparacao.map(
    (c) =>
      `    ${c.atual ? '▶' : ' '} ${linha(c.etapa, 28)}${linha(c.hardware || '2 CPUs / 2 GB', 15)}${col(`${c.capacidade}/s`, 9)}` +
      `${col(pct(c.atendidasNoPico), 12)}${col(seg(c.p95RedirecionarNoPico === null ? undefined : c.p95RedirecionarNoPico), 12)}` +
      `${col(pct(c.cliquesContados), 12)}   ${c.travou ? 'travou' : c.caiuNaSubida ? 'caiu, voltou' : 'ficou de pé'}`,
  );

  return `
════════════════════════════════════════════════════════════════════
  O DIA EM QUE O ENCURTADOR BOMBOU · ${r.etapa}
════════════════════════════════════════════════════════════════════

  1. A SUBIDA: quantas requisições por segundo o encurtador aguenta?

    ${capacidade}

    chegando   atendidas/s   95% redireção   95% criar   erros/barradas   viável?
${degraus.join('\n')}

    Velocidade por endpoint (a subida inteira)
${tabelaDeEndpoints(r.endpoints.subida)}

  2. O PICO: ${p.porSegundo} requisições/s + ${p.robosPorSegundo} robôs/s, por 1 minuto

    Atendidas ....................... ${p.atendidas} de ${p.enviadas} (${pct(p.enviadas ? p.atendidas / p.enviadas : 0)})
    Nem chegaram a ser enviadas ..... ${p.naoEnviadas} (todos os usuários virtuais estavam esperando)
    Redirecionar .................... metade em até ${seg(p.espera.mediana)}, 95% em até ${seg(p.espera.p95)}, o pior ${seg(p.espera.pior)}

    Velocidade por endpoint (todos, inclusive os robôs)
${tabelaDeEndpoints(r.endpoints.pico)}

  OS CLIQUES: ${r.cliques.redirecionados} redirecionados, ${r.cliques.contados === undefined ? '—' : r.cliques.contados} contados pelo encurtador

  METAS DO PICO
${r.metas.lista.map((m) => `    ${icone(m.ok)} ${m.texto}${m.detalhe ? ` (${m.detalhe})` : ''}`).join('\n')}
${s.caiuEm ? `\n  ⚠️  O encurtador CAIU ainda na subida (com ${s.caiuEm.porSegundo}/s), antes de o pico começar.\n` : ''}${r.travou ? '\n  ⚠️  O encurtador TRAVOU e não voltou. Para destravar: docker compose restart app\n' : ''}
  3. COMPARAÇÃO COM AS ETAPAS ANTERIORES (último resultado de cada uma)

      etapa                       hardware        aguenta   atendidas   95% redir.   cliques     no fim
                                                             no pico     no pico    contados
${comparacao.join('\n')}

  Relatório para projetar: relatorios/viral.html
════════════════════════════════════════════════════════════════════
`;
}

export function handleSummary(data) {
  if (!data.setup_data) {
    return { stdout: '\n  ⚠️  O encurtador não está respondendo. Para destravar: docker compose restart app\n\n' };
  }
  const resultado = calcularResultado(data);
  const resumo = resumir(resultado);
  resultado.comparacao = [...ETAPAS_ANTERIORES, { ...resumo, atual: true }].sort((a, b) => a.etapa.localeCompare(b.etapa));
  return {
    stdout: gerarTexto(resultado),
    '/relatorios/viral.txt': gerarTexto(resultado),
    '/relatorios/viral.html': gerarHtml(resultado),
    '/relatorios/viral.json': JSON.stringify(resumo, null, 2),
  };
}
