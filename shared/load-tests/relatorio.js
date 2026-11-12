// Relatório visual da estreia: um HTML único, sem dependências, para abrir
// no navegador e projetar para a turma.

const inteiro = (n) => String(Math.round(n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
const decimal = (n) => (n || 0).toFixed(1).replace('.', ',');
const pct = (parte, total) => (total ? Math.round((parte / total) * 100) : 0);
// "1 usuário", "2 usuários"
const usuarios = (n) => `${n} ${n === 1 ? 'usuário' : 'usuários'}`;
const tempo = (ms) => {
  if (ms === undefined || ms === null) return '—';
  return ms >= 1000 ? `${decimal(ms / 1000)} s` : `${Math.round(ms)} ms`;
};

function alertas(r) {
  const lista = [];
  if (r.subida.caiuEm) {
    lista.push(
      `O Ingressa <b>caiu ainda na subida</b>, com ${usuarios(r.subida.caiuEm.usuariosPorSegundo)} por segundo,` +
        ' antes de o pico começar: o resultado do pico mostra um sistema que já estava fora do ar.',
    );
  }
  if (r.travou) {
    lista.push(
      'O Ingressa <b>travou</b> e não voltou nem depois que o público foi embora.' +
        ' Para destravar: <code>docker compose restart ingressa</code>',
    );
  }
  if (r.semConfirmacao > 0) {
    lista.push(
      `<b>${inteiro(r.semConfirmacao)} ingressos</b> foram vendidos, mas o teste acabou antes de o usuário` +
        ' receber a confirmação: ele ainda estava esperando na tela de pagamento.',
    );
  }
  return lista.map((texto) => `<div class="alerta">⚠️ ${texto}</div>`).join('');
}

function cartao(titulo, valor, detalhe, barra) {
  const progresso = barra === undefined ? '' : `<div class="trilho"><div class="cheio" style="width:${barra}%"></div></div>`;
  return `<div class="cartao"><div class="rotulo">${titulo}</div><div class="valor">${valor}</div>${progresso}<div class="detalhe">${detalhe}</div></div>`;
}

function funil(etapas) {
  const total = etapas[0][1];
  return etapas
    .map(([nome, valor]) => {
      const p = pct(valor, total);
      return `<div class="etapa">
        <div class="nome">${nome}</div>
        <div class="trilho largo"><div class="cheio" style="width:${Math.max(p, valor ? 1 : 0)}%"></div></div>
        <div class="numero">${inteiro(valor)} <span>${p}%</span></div>
      </div>`;
    })
    .join('');
}

function comparacao(lista) {
  const porcento = (fracao) => `${pct(fracao, 1)}%`;
  const fim = (c) => (c.travou ? '<span class="ruim">travou</span>' : c.caiuNaSubida ? '<span class="aviso">caiu e voltou</span>' : '<span class="bom">ficou de pé</span>');
  const quando = (iso) => new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  const linhas = lista.map(
    (c) => `<div class="linha-etapa ${c.atual ? 'atual' : ''}">
      <div><b>${c.etapa}</b><span>${c.hardware || '2 CPUs / 2 GB'} · pico de ${c.picoUsuariosPorSegundo || 120}/s</span><span>${c.atual ? 'esta rodada' : `rodou em ${quando(c.quando)}`}</span></div>
      <div class="forte">${c.capacidade}/s</div>
      <div>${porcento(c.curiososAtendidos)}</div>
      <div>${porcento(c.compradoresAtendidos)}</div>
      <div class="opcional">${decimal(c.comprasPorSegundoNoPico)}/s</div>
      <div class="opcional">${inteiro(c.vendidos)}</div>
      <div>${fim(c)}</div>
    </div>`,
  );
  return `<div class="linha-etapa cabecalho">
      <div>etapa</div><div>aguenta</div><div>curiosos que viram tudo no pico</div><div>compradores que compraram no pico</div>
      <div class="opcional">compras no pico</div><div class="opcional">ingressos vendidos</div><div>no fim</div>
    </div>
    ${linhas.join('')}`;
}

// Procura x vendas, degrau a degrau até o pico: barras lado a lado (SVG puro)
function graficoDaProgressao(pontos) {
  const L = 1000, A = 340, esq = 56, dir = 12, topo = 16, base = 56;
  const largura = L - esq - dir, altura = A - topo - base;
  const maximo = Math.max(1, ...pontos.map((p) => Math.max(p.procura, p.vendas))) * 1.1;
  const y = (valor) => topo + altura - (valor / maximo) * altura;
  const grupo = largura / pontos.length;
  const barra = grupo * 0.34;
  const linhasDeGrade = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const valor = maximo * f;
    return `<line x1="${esq}" x2="${L - dir}" y1="${y(valor)}" y2="${y(valor)}" stroke="#e7e2d8"/>
      <text x="${esq - 8}" y="${y(valor) + 4}" text-anchor="end" font-size="13" fill="#78716c">${decimal(valor)}</text>`;
  });
  const barras = pontos.map((p, i) => {
    const x = esq + i * grupo + grupo / 2;
    const fundo = p.pico ? `<rect x="${esq + i * grupo}" y="${topo}" width="${grupo}" height="${altura}" fill="#fef9e7"/>` : '';
    const cor = p.pico ? '#d4a017' : p.viavel ? '#15803d' : '#b91c1c';
    return `${fundo}
      <rect x="${x - barra}" y="${y(p.procura)}" width="${barra}" height="${topo + altura - y(p.procura)}" fill="#d6d3d1"><title>${p.rotulo}: ${decimal(p.procura)} queriam comprar por segundo</title></rect>
      <rect x="${x}" y="${y(p.vendas)}" width="${barra}" height="${topo + altura - y(p.vendas)}" fill="${cor}"><title>${p.rotulo}: ${decimal(p.vendas)} compraram por segundo</title></rect>
      <text x="${x}" y="${A - base + 22}" text-anchor="middle" font-size="13" font-weight="${p.pico ? 700 : 400}" fill="#1c1917">${p.pico ? 'pico' : p.rotulo}</text>`;
  });
  return `<svg viewBox="0 0 ${L} ${A}" width="100%" role="img" aria-label="Procura e vendas por segundo em cada degrau e no pico">
    ${linhasDeGrade.join('')}
    ${barras.join('')}
    <text x="${esq + largura / 2}" y="${A - 8}" text-anchor="middle" font-size="13" fill="#78716c">usuários chegando por segundo</text>
  </svg>
  <div class="legenda">
    <span><i style="background:#d6d3d1"></i>queriam comprar (por segundo)</span>
    <span><i style="background:#15803d"></i>compraram, num degrau viável</span>
    <span><i style="background:#b91c1c"></i>compraram, num degrau inviável</span>
    <span><i style="background:#d4a017"></i>compraram, no pico</span>
  </div>`;
}

function tabelaDaProgressao(pontos) {
  const porcento = (fracao) => (fracao === undefined ? '—' : `${pct(fracao, 1)}%`);
  const classe = (fracao) => (fracao === undefined ? '' : fracao >= 0.9 ? 'bom' : fracao >= 0.5 ? 'aviso' : 'ruim');
  const linhas = pontos.map(
    (p) => `<div class="linha-progressao ${p.pico ? 'pico' : ''}">
      <div class="forte">${p.rotulo}</div>
      <div>${decimal(p.procura)}/s</div>
      <div>${decimal(p.vendas)}/s</div>
      <div class="${classe(p.compradoresAtendidos)}">${porcento(p.compradoresAtendidos)}</div>
      <div class="${classe(p.curiososAtendidos)}">${porcento(p.curiososAtendidos)}</div>
      <div class="estado">${p.pico ? '' : p.viavel ? '✅' : '❌'}</div>
    </div>`,
  );
  return `<div class="linha-progressao cabecalho">
      <div>usuários chegando</div><div>queriam comprar</div><div>compraram</div>
      <div>compradores que compraram</div><div>curiosos que viram tudo</div><div>viável?</div>
    </div>
    ${linhas.join('')}`;
}

function tabelaDeEndpoints(lista) {
  const porcento = (fracao) => `${decimal(fracao * 100)}%`;
  const linhas = lista.map(
    (e) => `<div class="linha-endpoint">
      <div><code>${e.nome}</code></div>
      <div>${decimal(e.porSegundo)}/s</div>
      <div>${tempo(e.mediana)}</div>
      <div class="forte">${tempo(e.p95)}</div>
      <div class="opcional">${tempo(e.pior)}</div>
      <div class="${e.erros < 0.01 ? 'bom' : 'ruim'}">${porcento(e.erros)}</div>
      <div class="opcional">${porcento(e.barradas)}</div>
    </div>`,
  );
  return `<div class="linha-endpoint cabecalho">
      <div>endpoint</div><div>requisições</div><div>metade em até</div><div>95% em até</div>
      <div class="opcional">o pior</div><div>erros</div><div class="opcional">barradas na porta</div>
    </div>
    ${linhas.join('')}`;
}

function espera(nome, e, limiteMs) {
  const classe = (ms) => (ms === undefined ? '' : ms <= limiteMs ? 'bom' : 'ruim');
  return `<div class="espera">
    <div class="nome">${nome}<span>meta: 95% em até ${tempo(limiteMs)}</span></div>
    <div class="medida"><div class="rotulo">metade esperou até</div><div class="${classe(e.mediana)}">${tempo(e.mediana)}</div></div>
    <div class="medida"><div class="rotulo">95% esperaram até</div><div class="${classe(e.p95)}">${tempo(e.p95)}</div></div>
    <div class="medida"><div class="rotulo">o pior caso</div><div class="${classe(e.pior)}">${tempo(e.pior)}</div></div>
  </div>`;
}

function metas(lista) {
  return lista
    .map((meta) => {
      const classe = meta.ok === null ? 'aviso' : meta.ok ? 'bom' : 'ruim';
      const icone = meta.ok === null ? '⚠️' : meta.ok ? '✅' : '❌';
      const detalhe = meta.detalhe ? `<span>${meta.detalhe}</span>` : '';
      return `<div class="meta ${classe}">${icone} ${meta.texto}${detalhe}</div>`;
    })
    .join('');
}

const ESTILO = `
<style>
  :root {
    --fundo: #f4f1ea; --papel: #ffffff; --tinta: #1c1917; --apagado: #78716c; --linha: #e7e2d8;
    --ouro: #d4a017; --bom: #15803d; --ruim: #b91c1c; --aviso: #b45309; --barra: #1c1917;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--fundo); color: var(--tinta); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  header { background: #0c0a09; color: #fafaf9; padding: 40px 0 48px; }
  header > div { padding: 0 16px; }
  main, header > div { max-width: 1080px; margin: 0 auto; }
  main { padding: 0 16px 48px; }
  .selo { color: var(--ouro); font-weight: 700; letter-spacing: .14em; text-transform: uppercase; font-size: 13px; }
  h1 { font-size: clamp(28px, 5vw, 46px); line-height: 1.1; margin: 10px 0 8px; }
  header p { margin: 0; color: #a8a29e; }
  .veredito { background: var(--papel); border-radius: 16px; margin-top: -24px; padding: 28px; box-shadow: 0 8px 30px rgb(0 0 0 / .06); }
  .veredito .grande { font-size: clamp(40px, 8vw, 72px); font-weight: 800; line-height: 1; }
  .veredito .grande small { font-size: .4em; font-weight: 600; color: var(--apagado); }
  .veredito p { margin: 8px 0 0; font-size: 20px; }
  .alerta { background: #fef2f2; border: 1px solid #fecaca; color: #7f1d1d; border-radius: 12px; padding: 14px 18px; margin-top: 16px; }
  code { background: rgb(0 0 0 / .06); padding: 2px 6px; border-radius: 6px; }
  h2 { font-size: 14px; letter-spacing: .12em; text-transform: uppercase; color: var(--apagado); margin: 40px 0 14px; }
  .cartoes { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
  .cartao, .bloco { background: var(--papel); border-radius: 14px; padding: 20px; }
  .rotulo { color: var(--apagado); font-size: 14px; }
  .valor { font-size: 34px; font-weight: 800; margin: 4px 0; }
  .detalhe { color: var(--apagado); font-size: 14px; }
  .trilho { background: var(--linha); border-radius: 99px; height: 8px; margin: 8px 0; overflow: hidden; }
  .trilho.largo { height: 26px; border-radius: 8px; margin: 0; }
  .cheio { background: var(--barra); height: 100%; border-radius: inherit; }
  .etapa { display: grid; grid-template-columns: 230px 1fr 120px; gap: 14px; align-items: center; padding: 8px 0; }
  .etapa:last-child .cheio { background: var(--ouro); }
  .etapa .numero { font-weight: 700; font-size: 18px; text-align: right; }
  .etapa .numero span { color: var(--apagado); font-weight: 500; font-size: 14px; margin-left: 4px; }
  .espera { display: grid; grid-template-columns: 1.3fr repeat(3, 1fr); gap: 14px; align-items: center; padding: 12px 0; border-top: 1px solid var(--linha); }
  .espera:first-child { border-top: 0; }
  .espera .nome { font-weight: 700; font-size: 18px; }
  .espera .nome span { display: block; font-weight: 400; font-size: 13px; color: var(--apagado); }
  .medida > div:last-child { font-size: 26px; font-weight: 800; }
  .bom { color: var(--bom); } .ruim { color: var(--ruim); } .aviso { color: var(--aviso); }
  .metas { display: grid; gap: 10px; }
  .meta { background: var(--papel); border-radius: 12px; padding: 14px 18px; font-weight: 600; border-left: 6px solid currentColor; }
  .meta span { color: var(--apagado); font-weight: 400; margin-left: 8px; }
  footer { color: var(--apagado); font-size: 14px; margin-top: 32px; }
  @media (max-width: 700px) {
    .etapa { grid-template-columns: 1fr 90px; }
    .etapa .trilho { grid-column: 1 / -1; grid-row: 2; }
    .espera { grid-template-columns: 1fr 1fr 1fr; }
    .espera .nome { grid-column: 1 / -1; }
  }
  .degrau { display: grid; grid-template-columns: 90px repeat(6, 1fr) 70px; gap: 10px; align-items: center; padding: 12px 16px; border-radius: 10px; }
  .degrau.com-sala { grid-template-columns: 90px repeat(7, 1fr) 70px; }
  .degrau + .degrau { margin-top: 6px; }
  .degrau.cabecalho { color: var(--apagado); font-size: 13px; padding-top: 0; padding-bottom: 4px; }
  .degrau.viavel { background: #f0fdf4; } .degrau.inviavel { background: #fef2f2; }
  .degrau .fas { font-weight: 800; font-size: 20px; }
  .degrau .estado { font-size: 22px; text-align: center; }
  @media (max-width: 700px) {
    .degrau { grid-template-columns: 60px repeat(4, 1fr) 40px; font-size: 14px; }
    .degrau .opcional { display: none; }
  }
  .tripla { display: grid; grid-template-columns: repeat(3, 1fr); gap: 28px; }
  .tripla > div + div { border-left: 1px solid var(--linha); padding-left: 28px; }
  .tripla .rotulo { margin-bottom: 6px; }
  .tripla .grande { font-size: clamp(36px, 5vw, 56px); }
  .tripla p { font-size: 16px; color: var(--apagado); }
  .publicos { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .publicos h3 { margin: 0 0 4px; font-size: 18px; }
  .publicos .detalhe { margin-bottom: 10px; }
  .publicos .etapa { grid-template-columns: 150px 1fr 90px; }
  .linha-etapa { display: grid; grid-template-columns: 1.6fr repeat(6, 1fr); gap: 10px; align-items: center; padding: 12px 16px; border-radius: 10px; }
  .linha-etapa + .linha-etapa { margin-top: 6px; }
  .linha-etapa.cabecalho { color: var(--apagado); font-size: 13px; padding-top: 0; padding-bottom: 4px; }
  .linha-etapa.atual { background: #fef9e7; outline: 2px solid var(--ouro); }
  .linha-etapa span { display: block; color: var(--apagado); font-size: 13px; }
  .linha-etapa .forte { font-weight: 800; font-size: 22px; }
  .linha-endpoint { display: grid; grid-template-columns: 2fr repeat(6, 1fr); gap: 10px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--linha); }
  .linha-endpoint.cabecalho { color: var(--apagado); font-size: 13px; border-top: 0; padding-top: 0; }
  .linha-endpoint .forte { font-weight: 800; }
  .linha-progressao { display: grid; grid-template-columns: 1.3fr repeat(4, 1fr) 70px; gap: 10px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--linha); }
  .linha-progressao.cabecalho { color: var(--apagado); font-size: 13px; border-top: 0; padding-top: 0; }
  .linha-progressao.pico { background: #fef9e7; border-radius: 10px; }
  .linha-progressao .forte { font-weight: 800; }
  .linha-progressao .estado { text-align: center; }
  .legenda { display: flex; flex-wrap: wrap; gap: 8px 20px; color: var(--apagado); font-size: 14px; margin-top: 8px; }
  .legenda i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
  @media (max-width: 700px) {
    .tripla, .publicos { grid-template-columns: 1fr; }
    .tripla > div + div { border-left: 0; padding-left: 0; border-top: 1px solid var(--linha); padding-top: 20px; }
    .linha-etapa { grid-template-columns: 1.4fr repeat(4, 1fr); font-size: 14px; }
    .linha-etapa .opcional { display: none; }
    .linha-endpoint { grid-template-columns: 1.6fr repeat(4, 1fr); font-size: 14px; }
    .linha-endpoint .opcional { display: none; }
    .linha-progressao { grid-template-columns: 1.2fr repeat(4, 1fr) 40px; font-size: 13px; gap: 6px; padding: 10px 8px; }
  }
</style>
`;

function pagina(titulo, corpo) {
  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${titulo}</title>
${ESTILO}
</head>
<body>
${corpo}
</body>
</html>
`;
}

function vereditoCapacidade(s) {
  if (!s.capacidade) {
    return `<div class="grande">Inviável</div><p>Não aguentou nem ${s.degraus[0].usuariosPorSegundo} usuário por segundo.</p>`;
  }
  const quebra = s.quebrou
    ? `Com ${usuarios(s.quebrou.usuariosPorSegundo)}/s, fica inviável.`
    : 'Aguentou todos os degraus.';
  return `<div class="grande">${usuarios(s.capacidade.usuariosPorSegundo)}/s</div>
    <p>≈ ${inteiro(s.capacidade.simultaneos)} pessoas no site ao mesmo tempo. ${quebra}</p>`;
}

function tabelaDeDegraus(s, metas, sala) {
  // Nas etapas com sala de espera, uma coluna a mais: quanto tempo esperaram a vez
  const comSala = sala ? ' com-sala' : '';
  const classe = (valor, limite) => (valor === undefined ? '' : valor <= limite ? 'bom' : 'ruim');
  const porcento = (fracao) => (fracao === undefined ? '—' : `${decimal(fracao * 100)}%`);
  const linhas = s.degraus.map(
    (d) => `<div class="degrau${comSala} ${d.viavel ? 'viavel' : 'inviavel'}">
      <div class="fas">${d.usuariosPorSegundo}/s</div>
      <div>${d.simultaneos === undefined ? '—' : inteiro(d.simultaneos)}</div>
      <div class="opcional">${decimal(d.comprasPorSegundo)}/s</div>
      <div class="${classe(d.p95Pagina, metas.paginaMs)}">${tempo(d.p95Pagina)}</div>
      <div class="${classe(d.p95Compra, metas.compraMs)}">${tempo(d.p95Compra)}</div>
      <div class="opcional ${d.erros === undefined ? '' : d.erros < metas.erros ? 'bom' : 'ruim'}">${porcento(d.erros)}</div>
      <div class="${d.barrados < metas.erros ? 'bom' : 'ruim'}">${porcento(d.barrados)}</div>${sala ? `<div class="${classe(d.p95Sala, sala.metaMs)}">${tempo(d.p95Sala)}</div>` : ''}
      <div class="estado">${d.viavel ? '✅' : '❌'}</div>
    </div>`,
  );
  return `<div class="degrau cabecalho${comSala}">
      <div>usuários chegando</div><div>pessoas no site ao mesmo tempo</div><div class="opcional">compras</div>
      <div>95% das páginas abriram em até</div><div>95% compraram em até</div><div class="opcional">erros</div><div>barrados na porta</div>${sala ? '<div>95% esperaram na sala até</div>' : ''}
      <div></div>
    </div>
    ${linhas.join('')}`;
}

export function gerarHtml(r) {
  const s = r.subida;
  const p = r.pico;
  const cu = p.curiosos;
  const co = p.compradores;
  const e = r.engajados;
  const porSeg = (total) => decimal(total / p.duracaoS);

  return pagina(
    `Estreia · ${r.etapa}`,
    `
<header><div>
  <div class="selo">Teste de carga · ${r.etapa}</div>
  <h1>Estreia do maior filme da história</h1>
  <p>Como numa loja de verdade, a maioria só olha: de cada 10 usuários, 7 são curiosos (olham a programação e o mapa e vão embora) e 3 compram.
  Primeiro o público cresce aos poucos, para descobrir até onde o Ingressa aguenta. Depois, o pico:
  ${usuarios(p.usuariosPorSegundo)} por segundo, ${usuarios(p.engajadosPorSegundo)} muito engajados por segundo e ${p.robos} robôs cambistas, durante ${p.duracaoS} segundos.</p>
</div></header>
<main>
  <section class="veredito tripla">
    <div>
      <div class="rotulo">O máximo que o Ingressa aguenta</div>
      ${vereditoCapacidade(s)}
    </div>
    <div>
      <div class="rotulo">No pico, os curiosos</div>
      <div class="grande">${pct(cu.soOlharam, cu.chegaram)}%</div>
      <p>conseguiram ver tudo o que queriam: ${inteiro(cu.soOlharam)} de ${inteiro(cu.chegaram)}.</p>
    </div>
    <div>
      <div class="rotulo">No pico, os compradores</div>
      <div class="grande">${pct(co.compraram, co.chegaram)}%</div>
      <p>conseguiram comprar: ${inteiro(co.compraram)} de ${inteiro(co.chegaram)}.</p>
    </div>
  </section>
  ${alertas(r)}

  <h2>A progressão das vendas: do primeiro usuário até o pico</h2>
  <p class="detalhe" style="margin:-6px 0 14px">A cada degrau chega mais gente. Enquanto as vendas acompanham a procura, o Ingressa dá conta; quando elas param de subir (ou caem), ele chegou no limite.</p>
  <div class="bloco">
    ${graficoDaProgressao(r.progressao)}
  </div>
  <div class="bloco" style="margin-top:14px">${tabelaDaProgressao(r.progressao)}</div>

  <h2>O ganho de cada etapa</h2>
  <p class="detalhe" style="margin:-6px 0 14px">Esta rodada ao lado do último resultado de cada etapa anterior. Até a etapa 06, todas com o mesmo hardware: 2 CPUs e 2 GB para o Ingressa.</p>
  <div class="bloco">${comparacao(r.comparacao)}</div>

  <h2>1 · A subida: até quantos usuários o Ingressa aguenta?</h2>
  <p class="detalhe" style="margin:-6px 0 14px">A chegada de usuários sobe em degraus de ${s.duracaoDegrauS} s. Um degrau é viável quando 95% das páginas (programação e mapa) abrem em até ${tempo(r.metas.paginaMs)}, 95% compram em até ${tempo(r.metas.compraMs)}, e menos de ${decimal(r.metas.erros * 100)}% das requisições dão erro ou são barradas no limite.</p>
  <div class="bloco">${tabelaDeDegraus(s, r.metas, r.sala)}</div>

  <h2>1 · A subida: a velocidade de cada endpoint ${s.capacidade ? `com ${inteiro(s.capacidade.usuariosPorSegundo)} usuários/s, o último degrau viável` : ''}</h2>
  <p class="detalhe" style="margin:-6px 0 14px">O tempo é só de quem foi atendido: quem foi barrado na porta aparece à parte.</p>
  ${s.capacidade ? `<div class="bloco">${tabelaDeEndpoints(r.endpoints.capacidade)}</div>` : '<p class="detalhe">Nenhum degrau foi viável.</p>'}

  <h2>2 · O pico: cada público conseguiu o que queria?</h2>
  <div class="publicos">
    <div class="bloco">
      <h3>Os curiosos</h3>
      <div class="detalhe">Olham a programação e o mapa de duas sessões, e vão embora.</div>
      ${funil([
        ['Chegaram', cu.chegaram],
        ...(r.sala ? [['Passaram pela sala de espera', cu.passaramPelaSala]] : []),
        ['Viram a programação', cu.viramProgramacao],
        ['Viram o mapa', cu.viramMapa],
        ['Viram tudo', cu.soOlharam],
      ])}
      <div class="detalhe" style="margin-top:10px">Desistiram porque uma página não carregou em 60 s: <b>${inteiro(cu.desistiram)}</b></div>
    </div>
    <div class="bloco">
      <h3>Os compradores</h3>
      <div class="detalhe">Olham a programação e o mapa, e compram de 1 a 4 ingressos.</div>
      ${funil([
        ['Chegaram', co.chegaram],
        ...(r.sala ? [['Passaram pela sala de espera', co.passaramPelaSala]] : []),
        ['Viram a programação', co.viramProgramacao],
        ['Viram o mapa', co.viramMapa],
        ['Tentaram comprar', co.tentaramComprar],
        ['Compraram', co.compraram],
      ])}
      <div class="detalhe" style="margin-top:10px">Desistiram porque uma página não carregou em 60 s: <b>${inteiro(co.desistiram)}</b> · Encontraram a sessão esgotada: <b>${inteiro(co.esgotado)}</b></div>
    </div>
  </div>

  <h2>2 · O pico: os usuários muito engajados</h2>
  <p class="detalhe" style="margin:-6px 0 14px">Nunca desistem: esperam o quanto for preciso e, se algo der errado, tentam de novo.</p>
  <div class="cartoes">
    ${cartao('Conseguiram comprar', `${pct(e.compraram, e.chegaram)}%`, `${inteiro(e.compraram)} de ${inteiro(e.chegaram)} engajados`, pct(e.compraram, e.chegaram))}
    ${cartao('Ainda esperando no fim', inteiro(e.aindaEsperando), 'o teste acabou e eles continuavam lá')}
    ${cartao('Tempo até comprar', tempo(e.tempo.mediana), `metade em até isso; o pior: ${tempo(e.tempo.pior)}`)}
    ${cartao('Tentativas', inteiro(e.tentativas), `${e.chegaram ? decimal(e.tentativas / e.chegaram) : '0,0'} por engajado, em média`)}
  </div>

  <h2>2 · O pico: o sistema</h2>
  <div class="cartoes">
    ${cartao('Ingressos vendidos', inteiro(r.vendidos), `de ${inteiro(r.lugares)} lugares, na rodada inteira`, pct(r.vendidos, r.lugares))}
    ${cartao('Requisições respondidas', `${porSeg(p.respondidas)}/s`, `de ${porSeg(p.enviadas)}/s enviadas`, pct(p.respondidas, p.enviadas))}
    ${cartao('Compras concluídas', `${porSeg(p.compras)}/s`, `${inteiro(p.compras)} compras no pico`)}
    ${cartao('Pico de usuários ao mesmo tempo', inteiro(r.picoSimultaneos), 'no site no mesmo instante')}
    ${cartao('Barrados na porta', `${porSeg(p.barradosNaPorta)}/s`, `${inteiro(p.barradosNaPorta)} requisições recusadas pelo limite`)}
    ${r.fila ? cartao('Fila de compras', inteiro(r.fila.maior), r.fila.esvaziouDepoisS === undefined ? 'no máximo esperando o worker; não esvaziou a tempo' : `no máximo esperando o worker; esvaziou ${Math.round(r.fila.esvaziouDepoisS)} s depois do fim`) : ''}
  </div>

  <h2>2 · O pico: a espera</h2>
  <div class="bloco">
    ${espera('Abrir uma página', p.espera.pagina, r.metas.paginaMs)}
    ${espera('Concluir a compra', p.espera.compra, r.metas.compraMs)}
    ${r.sala ? espera('Esperar a vez na sala', r.sala.espera, r.sala.metaMs) : ''}
  </div>

  <h2>2 · O pico: a velocidade de cada endpoint</h2>
  <p class="detalhe" style="margin:-6px 0 14px">Todos os públicos juntos: usuários, engajados e robôs.</p>
  <div class="bloco">
    ${tabelaDeEndpoints(r.endpoints.pico)}
  </div>

  <h2>Metas do pico</h2>
  <div class="metas">${metas(r.metas.lista)}</div>

  <footer>
    "Pessoas no site ao mesmo tempo" é estimado pela Lei de Little: usuários chegando por segundo × tempo médio que cada um passa no site.<br>
    Gráficos ao longo da rodada: <code>relatorios/ultimo-teste.html</code>
  </footer>
</main>`,
  );
}
