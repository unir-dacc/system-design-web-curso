<p align="center">
  <img src="imagens/banner.svg" alt="Mural: o dia em que um post viralizou" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy">
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/k6-teste%20de%20carga-7D64FF?style=for-the-badge&logo=k6&logoColor=white" alt="k6">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Compose">
</p>

<p align="center">
  <b>Seguir, publicar, curtir, comentar. Parece simples.</b><br>
  Até a maior celebridade da rede publicar um post que todo mundo quer ver.
</p>

<p align="center">
  <a href="#-comece-em-1-minuto">Comece agora</a> ·
  <a href="#-as-aulas">As aulas</a> ·
  <a href="#-o-dia-em-que-um-post-viralizou">O teste de carga</a> ·
  <a href="#-as-regras-do-jogo">As regras do jogo</a>
</p>

---

## 💜 Por que uma rede social?

Porque poucas aplicações maltratam tanto um banco de dados. Para montar **um único feed**, o
banco precisa cruzar quem eu sigo com **1 milhão de posts**, ordenar do mais novo para o mais
antigo, paginar e contar as curtidas de cada um. E a rede não é igual para todo mundo:

<p align="center">
  <img src="imagens/rede.svg" alt="Uma rede desigual: poucas celebridades, algumas contas médias e a multidão" width="90%">
</p>

O Mural é essa rede social, rodando na sua máquina com uma rede inteira no banco. A cada aula
ele enfrenta **um problema de banco de dados** que aparece quando a carga cresce, e a gente
mede, com números, o que muda.

## 🚀 Comece em 1 minuto

Você só precisa do **Docker**. A partir da raiz do repositório:

```bash
cd mural/01-ponto-de-partida

docker compose up -d --build --wait                                # sobe o Mural (a 1ª vez cria a rede inteira)
docker compose run --rm --service-ports k6 run /scripts/viral.js   # o dia em que um post viralizou
```

Enquanto o teste roda, abra o painel ao vivo em **http://localhost:5665**. No fim, o
relatório completo fica em **`relatorios/viral.html`**.

<details>
<summary><b>Outros comandos úteis</b></summary>

```bash
docker compose stats                          # CPU e memória de cada peça, ao vivo
docker compose exec postgres psql -U mural    # o banco, para olhar por dentro
docker compose --profile observar up -d pghero   # painel do banco em http://localhost:8080
docker compose down -v                        # derruba e apaga os dados
```

</details>

## 📚 As aulas

Cada etapa é uma pasta independente, com o código, o `docker-compose.yml` e um roteiro
para a aula (`DEMO.md`): o que rodar, onde olhar e as perguntas para a turma.

| Etapa | Tema |
|:-----:|------|
| [`01-ponto-de-partida`](01-ponto-de-partida/) | **O ponto de partida.** Um backend robusto (nginx e 4 réplicas async) na frente de um banco usado do jeito mais direto com o ORM. Quanto ele aguenta? |
| [`02-codigo-robusto`](02-codigo-robusto/) | **O código robusto.** Sem peça nova: os índices certos, o fim do N+1, uma consulta do feed que deixa o índice trabalhar, a paginação por cursor e o total de curtidas guardado no post |

> 🚧 **Em construção.** As próximas aulas vão atacar, uma de cada vez, os problemas que
> aparecem no banco quando o Mural cresce.

## 🧩 O que tem dentro

<p align="center">
  <img src="imagens/arquitetura.svg" alt="O público (k6) chega ao nginx, que distribui entre 4 réplicas do Mural com CPU sem limite; todas falam com um único PostgreSQL limitado a 1 CPU e 1 GB" width="90%">
</p>

O lado do app é robusto desde a primeira aula: o **nginx** distribui as requisições entre
**4 réplicas** do Mural (FastAPI async, 4 processos cada), com CPU de sobra. Quando o banco
não dá conta a tempo, o Mural responde na hora com 503, em vez de ficar pendurado. Do outro
lado, um único **PostgreSQL com 1 CPU e 1 GB**: é ele que chega no limite, e é nele que cada
aula mexe.

| Rota | O que faz |
|------|-----------|
| `GET /feed?usuario_id=&pagina=` | os posts de quem o usuário segue, dos mais novos para os mais antigos, de 20 em 20 (a partir da etapa 02, a próxima página é `antes_de=`, o `criado_em` do último post visto) |
| `GET /usuarios/{id}` | o perfil: o usuário e os posts dele |
| `GET /posts/{id}` | o post com os comentários mais recentes |
| `POST /posts` | publica: `{"usuario_id": 42, "texto": "..."}` |
| `POST /posts/{id}/curtidas` | curte: `{"usuario_id": 42}` (201; se já tinha curtido, 200) |
| `POST /posts/{id}/comentarios` | comenta: `{"usuario_id": 42, "texto": "..."}` |

Sem login, para simplificar: quem escreve diz quem é no corpo da requisição.

### A rede inicial

Na primeira subida, o Mural cria uma rede inteira, direto no banco:

| 👥 Usuários | 🔗 "Segue" | 📝 Posts | ❤️ Curtidas | 💬 Comentários |
|:-----------:|:----------:|:--------:|:-----------:|:--------------:|
| 100 mil | ~5 milhões | 1 milhão | ~5 milhões | 500 mil |

Desigual como uma rede de verdade: cada um segue de 1 a 300 pessoas, poucas celebridades
concentram os seguidores, e poucos posts concentram as curtidas. Para mudar o tamanho:
`USUARIOS_INICIAIS`, `POSTS_INICIAIS`, `CURTIDAS_INICIAIS` e `COMENTARIOS_INICIAIS`
(veja o `docker-compose.yml`).

## 🔥 O dia em que um post viralizou

Um único teste de carga, [`shared/load-tests/viral.js`](shared/load-tests/viral.js), igual
em todas as aulas. A maior celebridade da rede publica um post, e todo mundo aparece.

<p align="center">
  <img src="imagens/teste.svg" alt="A subida em degraus crescentes, seguida do pico de 1.000 requisições por segundo por 30 segundos" width="90%">
</p>

1. **A subida:** as requisições chegam em degraus de 10 segundos (1 por segundo, 2, 5, 10...). Em cada degrau o teste
   confere se o Mural continua viável e descobre **quantas requisições por segundo ele aguenta**.
2. **O pico:** por 30 segundos chegam **1.000 requisições por segundo**. A maioria das pessoas fica
   na primeira página do feed, poucas rolam bem fundo, e quem rola pede uma página depois da
   outra. Quem espera desiste depois de 5 s.

<p align="center">
  <img src="imagens/mistura.svg" alt="De cada 100 pessoas no pico: 70 abrem o feed, 10 um perfil, 10 um post, 7 curtem, 2 publicam e 1 comenta" width="90%">
</p>

No fim, o relatório (`relatorios/viral.html`) mostra:

- 📈 **a capacidade:** até quantas requisições por segundo o Mural aguenta;
- 🪜 **a progressão:** degrau a degrau, quantas chegaram e quantas foram atendidas;
- ⏱️ **a velocidade de cada endpoint**, no último degrau viável e no pico;
- ❤️ **a conferência das curtidas do post viral:** quantas estão gravadas no banco e quantas o Mural mostra;
- 🏁 **a comparação com as etapas anteriores**, lado a lado.

E para ver o que aconteceu **dentro do banco** durante a rodada, o **pgHero**
(`docker compose --profile observar up -d pghero`, em **http://localhost:8080**) mostra
as consultas que mais tomaram tempo do Postgres, os índices e as tabelas. As estatísticas
são zeradas no começo de cada teste, então ele mostra só a rodada.

## 📏 As regras do jogo

- **O app tem CPU de sobra; o banco, não:** o Postgres tem sempre **1 CPU e 1 GB de RAM**.
  Uma peça nova do lado do banco (um pool de conexões, uma réplica, um cache) divide esse
  mesmo orçamento.
- **Os ganhos vêm do que se faz no banco**, nunca de banco maior.
- **Toda aula se mede com o mesmo teste**, e o relatório compara com as etapas anteriores.

<p align="center">
  <sub>Parte do <a href="../">Mini Curso de System Design para Aplicações Web</a> · feito para quem está começando 💜</sub>
</p>
