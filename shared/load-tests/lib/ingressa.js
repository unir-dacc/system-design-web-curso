import http from 'k6/http';

export const BASE_URL = __ENV.BASE_URL || 'http://ingressa:8000';
const CINEMA_URL = __ENV.CINEMA_URL || 'http://sistema-cinema:8000';
const GATEWAY_URL = __ENV.GATEWAY_URL || 'http://gateway-pagamento:8000';

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

// Apaga pedidos, ingressos, reservas e cobranças para que toda rodada parta
// do mesmo estado. A CONFIGURAÇÃO dos simuladores (latência, erros...) é mantida.
// Para pular: -e RESET=0
export function resetarTudo() {
  if (__ENV.RESET === '0') return;
  for (const url of [`${BASE_URL}/admin/reset`, `${CINEMA_URL}/admin/reset`, `${GATEWAY_URL}/admin/reset`]) {
    const resposta = http.post(url, null, { tags: { name: 'reset' } });
    if (resposta.status !== 200) throw new Error(`Falha ao resetar ${url}: ${resposta.status}`);
  }
  console.log('Estado zerado: Ingressa, cinema e gateway');
}
