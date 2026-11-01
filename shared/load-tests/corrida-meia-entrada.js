// Condição de corrida na cota de meia-entrada (40% da sala).
// Sessão 4, Sala 3: 96 lugares -> cota de 38 meias.
// 60 pessoas diferentes tentam comprar meia-entrada ao mesmo tempo.
//
// Esperado: 38 meias confirmadas e 22 recusadas pela regra (422).
//
//   docker compose run --rm k6 run /scripts/corrida-meia-entrada.js

import { Counter } from 'k6/metrics';
import { comprar, gerarCpf, resumo } from './lib/ingressa.js';

const SESSAO = 4;
const TENTATIVAS = 60;
const FILEIRAS = 'ABCDEFGH';
const POR_FILEIRA = 12;

const confirmadas = new Counter('meias_confirmadas');
const barradas = new Counter('barradas_pela_regra');

export const options = {
  scenarios: {
    corrida: { executor: 'per-vu-iterations', vus: TENTATIVAS, iterations: 1, maxDuration: '2m' },
  },
  thresholds: {
    meias_confirmadas: ['count<=38'],
  },
};

export default function () {
  const indice = __VU - 1;
  const assento = `${FILEIRAS[Math.floor(indice / POR_FILEIRA)]}${(indice % POR_FILEIRA) + 1}`;
  const resposta = comprar({ sessaoId: SESSAO, cpf: gerarCpf(), itens: [{ assento, tipo: 'meia' }] });
  if (resposta.status === 201) confirmadas.add(1);
  if (resposta.status === 422) barradas.add(1);
}

export function teardown() {
  console.log(`Resumo da sessão ${SESSAO}: ${JSON.stringify(resumo(SESSAO))}`);
}
