package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
)

// As mesmas rotas e as mesmas respostas da versão em Python
func rotas() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		responderJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// Sala de espera
	mux.HandleFunc("POST /sala", entrarNaSalaDeEspera)
	mux.HandleFunc("GET /sala/{senha}", consultarAVez)

	// Catálogo (a programação e o mapa exigem o passe da sala)
	mux.HandleFunc("GET /filmes", exigePasse(listarFilmes))
	mux.HandleFunc("GET /sessoes", exigePasse(listarSessoes))
	mux.HandleFunc("GET /sessoes/{id}", detalharSessao)
	mux.HandleFunc("GET /sessoes/{id}/assentos", exigePasse(mapaDeAssentos))
	mux.HandleFunc("GET /sessoes/{id}/resumo", resumoDeVendas)

	// Pedidos e ingressos
	mux.HandleFunc("POST /pedidos", exigePasse(criarPedidoHandler))
	mux.HandleFunc("GET /pedidos/{id}", detalharPedido)
	mux.HandleFunc("GET /ingressos/{codigo}", detalharIngresso)
	mux.HandleFunc("GET /ingressos/{codigo}/qrcode", qrcodeDoIngresso)

	// Apoio às aulas
	mux.HandleFunc("POST /admin/reset", reset)
	mux.HandleFunc("GET /admin/fila", tamanhoDaFilaHandler)
	return mux
}

func idDaRota(r *http.Request, nome string) (int, error) {
	id, err := strconv.Atoi(r.PathValue(nome))
	if err != nil {
		return 0, erroHTTP{http.StatusUnprocessableEntity, nome + " precisa ser um número"}
	}
	return id, nil
}

// --- Sala de espera ---

func situacaoNaSala(ctx context.Context, w http.ResponseWriter, senha int) {
	naFrente := senha - senhasLiberadas(ctx)
	if naFrente <= 0 {
		responderJSON(w, http.StatusOK, map[string]any{"senha": senha, "liberado": true, "passe": passeDaSenha(senha)})
		return
	}
	// Volta quando for mais ou menos a sua vez (entre 1 e 60 segundos)
	espera := float64(naFrente) / float64(taxaAtual(ctx))
	w.Header().Set("Retry-After", strconv.Itoa(min(60, max(1, int(math.Ceil(espera))))))
	responderJSON(w, http.StatusOK, map[string]any{
		"senha": senha, "liberado": false, "pessoas_na_frente": naFrente, "espera_estimada_s": int(math.Round(espera)),
	})
}

func entrarNaSalaDeEspera(w http.ResponseWriter, r *http.Request) {
	senha, err := entrarNaSala(r.Context())
	if err != nil {
		responderErro(w, err)
		return
	}
	situacaoNaSala(r.Context(), w, senha)
}

func consultarAVez(w http.ResponseWriter, r *http.Request) {
	senha, err := idDaRota(r, "senha")
	if err != nil {
		responderErro(w, err)
		return
	}
	situacaoNaSala(r.Context(), w, senha)
}

// exigePasse: só atende quem já passou pela sala de espera (cabeçalho X-Passe)
func exigePasse(proxima http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !passeValido(r.Context(), r.Header.Get("X-Passe")) {
			responderJSON(w, http.StatusForbidden, map[string]any{"detail": "Entre na sala de espera (POST /sala) e aguarde a sua vez"})
			return
		}
		proxima(w, r)
	}
}

// --- Catálogo ---

type sessaoOut struct {
	ID                   int    `json:"id"`
	FilmeID              int    `json:"filme_id"`
	Filme                string `json:"filme"`
	Cinema               string `json:"cinema"`
	Sala                 string `json:"sala"`
	Inicio               string `json:"inicio"`
	PrecoInteiraCentavos int    `json:"preco_inteira_centavos"`
	PrecoMeiaCentavos    int    `json:"preco_meia_centavos"`
}

func paraSessaoOut(s sessao) sessaoOut {
	return sessaoOut{s.ID, s.FilmeID, s.Filme, s.Cinema, s.Sala, s.Inicio.In(fusoHorario).Format(time.RFC3339),
		s.PrecoInteiraCentavos, s.precoMeiaCentavos()}
}

// As respostas abaixo vêm do cache: o JSON pronto. As funções "montar" só
// rodam quando a cópia não existe.

func montarFilmes(ctx context.Context) ([]byte, error) {
	linhas, err := db.Query(ctx, "SELECT id, titulo, duracao_min, classificacao, sinopse FROM filmes ORDER BY id")
	if err != nil {
		return nil, err
	}
	type filmeOut struct {
		ID            int    `json:"id"`
		Titulo        string `json:"titulo"`
		DuracaoMin    int    `json:"duracao_min"`
		Classificacao string `json:"classificacao"`
		Sinopse       string `json:"sinopse"`
	}
	filmes, err := pgx.CollectRows(linhas, func(l pgx.CollectableRow) (filmeOut, error) {
		var f filmeOut
		err := l.Scan(&f.ID, &f.Titulo, &f.DuracaoMin, &f.Classificacao, &f.Sinopse)
		return f, err
	})
	if err != nil {
		return nil, err
	}
	return json.Marshal(filmes)
}

func montarSessoes(ctx context.Context, filmeID string) ([]byte, error) {
	consulta, args := selecionarSessoes+" ORDER BY s.inicio", []any{}
	if filmeID != "" {
		id, err := strconv.Atoi(filmeID)
		if err != nil {
			return nil, erroHTTP{http.StatusUnprocessableEntity, "filme_id precisa ser um número"}
		}
		consulta, args = selecionarSessoes+" WHERE s.filme_id = $1 ORDER BY s.inicio", []any{id}
	}
	linhas, err := db.Query(ctx, consulta, args...)
	if err != nil {
		return nil, err
	}
	sessoes, err := pgx.CollectRows(linhas, func(l pgx.CollectableRow) (sessaoOut, error) {
		s, err := lerSessao(l)
		return paraSessaoOut(s), err
	})
	if err != nil {
		return nil, err
	}
	return json.Marshal(sessoes)
}

func montarMapa(ctx context.Context, sessaoID int) ([]byte, error) {
	if _, err := buscarSessao(ctx, sessaoID); err != nil {
		return nil, err
	}
	assentos, err := buscarMapa(ctx, sessaoID)
	if err != nil {
		return nil, err
	}
	livres := 0
	for _, a := range assentos {
		if a.Status == "livre" {
			livres++
		}
	}
	return json.Marshal(map[string]any{"sessao_id": sessaoID, "livres": livres, "assentos": assentos})
}

func listarFilmes(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	conteudo, err := respostaPronta(ctx, "filmes", programacaoTTL, func() ([]byte, error) { return montarFilmes(ctx) })
	if err != nil {
		responderErro(w, err)
		return
	}
	jsonPronto(w, conteudo)
}

func listarSessoes(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	filmeID := r.URL.Query().Get("filme_id")
	chave := "sessoes:filme:" + map[bool]string{true: "None", false: filmeID}[filmeID == ""]
	conteudo, err := respostaPronta(ctx, chave, programacaoTTL, func() ([]byte, error) { return montarSessoes(ctx, filmeID) })
	if err != nil {
		responderErro(w, err)
		return
	}
	jsonPronto(w, conteudo)
}

func detalharSessao(w http.ResponseWriter, r *http.Request) {
	id, err := idDaRota(r, "id")
	if err == nil {
		var s sessao
		if s, err = buscarSessao(r.Context(), id); err == nil {
			responderJSON(w, http.StatusOK, paraSessaoOut(s))
			return
		}
	}
	responderErro(w, err)
}

// O mapa é apagado do cache sempre que uma compra mexe nos assentos da sessão.
// A validade curta cobre o resto: vendas feitas por outros canais.
func mapaDeAssentos(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id, err := idDaRota(r, "id")
	if err != nil {
		responderErro(w, err)
		return
	}
	conteudo, err := respostaPronta(ctx, chaveDoMapa(id), mapaTTL, func() ([]byte, error) { return montarMapa(ctx, id) })
	if err != nil {
		responderErro(w, err)
		return
	}
	jsonPronto(w, conteudo)
}

func resumoDeVendas(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id, err := idDaRota(r, "id")
	if err != nil {
		responderErro(w, err)
		return
	}
	s, err := buscarSessao(ctx, id)
	if err != nil {
		responderErro(w, err)
		return
	}
	var vendidos, meias, maiorCompra int
	err = db.QueryRow(ctx, `
		SELECT
		  (SELECT count(*) FROM ingressos WHERE sessao_id = $1),
		  (SELECT count(*) FROM ingressos WHERE sessao_id = $1 AND tipo = 'meia'),
		  (SELECT coalesce(max(q), 0) FROM (
		     SELECT count(i.id) AS q FROM ingressos i JOIN pedidos p ON p.id = i.pedido_id
		     WHERE i.sessao_id = $1 GROUP BY p.cpf) por_cpf)`, id).Scan(&vendidos, &meias, &maiorCompra)
	if err != nil {
		responderErro(w, err)
		return
	}
	responderJSON(w, http.StatusOK, map[string]int{
		"sessao_id": id, "capacidade": s.Capacidade, "ingressos_vendidos": vendidos, "meia_vendidas": meias,
		"cota_meia": s.Capacidade * cotaMeiaEntradaPct / 100, "maior_compra_por_cpf": maiorCompra,
	})
}

// --- Pedidos e ingressos ---

type ingresso struct {
	Codigo        string `json:"codigo"`
	Assento       string `json:"assento"`
	Tipo          string `json:"tipo"`
	PrecoCentavos int    `json:"preco_centavos"`
	QRCodeURL     string `json:"qrcode_url"`
}

type pedidoOut struct {
	ID               int        `json:"id"`
	SessaoID         int        `json:"sessao_id"`
	Nome             string     `json:"nome"`
	Email            string     `json:"email"`
	Status           string     `json:"status"`
	SubtotalCentavos int        `json:"subtotal_centavos"`
	TaxaCentavos     int        `json:"taxa_centavos"`
	TotalCentavos    int        `json:"total_centavos"`
	CriadoEm         string     `json:"criado_em"`
	Ingressos        []ingresso `json:"ingressos"`
}

func paraPedidoOut(ctx context.Context, p pedido) (pedidoOut, error) {
	saida := pedidoOut{p.ID, p.SessaoID, p.Nome, p.Email, p.Status, p.SubtotalCentavos, p.TaxaCentavos, p.TotalCentavos,
		p.CriadoEm.UTC().Format(time.RFC3339Nano), []ingresso{}}
	linhas, err := db.Query(ctx, "SELECT codigo, assento, tipo, preco_centavos FROM ingressos WHERE pedido_id = $1 ORDER BY id", p.ID)
	if err != nil {
		return saida, err
	}
	saida.Ingressos, err = pgx.CollectRows(linhas, lerIngresso)
	return saida, err
}

func lerIngresso(l pgx.CollectableRow) (ingresso, error) {
	var i ingresso
	err := l.Scan(&i.Codigo, &i.Assento, &i.Tipo, &i.PrecoCentavos)
	i.QRCodeURL = "/ingressos/" + i.Codigo + "/qrcode"
	return i, err
}

// 202 = "aceito, ainda processando": os assentos estão reservados e o worker
// conclui a compra. O cliente não precisa esperar: o resultado chega por e-mail.
func criarPedidoHandler(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var dados criarPedido
	if err := json.NewDecoder(r.Body).Decode(&dados); err != nil {
		responderErro(w, erroHTTP{http.StatusUnprocessableEntity, "JSON inválido"})
		return
	}
	if err := dados.validar(); err != nil {
		responderErro(w, err)
		return
	}
	p, err := realizarCompra(ctx, dados)
	var indisponiveis assentosIndisponiveis
	var inexistentes assentosInexistentes
	switch {
	case errors.As(err, &indisponiveis):
		responderErro(w, erroHTTP{http.StatusConflict, map[string]any{"mensagem": "Assentos indisponíveis", "indisponiveis": indisponiveis.assentos}})
		return
	case errors.As(err, &inexistentes):
		responderErro(w, erroHTTP{http.StatusUnprocessableEntity, fmt.Sprintf("Assentos inexistentes: %v", inexistentes.assentos)})
		return
	case err != nil:
		responderErro(w, err)
		return
	}
	saida, err := paraPedidoOut(ctx, p)
	if err != nil {
		responderErro(w, err)
		return
	}
	w.Header().Set("Location", fmt.Sprintf("/pedidos/%d", p.ID))
	responderJSON(w, http.StatusAccepted, saida)
}

func detalharPedido(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id, err := idDaRota(r, "id")
	if err == nil {
		var p pedido
		if p, err = buscarPedido(ctx, id); err == nil {
			var saida pedidoOut
			if saida, err = paraPedidoOut(ctx, p); err == nil {
				responderJSON(w, http.StatusOK, saida)
				return
			}
		}
	}
	responderErro(w, err)
}

func buscarIngresso(ctx context.Context, codigo string) (ingresso, error) {
	linhas, err := db.Query(ctx, "SELECT codigo, assento, tipo, preco_centavos FROM ingressos WHERE codigo = $1", codigo)
	if err != nil {
		return ingresso{}, err
	}
	i, err := pgx.CollectOneRow(linhas, lerIngresso)
	if errors.Is(err, pgx.ErrNoRows) {
		return i, erroHTTP{http.StatusNotFound, "Ingresso não encontrado"}
	}
	return i, err
}

func detalharIngresso(w http.ResponseWriter, r *http.Request) {
	i, err := buscarIngresso(r.Context(), r.PathValue("codigo"))
	if err != nil {
		responderErro(w, err)
		return
	}
	responderJSON(w, http.StatusOK, i)
}

func qrcodeDoIngresso(w http.ResponseWriter, r *http.Request) {
	i, err := buscarIngresso(r.Context(), r.PathValue("codigo"))
	if err != nil {
		responderErro(w, err)
		return
	}
	png, err := gerarQRCodePNG(i.Codigo)
	if err != nil {
		responderErro(w, err)
		return
	}
	w.Header().Set("Content-Type", "image/png")
	w.Write(png)
}

// --- Apoio às aulas (não existiriam em produção) ---

func reset(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	if _, err := db.Exec(ctx, "TRUNCATE ingressos, pedidos RESTART IDENTITY"); err != nil {
		responderErro(w, err)
		return
	}
	if err := rdb.FlushDB(ctx).Err(); err != nil {
		responderErro(w, err)
		return
	}
	responderJSON(w, http.StatusOK, map[string]string{"status": "pedidos, ingressos, cache e fila apagados"})
}

func tamanhoDaFilaHandler(w http.ResponseWriter, r *http.Request) {
	responderJSON(w, http.StatusOK, map[string]int64{"compras_na_fila": tamanhoDaFila(r.Context())})
}
