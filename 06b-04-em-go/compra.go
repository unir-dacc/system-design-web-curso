package main

// Fluxo de compra de ingressos, igual ao da etapa 04: tudo dentro da
// requisição. Confere as regras, registra o pedido, segura os assentos no
// cinema, cobra no gateway, confirma a venda, emite os ingressos e manda o
// e-mail. O cliente espera tudo isso com a requisição aberta.

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"log"
	"net/http"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
)

// Pedidos nesses status contam para o limite por CPF e para a cota de meia
var statusQueContam = []string{"reservando", "aguardando_pagamento", "confirmado"}

var emailValido = regexp.MustCompile(`^[^@\s]+@[^@\s]+$`)

type itemPedido struct {
	Assento string `json:"assento"`
	Tipo    string `json:"tipo"`
}

type criarPedido struct {
	SessaoID    int          `json:"sessao_id"`
	Nome        string       `json:"nome"`
	CPF         string       `json:"cpf"`
	Email       string       `json:"email"`
	CartaoToken string       `json:"cartao_token"`
	Itens       []itemPedido `json:"itens"`
}

// validar confere o pedido e normaliza o CPF (as mesmas regras da versão em Python)
func (d *criarPedido) validar() error {
	invalido := func(msg string) error { return erroHTTP{http.StatusUnprocessableEntity, msg} }
	switch {
	case d.SessaoID == 0:
		return invalido("sessao_id é obrigatório")
	case utf8.RuneCountInString(d.Nome) < 2:
		return invalido("O nome precisa ter pelo menos 2 caracteres")
	case !emailValido.MatchString(d.Email):
		return invalido("E-mail inválido")
	case d.CartaoToken == "":
		return invalido("cartao_token é obrigatório")
	case len(d.Itens) == 0:
		return invalido("O pedido precisa ter pelo menos um ingresso")
	}
	d.CPF = normalizarCPF(d.CPF)
	if !cpfValido(d.CPF) {
		return invalido("CPF inválido")
	}
	for i := range d.Itens {
		item := &d.Itens[i]
		if n := len(item.Assento); n < 2 || n > 4 {
			return invalido("Assento inválido: " + item.Assento)
		}
		if item.Tipo == "" {
			item.Tipo = "inteira"
		}
		if item.Tipo != "inteira" && item.Tipo != "meia" {
			return invalido("O tipo do ingresso deve ser inteira ou meia")
		}
	}
	return nil
}

type pedido struct {
	ID, SessaoID                                  int
	Nome, CPF, Email, Status                      string
	SubtotalCentavos, TaxaCentavos, TotalCentavos int
	QtdIngressos, QtdMeia                         int
	ReservaID, CobrancaID                         *string
	CriadoEm                                      time.Time
}

// pagamentoNaoConcluido: a compra parou no pagamento. Nada foi cobrado e os
// assentos foram liberados; a resposta leva o pedido com o status final.
type pagamentoNaoConcluido struct {
	pedido  pedido
	codigo  int
	detalhe string
}

func (e pagamentoNaoConcluido) Error() string { return e.detalhe }

// realizarCompra faz a compra inteira durante a requisição.
func realizarCompra(ctx context.Context, dados criarPedido) (pedido, error) {
	s, err := buscarSessao(ctx, dados.SessaoID)
	if err != nil {
		return pedido{}, err
	}

	assentos := make([]string, len(dados.Itens))
	repetidos := map[string]bool{}
	for i, item := range dados.Itens {
		assentos[i] = strings.ToUpper(item.Assento)
		if repetidos[assentos[i]] {
			return pedido{}, erroHTTP{http.StatusUnprocessableEntity, "O pedido tem assentos repetidos"}
		}
		repetidos[assentos[i]] = true
	}

	precos := make([]int, len(dados.Itens))
	subtotal, qtdMeia := 0, 0
	for i, item := range dados.Itens {
		precos[i] = s.PrecoInteiraCentavos
		if item.Tipo == "meia" {
			precos[i] = s.precoMeiaCentavos()
			qtdMeia++
		}
		subtotal += precos[i]
	}
	taxa := subtotal * taxaConvenienciaPct / 100

	// 1. Confere as regras e registra o pedido, tudo de uma vez
	p, err := registrarPedido(ctx, s, dados, len(assentos), qtdMeia, subtotal, taxa)
	if err != nil {
		return p, err
	}

	// 2. Segura os assentos no sistema do cinema
	reservaID, err := reservarAssentos(ctx, s.ID, assentos)
	if err != nil {
		mudarStatus(ctx, p.ID, "cancelado") // deixa de contar para o limite
		return p, err
	}
	p.ReservaID, p.Status = &reservaID, "aguardando_pagamento"
	if _, err := db.Exec(ctx, "UPDATE pedidos SET status = $1, reserva_id = $2 WHERE id = $3", p.Status, reservaID, p.ID); err != nil {
		return p, err
	}
	mapaMudou(ctx, s.ID)

	// 3. Cobra no gateway de pagamento (lento). O cliente espera com a
	// requisição aberta, mas aqui a espera ocupa só uma goroutine.
	c, err := cobrar(ctx, p.TotalCentavos, dados.CartaoToken, fmt.Sprintf("pedido-%d", p.ID))
	if errors.Is(err, errPagamentoNaoRealizado) {
		// Nada foi cobrado: libera o assento e o pedido deixa de contar para o limite
		return p, pagamentoNaoDeuCerto(ctx, p, s, "pagamento_falhou", http.StatusServiceUnavailable,
			"Não foi possível falar com o gateway de pagamento. Nada foi cobrado, tente de novo.")
	}
	if err != nil {
		return p, err
	}
	p.CobrancaID = &c.ID
	if _, err := db.Exec(ctx, "UPDATE pedidos SET cobranca_id = $1 WHERE id = $2", c.ID, p.ID); err != nil {
		return p, err
	}
	if c.Status != "aprovada" {
		return p, pagamentoNaoDeuCerto(ctx, p, s, "pagamento_recusado", http.StatusPaymentRequired, "Pagamento recusado")
	}

	// 4. Confirma a venda no cinema
	if err := confirmarReserva(ctx, reservaID); err != nil {
		return p, err
	}
	mapaMudou(ctx, s.ID)

	// 5. Emite os ingressos
	ingressos := make([]ingresso, len(dados.Itens))
	tx, err := db.Begin(ctx)
	if err != nil {
		return p, err
	}
	defer tx.Rollback(ctx)
	for i, item := range dados.Itens {
		ingressos[i] = ingresso{Codigo: novoCodigo(), Assento: assentos[i], Tipo: item.Tipo, PrecoCentavos: precos[i]}
		_, err := tx.Exec(ctx,
			"INSERT INTO ingressos (pedido_id, sessao_id, assento, tipo, preco_centavos, codigo) VALUES ($1, $2, $3, $4, $5, $6)",
			p.ID, s.ID, assentos[i], item.Tipo, precos[i], ingressos[i].Codigo)
		if err != nil {
			return p, err
		}
	}
	if _, err := tx.Exec(ctx, "UPDATE pedidos SET status = 'confirmado' WHERE id = $1", p.ID); err != nil {
		return p, err
	}
	if err := tx.Commit(ctx); err != nil {
		return p, err
	}
	p.Status = "confirmado"

	// 6. Envia o e-mail com os QR codes, ainda dentro da requisição
	return p, enviarConfirmacao(p, s, ingressos)
}

// registrarPedido confere o limite por CPF e a cota de meia e registra o
// pedido, numa única transação curta. A trava do banco (pg_advisory_xact_lock)
// faz os pedidos da mesma sessão passarem por aqui um de cada vez.
func registrarPedido(ctx context.Context, s sessao, dados criarPedido, quantidade, qtdMeia, subtotal, taxa int) (pedido, error) {
	p := pedido{
		SessaoID: s.ID, Nome: dados.Nome, CPF: dados.CPF, Email: dados.Email, Status: "reservando",
		SubtotalCentavos: subtotal, TaxaCentavos: taxa, TotalCentavos: subtotal + taxa,
		QtdIngressos: quantidade, QtdMeia: qtdMeia,
	}
	tx, err := db.Begin(ctx)
	if err != nil {
		return p, err
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, "SELECT pg_advisory_xact_lock($1)", int64(s.ID)); err != nil {
		return p, err
	}

	var jaTem int
	err = tx.QueryRow(ctx,
		"SELECT coalesce(sum(qtd_ingressos), 0) FROM pedidos WHERE sessao_id = $1 AND cpf = $2 AND status = ANY($3)",
		s.ID, dados.CPF, statusQueContam).Scan(&jaTem)
	if err != nil {
		return p, err
	}
	if jaTem+quantidade > limiteIngressosPorCPF {
		return p, erroHTTP{http.StatusUnprocessableEntity,
			fmt.Sprintf("Limite de %d ingressos por CPF nesta sessão (você já tem %d)", limiteIngressosPorCPF, jaTem)}
	}

	if qtdMeia > 0 {
		cota := s.Capacidade * cotaMeiaEntradaPct / 100
		var meias int
		err = tx.QueryRow(ctx,
			"SELECT coalesce(sum(qtd_meia), 0) FROM pedidos WHERE sessao_id = $1 AND status = ANY($2)",
			s.ID, statusQueContam).Scan(&meias)
		if err != nil {
			return p, err
		}
		if meias+qtdMeia > cota {
			return p, erroHTTP{http.StatusUnprocessableEntity,
				fmt.Sprintf("Cota de meia-entrada esgotada (%d de %d vendidas)", meias, cota)}
		}
	}

	err = tx.QueryRow(ctx, `
		INSERT INTO pedidos (sessao_id, nome, cpf, email, status, subtotal_centavos, taxa_centavos, total_centavos, qtd_ingressos, qtd_meia)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id, criado_em`,
		p.SessaoID, p.Nome, p.CPF, p.Email, p.Status, p.SubtotalCentavos, p.TaxaCentavos, p.TotalCentavos, p.QtdIngressos, p.QtdMeia,
	).Scan(&p.ID, &p.CriadoEm)
	if err != nil {
		return p, err
	}
	return p, tx.Commit(ctx) // solta a trava
}

func mudarStatus(ctx context.Context, pedidoID int, status string) {
	if _, err := db.Exec(ctx, "UPDATE pedidos SET status = $1 WHERE id = $2", status, pedidoID); err != nil {
		log.Printf("Falha ao mudar o status do pedido %d: %v", pedidoID, err)
	}
}

func buscarPedido(ctx context.Context, id int) (pedido, error) {
	var p pedido
	err := db.QueryRow(ctx, `
		SELECT id, sessao_id, nome, cpf, email, status, subtotal_centavos, taxa_centavos, total_centavos,
		       qtd_ingressos, qtd_meia, reserva_id, cobranca_id, criado_em
		FROM pedidos WHERE id = $1`, id).Scan(
		&p.ID, &p.SessaoID, &p.Nome, &p.CPF, &p.Email, &p.Status, &p.SubtotalCentavos, &p.TaxaCentavos, &p.TotalCentavos,
		&p.QtdIngressos, &p.QtdMeia, &p.ReservaID, &p.CobrancaID, &p.CriadoEm)
	if errors.Is(err, pgx.ErrNoRows) {
		return p, erroHTTP{http.StatusNotFound, "Pedido não encontrado"}
	}
	return p, err
}

func pagamentoNaoDeuCerto(ctx context.Context, p pedido, s sessao, status string, codigo int, detalhe string) error {
	if err := cancelarReserva(ctx, *p.ReservaID); err != nil {
		return err
	}
	mapaMudou(ctx, s.ID)
	mudarStatus(ctx, p.ID, status)
	p.Status = status
	return pagamentoNaoConcluido{p, codigo, detalhe}
}

func novoCodigo() string {
	b := make([]byte, 16)
	rand.Read(b)
	return hex.EncodeToString(b)
}
