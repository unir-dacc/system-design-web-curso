// Usuários navegando: lista de filmes -> sessões -> página da sessão -> mapa de assentos.
// Ninguém compra; só leitura. Mostra o custo de ler sempre do banco e do sistema do cinema.
//
//   make load SCRIPT=navegacao
//   make load SCRIPT=navegacao VUS=100

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL } from './lib/ingressa.js';

const VUS = Number(__ENV.VUS || 50);

export const options = {
  stages: [
    { duration: '15s', target: VUS },
    { duration: '45s', target: VUS },
    { duration: '5s', target: 0 },
  ],
  thresholds: {
    'http_req_duration{name:GET /sessoes/:id/assentos}': ['p(95)<1000'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const filmeId = 1 + Math.floor(Math.random() * 3);
  const sessaoId = 1 + Math.floor(Math.random() * 6);

  http.get(`${BASE_URL}/filmes`, { tags: { name: 'GET /filmes' } });
  http.get(`${BASE_URL}/sessoes?filme_id=${filmeId}`, { tags: { name: 'GET /sessoes' } });
  http.get(`${BASE_URL}/sessoes/${sessaoId}`, { tags: { name: 'GET /sessoes/:id' } });
  const mapa = http.get(`${BASE_URL}/sessoes/${sessaoId}/assentos`, { tags: { name: 'GET /sessoes/:id/assentos' } });

  check(mapa, { 'mapa carregou': (r) => r.status === 200 });
  sleep(1);
}
