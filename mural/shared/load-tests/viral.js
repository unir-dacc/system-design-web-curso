// O DIA EM QUE UM POST VIRALIZOU
//
// O Mural já tem 100 mil usuários e 1 milhão de posts quando a maior
// celebridade da rede publica um post que todo mundo quer ver. Uma rodada,
// duas partes:
//
//   1. A SUBIDA: as requisições chegam em degraus (2 por segundo, 5, 10...).
//      Em cada degrau conferimos se o Mural continua viável. É assim que
//      descobrimos quantas requisições por segundo ele aguenta.
//
//   2. O PICO: por 30 segundos chega todo mundo de uma vez. De cada 100 requisições:
//      - 70 abrem o feed. A maioria das pessoas fica na primeira página,
//        algumas rolam um pouco, e poucas vão bem fundo. Quem rola pede uma
//        página depois da outra;
//      - 10 abrem um perfil (às vezes o da celebridade);
//      - 10 abrem um post com os comentários;
//      - 7 curtem, 2 publicam e 1 comenta.
//      No pico, a maior parte das curtidas, dos comentários e das visitas a
//      posts vai para o post viral. Quem espera desiste depois de 5 s.
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
const ETAPA = __ENV.ETAPA || 'Mural';
// O que é limitado nesta etapa: o banco (aparece na comparação entre etapas)
const HARDWARE = __ENV.HARDWARE || 'Postgres 1 CPU / 1 GB';

// Cada rodada salva um resumo em relatorios/viral.json. O relatório compara a
// rodada atual com o último resumo das etapas ANTERIORES. As seguintes ficam de
// fora: o resultado de uma aula que ainda não aconteceu não pode aparecer.
const PASTAS_DAS_ETAPAS = ['01-ponto-de-partida', '02-codigo-robusto'];
const ETAPAS_ANTERIORES = new SharedArray('etapas anteriores', () =>
  PASTAS_DAS_ETAPAS.flatMap((pasta) => {
    try {
      return [JSON.parse(open(`/curso/${pasta}/relatorios/viral.json`))];
    } catch (e) {
      return []; // essa etapa ainda não rodou o teste
    }
  }).filter((resumo) => resumo.etapa.localeCompare(ETAPA) < 0),
);

// O pico: requisições por segundo durante 30 segundos
const PICO = Number(__ENV.PICO || 1000);
const PICO_S = 30;

// A subida: cada degrau tem 2× a 2,5× o anterior, sempre abaixo do pico. Poucos
// degraus e curtos, para o teste inteiro caber em uns 2 minutos de aula
const DEGRAUS = (__ENV.DEGRAUS || '1,2,5,10,20,50,100,200,500')
  .split(',')
  .map(Number)
  .filter((d) => d < PICO);
// Cada degrau dura 10 s, mas nunca menos que o tempo de chegarem 30
// requisições: com poucas, os "95% em até" do degrau seriam só o pior caso
const DURACAO_DEGRAU_S = 10;
const MINIMO_DE_REQUISICOES = 30;
const DURACOES = DEGRAUS.map((d) => Math.max(DURACAO_DEGRAU_S, Math.ceil(MINIMO_DE_REQUISICOES / d)));
const INICIOS = DURACOES.map((_, i) => DURACOES.slice(0, i).reduce((s, x) => s + x, 0));
const SUBIDA_S = DURACOES.reduce((s, x) => s + x, 0);

// O público: de cada 100 requisições
const MISTURA = [
  ['feed', 70],
  ['perfil', 10],
  ['post', 10],
  ['curtir', 7],
  ['publicar', 2],
  ['comentar', 1],
];
// No pico, quanto vai para o post viral
const FRACAO_VIRAL = { post: 0.5, curtir: 0.8, comentar: 0.8 };
// Dos perfis abertos, quantos são o da celebridade
const FRACAO_PERFIL_DA_CELEBRIDADE = 0.2;

// Quanto tempo cada um espera antes de desistir
const PACIENCIA_S = 5;
const PACIENCIA = `${PACIENCIA_S}s`;

// O que é um Mural "viável"
const META_FEED_MS = 500;
const META_ESCRITA_MS = 1000;
const META_ERROS = 0.01;

const ENDPOINTS = {
  feed: 'GET /feed',
  perfil: 'GET /usuarios/{id}',
  post: 'GET /posts/{id}',
  curtir: 'POST /posts/{id}/curtidas',
  publicar: 'POST /posts',
  comentar: 'POST /posts/{id}/comentarios',
};
const ESCRITAS = ['curtir', 'publicar', 'comentar'];
const RESULTADOS = ['ok', 'erro', 'barrada'];

// --- Métricas ---

const tempo = new Trend('tempo', true); // só de quem foi atendido
const requisicoes = new Counter('requisicoes');
const curtidasRegistradas = new Gauge('curtidas_registradas'); // as curtidas gravadas no banco, no fim
const curtidasContadas = new Gauge('curtidas_contadas'); // o total que o Mural mostra no fim
const naoRespondeu = new Gauge('nao_respondeu');

// Não são falhas do sistema: a curtida repetida (200), o que não existe (404),
// o texto inválido (422) e a recusa na porta (429)
http.setResponseCallback(http.expectedStatuses(200, 201, 404, 422, 429));

// --- Cenários ---

// Cada requisição esperando ocupa um usuário virtual do k6, criados ANTES do
// teste. No pior caso, todos esperam até desistir: chegada × paciência.
function chegada(stages, porSegundoNoMaximo, extras = {}) {
  const vus = Math.ceil(porSegundoNoMaximo * (PACIENCIA_S + 1));
  return {
    executor: 'ramping-arrival-rate',
    exec: 'acesso',
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
      DEGRAUS.flatMap((d, i) => [
        { duration: '2s', target: d },
        { duration: `${DURACOES[i] - 2}s`, target: d },
      ]),
      Math.max(...DEGRAUS),
    ),
    pico: chegada(
      [
        { duration: '5s', target: PICO }, // a notícia do post se espalha
        { duration: `${PICO_S - 5}s`, target: PICO },
      ],
      PICO,
      { startTime: `${SUBIDA_S}s` },
    ),
  },
  thresholds: {
    [`tempo{endpoint:feed,parte:pico}`]: [`p(95)<${META_FEED_MS}`],
    // Cada endpoint no pico, e cada endpoint em cada degrau da subida
    ...guardar(Object.keys(ENDPOINTS).flatMap((endpoint) => RESULTADOS.map((resultado) => `requisicoes{endpoint:${endpoint},parte:pico,resultado:${resultado}}`))),
    ...guardar(Object.keys(ENDPOINTS).map((endpoint) => `tempo{endpoint:${endpoint},parte:pico}`), 'max>=0'),
    ...guardar(DEGRAUS.flatMap((d) => RESULTADOS.map((resultado) => `requisicoes{degrau:${d},resultado:${resultado}}`))),
    ...guardar(
      DEGRAUS.flatMap((d) =>
        Object.keys(ENDPOINTS).flatMap((endpoint) => RESULTADOS.map((resultado) => `requisicoes{degrau:${d},endpoint:${endpoint},resultado:${resultado}}`)),
      ),
    ),
    ...guardar(
      DEGRAUS.flatMap((d) => [...Object.keys(ENDPOINTS).map((endpoint) => `tempo{degrau:${d},endpoint:${endpoint}}`), `tempo{degrau:${d},tipo:escrita}`]),
      'max>=0',
    ),
    ...guardar(['dropped_iterations{scenario:pico}', 'dropped_iterations{scenario:subida}']),
  },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  setupTimeout: '120s',
  teardownTimeout: '60s',
};

// --- Ações ---

function degrauAtual() {
  const segundos = (Date.now() - exec.scenario.startTime) / 1000;
  let i = 0;
  while (i + 1 < DEGRAUS.length && INICIOS[i + 1] <= segundos) i += 1;
  return DEGRAUS[i];
}

const noPico = () => exec.scenario.name === 'pico';

// Conta a requisição no seu endpoint. Um 429 é contado à parte e não entra no
// tempo, para uma recusa instantânea não parecer "rápida".
function medir(endpoint, r, esperados) {
  const parte = noPico() ? 'pico' : 'subida';
  const tags = { endpoint, parte, tipo: ESCRITAS.includes(endpoint) ? 'escrita' : 'leitura' };
  if (parte === 'subida') tags.degrau = String(degrauAtual());
  const resultado = r.status === 429 ? 'barrada' : esperados.includes(r.status) ? 'ok' : 'erro';
  requisicoes.add(1, { ...tags, resultado });
  if (resultado === 'ok') tempo.add(r.timings.duration, tags);
  return resultado === 'ok';
}

const sortear = (lista) => lista[Math.floor(Math.random() * lista.length)];
const entre = (de, ate) => de + Math.floor(Math.random() * (ate - de + 1));

// Até onde cada pessoa rola o feed: a maioria fica na primeira página,
// algumas rolam um pouco, e poucas vão bem fundo
function ateOndeRola() {
  const sorteio = Math.random();
  if (sorteio < 0.6) return 1;
  if (sorteio < 0.9) return entre(2, 5);
  return entre(6, 20);
}

// Quem rola o feed pede uma página depois da outra, como num app de verdade.
// Cada usuário virtual do k6 lembra onde parou: da próxima vez que abrir o
// feed, pede a página seguinte. Cada página é uma requisição.
let rolagem = null;

function abrirFeed(rede) {
  if (!rolagem) rolagem = { usuario: sortear(rede.usuarios), pagina: 1, ate: ateOndeRola(), antesDe: null };
  // A próxima página vai de dois jeitos, e cada etapa usa o seu: o número da
  // página (OFFSET) ou o cursor, o criado_em do último post visto (antes_de)
  const cursor = rolagem.antesDe ? `&antes_de=${encodeURIComponent(rolagem.antesDe)}` : '';
  const r = enviar('GET', `/feed?usuario_id=${rolagem.usuario}&pagina=${rolagem.pagina}${cursor}`, null, 'feed');
  if (!medir('feed', r, [200]) || rolagem.pagina >= rolagem.ate) {
    rolagem = null; // chegou até onde queria (ou desistiu)
    return;
  }
  const posts = r.json();
  if (!posts.length) {
    rolagem = null; // o feed acabou
    return;
  }
  rolagem.pagina += 1;
  rolagem.antesDe = posts[posts.length - 1].criado_em;
}

function postAlvo(rede, endpoint) {
  return noPico() && Math.random() < FRACAO_VIRAL[endpoint] ? rede.viral : sortear(rede.posts);
}

function enviar(metodo, caminho, corpo, endpoint) {
  const params = { timeout: PACIENCIA, tags: { name: endpoint }, headers: { 'Content-Type': 'application/json' } };
  return metodo === 'GET' ? http.get(`${BASE}${caminho}`, params) : http.post(`${BASE}${caminho}`, JSON.stringify(corpo), params);
}

function texto() {
  return `Post do teste de carga ${exec.vu.idInTest}-${Date.now()}`;
}

// --- O público ---

const TOTAL_DA_MISTURA = MISTURA.reduce((s, [, peso]) => s + peso, 0);
function sortearAcao() {
  let sorteio = Math.random() * TOTAL_DA_MISTURA;
  for (const [acao, peso] of MISTURA) {
    if ((sorteio -= peso) < 0) return acao;
  }
  return MISTURA[0][0];
}

export function acesso(rede) {
  const eu = entre(1, rede.totalDeUsuarios);
  const acao = sortearAcao();
  if (acao === 'feed') {
    return abrirFeed(rede);
  }
  if (acao === 'perfil') {
    const quem = Math.random() < FRACAO_PERFIL_DA_CELEBRIDADE ? rede.celebridade : sortear(rede.usuarios);
    return medir('perfil', enviar('GET', `/usuarios/${quem}`, null, 'perfil'), [200]);
  }
  if (acao === 'post') {
    return medir('post', enviar('GET', `/posts/${postAlvo(rede, 'post')}`, null, 'post'), [200]);
  }
  if (acao === 'curtir') {
    const post = postAlvo(rede, 'curtir');
    // 201: curtida nova. 200: essa pessoa já tinha curtido
    return medir('curtir', enviar('POST', `/posts/${post}/curtidas`, { usuario_id: eu }, 'curtir'), [200, 201]);
  }
  if (acao === 'publicar') {
    return medir('publicar', enviar('POST', '/posts', { usuario_id: eu, texto: texto() }, 'publicar'), [201]);
  }
  medir('comentar', enviar('POST', `/posts/${postAlvo(rede, 'comentar')}/comentarios`, { usuario_id: eu, texto: 'Que post!' }, 'comentar'), [201]);
}

// --- Antes e depois ---

export function setup() {
  if (http.get(`${BASE}/health`, { timeout: '10s' }).status !== 200) exec.test.abort('O Mural não está respondendo');
  // Toda rodada parte do zero: apaga o que a rodada anterior criou
  http.post(`${BASE}/admin/reset`, null, { timeout: '120s' });
  const amostra = http.get(`${BASE}/admin/amostra?quantidade=1000`, { timeout: '60s' }).json();
  // A celebridade publica o post que vai viralizar
  const r = http.post(`${BASE}/posts`, JSON.stringify({ usuario_id: amostra.celebridade, texto: 'Vocês não vão acreditar no que aconteceu hoje 😱' }), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '60s',
  });
  if (r.status !== 201) exec.test.abort('Não deu para publicar o post viral');
  return {
    usuarios: amostra.usuarios,
    posts: amostra.posts,
    totalDeUsuarios: amostra.total_de_usuarios,
    celebridade: amostra.celebridade,
    viral: r.json('id'),
  };
}

export function teardown(rede) {
  sleep(2);
  // O Mural ainda responde depois que o público foi embora?
  if (http.get(`${BASE}/health`, { timeout: '10s' }).status !== 200) {
    naoRespondeu.add(1);
    return;
  }
  // Quantas curtidas o post viral tem de verdade (as linhas gravadas no banco),
  // e quantas o Mural mostra? Uma curtida pode ser gravada mesmo depois que
  // quem curtiu desistiu de esperar: por isso o teste pergunta ao banco.
  const registradas = http.get(`${BASE}/admin/curtidas/${rede.viral}`, { timeout: '60s' });
  if (registradas.status === 200) curtidasRegistradas.add(registradas.json('curtidas'));
  const r = http.get(`${BASE}/posts/${rede.viral}`, { timeout: '60s' });
  if (r.status === 200) curtidasContadas.add(r.json('curtidas'));
}

// --- Resultado ---

function calcularResultado(data) {
  const v = (nome) => (data.metrics[nome] ? data.metrics[nome].values : {});
  const n = (nome) => v(nome).count || 0;
  const p95 = (nome) => v(nome)['p(95)'] || undefined;

  // 1. A subida
  const degraus = DEGRAUS.map((d, i) => {
    const conta = (resultado) => n(`requisicoes{degrau:${d},resultado:${resultado}}`);
    const total = conta('ok') + conta('erro') + conta('barrada');
    const p95Feed = p95(`tempo{degrau:${d},endpoint:feed}`);
    const p95Escrita = p95(`tempo{degrau:${d},tipo:escrita}`);
    const erros = total ? (conta('erro') + conta('barrada')) / total : undefined;
    return {
      porSegundo: d,
      atendidasPorSegundo: conta('ok') / DURACOES[i],
      duracaoS: DURACOES[i],
      p95Feed,
      p95Escrita,
      erros,
      viavel:
        p95Feed !== undefined && p95Feed <= META_FEED_MS &&
        (p95Escrita === undefined || p95Escrita <= META_ESCRITA_MS) &&
        erros !== undefined && erros < META_ERROS,
    };
  });
  const viaveis = degraus.filter((d) => d.viavel);
  const capacidade = viaveis.length ? viaveis[viaveis.length - 1] : null;
  const quebrou = degraus.find((d) => !d.viavel && (!capacidade || d.porSegundo > capacidade.porSegundo)) || null;

  // Velocidade por endpoint: no pico, e no último degrau viável da subida (os
  // degraus em que o Mural já caiu fariam qualquer endpoint parecer lento)
  const porEndpoint = (filtro, duracaoS) =>
    Object.entries(ENDPOINTS)
      .map(([endpoint, nome]) => {
        const conta = (resultado) => n(`requisicoes{${filtro(endpoint)},resultado:${resultado}}`);
        const total = conta('ok') + conta('erro') + conta('barrada');
        const t = v(`tempo{${filtro(endpoint)}}`);
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
  const doPico = porEndpoint((endpoint) => `endpoint:${endpoint},parte:pico`, PICO_S);
  const enviadasNoPico = doPico.reduce((s, e) => s + e.total, 0);
  const atendidasNoPico = doPico.reduce((s, e) => s + e.ok, 0);
  const naoEnviadas = n('dropped_iterations{scenario:pico}');

  // A progressão: degrau a degrau, e o pico como último ponto
  const progressao = [
    ...degraus.map((d) => ({ rotulo: `${d.porSegundo}/s`, procura: d.porSegundo, atendidas: d.atendidasPorSegundo, viavel: d.viavel })),
    { rotulo: `pico ${PICO}/s`, procura: PICO, atendidas: atendidasNoPico / PICO_S, viavel: null, pico: true },
  ];

  const feed = doPico.find((e) => e.nome === ENDPOINTS.feed);
  const semResposta = enviadasNoPico + naoEnviadas ? 1 - atendidasNoPico / (enviadasNoPico + naoEnviadas) : null;
  return {
    etapa: ETAPA,
    travou: Boolean(v('nao_respondeu').value),
    subida: {
      degraus,
      duracaoDegrauS: DURACAO_DEGRAU_S,
      minimoDeRequisicoes: MINIMO_DE_REQUISICOES,
      capacidade,
      quebrou,
      caiuEm: degraus.find((d) => d.erros !== undefined && d.erros >= 0.5) || null,
    },
    pico: {
      porSegundo: PICO,
      duracaoS: PICO_S,
      enviadas: enviadasNoPico + naoEnviadas,
      atendidas: atendidasNoPico,
      naoEnviadas,
      feed: feed ? { mediana: feed.mediana, p95: feed.p95, pior: feed.pior } : {},
    },
    // As curtidas do post viral: quantas estão gravadas no banco, e quantas o Mural mostra
    curtidas: { registradas: v('curtidas_registradas').value, contadas: v('curtidas_contadas').value },
    progressao,
    endpoints: {
      capacidade: capacidade
        ? porEndpoint((endpoint) => `degrau:${capacidade.porSegundo},endpoint:${endpoint}`, capacidade.duracaoS)
        : [],
      pico: doPico,
    },
    metas: {
      feedMs: META_FEED_MS,
      escritaMs: META_ESCRITA_MS,
      erros: META_ERROS,
      lista: [
        {
          texto: `95% dos feeds no pico em até ${META_FEED_MS} ms`,
          ok: feed && feed.p95 !== undefined ? feed.p95 <= META_FEED_MS : null,
          detalhe: feed && feed.p95 !== undefined ? undefined : 'nenhum feed respondeu',
        },
        {
          texto: 'Menos de 1% das requisições do pico sem resposta',
          ok: semResposta === null ? null : semResposta < META_ERROS,
          detalhe: semResposta === null ? 'nenhuma requisição' : `${(semResposta * 100).toFixed(1)}% sem resposta`,
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
    p95FeedNoPico: r.pico.feed.p95 === undefined ? null : r.pico.feed.p95,
    curtidasContadas: r.curtidas.registradas ? (r.curtidas.contadas || 0) / r.curtidas.registradas : null,
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
      `    ${col(`${d.porSegundo}/s`, 8)}${col(d.atendidasPorSegundo.toFixed(1), 13)}${col(seg(d.p95Feed), 11)}` +
      `${col(seg(d.p95Escrita), 13)}${col(pct(d.erros), 15)}    ${d.viavel ? '✅' : '❌'}`,
  );
  const tabelaDeEndpoints = (lista) =>
    [
      `    ${linha('endpoint', 30)}${col('req/s', 8)}${col('metade em', 11)}${col('95% em', 9)}${col('o pior', 9)}${col('erros', 8)}${col('barradas', 10)}`,
      ...lista.map(
        (e) =>
          `    ${linha(e.nome, 30)}${col(e.porSegundo.toFixed(1), 8)}${col(seg(e.mediana), 11)}${col(seg(e.p95), 9)}` +
          `${col(seg(e.pior), 9)}${col(pct(e.erros), 8)}${col(pct(e.barradas), 10)}`,
      ),
    ].join('\n');
  const comparacao = r.comparacao.map(
    (c) =>
      `    ${c.atual ? '▶' : ' '} ${linha(c.etapa, 28)}${linha(c.hardware || 'Postgres 1 CPU / 1 GB', 24)}${col(`${c.capacidade}/s`, 9)}` +
      `${col(pct(c.atendidasNoPico), 12)}${col(seg(c.p95FeedNoPico === null ? undefined : c.p95FeedNoPico), 11)}` +
      `${col(pct(c.curtidasContadas), 12)}   ${c.travou ? 'travou' : c.caiuNaSubida ? 'caiu, voltou' : 'ficou de pé'}`,
  );

  return `
════════════════════════════════════════════════════════════════════
  O DIA EM QUE UM POST VIRALIZOU · ${r.etapa}
════════════════════════════════════════════════════════════════════

  1. A SUBIDA: quantas requisições por segundo o Mural aguenta?

    ${capacidade}

    chegando   atendidas/s   95% feed   95% escrita   erros/barradas   viável?
${degraus.join('\n')}

${s.capacidade ? `    Velocidade por endpoint com ${s.capacidade.porSegundo}/s, o último degrau viável\n${tabelaDeEndpoints(r.endpoints.capacidade)}` : '    Nenhum degrau foi viável.'}

  2. O PICO: ${p.porSegundo} requisições/s, por ${p.duracaoS} s

    Atendidas ....................... ${p.atendidas} de ${p.enviadas} (${pct(p.enviadas ? p.atendidas / p.enviadas : 0)})
    Nem chegaram a ser enviadas ..... ${p.naoEnviadas}${p.naoEnviadas ? ' (todos os usuários virtuais estavam esperando)' : ''}
    Feed ............................ metade em até ${seg(p.feed.mediana)}, 95% em até ${seg(p.feed.p95)}, o pior ${seg(p.feed.pior)}

    Velocidade por endpoint
${tabelaDeEndpoints(r.endpoints.pico)}

  AS CURTIDAS DO POST VIRAL: ${r.curtidas.registradas === undefined ? '—' : r.curtidas.registradas} gravadas no banco, ${r.curtidas.contadas === undefined ? '—' : r.curtidas.contadas} mostradas pelo Mural

  METAS DO PICO
${r.metas.lista.map((m) => `    ${icone(m.ok)} ${m.texto}${m.detalhe ? ` (${m.detalhe})` : ''}`).join('\n')}
${s.caiuEm ? `\n  ⚠️  O Mural CAIU ainda na subida (com ${s.caiuEm.porSegundo}/s), antes de o pico começar.\n` : ''}${r.travou ? '\n  ⚠️  O Mural TRAVOU e não voltou. Para destravar: docker compose restart app\n' : ''}
  3. COMPARAÇÃO COM AS ETAPAS ANTERIORES (último resultado de cada uma)

      etapa                       banco                    aguenta   atendidas   95% feed    curtidas     no fim
                                                                      no pico    no pico    mostradas
${comparacao.join('\n')}

  Relatório para projetar: relatorios/viral.html
════════════════════════════════════════════════════════════════════
`;
}

export function handleSummary(data) {
  if (!data.setup_data) {
    return { stdout: '\n  ⚠️  O Mural não está respondendo. Para destravar: docker compose restart app\n\n' };
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
