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

function funil(f) {
  const etapas = [
    ['Chegaram', f.chegaram],
    ['Conseguiram entrar no site', f.entraram],
    ['Viram a programação', f.viramProgramacao],
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
  .degrau + .degrau { margin-top: 6px; }
  .degrau.cabecalho { color: var(--apagado); font-size: 13px; padding-top: 0; padding-bottom: 4px; }
  .degrau.viavel { background: #f0fdf4; } .degrau.inviavel { background: #fef2f2; }
  .degrau .fas { font-weight: 800; font-size: 20px; }
  .degrau .estado { font-size: 22px; text-align: center; }
  @media (max-width: 700px) {
    .degrau { grid-template-columns: 60px repeat(4, 1fr) 40px; font-size: 14px; }
    .degrau .opcional { display: none; }
  }
  .dupla { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
  .dupla > div + div { border-left: 1px solid var(--linha); padding-left: 28px; }
  .dupla .rotulo { margin-bottom: 6px; }
  .dupla .grande { font-size: clamp(36px, 6vw, 60px); }
  @media (max-width: 700px) {
    .dupla { grid-template-columns: 1fr; }
    .dupla > div + div { border-left: 0; padding-left: 0; border-top: 1px solid var(--linha); padding-top: 20px; }
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

function tabelaDeDegraus(s, metas) {
  const classe = (valor, limite) => (valor === undefined ? '' : valor <= limite ? 'bom' : 'ruim');
  const porcento = (fracao) => (fracao === undefined ? '—' : `${decimal(fracao * 100)}%`);
  const linhas = s.degraus.map(
    (d) => `<div class="degrau ${d.viavel ? 'viavel' : 'inviavel'}">
      <div class="fas">${d.usuariosPorSegundo}/s</div>
      <div>${d.simultaneos === undefined ? '—' : inteiro(d.simultaneos)}</div>
      <div class="opcional">${decimal(d.comprasPorSegundo)}/s</div>
      <div class="${classe(d.p95Pagina, metas.paginaMs)}">${tempo(d.p95Pagina)}</div>
      <div class="${classe(d.p95Compra, metas.compraMs)}">${tempo(d.p95Compra)}</div>
      <div class="opcional ${d.erros === undefined ? '' : d.erros < metas.erros ? 'bom' : 'ruim'}">${porcento(d.erros)}</div>
      <div class="${d.barrados < metas.erros ? 'bom' : 'ruim'}">${porcento(d.barrados)}</div>
      <div class="estado">${d.viavel ? '✅' : '❌'}</div>
    </div>`,
  );
  return `<div class="degrau cabecalho">
      <div>usuários chegando</div><div>pessoas no site ao mesmo tempo</div><div class="opcional">compras</div>
      <div>95% das páginas abriram em até</div><div>95% compraram em até</div><div class="opcional">erros</div><div>barrados na porta</div>
      <div></div>
    </div>
    ${linhas.join('')}`;
}

export function gerarHtml(r) {
  const s = r.subida;
  const p = r.pico;
  const f = p.funil;
  const e = r.engajados;
  const porSeg = (total) => decimal(total / p.duracaoS);

  return pagina(
    `Estreia · ${r.etapa}`,
    `
<header><div>
  <div class="selo">Teste de carga · ${r.etapa}</div>
  <h1>Estreia do maior filme da história</h1>
  <p>Como numa loja de verdade, a maioria só olha: de cada 10 usuários, 3 compram. Primeiro o público cresce aos poucos, para descobrir até onde o Ingressa aguenta. Depois, o pico:
  ${usuarios(p.usuariosPorSegundo)} por segundo, ${usuarios(p.engajadosPorSegundo)} muito engajados por segundo e ${p.robos} robôs cambistas, durante 1 minuto.</p>
</div></header>
<main>
  <section class="veredito dupla">
    <div>
      <div class="rotulo">O máximo que o Ingressa aguenta</div>
      ${vereditoCapacidade(s)}
    </div>
    <div>
      <div class="rotulo">No pico</div>
      <div class="grande">${pct(f.compraram, f.tentaramComprar)}%</div>
      <p>de quem tentou comprar conseguiu: ${inteiro(f.compraram)} de ${inteiro(f.tentaramComprar)}.</p>
    </div>
  </section>
  ${alertas(r)}

  <h2>1 · A subida: até quantos usuários o Ingressa aguenta?</h2>
  <p class="detalhe" style="margin:-6px 0 14px">A chegada de usuários sobe em degraus de ${s.duracaoDegrauS} s. Um degrau é viável quando 95% das páginas (programação e mapa) abrem em até ${tempo(r.metas.paginaMs)}, 95% compram em até ${tempo(r.metas.compraMs)}, e menos de ${decimal(r.metas.erros * 100)}% das requisições dão erro ou são barradas no limite.</p>
  <div class="bloco">${tabelaDeDegraus(s, r.metas)}</div>

  <h2>2 · O pico: o sistema</h2>
  <div class="cartoes">
    ${cartao('Ingressos vendidos', inteiro(r.vendidos), `de ${inteiro(r.lugares)} lugares, na rodada inteira`, pct(r.vendidos, r.lugares))}
    ${cartao('Pico de usuários ao mesmo tempo', inteiro(r.picoSimultaneos), 'esperando uma resposta no mesmo instante')}
    ${cartao('Requisições respondidas', `${porSeg(p.respondidas)}/s`, `de ${porSeg(p.enviadas)}/s enviadas`, pct(p.respondidas, p.enviadas))}
    ${cartao('Compras concluídas', `${porSeg(p.compras)}/s`, `${inteiro(p.compras)} compras no pico`)}
    ${cartao('Barrados na porta', `${porSeg(p.barradosNaPorta)}/s`, `${inteiro(p.barradosNaPorta)} requisições recusadas pelo limite`)}
  </div>

  <h2>2 · O pico: o caminho do usuário</h2>
  <div class="bloco">${funil(f)}</div>
  <div class="detalhe" style="margin-top:10px">Só olharam e foram embora: <b>${inteiro(p.soOlharam)}</b> · Desistiram porque uma página não carregou em 60 s: <b>${inteiro(p.desistiram)}</b> · Barrados na porta: <b>${inteiro(p.barrados)}</b> · Encontraram a sessão esgotada: <b>${inteiro(p.esgotado)}</b></div>

  <h2>2 · O pico: os usuários muito engajados</h2>
  <p class="detalhe" style="margin:-6px 0 14px">Nunca desistem: esperam o quanto for preciso e, se algo der errado, tentam de novo.</p>
  <div class="cartoes">
    ${cartao('Conseguiram comprar', `${pct(e.compraram, e.chegaram)}%`, `${inteiro(e.compraram)} de ${inteiro(e.chegaram)} engajados`, pct(e.compraram, e.chegaram))}
    ${cartao('Ainda esperando no fim', inteiro(e.aindaEsperando), 'o teste acabou e eles continuavam lá')}
    ${cartao('Tempo até comprar', tempo(e.tempo.mediana), `metade em até isso; o pior: ${tempo(e.tempo.pior)}`)}
    ${cartao('Tentativas', inteiro(e.tentativas), `${e.chegaram ? decimal(e.tentativas / e.chegaram) : '0,0'} por engajado, em média`)}
  </div>

  <h2>2 · O pico: a espera</h2>
  <div class="bloco">
    ${espera('Abrir uma página', p.espera.pagina, r.metas.paginaMs)}
    ${espera('Concluir a compra', p.espera.compra, r.metas.compraMs)}
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
