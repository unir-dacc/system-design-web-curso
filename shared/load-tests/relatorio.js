// Relatório visual da estreia: um HTML único, sem dependências, para abrir
// no navegador e projetar para a turma.

const inteiro = (n) => String(Math.round(n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
const decimal = (n) => (n || 0).toFixed(1).replace('.', ',');
const pct = (parte, total) => (total ? Math.round((parte / total) * 100) : 0);
const tempo = (ms) => {
  if (ms === undefined || ms === null) return '—';
  return ms >= 1000 ? `${decimal(ms / 1000)} s` : `${Math.round(ms)} ms`;
};

function alertas(r) {
  const lista = [];
  if (r.travou) {
    lista.push(
      'O Ingressa <b>travou</b> e não voltou nem depois que o público foi embora.' +
        ' Para destravar: <code>docker compose restart ingressa</code>',
    );
  }
  const fantasmas = r.vendidos - r.confirmados;
  if (fantasmas > 0) {
    lista.push(
      `<b>${inteiro(fantasmas)} ingressos</b> foram vendidos para quem já tinha desistido:` +
        ' a pessoa foi embora sem saber que comprou.',
    );
  }
  return lista.map((texto) => `<div class="alerta">⚠️ ${texto}</div>`).join('');
}

function cartao(titulo, valor, detalhe, barra) {
  const progresso = barra === undefined ? '' : `<div class="trilho"><div class="cheio" style="width:${barra}%"></div></div>`;
  return `<div class="cartao"><div class="rotulo">${titulo}</div><div class="valor">${valor}</div>${progresso}<div class="detalhe">${detalhe}</div></div>`;
}

function funil(f) {
  const etapas = [
    ['Chegaram', f.chegaram],
    ['Conseguiram entrar no site', f.entraram],
    ['Viram o mapa de assentos', f.viramMapa],
    ['Tentaram comprar', f.tentaramComprar],
    ['Compraram', f.compraram],
  ];
  return etapas
    .map(([nome, total]) => {
      const p = pct(total, f.chegaram);
      return `<div class="etapa">
        <div class="nome">${nome}</div>
        <div class="trilho largo"><div class="cheio" style="width:${Math.max(p, total ? 1 : 0)}%"></div></div>
        <div class="numero">${inteiro(total)} <span>${p}%</span></div>
      </div>`;
    })
    .join('');
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

export function gerarHtml(r) {
  const f = r.funil;
  const porSeg = (total) => decimal(total / r.duracaoS);

  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estreia · ${r.etapa}</title>
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
</style>
</head>
<body>
<header><div>
  <div class="selo">Teste de carga · ${r.etapa}</div>
  <h1>Estreia do maior filme da história</h1>
  <p>${r.fasPorSegundo} fãs chegando por segundo + ${r.robos} robôs cambistas, durante 1 minuto</p>
</div></header>
<main>
  <section class="veredito">
    <div class="grande">${pct(f.compraram, f.chegaram)}% <small>dos fãs conseguiram comprar</small></div>
    <p>${inteiro(f.compraram)} de ${inteiro(f.chegaram)} fãs saíram com ingresso.</p>
  </section>
  ${alertas(r)}

  <h2>O sistema</h2>
  <div class="cartoes">
    ${cartao('Ingressos vendidos', inteiro(r.vendidos), `de ${inteiro(r.lugares)} lugares`, pct(r.vendidos, r.lugares))}
    ${cartao('Pico de usuários ao mesmo tempo', inteiro(r.picoSimultaneos), 'esperando uma resposta no mesmo instante')}
    ${cartao('Requisições respondidas', `${porSeg(r.respondidas)}/s`, `de ${porSeg(r.enviadas)}/s enviadas`, pct(r.respondidas, r.enviadas))}
    ${cartao('Compras concluídas', `${porSeg(r.compras)}/s`, `${inteiro(r.compras)} no total, contando os robôs`)}
  </div>

  <h2>O caminho do fã</h2>
  <div class="bloco">${funil(f)}</div>
  <div class="detalhe" style="margin-top:10px">Desistiram depois de esperar 30 s: <b>${inteiro(r.desistiram)}</b> · Encontraram a sessão esgotada: <b>${inteiro(r.esgotado)}</b></div>

  <h2>A espera</h2>
  <div class="bloco">
    ${espera('Abrir o mapa', r.espera.mapa, 2000)}
    ${espera('Concluir a compra', r.espera.compra, 3000)}
  </div>

  <h2>Metas</h2>
  <div class="metas">${metas(r.metas)}</div>

  <footer>Gráficos ao longo do minuto: <code>relatorios/ultimo-teste.html</code></footer>
</main>
</body>
</html>
`;
}
