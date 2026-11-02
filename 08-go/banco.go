package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"time"

	"github.com/jackc/pgx/v5"
)

// As mesmas tabelas da versão em Python
const esquema = `
CREATE TABLE IF NOT EXISTS filmes (
	id integer PRIMARY KEY,
	titulo varchar NOT NULL,
	duracao_min integer NOT NULL,
	classificacao varchar(2) NOT NULL,
	sinopse varchar NOT NULL
);
CREATE TABLE IF NOT EXISTS cinemas (
	id integer PRIMARY KEY,
	nome varchar NOT NULL
);
CREATE TABLE IF NOT EXISTS salas (
	id integer PRIMARY KEY,
	cinema_id integer NOT NULL REFERENCES cinemas(id),
	nome varchar NOT NULL,
	capacidade integer NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes (
	id integer PRIMARY KEY,
	filme_id integer NOT NULL REFERENCES filmes(id),
	sala_id integer NOT NULL REFERENCES salas(id),
	inicio timestamptz NOT NULL,
	preco_inteira_centavos integer NOT NULL
);
CREATE TABLE IF NOT EXISTS pedidos (
	id serial PRIMARY KEY,
	sessao_id integer NOT NULL REFERENCES sessoes(id),
	nome varchar NOT NULL,
	cpf varchar(11) NOT NULL,
	email varchar NOT NULL,
	-- reservando -> aguardando_pagamento -> confirmado | pagamento_recusado | pagamento_falhou | cancelado
	status varchar NOT NULL,
	subtotal_centavos integer NOT NULL,
	taxa_centavos integer NOT NULL,
	total_centavos integer NOT NULL,
	-- Pedidos em andamento também contam para o limite por CPF e para a cota de meia
	qtd_ingressos integer NOT NULL,
	qtd_meia integer NOT NULL,
	reserva_id varchar,
	cobranca_id varchar,
	criado_em timestamptz NOT NULL DEFAULT now()
);
-- ⚠️ PROPOSITAL: o Postgres NÃO cria índice para chave estrangeira (como na versão em Python)
CREATE TABLE IF NOT EXISTS ingressos (
	id serial PRIMARY KEY,
	pedido_id integer NOT NULL REFERENCES pedidos(id),
	sessao_id integer NOT NULL REFERENCES sessoes(id),
	assento varchar(4) NOT NULL,
	tipo varchar(7) NOT NULL,
	preco_centavos integer NOT NULL,
	codigo varchar(32) NOT NULL UNIQUE,
	criado_em timestamptz NOT NULL DEFAULT now()
);
`

// prepararBanco cria as tabelas e carrega o catálogo. Os backends sobem ao
// mesmo tempo: a trava do banco faz um de cada vez; os outros encontram tudo pronto.
func prepararBanco(ctx context.Context) error {
	tx, err := db.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, "SELECT pg_advisory_xact_lock(0)"); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, esquema); err != nil {
		return err
	}
	var filmes int
	if err := tx.QueryRow(ctx, "SELECT count(*) FROM filmes").Scan(&filmes); err != nil {
		return err
	}
	if filmes == 0 {
		if err := carregarCatalogo(ctx, tx); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

type catalogo struct {
	Filmes []struct {
		ID            int    `json:"id"`
		Titulo        string `json:"titulo"`
		DuracaoMin    int    `json:"duracao_min"`
		Classificacao string `json:"classificacao"`
		Sinopse       string `json:"sinopse"`
	} `json:"filmes"`
	Cinemas []struct {
		ID   int    `json:"id"`
		Nome string `json:"nome"`
	} `json:"cinemas"`
	Salas []struct {
		ID                 int    `json:"id"`
		CinemaID           int    `json:"cinema_id"`
		Nome               string `json:"nome"`
		Fileiras           string `json:"fileiras"`
		AssentosPorFileira int    `json:"assentos_por_fileira"`
	} `json:"salas"`
	Sessoes []struct {
		ID                   int       `json:"id"`
		FilmeID              int       `json:"filme_id"`
		SalaID               int       `json:"sala_id"`
		Inicio               time.Time `json:"inicio"`
		PrecoInteiraCentavos int       `json:"preco_inteira_centavos"`
	} `json:"sessoes"`
}

// carregarCatalogo popula filmes, cinemas, salas e sessões a partir do mesmo
// arquivo usado pelo sistema do cinema.
func carregarCatalogo(ctx context.Context, tx pgx.Tx) error {
	conteudo, err := os.ReadFile(seedPath)
	if err != nil {
		return err
	}
	var c catalogo
	if err := json.Unmarshal(conteudo, &c); err != nil {
		return fmt.Errorf("catálogo inválido: %w", err)
	}
	for _, f := range c.Filmes {
		if _, err := tx.Exec(ctx, "INSERT INTO filmes VALUES ($1, $2, $3, $4, $5)", f.ID, f.Titulo, f.DuracaoMin, f.Classificacao, f.Sinopse); err != nil {
			return err
		}
	}
	for _, ci := range c.Cinemas {
		if _, err := tx.Exec(ctx, "INSERT INTO cinemas VALUES ($1, $2)", ci.ID, ci.Nome); err != nil {
			return err
		}
	}
	for _, s := range c.Salas {
		capacidade := len(s.Fileiras) * s.AssentosPorFileira
		if _, err := tx.Exec(ctx, "INSERT INTO salas VALUES ($1, $2, $3, $4)", s.ID, s.CinemaID, s.Nome, capacidade); err != nil {
			return err
		}
	}
	for _, s := range c.Sessoes {
		if _, err := tx.Exec(ctx, "INSERT INTO sessoes VALUES ($1, $2, $3, $4, $5)", s.ID, s.FilmeID, s.SalaID, s.Inicio, s.PrecoInteiraCentavos); err != nil {
			return err
		}
	}
	return nil
}

// --- Sessões ---

type sessao struct {
	ID, FilmeID          int
	Filme, Cinema, Sala  string
	Inicio               time.Time
	PrecoInteiraCentavos int
	Capacidade           int
}

func (s sessao) precoMeiaCentavos() int { return s.PrecoInteiraCentavos / 2 }

// Sala, filme e cinema vêm na mesma consulta da sessão
const selecionarSessoes = `
SELECT s.id, s.filme_id, f.titulo, c.nome, sa.nome, s.inicio, s.preco_inteira_centavos, sa.capacidade
FROM sessoes s
JOIN filmes f ON f.id = s.filme_id
JOIN salas sa ON sa.id = s.sala_id
JOIN cinemas c ON c.id = sa.cinema_id`

func lerSessao(linha pgx.Row) (sessao, error) {
	var s sessao
	err := linha.Scan(&s.ID, &s.FilmeID, &s.Filme, &s.Cinema, &s.Sala, &s.Inicio, &s.PrecoInteiraCentavos, &s.Capacidade)
	return s, err
}

// buscarSessao devolve a sessão, ou um erro 404
func buscarSessao(ctx context.Context, id int) (sessao, error) {
	s, err := lerSessao(db.QueryRow(ctx, selecionarSessoes+" WHERE s.id = $1", id))
	if errors.Is(err, pgx.ErrNoRows) {
		return s, erroHTTP{http.StatusNotFound, "Sessão não encontrada"}
	}
	return s, err
}
