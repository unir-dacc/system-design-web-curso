package main

// Fila de compras (Redis): a requisição de compra só reserva os assentos e
// põe uma tarefa aqui; o worker conclui a compra. Ao pegar uma tarefa, o
// worker a move para a lista "processando"; só quando termina ele a apaga de
// lá. Ao subir de novo, o que ficou em "processando" volta para a fila.

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	filaDeCompras = "fila:compras"
	processando   = "fila:compras:processando"
)

type itemDaTarefa struct {
	Assento string `json:"assento"`
	Tipo    string `json:"tipo"`
	Preco   int    `json:"preco"`
}

type tarefa struct {
	PedidoID    int            `json:"pedido_id"`
	CartaoToken string         `json:"cartao_token"`
	Itens       []itemDaTarefa `json:"itens"`
}

func enfileirar(ctx context.Context, t tarefa) error {
	conteudo, _ := json.Marshal(t)
	return rdb.LPush(ctx, filaDeCompras, conteudo).Err()
}

// proximaTarefa pega a tarefa mais antiga, esperando até 5 s se a fila estiver vazia
func proximaTarefa(ctx context.Context) (string, bool) {
	t, err := rdb.BLMove(ctx, filaDeCompras, processando, "RIGHT", "LEFT", 5*time.Second).Result()
	if err != nil {
		if !errors.Is(err, redis.Nil) {
			time.Sleep(time.Second) // o Redis falhou: respira e tenta de novo
		}
		return "", false
	}
	return t, true
}

func terminarTarefa(ctx context.Context, t string) {
	rdb.LRem(ctx, processando, 1, t)
}

// recuperarTarefas devolve para a fila as tarefas que ficaram pela metade. Só funciona com um worker.
func recuperarTarefas(ctx context.Context) int {
	devolvidas := 0
	for rdb.LMove(ctx, processando, filaDeCompras, "RIGHT", "RIGHT").Err() == nil {
		devolvidas++
	}
	return devolvidas
}

// tamanhoDaFila: compras ainda não concluídas (esperando o worker ou sendo feitas)
func tamanhoDaFila(ctx context.Context) int64 {
	return rdb.LLen(ctx, filaDeCompras).Val() + rdb.LLen(ctx, processando).Val()
}
