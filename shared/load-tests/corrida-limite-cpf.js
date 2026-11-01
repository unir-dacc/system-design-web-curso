// Condição de corrida no limite de ingressos por CPF (máximo 6 por sessão).
// 20 requisições simultâneas com o MESMO CPF, cada uma comprando 1 assento diferente.
//
// Esperado: 6 compras confirmadas e 14 recusadas pela regra (422).
//
//   make load SCRIPT=corrida-limite-cpf

import { Counter } from 'k6/metrics';
import { comprar, gerarCpf, resumo } from './lib/ingressa.js';

const SESSAO = 2;
const TENTATIVAS = 20;

const confirmadas = new Counter('compras_confirmadas');
const barradas = new Counter('barradas_pela_regra');

export const options = {
  scenarios: {
    corrida: { executor: 'per-vu-iterations', vus: TENTATIVAS, iterations: 1, maxDuration: '2m' },
  },
  thresholds: {
    // A regra de negócio diz no máximo 6. Se passar disso, o teste falha.
    compras_confirmadas: ['count<=6'],
  },
};

export function setup() {
  return { cpf: gerarCpf() };
}

export default function ({ cpf }) {
  const resposta = comprar({ sessaoId: SESSAO, cpf, itens: [{ assento: `A${__VU}`, tipo: 'inteira' }] });
  if (resposta.status === 201) confirmadas.add(1);
  if (resposta.status === 422) barradas.add(1);
}

export function teardown({ cpf }) {
  console.log(`CPF ${cpf} | resumo da sessão ${SESSAO}: ${JSON.stringify(resumo(SESSAO))}`);
}
