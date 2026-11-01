// Abertura das vendas da estreia (sessão 1, 400 lugares).
// Cada usuário abre o mapa, escolhe um assento livre e tenta comprar.
//
//   docker compose run --rm --service-ports k6 run /scripts/abertura-vendas.js
//   docker compose run --rm --service-ports k6 run -e VUS=200 /scripts/abertura-vendas.js

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, comprar, gerarCpf, resetarTudo, resumo } from './lib/ingressa.js';

const VUS = Number(__ENV.VUS || 100);
const SESSAO = 1;

const compras = new Counter('compras_confirmadas');
const ocupados = new Counter('assento_ja_ocupado');
const recusados = new Counter('pagamento_recusado');
const erros = new Counter('erros_do_sistema');

export const options = {
  scenarios: {
    abertura: {
      executor: 'ramping-vus',
      stages: [
        { duration: '10s', target: VUS },
        { duration: '50s', target: VUS },
      ],
      gracefulStop: '30s',
    },
  },
  thresholds: {
    'http_req_duration{name:POST /pedidos}': ['p(95)<3000'],
    http_req_failed: ['rate<0.01'],
  },
};

export function setup() {
  resetarTudo();
}

export default function () {
  const mapa = http.get(`${BASE_URL}/sessoes/${SESSAO}/assentos`, { tags: { name: 'GET /sessoes/:id/assentos' } });
  if (mapa.status !== 200) {
    erros.add(1);
    return;
  }

  const livres = mapa.json('assentos').filter((a) => a.status === 'livre');
  if (livres.length === 0) return;
  const escolhido = livres[Math.floor(Math.random() * livres.length)].codigo;

  // Cartão "comum": o gateway recusa uma pequena parte, como na vida real
  const resposta = comprar({
    sessaoId: SESSAO,
    cpf: gerarCpf(),
    itens: [{ assento: escolhido, tipo: 'inteira' }],
    cartao: `tok_cliente_${__VU}`,
  });

  check(resposta, { 'compra respondida sem erro': (r) => r.status < 500 && r.status !== 0 });
  if (resposta.status === 201) compras.add(1);
  else if (resposta.status === 409) ocupados.add(1);
  else if (resposta.status === 402) recusados.add(1);
  else erros.add(1);
}

export function teardown() {
  console.log(`Resumo da sessão ${SESSAO}: ${JSON.stringify(resumo(SESSAO))}`);
}
