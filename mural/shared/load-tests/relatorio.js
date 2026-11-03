// Relatório visual do dia em que um post viralizou: um HTML único, sem dependências,
// para abrir no navegador e projetar para a turma. Mesmo visual dos outros labs.

const inteiro = (n) => String(Math.round(n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
const decimal = (n) => (n || 0).toFixed(1).replace('.', ',');
const porcento = (fracao) => (fracao === undefined || fracao === null ? '—' : `${decimal(fracao * 100)}%`);
const tempo = (ms) => {
  if (ms === undefined || ms === null) return '—';
  return ms >= 1000 ? `${decimal(ms / 1000)} s` : `${Math.round(ms)} ms`;
};

function alertas(r) {
  const lista = [];
  if (r.subida.caiuEm) {
    lista.push(`O Mural <b>caiu ainda na subida</b>, com ${r.subida.caiuEm.porSegundo} requisições por segundo, antes de o pico começar.`);
  }
  if (r.travou) lista.push('O Mural <b>travou</b> e não voltou. Para destravar: <code>docker compose restart app</code>');
  if (r.curtidas.contadas !== undefined && r.curtidas.aceitas && r.curtidas.contadas < r.curtidas.aceitas) {
    lista.push(
      `<b>${inteiro(r.curtidas.aceitas)} curtidas</b> no post viral foram aceitas, mas o Mural mostra só <b>${inteiro(r.curtidas.contadas)}</b>.`,
    );
  }
  return lista.map((texto) => `<div class="alerta">⚠️ ${texto}</div>`).join('');
}

function cartao(titulo, valor, detalhe, barra) {
  const progresso = barra === undefined ? '' : `<div class="trilho"><div class="cheio" style="width:${barra}%"></div></div>`;
  return `<div class="cartao"><div class="rotulo">${titulo}</div><div class="valor">${valor}</div>${progresso}<div class="detalhe">${detalhe}</div></div>`;
}

// Procura x atendidas, degrau a degrau até o pico (SVG puro)
function graficoDaProgressao(pontos) {
  const L = 1000, A = 340, esq = 56, dir = 12, topo = 16, base = 56;
  const largura = L - esq - dir, altura = A - topo - base;
  const maximo = Math.max(1, ...pontos.map((p) => Math.max(p.procura, p.atendidas))) * 1.1;
  const y = (valor) => topo + altura - (valor / maximo) * altura;
  const grupo = largura / pontos.length;
  const barra = grupo * 0.34;
  const grade = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const valor = maximo * f;
    return `<line x1="${esq}" x2="${L - dir}" y1="${y(valor)}" y2="${y(valor)}" stroke="#e7e2d8"/>
      <text x="${esq - 8}" y="${y(valor) + 4}" text-anchor="end" font-size="13" fill="#78716c">${inteiro(valor)}</text>`;
  });
  const barras = pontos.map((p, i) => {
    const x = esq + i * grupo + grupo / 2;
    const fundo = p.pico ? `<rect x="${esq + i * grupo}" y="${topo}" width="${grupo}" height="${altura}" fill="#fef9e7"/>` : '';
    const cor = p.pico ? '#d4a017' : p.viavel ? '#15803d' : '#b91c1c';
    return `${fundo}
      <rect x="${x - barra}" y="${y(p.procura)}" width="${barra}" height="${topo + altura - y(p.procura)}" fill="#d6d3d1"><title>${p.rotulo}: ${inteiro(p.procura)} chegando por segundo</title></rect>
      <rect x="${x}" y="${y(p.atendidas)}" width="${barra}" height="${topo + altura - y(p.atendidas)}" fill="${cor}"><title>${p.rotulo}: ${decimal(p.atendidas)} atendidas por segundo</title></rect>
      <text x="${x}" y="${A - base + 22}" text-anchor="middle" font-size="12" font-weight="${p.pico ? 700 : 400}" fill="#1c1917">${p.pico ? 'pico' : p.rotulo}</text>`;
  });
  return `<svg viewBox="0 0 ${L} ${A}" width="100%" role="img" aria-label="Requisições chegando e atendidas por segundo em cada degrau e no pico">
    ${grade.join('')}
    ${barras.join('')}
    <text x="${esq + largura / 2}" y="${A - 8}" text-anchor="middle" font-size="13" fill="#78716c">requisições chegando por segundo</text>
  </svg>
  <div class="legenda">
    <span><i style="background:#d6d3d1"></i>chegando (por segundo)</span>
    <span><i style="background:#15803d"></i>atendidas, num degrau viável</span>
    <span><i style="background:#b91c1c"></i>atendidas, num degrau inviável</span>
    <span><i style="background:#d4a017"></i>atendidas, no pico</span>
  </div>`;
}

function tabelaDeDegraus(s, metas) {
  const classe = (valor, limite) => (valor === undefined ? '' : valor <= limite ? 'bom' : 'ruim');
  const linhas = s.degraus.map(
    (d) => `<div class="degrau ${d.viavel ? 'viavel' : 'inviavel'}">
      <div class="fas">${inteiro(d.porSegundo)}/s</div>
      <div>${decimal(d.atendidasPorSegundo)}/s</div>
      <div class="${classe(d.p95Feed, metas.feedMs)}">${tempo(d.p95Feed)}</div>
      <div class="opcional ${classe(d.p95Escrita, metas.escritaMs)}">${tempo(d.p95Escrita)}</div>
      <div class="${d.erros === undefined ? '' : d.erros < metas.erros ? 'bom' : 'ruim'}">${porcento(d.erros)}</div>
      <div class="opcional"></div><div class="opcional"></div>
      <div class="estado">${d.viavel ? '✅' : '❌'}</div>
    </div>`,
  );
  return `<div class="degrau cabecalho">
      <div>chegando</div><div>atendidas</div><div>95% dos feeds em até</div><div class="opcional">95% das escritas em até</div>
      <div>erros ou barradas</div><div class="opcional"></div><div class="opcional"></div><div></div>
    </div>
    ${linhas.join('')}`;
}

function tabelaDeEndpoints(lista) {
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

function comparacao(lista) {
  const fim = (c) => (c.travou ? '<span class="ruim">travou</span>' : c.caiuNaSubida ? '<span class="aviso">caiu e voltou</span>' : '<span class="bom">ficou de pé</span>');
  const quando = (iso) => new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  const linhas = lista.map(
    (c) => `<div class="linha-etapa ${c.atual ? 'atual' : ''}">
      <div><b>${c.etapa}</b><span>${c.hardware || '2 CPUs / 2 GB'}</span><span>${c.atual ? 'esta rodada' : `rodou em ${quando(c.quando)}`}</span></div>
      <div class="forte">${inteiro(c.capacidade)}/s</div>
      <div>${porcento(c.atendidasNoPico)}</div>
      <div>${tempo(c.p95FeedNoPico === null ? undefined : c.p95FeedNoPico)}</div>
      <div class="opcional">${porcento(c.curtidasContadas)}</div>
      <div class="opcional"></div>
      <div>${fim(c)}</div>
    </div>`,
  );
  return `<div class="linha-etapa cabecalho">
      <div>etapa</div><div>aguenta</div><div>atendidas no pico</div><div>95% dos feeds no pico em até</div>
      <div class="opcional">curtidas mostradas</div><div class="opcional"></div><div>no fim</div>
    </div>
    ${linhas.join('')}`;
}

function metas(lista) {
  return lista
    .map((m) => {
      const classe = m.ok === null ? 'aviso' : m.ok ? 'bom' : 'ruim';
      const icone = m.ok === null ? '⚠️' : m.ok ? '✅' : '❌';
      return `<div class="meta ${classe}">${icone} ${m.texto}${m.detalhe ? `<span>${m.detalhe}</span>` : ''}</div>`;
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

export function gerarHtml(r) {
  const s = r.subida;
  const p = r.pico;
  const capacidade = s.capacidade
    ? `<div class="grande">${inteiro(s.capacidade.porSegundo)}/s</div><p>requisições por segundo. ${s.quebrou ? `Com ${inteiro(s.quebrou.porSegundo)}/s, fica inviável.` : 'Aguentou todos os degraus.'}</p>`
    : `<div class="grande">Inviável</div><p>Não aguentou nem ${s.degraus[0].porSegundo} requisições por segundo.</p>`;
  const contados = r.curtidas.contadas === undefined ? '—' : porcento(r.curtidas.aceitas ? r.curtidas.contadas / r.curtidas.aceitas : 1);

  return pagina(
    `Mural · ${r.etapa}`,
    `
<header><div>
  <div class="selo">Teste de carga · ${r.etapa}</div>
  <h1>O dia em que um post viralizou</h1>
  <p>O Mural já tem 100 mil usuários e 1 milhão de posts quando a maior celebridade da rede publica um post que todo mundo quer ver.
  Primeiro as requisições crescem aos poucos, para descobrir até onde ele aguenta. Depois, o pico: ${inteiro(p.porSegundo)} requisições
  por segundo durante 1 minuto. De cada 100, 70 abrem o feed, 10 um perfil, 10 um post com os comentários, 7 curtem, 2 publicam e
  1 comenta, e a maior parte das curtidas, dos comentários e das visitas a posts vai para o post viral.</p>
</div></header>
<main>
  <section class="veredito tripla">
    <div>
      <div class="rotulo">O máximo que o Mural aguenta</div>
      ${capacidade}
    </div>
    <div>
      <div class="rotulo">No pico, foram atendidas</div>
      <div class="grande">${porcento(p.enviadas ? p.atendidas / p.enviadas : 0)}</div>
      <p>das requisições: ${inteiro(p.atendidas)} de ${inteiro(p.enviadas)}.</p>
    </div>
    <div>
      <div class="rotulo">Curtidas do post viral mostradas pelo Mural</div>
      <div class="grande">${contados}</div>
      <p>${inteiro(r.curtidas.contadas)} mostradas de ${inteiro(r.curtidas.aceitas)} aceitas.</p>
    </div>
  </section>
  ${alertas(r)}

  <h2>A progressão: das primeiras requisições até o pico</h2>
  <p class="detalhe" style="margin:-6px 0 14px">A cada degrau chega mais gente. Enquanto as atendidas acompanham as que chegam, o Mural dá conta.</p>
  <div class="bloco">${graficoDaProgressao(r.progressao)}</div>

  <h2>O ganho de cada etapa</h2>
  <p class="detalhe" style="margin:-6px 0 14px">Esta rodada ao lado do último resultado de cada etapa anterior. Todas com 2 CPUs e 2 GB para o Mural.</p>
  <div class="bloco">${comparacao(r.comparacao)}</div>

  <h2>1 · A subida: quantas requisições por segundo o Mural aguenta?</h2>
  <p class="detalhe" style="margin:-6px 0 14px">Degraus de ${s.duracaoDegrauS} s. Um degrau é viável quando 95% dos feeds levam até ${tempo(r.metas.feedMs)}, 95% das escritas (curtir, publicar, comentar) até ${tempo(r.metas.escritaMs)}, e menos de ${decimal(r.metas.erros * 100)}% das requisições dão erro ou são barradas.</p>
  <div class="bloco">${tabelaDeDegraus(s, r.metas)}</div>

  <h2>1 · A subida: a velocidade de cada endpoint</h2>
  <div class="bloco">${tabelaDeEndpoints(r.endpoints.subida)}</div>

  <h2>2 · O pico: a velocidade de cada endpoint</h2>
  <p class="detalhe" style="margin:-6px 0 14px">Todo mundo junto. Requisições que nem chegaram a ser enviadas (todos esperando): <b>${inteiro(p.naoEnviadas)}</b>.</p>
  <div class="bloco">${tabelaDeEndpoints(r.endpoints.pico)}</div>

  <h2>Metas do pico</h2>
  <div class="metas">${metas(r.metas.lista)}</div>

  <footer>Gráficos ao longo da rodada: <code>relatorios/ultimo-teste.html</code></footer>
</main>`,
  );
}
