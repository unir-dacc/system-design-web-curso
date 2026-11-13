package main

// Worker: tira as compras da fila e conclui cada uma. Também roda o porteiro
// da sala de espera. Cada compra passa a maior parte do tempo esperando o
// gateway, então o worker trabalha em várias ao mesmo tempo, uma por goroutine.

import (
	"context"
	"encoding/json"
	"log"
	"math"
	"time"
)

func rodarWorker(ctx context.Context) {
	trabalhadores := envInt("WORKER_THREADS", 40)
	// Quantas pessoas da sala de espera entram por segundo: um pouco abaixo do
	// que o Ingressa aguenta
	liberarPorSegundo := envInt("LIBERAR_POR_SEGUNDO", 60)

	if devolvidas := recuperarTarefas(ctx); devolvidas > 0 {
		log.Printf("%d compras ficaram pela metade e voltaram para a fila", devolvidas)
	}
	log.Printf("Worker pronto: %d trabalhadores, %d compras na fila", trabalhadores, tamanhoDaFila(ctx))
	log.Printf("Porteiro da sala de espera: %d pessoas por segundo", liberarPorSegundo)

	for range trabalhadores {
		go trabalhar(ctx)
	}
	porteiro(ctx, liberarPorSegundo)
}

func trabalhar(ctx context.Context) {
	for {
		conteudo, ok := proximaTarefa(ctx) // espera até chegar uma
		if !ok {
			continue
		}
		var t tarefa
		if err := json.Unmarshal([]byte(conteudo), &t); err != nil {
			log.Printf("Tarefa com defeito %s: %v", conteudo, err)
		} else if err := concluirCompra(ctx, t); err != nil {
			// Não volta para a fila: uma tarefa com defeito travaria o worker para sempre
			log.Printf("Falha ao concluir a tarefa %s: %v", conteudo, err)
		}
		terminarTarefa(ctx, conteudo)
	}
}

// porteiro libera senhas da sala de espera num ritmo fixo, um pouco a cada 0,2 s
func porteiro(ctx context.Context, porSegundo int) {
	porVez := max(1, int(math.Round(float64(porSegundo)*0.2)))
	for range time.Tick(200 * time.Millisecond) {
		// O ritmo é anotado de novo a cada volta: o reset das aulas apaga o Redis
		if err := anotarTaxa(ctx, porSegundo); err != nil {
			log.Printf("Falha no porteiro da sala de espera: %v", err)
			continue
		}
		if err := liberarSenhas(ctx, porVez); err != nil {
			log.Printf("Falha no porteiro da sala de espera: %v", err)
		}
	}
}
