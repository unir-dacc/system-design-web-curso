package main

// Cache de respostas prontas (Redis): a programação e o mapa de assentos são
// iguais para todo mundo. O Ingressa monta uma vez, guarda o JSON pronto no
// Redis e entrega a cópia para os próximos. Quando uma compra mexe nos
// assentos de uma sessão, a cópia do mapa é apagada na hora.
//
// Proteção contra estouro de cache: quando a cópia não existe, só UMA
// requisição monta a resposta; as outras esperam ela ficar pronta.

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	travaDoCache    = 10 * time.Second // se quem está montando travar, a trava se desfaz sozinha
	esperaMaxima    = 5 * time.Second
	intervaloEspera = 20 * time.Millisecond
)

func respostaPronta(ctx context.Context, chave string, validade time.Duration, montar func() ([]byte, error)) ([]byte, error) {
	guardada, err := rdb.Get(ctx, chave).Bytes()
	if err == nil {
		return guardada, nil
	}
	if !errors.Is(err, redis.Nil) {
		return nil, err
	}

	// Só quem conseguir criar a trava monta a resposta
	if ok, err := rdb.SetNX(ctx, "trava:"+chave, 1, travaDoCache).Result(); err != nil {
		return nil, err
	} else if ok {
		defer rdb.Del(ctx, "trava:"+chave)
		resposta, err := montar()
		if err != nil {
			return nil, err
		}
		return resposta, rdb.Set(ctx, chave, resposta, validade).Err()
	}

	// Outra requisição já está montando: espera a cópia aparecer
	limite := time.Now().Add(esperaMaxima)
	for time.Now().Before(limite) {
		time.Sleep(intervaloEspera)
		if guardada, err := rdb.Get(ctx, chave).Bytes(); err == nil {
			return guardada, nil
		}
	}
	return montar()
}

func chaveDoMapa(sessaoID int) string { return fmt.Sprintf("mapa:%d", sessaoID) }

// mapaMudou: os assentos da sessão mudaram, a cópia do mapa no cache ficou velha
func mapaMudou(ctx context.Context, sessaoID int) {
	rdb.Del(ctx, chaveDoMapa(sessaoID))
}
