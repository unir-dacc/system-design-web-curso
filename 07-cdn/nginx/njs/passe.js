// Confere o passe da sala de espera na borda, sem chamar o backend.
//
// O passe é "senha.assinatura": a assinatura é o HMAC-SHA256 da senha com o
// segredo da sala (os 16 primeiros caracteres, em hexadecimal). É o mesmo
// cálculo do app/sala.py, então o Nginx sabe dizer se um passe é verdadeiro
// sem perguntar a ninguém. Um passe só é emitido para uma senha já liberada,
// então a assinatura basta.
const crypto = require('crypto');

const SEGREDO = process.env.SEGREDO_DA_SALA || 'troque-em-producao';

function valido(r) {
  const passe = r.headersIn['X-Passe'] || '';
  const ponto = passe.indexOf('.');
  const senha = passe.slice(0, ponto);
  if (ponto < 1 || !/^[0-9]+$/.test(senha)) return '0';
  const esperada = crypto.createHmac('sha256', SEGREDO).update(senha).digest('hex').slice(0, 16);
  return passe.slice(ponto + 1) === esperada ? '1' : '0';
}

export default { valido };
