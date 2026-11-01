import http from 'k6/http';

export const BASE_URL = __ENV.BASE_URL || 'http://ingressa:8000';

// Status que fazem parte do negócio e NÃO são falhas do sistema:
// 402 pagamento recusado, 409 assento já ocupado, 422 regra de negócio
http.setResponseCallback(http.expectedStatuses(200, 201, 402, 409, 422));

export const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } };

// Gera um CPF com dígitos verificadores válidos
export function gerarCpf() {
  const digitos = Array.from({ length: 9 }, () => Math.floor(Math.random() * 10));
  for (const tamanho of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < tamanho; i++) soma += digitos[i] * (tamanho + 1 - i);
    digitos.push(((soma * 10) % 11) % 10);
  }
  return digitos.join('');
}

export function comprar({ sessaoId, cpf, itens, cartao = 'tok_aprovado' }) {
  const corpo = {
    sessao_id: sessaoId,
    nome: 'Cliente Teste',
    cpf,
    email: `cliente.${cpf}@exemplo.com`,
    cartao_token: cartao,
    itens,
  };
  return http.post(`${BASE_URL}/pedidos`, JSON.stringify(corpo), {
    ...JSON_HEADERS,
    tags: { name: 'POST /pedidos' },
  });
}

export function resumo(sessaoId) {
  return http.get(`${BASE_URL}/sessoes/${sessaoId}/resumo`).json();
}
