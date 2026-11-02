// ESTREIA DO MAIOR FILME DA HISTÓRIA
//
// Uma rodada, duas partes:
//
//   1. A SUBIDA: antes do pico, os usuários chegam em degraus (1 por segundo, 2, 3...).
//      Em cada degrau conferimos se o site continua viável. É assim que
//      descobrimos até quantos usuários o Ingressa aguenta.
//
//   2. O PICO: as vendas abrem e, por 1 minuto, chegam ao mesmo tempo:
//      - usuários: abrem o mapa e compram de 1 a 4 ingressos (alguns meia-entrada).
//        Se o site não carregar em 60 s, desistem. Depois de clicar em comprar,
//        esperam a resposta.
//      - usuários muito engajados: nunca desistem; tentam de novo até comprar ou esgotar
//      - cambistas: robôs com poucos CPFs comprando sem parar, tentando furar o limite
//
// No final: relatorios/estreia.html (para projetar) e um resumo no terminal.
//
//   docker compose run --rm --service-ports k6 run /scripts/estreia.js
//   docker compose run --rm --service-ports k6 run -e USUARIOS=100 /scripts/estreia.js

import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter, Gauge, Trend } from 'k6/metrics';
import { gerarHtml } from './relatorio.js';

const INGRESSA = __ENV.BASE_URL || 'http://ingressa:8000';
const CINEMA = 'http://sistema-cinema:8000';
const GATEWAY = 'http://gateway-pagamento:8000';
const ETAPA = __ENV.ETAPA || 'Ingressa';

// O pico
const USUARIOS_NO_PICO = Number(__ENV.USUARIOS || 50);

// A subida: degraus sempre abaixo do pico
const DEGRAUS = (__ENV.DEGRAUS || '1,2,3,4,6,8,12,16,24,32')
  .split(',')
  .map(Number)
  .filter((d) => d < USUARIOS_NO_PICO);
if (DEGRAUS.length === 0) throw new Error('O pico precisa de pelo menos 2 usuários por segundo (-e USUARIOS=2)');
const DURACAO_DEGRAU_S = 15;
const SUBIDA_S = DEGRAUS.length * DURACAO_DEGRAU_S;

const ENGAJADOS_POR_SEGUNDO = Math.max(1, Math.round(USUARIOS_NO_PICO / 10));
const ROBOS_CAMBISTAS = 20;
const PICO_S = 60;

// O usuário comum espera o site carregar por no máximo isso; depois de clicar em
// comprar, todo mundo espera a resposta.
const PACIENCIA = '60s';
const ESPERA_DA_COMPRA = '10m';
const ESPERA_DA_COMPRA_MS = 10 * 60 * 1000;

// O que é um site "viável"
const META_MAPA_MS = 2000;
const META_COMPRA_MS = 5000; // uma compra leva ~2,7 s só esperando o cinema e o gateway
const META_ERROS = 0.01;

// Sessões e cambistas
const SESSOES = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]; // todas da estreia, 400 lugares cada
const CPFS_CAMBISTAS = ['11144477735', '52998224725', '39053344705'];

// --- Métricas ---

// O caminho do usuário (subida e pico são separados pela tag "scenario")
const usuariosEntraram = new Counter('usuarios_entraram');
const usuariosViramMapa = new Counter('usuarios_viram_mapa');
const usuariosTentaramComprar = new Counter('usuarios_tentaram_comprar');
const usuariosCompraram = new Counter('usuarios_compraram');
const desistiram = new Counter('usuarios_desistiram');
const esgotado = new Counter('usuarios_encontraram_esgotado');
const tempoDoUsuario = new Trend('tempo_do_usuario', true); // do momento em que chega até ir embora


// Usuários muito engajados
const engajadosChegaram = new Counter('engajados_chegaram');
const engajadosCompraram = new Counter('engajados_compraram');
const engajadosEsgotado = new Counter('engajados_encontraram_esgotado');
const engajadosTentativas = new Counter('engajados_tentativas');
const engajadosTempo = new Trend('engajados_tempo_ate_comprar', true);

// Compras e ingressos que o comprador viu confirmados
const comprasConcluidas = new Counter('compras_concluidas');
// Requisições recusadas na porta pelo limite (429, a partir da etapa 04)
const barradosNaPorta = new Counter('barrados_na_porta');

// Tempo de quem foi ATENDIDO: um 429 responde na hora e não pode contar como "rápido"
const tempoDoMapa = new Trend('tempo_do_mapa', true);
const tempoDaCompra = new Trend('tempo_da_compra', true);
const ingressosConfirmados = new Counter('ingressos_confirmados');

// Conferidos no final
const vendidos = new Gauge('ingressos_vendidos');
const naoRespondeu = new Gauge('ingressa_nao_respondeu');

// Não são falhas do sistema: compra aceita para processar (202), erros de negócio (402, 409, 422) e a recusa na
// porta pelo limite de compras (429), que é a proteção funcionando
http.setResponseCallback(http.expectedStatuses(200, 201, 202, 402, 409, 422, 429));

// --- Cenários ---

// Cada pessoa esperando ocupa um usuário virtual do k6. Eles são todos criados
// ANTES do teste: criar sob demanda é lento, e o k6 deixaria chegadas de fora
// (contadas como "não conseguiram entrar", sem culpa do Ingressa).
// `vus` = quantas pessoas chegam naquela parte, o pior caso de todas esperando juntas.
function chegada(funcao, stages, vus, extras = {}) {
  return {
    executor: 'ramping-arrival-rate',
    exec: funcao,
    startRate: 0,
    timeUnit: '1s',
    preAllocatedVUs: vus,
    maxVUs: vus,
    stages,
    gracefulStop: '60s', // quem chegou no fim também tem tempo de terminar
    ...extras,
  };
}

const inicioDoPico = `${SUBIDA_S}s`;

// Números separados por parte e por degrau só aparecem no resumo se tiverem uma meta.
// As metas "sempre verdadeiras" abaixo servem apenas para o k6 guardar esses números.
function guardar(metricas, condicao = 'count>=0') {
  return Object.fromEntries(metricas.map((m) => [m, [condicao]]));
}

export const options = {
  scenarios: {
    subida: chegada(
      'usuario',
      DEGRAUS.flatMap((d) => [
        { duration: '2s', target: d },
        { duration: `${DURACAO_DEGRAU_S - 2}s`, target: d },
      ]),
      DEGRAUS.reduce((total, d) => total + d * DURACAO_DEGRAU_S, 0),
    ),
    pico: chegada(
      'usuario',
      [
        { duration: '10s', target: USUARIOS_NO_PICO }, // as vendas abrem
        { duration: `${PICO_S - 10}s`, target: USUARIOS_NO_PICO },
      ],
      USUARIOS_NO_PICO * PICO_S,
      { startTime: inicioDoPico },
    ),
    engajados: chegada(
      'engajado',
      [
        { duration: '10s', target: ENGAJADOS_POR_SEGUNDO },
        { duration: `${PICO_S - 10}s`, target: ENGAJADOS_POR_SEGUNDO },
      ],
      ENGAJADOS_POR_SEGUNDO * PICO_S,
      { startTime: inicioDoPico },
    ),
    cambistas: {
      executor: 'constant-vus',
      exec: 'cambista',
      vus: ROBOS_CAMBISTAS,
      duration: `${PICO_S}s`,
      startTime: inicioDoPico,
    },
  },
  thresholds: {
    // Metas do pico
    'tempo_do_mapa{scenario:pico}': [`p(95)<${META_MAPA_MS}`],
    'tempo_da_compra{scenario:pico}': [`p(95)<${META_COMPRA_MS}`],
    'http_req_failed{scenario:subida}': ['rate>=0'], // para separar os erros do pico (conta feita no resultado)

    // Só para guardar os números
    ...guardar([
      'usuarios_entraram{scenario:pico}',
      'usuarios_viram_mapa{scenario:pico}',
      'usuarios_tentaram_comprar{scenario:pico}',
      'usuarios_compraram{scenario:pico}',
      'usuarios_desistiram{scenario:pico}',
      'usuarios_encontraram_esgotado{scenario:pico}',
      'dropped_iterations{scenario:pico}',
      'http_reqs{scenario:subida}',
      'compras_concluidas{scenario:subida}',
      'barrados_na_porta{scenario:subida}',
      'barrados_na_porta{scenario:pico}',
      ...DEGRAUS.flatMap((d) => [
        `compras_concluidas{degrau:${d}}`,
        `usuarios_entraram{degrau:${d}}`,
        `barrados_na_porta{degrau:${d}}`,
      ]),
    ]),
    ...guardar(
      DEGRAUS.flatMap((d) => [
        `tempo_do_mapa{degrau:${d}}`,
        `tempo_da_compra{degrau:${d}}`,
        `tempo_do_usuario{degrau:${d}}`,
      ]),
      'max>=0',
    ),
    ...guardar(DEGRAUS.map((d) => `http_req_failed{degrau:${d}}`), 'rate>=0'),
  },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
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

// Sorteia `quantidade` itens diferentes, todos com a mesma chance (Fisher-Yates).
// Não use sort(() => Math.random() - 0.5): ele favorece os primeiros da lista.
function sortear(lista, quantidade = 1) {
  const copia = [...lista];
  const n = Math.min(quantidade, copia.length);
  for (let i = 0; i < n; i++) {
    const j = i + Math.floor(Math.random() * (copia.length - i));
    [copia[i], copia[j]] = [copia[j], copia[i]];
  }
  return copia.slice(0, n);
}

function souUsuarioComum() {
  return exec.scenario.name === 'subida' || exec.scenario.name === 'pico';
}

function degrauAtual() {
  const segundos = (Date.now() - exec.scenario.startTime) / 1000;
  return DEGRAUS[Math.min(Math.floor(segundos / DURACAO_DEGRAU_S), DEGRAUS.length - 1)];
}

function abrirMapa(sessao, tags = {}) {
  const timeout = exec.scenario.name === 'engajados' ? ESPERA_DA_COMPRA : PACIENCIA;
  const r = http.get(`${INGRESSA}/sessoes/${sessao}/assentos`, { timeout, tags: { name: 'mapa', ...tags } });
  if (r.status === 429) barradosNaPorta.add(1, tags);
  else tempoDoMapa.add(r.timings.duration, tags);
  if (r.status === 0 && souUsuarioComum()) desistiram.add(1, tags);
  if (r.status !== 200) return null;
  return r.json('assentos').filter((a) => a.status === 'livre').map((a) => a.codigo);
}

function comprar(sessao, cpf, itens, cartao, tags = {}) {
  const corpo = { sessao_id: sessao, nome: 'Cliente', cpf, email: `${cpf}@exemplo.com`, cartao_token: cartao, itens };
  const r = http.post(`${INGRESSA}/pedidos`, JSON.stringify(corpo), {
    headers: { 'Content-Type': 'application/json' },
    timeout: ESPERA_DA_COMPRA,
    tags: { name: 'compra', ...tags },
  });
  let status = r.status;
  let duracao = r.timings.duration;
  if (r.status === 202) {
    // A partir da etapa 03, o pagamento continua em segundo plano: o usuário
    // acompanha o pedido até ele ser confirmado ou recusado
    const inicio = Date.now() - r.timings.duration;
    const id = r.json('id');
    status = 0;
    while (Date.now() - inicio < ESPERA_DA_COMPRA_MS) {
      sleep(0.5);
      const p = http.get(`${INGRESSA}/pedidos/${id}`, { timeout: PACIENCIA, tags: { name: 'pedido', ...tags } });
      const situacao = p.status === 200 ? p.json('status') : null;
      if (situacao === 'confirmado') status = 201;
      if (situacao === 'pagamento_recusado' || situacao === 'cancelado') status = 402;
      if (status !== 0) break;
    }
    duracao = Date.now() - inicio;
  }
  if (status === 201) {
    comprasConcluidas.add(1, tags);
    ingressosConfirmados.add(itens.length, tags);
  }
  if (status === 429) barradosNaPorta.add(1, tags);
  else tempoDaCompra.add(duracao, tags);
  return status;
}

// --- Personagens ---

export function usuario() {
  const tags = exec.scenario.name === 'subida' ? { degrau: String(degrauAtual()) } : {};
  const inicio = Date.now();
  tentarComprar(tags);
  tempoDoUsuario.add(Date.now() - inicio, tags);
}

function tentarComprar(tags) {
  usuariosEntraram.add(1, tags);
  const sessao = sortear(SESSOES)[0];
  const livres = abrirMapa(sessao, tags);
  if (livres === null) return;
  usuariosViramMapa.add(1, tags);
  if (livres.length === 0) return esgotado.add(1, tags);

  const quantidade = 1 + Math.floor(Math.random() * 4);
  const itens = sortear(livres, quantidade).map((assento) => ({
    assento,
    tipo: Math.random() < 0.4 ? 'meia' : 'inteira',
  }));
  usuariosTentaramComprar.add(1, tags);
  // ~5% dos cartões são recusados
  if (comprar(sessao, gerarCpf(), itens, `tok_usuario_${__VU}`, tags) === 201) usuariosCompraram.add(1, tags);
}

export function engajado() {
  engajadosChegaram.add(1);
  const inicio = Date.now();
  const sessoesEsgotadas = new Set();

  // Não desiste: tenta até comprar, até esgotar tudo ou até o teste acabar
  while (sessoesEsgotadas.size < SESSOES.length) {
    engajadosTentativas.add(1);
    const sessao = sortear(SESSOES.filter((s) => !sessoesEsgotadas.has(s)))[0];
    const livres = abrirMapa(sessao);
    if (livres === null) {
      sleep(1); // o site deu erro: respira e tenta de novo
      continue;
    }
    if (livres.length === 0) {
      sessoesEsgotadas.add(sessao);
      continue;
    }
    const itens = sortear(livres, 2).map((assento) => ({ assento, tipo: 'inteira' }));
    if (comprar(sessao, gerarCpf(), itens, `tok_engajado_${__VU}`) === 201) {
      engajadosCompraram.add(1);
      engajadosTempo.add(Date.now() - inicio);
      return;
    }
    sleep(1); // assento ocupado, cartão recusado ou erro: tenta de novo
  }
  engajadosEsgotado.add(1);
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
  // Pedidos ainda em andamento continuam sendo processados no servidor.
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

  // O Ingressa ainda responde depois que o público foi embora?
  if (http.get(`${INGRESSA}/health`, { timeout: '10s' }).status !== 200) naoRespondeu.add(1);
}

// --- Resultado ---

function calcularResultado(data) {
  const v = (nome) => (data.metrics[nome] ? data.metrics[nome].values : {});
  const n = (nome) => v(nome).count || 0;
  const passou = (nome) => {
    if (!data.metrics[nome] || !data.metrics[nome].thresholds) return null;
    return Object.values(data.metrics[nome].thresholds).every((t) => t.ok);
  };
  // Sem nenhuma resposta, o k6 informa 0 ms: tratamos como "sem medida"
  const p95 = (nome) => v(nome)['p(95)'] || undefined;
  const espera = (nome) => ({ mediana: v(nome).med || undefined, p95: p95(nome), pior: v(nome).max || undefined });
  // Sem nenhuma medida, o k6 considera a meta cumprida: aqui ela aparece como "não medida"
  const medida = (texto, nome, semDados) =>
    p95(nome) === undefined ? { texto, ok: null, detalhe: semDados } : { texto, ok: passou(nome) };

  // 1. A subida
  const degraus = DEGRAUS.map((d) => {
    const p95Mapa = p95(`tempo_do_mapa{degrau:${d}}`);
    const p95Compra = p95(`tempo_da_compra{degrau:${d}}`);
    const erros = v(`http_req_failed{degrau:${d}}`).rate;
    const tempoMedio = v(`tempo_do_usuario{degrau:${d}}`).avg;
    const entraram = n(`usuarios_entraram{degrau:${d}}`);
    const barrados = entraram ? n(`barrados_na_porta{degrau:${d}}`) / entraram : 0;
    return {
      usuariosPorSegundo: d,
      comprasPorSegundo: n(`compras_concluidas{degrau:${d}}`) / DURACAO_DEGRAU_S,
      p95Mapa,
      p95Compra,
      erros,
      barrados,
      // Lei de Little: pessoas no site ao mesmo tempo = chegada por segundo × tempo que cada uma fica
      simultaneos: tempoMedio ? Math.round((d * tempoMedio) / 1000) : undefined,
      viavel:
        p95Mapa !== undefined && p95Mapa <= META_MAPA_MS &&
        p95Compra !== undefined && p95Compra <= META_COMPRA_MS &&
        erros !== undefined && erros < META_ERROS &&
        barrados < META_ERROS, // um site que recusa gente não está atendendo todo mundo
    };
  });
  // Capacidade = o maior degrau viável (um degrau azarado no meio não derruba o resultado)
  const viaveis = degraus.filter((d) => d.viavel);
  const capacidade = viaveis.length ? viaveis[viaveis.length - 1] : null;
  const quebrou = degraus.find((d) => !d.viavel && (!capacidade || d.usuariosPorSegundo > capacidade.usuariosPorSegundo)) || null;

  // 2. O pico
  // No pico conta todo mundo: usuários comuns, engajados e robôs (venda é venda)
  const enviadas = n('http_reqs') - n('http_reqs{scenario:subida}');
  const comErro = (v('http_req_failed').passes || 0) - (v('http_req_failed{scenario:subida}').passes || 0);
  const naoEntraram = n('dropped_iterations{scenario:pico}');
  const travou = Boolean(v('ingressa_nao_respondeu').value);
  const totalVendidos = v('ingressos_vendidos').value || 0;

  return {
    etapa: ETAPA,
    lugares: SESSOES.length * 400,
    travou,
    subida: {
      degraus,
      duracaoDegrauS: DURACAO_DEGRAU_S,
      capacidade,
      quebrou,
      // Metade ou mais das requisições falhando: o Ingressa caiu ainda na subida
      caiuEm: degraus.find((d) => d.erros !== undefined && d.erros >= 0.5) || null,
    },
    pico: {
      usuariosPorSegundo: USUARIOS_NO_PICO,
      engajadosPorSegundo: ENGAJADOS_POR_SEGUNDO,
      robos: ROBOS_CAMBISTAS,
      duracaoS: PICO_S,
      funil: {
        chegaram: n('usuarios_entraram{scenario:pico}') + naoEntraram,
        entraram: n('usuarios_entraram{scenario:pico}'),
        viramMapa: n('usuarios_viram_mapa{scenario:pico}'),
        tentaramComprar: n('usuarios_tentaram_comprar{scenario:pico}'),
        compraram: n('usuarios_compraram{scenario:pico}'),
      },
      desistiram: n('usuarios_desistiram{scenario:pico}'),
      barrados: n('barrados_na_porta{scenario:pico}'),
      esgotado: n('usuarios_encontraram_esgotado{scenario:pico}'),
      enviadas,
      respondidas: enviadas - comErro,
      compras: n('compras_concluidas') - n('compras_concluidas{scenario:subida}'),
      // Todas as recusas na porta no pico: usuários comuns, engajados e robôs
      barradosNaPorta: n('barrados_na_porta') - n('barrados_na_porta{scenario:subida}'),
      espera: {
        mapa: espera('tempo_do_mapa{scenario:pico}'),
        compra: espera('tempo_da_compra{scenario:pico}'),
      },
    },
    engajados: {
      chegaram: n('engajados_chegaram'),
      compraram: n('engajados_compraram'),
      aindaEsperando: n('engajados_chegaram') - n('engajados_compraram') - n('engajados_encontraram_esgotado'),
      tentativas: n('engajados_tentativas'),
      tempo: { mediana: v('engajados_tempo_ate_comprar').med, pior: v('engajados_tempo_ate_comprar').max },
    },
    picoSimultaneos: v('vus').max || 0,
    vendidos: totalVendidos,
    // Vendido no cinema, mas ninguém viu a confirmação: a compra ainda não tinha respondido quando o teste acabou
    semConfirmacao: Math.max(0, totalVendidos - n('ingressos_confirmados')),
    metas: {
      mapaMs: META_MAPA_MS,
      compraMs: META_COMPRA_MS,
      erros: META_ERROS,
      lista: [
        medida(`95% dos usuários abrem o mapa em até ${META_MAPA_MS / 1000} s`, 'tempo_do_mapa{scenario:pico}', 'nenhum mapa chegou a abrir'),
        medida(`95% dos usuários concluem a compra em até ${META_COMPRA_MS / 1000} s`, 'tempo_da_compra{scenario:pico}', 'ninguém chegou a comprar'),
        {
          texto: 'Menos de 1% de requisições com erro',
          ok: enviadas ? comErro / enviadas < META_ERROS : null,
          detalhe: enviadas ? `${((comErro / enviadas) * 100).toFixed(1)}% com erro` : 'nenhuma requisição',
        },
      ],
    },
  };
}

// "1 usuário", "2 usuários"
const usuarios = (n) => `${n} ${n === 1 ? 'usuário' : 'usuários'}`;

function gerarTexto(r) {
  const seg = (ms) => (ms === undefined ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
  const pct = (parte, total) => (total ? `${Math.round((parte / total) * 100)}%` : '0%');
  const pctFracao = (x) => (x === undefined ? '—' : `${(x * 100).toFixed(1)}%`);
  const col = (texto, largura) => String(texto).padStart(largura);
  const icone = (ok) => (ok === null ? '⚠️ ' : ok ? '✅' : '❌');
  const s = r.subida;
  const p = r.pico;
  const f = p.funil;
  const e = r.engajados;
  const porSeg = (total) => (total / p.duracaoS).toFixed(1);

  let capacidade;
  if (!s.capacidade) capacidade = `Não aguentou nem ${s.degraus[0].usuariosPorSegundo} usuário por segundo.`;
  else if (!s.quebrou) capacidade = `Aguentou todos os degraus (até ${usuarios(s.capacidade.usuariosPorSegundo)}/s).`;
  else {
    capacidade =
      `Aguenta até ${usuarios(s.capacidade.usuariosPorSegundo)} por segundo (≈ ${s.capacidade.simultaneos} pessoas no site ao mesmo tempo).\n` +
      `    Com ${usuarios(s.quebrou.usuariosPorSegundo)} por segundo, fica inviável.`;
  }

  const degraus = s.degraus.map(
    (d) =>
      `    ${col(d.usuariosPorSegundo, 10)}${col(d.simultaneos === undefined ? '—' : d.simultaneos, 13)}` +
      `${col(d.comprasPorSegundo.toFixed(1), 11)}${col(seg(d.p95Mapa), 11)}${col(seg(d.p95Compra), 12)}` +
      `${col(pctFracao(d.erros), 9)}${col(pctFracao(d.barrados), 10)}    ${d.viavel ? '✅' : '❌'}`,
  );

  return `
════════════════════════════════════════════════════════════════════
  ESTREIA DO MAIOR FILME DA HISTÓRIA · ${r.etapa}
════════════════════════════════════════════════════════════════════

  1. A SUBIDA: até quantos usuários o Ingressa aguenta?

    ${capacidade}

    usuários/s  no site junto  compras/s  95% mapa  95% compra   erros  barrados   viável?
${degraus.join('\n')}

  2. O PICO: ${p.usuariosPorSegundo} usuários/s + ${p.engajadosPorSegundo} engajados/s + ${p.robos} robôs, por 1 minuto

    Usuários que conseguiram comprar ..... ${f.compraram} de ${f.chegaram}  (${pct(f.compraram, f.chegaram)})

    O caminho do usuário
      Chegaram ...................... ${f.chegaram}
      Conseguiram entrar no site .... ${f.entraram}  (${pct(f.entraram, f.chegaram)})
      Viram o mapa de assentos ...... ${f.viramMapa}  (${pct(f.viramMapa, f.chegaram)})
      Tentaram comprar .............. ${f.tentaramComprar}  (${pct(f.tentaramComprar, f.chegaram)})
      Compraram ..................... ${f.compraram}  (${pct(f.compraram, f.chegaram)})
      Desistiram (site não carregou)  ${p.desistiram}
      Barrados na porta (limite) .... ${p.barrados}

    Os usuários muito engajados (nunca desistem)
      Compraram ..................... ${e.compraram} de ${e.chegaram}  (${pct(e.compraram, e.chegaram)})
      Ainda esperando no fim ........ ${e.aindaEsperando}
      Tempo até comprar ............. metade em até ${seg(e.tempo.mediana)}, o pior ${seg(e.tempo.pior)}

    O sistema
      Pico de usuários ao mesmo tempo ${r.picoSimultaneos}
      Requisições por segundo ....... ${porSeg(p.respondidas)} respondidas de ${porSeg(p.enviadas)} enviadas
      Compras por segundo ........... ${porSeg(p.compras)}
      Barrados na porta ............. ${p.barradosNaPorta}  (${porSeg(p.barradosNaPorta)} por segundo)

    A espera
      Abrir o mapa .... metade em até ${seg(p.espera.mapa.mediana)}, 95% em até ${seg(p.espera.mapa.p95)}, o pior ${seg(p.espera.mapa.pior)}
      Comprar ......... metade em até ${seg(p.espera.compra.mediana)}, 95% em até ${seg(p.espera.compra.p95)}, o pior ${seg(p.espera.compra.pior)}

  INGRESSOS VENDIDOS: ${r.vendidos} de ${r.lugares}

  METAS DO PICO
${r.metas.lista.map((meta) => `    ${icone(meta.ok)} ${meta.texto}${meta.detalhe ? ` (${meta.detalhe})` : ''}`).join('\n')}
${r.subida.caiuEm ? `\n  ⚠️  O Ingressa CAIU ainda na subida (com ${usuarios(r.subida.caiuEm.usuariosPorSegundo)}/s), antes de o pico começar.\n` : ''}${r.travou ? '\n  ⚠️  O Ingressa TRAVOU e não voltou. Para destravar: docker compose restart ingressa\n' : ''}
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
