// ESTREIA DO MAIOR FILME DA HISTÓRIA
//
// As vendas abrem e uma multidão tenta comprar ao mesmo tempo:
//   - fãs: chegam aos montes, abrem o mapa e compram de 1 a 4 ingressos (alguns meia-entrada).
//     Se esperarem mais de 60 s, desistem.
//   - fãs muito engajados: nunca desistem. Esperam o quanto for preciso e, se algo
//     der errado, tentam de novo até comprar ou até esgotar.
//   - cambistas: robôs com poucos CPFs comprando sem parar, tentando furar o limite
//
// Os fãs continuam chegando mesmo se o site estiver lento. No final, o resultado aparece no terminal e em
// relatorios/estreia.html (para abrir no navegador e mostrar para a turma).
//
//   docker compose run --rm --service-ports k6 run /scripts/estreia.js
//   docker compose run --rm --service-ports k6 run -e FAS=100 /scripts/estreia.js

import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter, Gauge, Trend } from 'k6/metrics';
import { gerarHtml, gerarHtmlCapacidade } from './relatorio.js';

const INGRESSA = __ENV.BASE_URL || 'http://ingressa:8000';
const CINEMA = 'http://sistema-cinema:8000';
const GATEWAY = 'http://gateway-pagamento:8000';

const ETAPA = __ENV.ETAPA || 'Ingressa';
const FAS_POR_SEGUNDO = Number(__ENV.FAS || 50);
const ENGAJADOS_POR_SEGUNDO = Math.max(1, Math.round(FAS_POR_SEGUNDO / 10));
const PACIENCIA = '60s'; // quanto o fã comum espera o site carregar antes de desistir
const ROBOS_CAMBISTAS = 20;
const DURACAO_S = 60;
const SESSOES = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]; // todas da estreia, 400 lugares cada
const LIMITE_POR_CPF = 6;
const COTA_MEIA = 160; // 40% de 400

// O que é um site "viável": as metas valem para a estreia e para o modo capacidade
const META_MAPA_MS = 2000;
const META_COMPRA_MS = 3000;
const META_ERROS = 0.01;

// MODO=capacidade: em vez do pico, só fãs comuns chegando em degraus
// (1/s, 2/s, 3/s...) para descobrir até onde o Ingressa continua viável.
const MODO = __ENV.MODO || 'estreia';
const DEGRAUS = (__ENV.DEGRAUS || '1,2,3,4,6,8,12,16,24,32').split(',').map(Number);
const DURACAO_DEGRAU_S = 15;

// Três CPFs válidos usados por todos os robôs cambistas
const CPFS_CAMBISTAS = ['11144477735', '52998224725', '39053344705'];

// O caminho do fã (funil)
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

// Vendas (fãs e robôs)
const comprasConcluidas = new Counter('compras_concluidas');
// Ingressos que o comprador viu confirmados, por tipo de comprador
const ingressosConfirmados = {
  fas: new Counter('ingressos_confirmados_fas'),
  engajados: new Counter('ingressos_confirmados_engajados'),
  cambistas: new Counter('ingressos_confirmados_cambistas'),
};

// Conferidos no final
const vendidos = new Gauge('ingressos_vendidos');
const maiorCompraPorCpf = new Gauge('maior_compra_por_cpf');
const maiorQtdMeia = new Gauge('maior_qtd_meia_na_sessao');
const naoRespondeu = new Gauge('ingressa_nao_respondeu');

http.setResponseCallback(http.expectedStatuses(200, 201, 402, 409, 422)); // erros de negócio não são falhas

const CENARIO_CAPACIDADE = {
  fas: {
    executor: 'ramping-arrival-rate',
    exec: 'fa',
    startRate: 0,
    timeUnit: '1s',
    preAllocatedVUs: 100,
    maxVUs: 2500,
    stages: DEGRAUS.flatMap((d) => [
      { duration: '2s', target: d },
      { duration: `${DURACAO_DEGRAU_S - 2}s`, target: d },
    ]),
    gracefulStop: '60s',
  },
};

// Números separados por degrau só aparecem no resumo se tiverem uma meta.
// Estas metas sempre passam: servem apenas para o k6 guardar os números.
function metasPorDegrau() {
  const metas = {};
  for (const d of DEGRAUS) {
    metas[`http_req_duration{name:mapa,degrau:${d}}`] = ['max>=0'];
    metas[`http_req_duration{name:compra,degrau:${d}}`] = ['max>=0'];
    metas[`http_req_failed{degrau:${d}}`] = ['rate>=0'];
    metas[`compras_concluidas{degrau:${d}}`] = ['count>=0'];
    metas[`fas_entraram{degrau:${d}}`] = ['count>=0'];
    metas[`tempo_do_fa{degrau:${d}}`] = ['max>=0'];
  }
  return metas;
}

export const options = {
  scenarios: MODO === 'capacidade' ? CENARIO_CAPACIDADE : {
    fas: {
      executor: 'ramping-arrival-rate',
      exec: 'fa',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 2500,
      stages: [
        { duration: '10s', target: FAS_POR_SEGUNDO }, // as vendas abrem
        { duration: `${DURACAO_S - 10}s`, target: FAS_POR_SEGUNDO },
      ],
      gracefulStop: '60s', // quem chegou no fim também tem 60 s de paciência
    },
    engajados: {
      executor: 'ramping-arrival-rate',
      exec: 'engajado',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 1000,
      stages: [
        { duration: '10s', target: ENGAJADOS_POR_SEGUNDO },
        { duration: `${DURACAO_S - 10}s`, target: ENGAJADOS_POR_SEGUNDO },
      ],
      gracefulStop: '60s', // depois do minuto de vendas, ainda esperam mais 1 min antes do teste encerrar
    },
    cambistas: { executor: 'constant-vus', exec: 'cambista', vus: ROBOS_CAMBISTAS, duration: `${DURACAO_S}s` },
  },
  thresholds: MODO === 'capacidade' ? metasPorDegrau() : {
    'http_req_duration{name:mapa}': [`p(95)<${META_MAPA_MS}`],
    'http_req_duration{name:compra}': [`p(95)<${META_COMPRA_MS}`],
    http_req_failed: [`rate<${META_ERROS}`],
    maior_compra_por_cpf: [`value<=${LIMITE_POR_CPF}`],
    maior_qtd_meia_na_sessao: [`value<=${COTA_MEIA}`],
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

function souFa() {
  return exec.scenario.name === 'fas';
}

// Quanto tempo esperar pelo mapa: o fã comum desiste depois de PACIENCIA,
// o engajado espera "para sempre" (até o teste acabar)
function paciencia() {
  return exec.scenario.name === 'engajados' ? '10m' : PACIENCIA;
}

// Depois de clicar em "comprar", ninguém abandona: todos esperam a resposta
const ESPERA_DA_COMPRA = '10m';

// No modo capacidade, em qual degrau estamos agora
function degrauAtual() {
  const segundos = (Date.now() - exec.scenario.startTime) / 1000;
  return DEGRAUS[Math.min(Math.floor(segundos / DURACAO_DEGRAU_S), DEGRAUS.length - 1)];
}

function abrirMapa(sessao, tags = {}) {
  const r = http.get(`${INGRESSA}/sessoes/${sessao}/assentos`, { timeout: paciencia(), tags: { name: 'mapa', ...tags } });
  if (r.status === 0 && souFa()) desistiram.add(1, tags);
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
    ingressosConfirmados[exec.scenario.name].add(itens.length);
  }
  return r.status;
}

// --- Personagens ---

export function fa() {
  const tags = MODO === 'capacidade' ? { degrau: String(degrauAtual()) } : {};
  const inicio = Date.now();
  tentarComprar(tags);
  tempoDoFa.add(Date.now() - inicio, tags);
}

function tentarComprar(tags) {
  fasEntraram.add(1, tags);
  const sessao = sortear(SESSOES)[0];
  const livres = abrirMapa(sessao, tags);
  if (livres === null) return;
  fasViramMapa.add(1);
  if (livres.length === 0) return esgotado.add(1);

  const quantidade = 1 + Math.floor(Math.random() * 4);
  const itens = sortear(livres, quantidade).map((assento) => ({
    assento,
    tipo: Math.random() < 0.4 ? 'meia' : 'inteira',
  }));
  fasTentaramComprar.add(1);
  if (comprar(sessao, gerarCpf(), itens, `tok_fa_${__VU}`, tags) === 201) fasCompraram.add(1); // ~5% dos cartões são recusados
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
  if (MODO === 'capacidade') return; // aqui só interessa o tempo de resposta

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
    engajados: {
      porSegundo: ENGAJADOS_POR_SEGUNDO,
      chegaram: n('engajados_chegaram'),
      compraram: n('engajados_compraram'),
      esgotado: n('engajados_encontraram_esgotado'),
      aindaEsperando: n('engajados_chegaram') - n('engajados_compraram') - n('engajados_encontraram_esgotado'),
      tentativas: n('engajados_tentativas'),
      tempo: { mediana: m('engajados_tempo_ate_comprar').med, pior: m('engajados_tempo_ate_comprar').max },
    },
    picoSimultaneos: m('vus').max || 0,
    enviadas,
    respondidas: enviadas - comErro,
    comErro,
    compras: n('compras_concluidas'),
    vendidos: m('ingressos_vendidos').value || 0,
    confirmados: {
      fas: n('ingressos_confirmados_fas'),
      engajados: n('ingressos_confirmados_engajados'),
      cambistas: n('ingressos_confirmados_cambistas'),
    },
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

// Vendido no cinema, mas ninguém viu a confirmação: a compra ainda não tinha
// respondido quando o teste acabou
function semConfirmacao(r) {
  const c = r.confirmados;
  return Math.max(0, r.vendidos - c.fas - c.engajados - c.cambistas);
}

function gerarTexto(r) {
  const porSeg = (total) => (total / r.duracaoS).toFixed(1);
  const pct = (parte, total) => (total ? `${Math.round((parte / total) * 100)}%` : '0%');
  const seg = (ms) => (ms === undefined ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
  const espera = (e) => `metade em até ${seg(e.mediana)}, 95% em até ${seg(e.p95)}, o pior ${seg(e.pior)}`;
  const icone = (ok) => (ok === null ? '⚠️ ' : ok ? '✅' : '❌');
  const f = r.funil;
  const e = r.engajados;

  return `
════════════════════════════════════════════════════════════════════
  ESTREIA DO MAIOR FILME DA HISTÓRIA · ${r.etapa}
  ${r.fasPorSegundo} fãs + ${r.engajados.porSegundo} fãs engajados chegando por segundo, ${r.robos} robôs cambistas, 1 minuto
════════════════════════════════════════════════════════════════════

  O CAMINHO DO FÃ
    Chegaram ........................ ${f.chegaram}
    Conseguiram entrar no site ...... ${f.entraram}  (${pct(f.entraram, f.chegaram)})
    Viram o mapa de assentos ........ ${f.viramMapa}  (${pct(f.viramMapa, f.chegaram)})
    Tentaram comprar ................ ${f.tentaramComprar}  (${pct(f.tentaramComprar, f.chegaram)})
    Compraram ....................... ${f.compraram}  (${pct(f.compraram, f.chegaram)})
    Desistiram (site não carregou) .. ${r.desistiram}

  OS FÃS MUITO ENGAJADOS (nunca desistem, tentam de novo até conseguir)
    Chegaram ........................ ${e.chegaram}  (${e.porSegundo} por segundo)
    Compraram ....................... ${e.compraram}  (${pct(e.compraram, e.chegaram)})
    Ainda esperando no fim do teste . ${e.aindaEsperando}
    Tempo até comprar ............... metade em até ${seg(e.tempo.mediana)}, o pior ${seg(e.tempo.pior)}
    Tentativas no total ............. ${e.tentativas}

  O SISTEMA
    Pico de usuários ao mesmo tempo . ${r.picoSimultaneos}
    Requisições por segundo ......... ${porSeg(r.respondidas)} respondidas de ${porSeg(r.enviadas)} enviadas
    Compras por segundo ............. ${porSeg(r.compras)}
    Ingressos vendidos .............. ${r.vendidos} de ${r.lugares}, e para quem foram:
       fãs (viram a confirmação) .... ${r.confirmados.fas}
       fãs engajados ................ ${r.confirmados.engajados}
       robôs cambistas .............. ${r.confirmados.cambistas}
       sem resposta até o fim ....... ${r.semConfirmacao}${r.semConfirmacao ? "  ⚠️ o fã ainda esperava a confirmação" : ""}

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

// --- Resultado do modo capacidade ---

function calcularCapacidade(data) {
  const v = (nome) => (data.metrics[nome] ? data.metrics[nome].values : {});
  const degraus = DEGRAUS.map((d) => {
    // Sem nenhuma resposta no degrau, o k6 informa 0: tratamos como "sem medida"
    const p95Mapa = v(`http_req_duration{name:mapa,degrau:${d}}`)['p(95)'] || undefined;
    const p95Compra = v(`http_req_duration{name:compra,degrau:${d}}`)['p(95)'] || undefined;
    const erros = v(`http_req_failed{degrau:${d}}`).rate;
    const tempoMedio = v(`tempo_do_fa{degrau:${d}}`).avg;
    return {
      fasPorSegundo: d,
      comprasPorSegundo: (v(`compras_concluidas{degrau:${d}}`).count || 0) / DURACAO_DEGRAU_S,
      p95Mapa,
      p95Compra,
      erros,
      // Lei de Little: pessoas no site ao mesmo tempo = chegada por segundo × tempo que cada uma fica
      simultaneos: tempoMedio === undefined ? undefined : Math.round((d * tempoMedio) / 1000),
      viavel:
        p95Mapa !== undefined && p95Mapa <= META_MAPA_MS &&
        p95Compra !== undefined && p95Compra <= META_COMPRA_MS &&
        erros !== undefined && erros < META_ERROS,
    };
  });

  const primeiroInviavel = degraus.findIndex((d) => !d.viavel);
  const ultimoViavel = primeiroInviavel === -1 ? degraus[degraus.length - 1] : degraus[primeiroInviavel - 1];
  return {
    etapa: ETAPA,
    degraus,
    duracaoDegrauS: DURACAO_DEGRAU_S,
    capacidade: ultimoViavel || null,
    quebrou: primeiroInviavel === -1 ? null : degraus[primeiroInviavel],
    metas: { mapaMs: META_MAPA_MS, compraMs: META_COMPRA_MS, erros: META_ERROS },
  };
}

function gerarTextoCapacidade(r) {
  const seg = (ms) => (ms === undefined ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
  const pct = (x) => (x === undefined ? '—' : `${(x * 100).toFixed(1)}%`);
  const col = (texto, largura) => String(texto).padStart(largura);

  let veredito;
  if (!r.capacidade) veredito = `Não aguentou nem ${r.degraus[0].fasPorSegundo} fã por segundo.`;
  else if (!r.quebrou) veredito = `Aguentou todos os degraus. Tente mais: -e DEGRAUS=...`;
  else {
    veredito =
      `Aguenta até ${r.capacidade.fasPorSegundo} fãs por segundo (≈ ${r.capacidade.simultaneos} pessoas no site ao mesmo tempo).\n` +
      `  Com ${r.quebrou.fasPorSegundo} fãs por segundo, fica inviável.`;
  }

  const linhas = r.degraus.map(
    (d) =>
      `  ${col(d.fasPorSegundo, 6)}${col(d.simultaneos === undefined ? '—' : d.simultaneos, 13)}` +
      `${col(d.comprasPorSegundo.toFixed(1), 11)}${col(seg(d.p95Mapa), 11)}${col(seg(d.p95Compra), 12)}` +
      `${col(pct(d.erros), 9)}    ${d.viavel ? '✅' : '❌'}`,
  );

  return `
════════════════════════════════════════════════════════════════════
  CAPACIDADE · ${r.etapa}
  Até quantos fãs o Ingressa aguenta?
════════════════════════════════════════════════════════════════════

  ${veredito}

  fãs/s  no site junto  compras/s  95% mapa  95% compra   erros   viável?
${linhas.join('\n')}

  Viável = 95% abrem o mapa em até ${seg(r.metas.mapaMs)}, 95% compram em até ${seg(r.metas.compraMs)}
           e menos de ${pct(r.metas.erros)} de erros. Cada degrau dura ${r.duracaoDegrauS} s.

  Relatório para projetar: relatorios/capacidade.html
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
  if (MODO === 'capacidade') {
    const capacidade = calcularCapacidade(data);
    return {
      stdout: gerarTextoCapacidade(capacidade),
      '/relatorios/capacidade.txt': gerarTextoCapacidade(capacidade),
      '/relatorios/capacidade.html': gerarHtmlCapacidade(capacidade),
    };
  }
  const resultado = calcularResultado(data);
  resultado.semConfirmacao = semConfirmacao(resultado);
  return {
    stdout: gerarTexto(resultado),
    '/relatorios/estreia.txt': gerarTexto(resultado),
    '/relatorios/estreia.html': gerarHtml(resultado),
  };
}
