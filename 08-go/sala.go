package main

// Sala de espera (Redis): cada pessoa recebe uma senha; o porteiro (no
// worker) libera um número fixo de senhas por segundo; quem é liberado
// recebe um passe assinado (HMAC), exigido pela programação, pelo mapa e pela
// compra. Igual à versão em Python (app/sala.py da etapa 07).

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"strings"

	"github.com/redis/go-redis/v9"
)

var segredoDaSala = []byte(env("SEGREDO_DA_SALA", "troque-em-producao"))

const (
	ultimaSenha = "sala:ultima_senha"          // a senha do último que chegou
	liberadas   = "sala:liberadas"             // todas as senhas até esta já podem entrar
	taxaDaSala  = "sala:liberadas_por_segundo" // o porteiro anota aqui o ritmo dele
)

// Libera até ARGV[1] senhas, sem passar de quem já chegou. Roda dentro do
// Redis, de uma vez só (atômico).
var scriptLiberar = redis.NewScript(`
local ultima = tonumber(redis.call('GET', KEYS[1]) or 0)
local liberadas = tonumber(redis.call('GET', KEYS[2]) or 0)
local novo = math.min(ultima, liberadas + tonumber(ARGV[1]))
redis.call('SET', KEYS[2], novo)
return novo
`)

func entrarNaSala(ctx context.Context) (int, error) {
	senha, err := rdb.Incr(ctx, ultimaSenha).Result()
	return int(senha), err
}

func senhasLiberadas(ctx context.Context) int {
	n, _ := rdb.Get(ctx, liberadas).Int()
	return n
}

func liberarSenhas(ctx context.Context, quantidade int) error {
	return scriptLiberar.Run(ctx, rdb, []string{ultimaSenha, liberadas}, quantidade).Err()
}

func anotarTaxa(ctx context.Context, porSegundo int) error {
	return rdb.Set(ctx, taxaDaSala, porSegundo, 0).Err()
}

func taxaAtual(ctx context.Context) int {
	if n, err := rdb.Get(ctx, taxaDaSala).Int(); err == nil && n > 0 {
		return n
	}
	return 1
}

func passeDaSenha(senha int) string {
	mac := hmac.New(sha256.New, segredoDaSala)
	mac.Write([]byte(strconv.Itoa(senha)))
	return strconv.Itoa(senha) + "." + hex.EncodeToString(mac.Sum(nil))[:16]
}

func passeValido(ctx context.Context, valor string) bool {
	numero, _, ok := strings.Cut(valor, ".")
	senha, err := strconv.Atoi(numero)
	if !ok || err != nil || !hmac.Equal([]byte(valor), []byte(passeDaSenha(senha))) {
		return false
	}
	return senha <= senhasLiberadas(ctx)
}
