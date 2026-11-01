// ESTREIA DO MAIOR FILME DA HISTÓRIA
//
// Uma rodada, duas partes:
//
//   1. A SUBIDA: antes do pico, os fãs chegam em degraus (1 por segundo, 2, 3...).
//      Em cada degrau conferimos se o site continua viável. É assim que
//      descobrimos até quantos fãs o Ingressa aguenta.
//
//   2. O PICO: as vendas abrem e, por 1 minuto, chegam ao mesmo tempo:
//      - fãs: abrem o mapa e compram de 1 a 4 ingressos (alguns meia-entrada).
//        Se o site não carregar em 60 s, desistem. Depois de clicar em comprar,
//        esperam a resposta.
//      - fãs muito engajados: nunca desistem; tentam de novo até comprar ou esgotar
//      - cambistas: robôs com poucos CPFs comprando sem parar, tentando furar o limite
//
// No final: relatorios/estreia.html (para projetar) e um resumo no terminal.
//
//   docker compose run --rm --service-ports k6 run /scripts/estreia.js
//   docker compose run --rm --service-ports k6 run -e FAS=100 /scripts/estreia.js

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
const FAS_NO_PICO = Number(__ENV.FAS || 50);

// A subida: degraus sempre abaixo do pico
const DEGRAUS = (__ENV.DEGRAUS || '1,2,3,4,6,8,12,16,24,32')
  .split(',')
  .map(Number)
  .filter((d) => d < FAS_NO_PICO);
if (DEGRAUS.length === 0) throw new Error('O pico precisa de pelo menos 2 fãs por segundo (-e FAS=2)');
const DURACAO_DEGRAU_S = 15;
const SUBIDA_S = DEGRAUS.length * DURACAO_DEGRAU_S;

const ENGAJADOS_POR_SEGUNDO = Math.max(1, Math.round(FAS_NO_PICO / 10));
const ROBOS_CAMBISTAS = 20;
const PICO_S = 60;

// O fã comum espera o site carregar por no máximo isso; depois de clicar em
// comprar, todo mundo espera a resposta.
const PACIENCIA = '60s';
const ESPERA_DA_COMPRA = '10m';

// O que é um site "viável"
const META_MAPA_MS = 2000;
const META_COMPRA_MS = 3000;
const META_ERROS = 0.01;

// Regras de negócio
const SESSOES = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]; // todas da estreia, 400 lugares cada
const LIMITE_POR_CPF = 6;
const COTA_MEIA = 160; // 40% de 400
const CPFS_CAMBISTAS = ['11144477735', '52998224725', '39053344705'];

// --- Métricas ---

// O caminho do fã (subida e pico são separados pela tag "scenario")
const fasEntraram = new Counter('fas_entraram');
const fasViramMapa = new Counter('fas_viram_mapa');
const fasTentaramComprar = new Counter('fas_tentaram_comprar');
const fasCompraram = new Counter('fas_compraram');
const desistiram = new Counter('fas_desistiram');
const esgotado = new Counter('fas_encontraram_esgotado');
const tempoDoFa = new Trend('tempo_do_fa', true); // do momento em que chega até ir embora

// Fãs muito engajados
const engajadosChegaram = new Counter('engajados_chegaram');
const engajadosCompraram = new Counter('engajados_compraram');
const engajadosEsgotado = new Counter('engajados_encontraram_esgotado');
const engajadosTentativas = new Counter('engajados_tentativas');
const engajadosTempo = new Trend('engajados_tempo_ate_comprar', true);

// Compras e ingressos que o comprador viu confirmados
const comprasConcluidas = new Counter('compras_concluidas');
const ingressosConfirmados = new Counter('ingressos_confirmados');

// Conferidos no final
const vendidos = new Gauge('ingressos_vendidos');
const maiorCompraPorCpf = new Gauge('maior_compra_por_cpf');
const maiorQtdMeia = new Gauge('maior_qtd_meia_na_sessao');
const naoRespondeu = new Gauge('ingressa_nao_respondeu');

http.setResponseCallback(http.expectedStatuses(200, 201, 402, 409, 422)); // erros de negócio não são falhas

// --- Cenários ---

function chegada(funcao, stages, extras = {}) {
  return {
    executor: 'ramping-arrival-rate',
    exec: funcao,
    startRate: 0,
    timeUnit: '1s',
    preAllocatedVUs: 50,
    maxVUs: 2500,
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
      'fa',
      DEGRAUS.flatMap((d) => [
        { duration: '2s', target: d },
        { duration: `${DURACAO_DEGRAU_S - 2}s`, target: d },
      ]),
    ),
    pico: chegada(
      'fa',
      [
        { duration: '10s', target: FAS_NO_PICO }, // as vendas abrem
        { duration: `${PICO_S - 10}s`, target: FAS_NO_PICO },
      ],
      { startTime: inicioDoPico },
    ),
    engajados: chegada(
      'engajado',
      [
        { duration: '10s', target: ENGAJADOS_POR_SEGUNDO },
        { duration: `${PICO_S - 10}s`, target: ENGAJADOS_POR_SEGUNDO },
      ],
      { startTime: inicioDoPico, maxVUs: 1000 },
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
    'http_req_duration{name:mapa,scenario:pico}': [`p(95)<${META_MAPA_MS}`],
    'http_req_duration{name:compra,scenario:pico}': [`p(95)<${META_COMPRA_MS}`],
    'http_req_failed{scenario:pico}': [`rate<${META_ERROS}`],
    maior_compra_por_cpf: [`value<=${LIMITE_POR_CPF}`],
    maior_qtd_meia_na_sessao: [`value<=${COTA_MEIA}`],

    // Só para guardar os números
    ...guardar([
      'fas_entraram{scenario:pico}',
      'fas_viram_mapa{scenario:pico}',
      'fas_tentaram_comprar{scenario:pico}',
      'fas_compraram{scenario:pico}',
      'fas_desistiram{scenario:pico}',
      'fas_encontraram_esgotado{scenario:pico}',
      'dropped_iterations{scenario:pico}',
      'http_reqs{scenario:pico}',
      'compras_concluidas{scenario:pico}',
      'ingressos_confirmados{scenario:subida}',
      'ingressos_confirmados{scenario:pico}',
      'ingressos_confirmados{scenario:engajados}',
      'ingressos_confirmados{scenario:cambistas}',
      ...DEGRAUS.flatMap((d) => [`compras_concluidas{degrau:${d}}`, `fas_entraram{degrau:${d}}`]),
    ]),
    ...guardar(
      DEGRAUS.flatMap((d) => [
        `http_req_duration{name:mapa,degrau:${d}}`,
        `http_req_duration{name:compra,degrau:${d}}`,
        `tempo_do_fa{degrau:${d}}`,
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

function sortear(lista, quantidade = 1) {
  return [...lista].sort(() => Math.random() - 0.5).slice(0, quantidade);
}

function souFaComum() {
  return exec.scenario.name === 'subida' || exec.scenario.name === 'pico';
}

function degrauAtual() {
  const segundos = (Date.now() - exec.scenario.startTime) / 1000;
  return DEGRAUS[Math.min(Math.floor(segundos / DURACAO_DEGRAU_S), DEGRAUS.length - 1)];
}

function abrirMapa(sessao, tags = {}) {
  const timeout = exec.scenario.name === 'engajados' ? ESPERA_DA_COMPRA : PACIENCIA;
  const r = http.get(`${INGRESSA}/sessoes/${sessao}/assentos`, { timeout, tags: { name: 'mapa', ...tags } });
  if (r.status === 0 && souFaComum()) desistiram.add(1, tags);
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
  if (r.status === 201) {
    comprasConcluidas.add(1, tags);
    ingressosConfirmados.add(itens.length, tags);
  }
  return r.status;
}

// --- Personagens ---

export function fa() {
  const tags = exec.scenario.name === 'subida' ? { degrau: String(degrauAtual()) } : {};
  const inicio = Date.now();
  tentarComprar(tags);
  tempoDoFa.add(Date.now() - inicio, tags);
}

function tentarComprar(tags) {
  fasEntraram.add(1, tags);
  const sessao = sortear(SESSOES)[0];
  const livres = abrirMapa(sessao, tags);
  if (livres === null) return;
  fasViramMapa.add(1, tags);
  if (livres.length === 0) return esgotado.add(1, tags);

  const quantidade = 1 + Math.floor(Math.random() * 4);
  const itens = sortear(livres, quantidade).map((assento) => ({
    assento,
    tipo: Math.random() < 0.4 ? 'meia' : 'inteira',
  }));
  fasTentaramComprar.add(1, tags);
  if (comprar(sessao, gerarCpf(), itens, `tok_fa_${__VU}`, tags) === 201) fasCompraram.add(1, tags); // ~5% dos cartões são recusados
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
    const p95Mapa = p95(`http_req_duration{name:mapa,degrau:${d}}`);
    const p95Compra = p95(`http_req_duration{name:compra,degrau:${d}}`);
    const erros = v(`http_req_failed{degrau:${d}}`).rate;
    const tempoMedio = v(`tempo_do_fa{degrau:${d}}`).avg;
    return {
      fasPorSegundo: d,
      comprasPorSegundo: n(`compras_concluidas{degrau:${d}}`) / DURACAO_DEGRAU_S,
      p95Mapa,
      p95Compra,
      erros,
      // Lei de Little: pessoas no site ao mesmo tempo = chegada por segundo × tempo que cada uma fica
      simultaneos: tempoMedio ? Math.round((d * tempoMedio) / 1000) : undefined,
      viavel:
        p95Mapa !== undefined && p95Mapa <= META_MAPA_MS &&
        p95Compra !== undefined && p95Compra <= META_COMPRA_MS &&
        erros !== undefined && erros < META_ERROS,
    };
  });
  // Capacidade = o maior degrau viável (um degrau azarado no meio não derruba o resultado)
  const viaveis = degraus.filter((d) => d.viavel);
  const capacidade = viaveis.length ? viaveis[viaveis.length - 1] : null;
  const quebrou = degraus.find((d) => !d.viavel && (!capacidade || d.fasPorSegundo > capacidade.fasPorSegundo)) || null;

  // 2. O pico
  const enviadas = n('http_reqs{scenario:pico}');
  const comErro = v('http_req_failed{scenario:pico}').passes || 0;
  const naoEntraram = n('dropped_iterations{scenario:pico}');
  const travou = Boolean(v('ingressa_nao_respondeu').value);
  const confirmados = {
    subida: n('ingressos_confirmados{scenario:subida}'),
    pico: n('ingressos_confirmados{scenario:pico}'),
    engajados: n('ingressos_confirmados{scenario:engajados}'),
    cambistas: n('ingressos_confirmados{scenario:cambistas}'),
  };
  const totalVendidos = v('ingressos_vendidos').value || 0;
  const totalConfirmados = confirmados.subida + confirmados.pico + confirmados.engajados + confirmados.cambistas;

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
      fasPorSegundo: FAS_NO_PICO,
      engajadosPorSegundo: ENGAJADOS_POR_SEGUNDO,
      robos: ROBOS_CAMBISTAS,
      duracaoS: PICO_S,
      funil: {
        chegaram: n('fas_entraram{scenario:pico}') + naoEntraram,
        entraram: n('fas_entraram{scenario:pico}'),
        viramMapa: n('fas_viram_mapa{scenario:pico}'),
        tentaramComprar: n('fas_tentaram_comprar{scenario:pico}'),
        compraram: n('fas_compraram{scenario:pico}'),
      },
      desistiram: n('fas_desistiram{scenario:pico}'),
      esgotado: n('fas_encontraram_esgotado{scenario:pico}'),
      enviadas,
      respondidas: enviadas - comErro,
      compras: n('compras_concluidas{scenario:pico}'),
      espera: {
        mapa: espera('http_req_duration{name:mapa,scenario:pico}'),
        compra: espera('http_req_duration{name:compra,scenario:pico}'),
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
    confirmados,
    // Vendido no cinema, mas ninguém viu a confirmação: a compra ainda não tinha respondido quando o teste acabou
    semConfirmacao: Math.max(0, totalVendidos - totalConfirmados),
    metas: {
      mapaMs: META_MAPA_MS,
      compraMs: META_COMPRA_MS,
      erros: META_ERROS,
      lista: [
        medida(`95% dos fãs abrem o mapa em até ${META_MAPA_MS / 1000} s`, 'http_req_duration{name:mapa,scenario:pico}', 'nenhum mapa chegou a abrir'),
        medida(`95% dos fãs concluem a compra em até ${META_COMPRA_MS / 1000} s`, 'http_req_duration{name:compra,scenario:pico}', 'ninguém chegou a comprar'),
        { texto: 'Menos de 1% de requisições com erro', ok: passou('http_req_failed{scenario:pico}') },
        {
          texto: `No máximo ${LIMITE_POR_CPF} ingressos por CPF`,
          ok: travou ? null : passou('maior_compra_por_cpf'),
          detalhe: travou ? 'não conferido' : `maior compra: ${v('maior_compra_por_cpf').value}`,
        },
        {
          texto: `No máximo ${COTA_MEIA} meias-entradas por sessão`,
          ok: travou ? null : passou('maior_qtd_meia_na_sessao'),
          detalhe: travou ? 'não conferido' : `maior venda: ${v('maior_qtd_meia_na_sessao').value}`,
        },
      ],
    },
  };
}

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
  if (!s.capacidade) capacidade = `Não aguentou nem ${s.degraus[0].fasPorSegundo} fã por segundo.`;
  else if (!s.quebrou) capacidade = `Aguentou todos os degraus (até ${s.capacidade.fasPorSegundo} fãs/s).`;
  else {
    capacidade =
      `Aguenta até ${s.capacidade.fasPorSegundo} fãs por segundo (≈ ${s.capacidade.simultaneos} pessoas no site ao mesmo tempo).\n` +
      `    Com ${s.quebrou.fasPorSegundo} fãs por segundo, fica inviável.`;
  }

  const degraus = s.degraus.map(
    (d) =>
      `    ${col(d.fasPorSegundo, 5)}${col(d.simultaneos === undefined ? '—' : d.simultaneos, 13)}` +
      `${col(d.comprasPorSegundo.toFixed(1), 11)}${col(seg(d.p95Mapa), 11)}${col(seg(d.p95Compra), 12)}` +
      `${col(pctFracao(d.erros), 9)}    ${d.viavel ? '✅' : '❌'}`,
  );

  return `
════════════════════════════════════════════════════════════════════
  ESTREIA DO MAIOR FILME DA HISTÓRIA · ${r.etapa}
════════════════════════════════════════════════════════════════════

  1. A SUBIDA: até quantos fãs o Ingressa aguenta?

    ${capacidade}

    fãs/s  no site junto  compras/s  95% mapa  95% compra   erros   viável?
${degraus.join('\n')}

  2. O PICO: ${p.fasPorSegundo} fãs/s + ${p.engajadosPorSegundo} engajados/s + ${p.robos} robôs, por 1 minuto

    Fãs que conseguiram comprar ..... ${f.compraram} de ${f.chegaram}  (${pct(f.compraram, f.chegaram)})

    O caminho do fã
      Chegaram ...................... ${f.chegaram}
      Conseguiram entrar no site .... ${f.entraram}  (${pct(f.entraram, f.chegaram)})
      Viram o mapa de assentos ...... ${f.viramMapa}  (${pct(f.viramMapa, f.chegaram)})
      Tentaram comprar .............. ${f.tentaramComprar}  (${pct(f.tentaramComprar, f.chegaram)})
      Compraram ..................... ${f.compraram}  (${pct(f.compraram, f.chegaram)})
      Desistiram (site não carregou)  ${p.desistiram}

    Os fãs muito engajados (nunca desistem)
      Compraram ..................... ${e.compraram} de ${e.chegaram}  (${pct(e.compraram, e.chegaram)})
      Ainda esperando no fim ........ ${e.aindaEsperando}
      Tempo até comprar ............. metade em até ${seg(e.tempo.mediana)}, o pior ${seg(e.tempo.pior)}

    O sistema
      Pico de usuários ao mesmo tempo ${r.picoSimultaneos}
      Requisições por segundo ....... ${porSeg(p.respondidas)} respondidas de ${porSeg(p.enviadas)} enviadas
      Compras por segundo ........... ${porSeg(p.compras)}

    A espera
      Abrir o mapa .... metade em até ${seg(p.espera.mapa.mediana)}, 95% em até ${seg(p.espera.mapa.p95)}, o pior ${seg(p.espera.mapa.pior)}
      Comprar ......... metade em até ${seg(p.espera.compra.mediana)}, 95% em até ${seg(p.espera.compra.p95)}, o pior ${seg(p.espera.compra.pior)}

  INGRESSOS VENDIDOS: ${r.vendidos} de ${r.lugares}
    fãs na subida ${r.confirmados.subida} · fãs no pico ${r.confirmados.pico} · engajados ${r.confirmados.engajados} · robôs ${r.confirmados.cambistas} · sem resposta até o fim ${r.semConfirmacao}

  METAS DO PICO
${r.metas.lista.map((meta) => `    ${icone(meta.ok)} ${meta.texto}${meta.detalhe ? ` (${meta.detalhe})` : ''}`).join('\n')}
${r.subida.caiuEm ? `\n  ⚠️  O Ingressa CAIU ainda na subida (com ${r.subida.caiuEm.fasPorSegundo} fãs/s), antes de o pico começar.\n` : ''}${r.travou ? '\n  ⚠️  O Ingressa TRAVOU e não voltou. Para destravar: docker compose restart ingressa\n' : ''}
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
