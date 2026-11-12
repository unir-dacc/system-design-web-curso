// Ingressa em Go: o mesmo sistema da etapa 04 (cache, compra dentro da
// requisição, sem fila e sem sala de espera), com as mesmas rotas e as mesmas
// respostas, reescrito em Go.
//
// Diferente do Python, um único processo Go usa todas as CPUs que tiver: não
// existe GIL. Cada requisição roda numa goroutine, que custa poucos KB: uma
// compra esperando o gateway não prende uma thread.
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

var (
	databaseURL = env("DATABASE_URL", "postgres://ingressa:ingressa@postgres:5432/ingressa")
	cinemaURL   = env("CINEMA_URL", "http://sistema-cinema:8000")
	gatewayURL  = env("GATEWAY_URL", "http://gateway-pagamento:8000")
	smtpAddr    = env("SMTP_HOST", "mailpit") + ":" + env("SMTP_PORT", "1025")
	seedPath    = env("SEED_PATH", "/seed/catalogo.json")
	redisURL    = env("REDIS_URL", "redis://redis:6379/0")

	// Por quanto tempo cada resposta fica guardada no cache
	programacaoTTL = time.Duration(envInt("PROGRAMACAO_TTL_S", 60)) * time.Second // muda pouco
	mapaTTL        = time.Duration(envInt("MAPA_TTL_S", 5)) * time.Second         // também é apagado a cada compra

	// Horários são exibidos no fuso das sessões do catálogo
	fusoHorario = time.FixedZone("-04", -4*60*60)
)

// Regras de negócio
const (
	taxaConvenienciaPct   = 10
	limiteIngressosPorCPF = 6  // por sessão
	cotaMeiaEntradaPct    = 40 // Lei 12.933/2013: 40% dos ingressos da sessão
)

var (
	db  *pgxpool.Pool
	rdb *redis.Client
)

func main() {
	ctx := context.Background()
	conectar(ctx)

	if err := prepararBanco(ctx); err != nil {
		log.Fatalf("Falha ao preparar o banco: %v", err)
	}
	log.Println("Ingressa (Go) pronto na porta 8000")
	log.Fatal(http.ListenAndServe(":8000", rotas()))
}

func conectar(ctx context.Context) {
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		log.Fatal(err)
	}
	// Quantas conexões com o banco este processo pode abrir
	config.MaxConns = int32(envInt("DB_POOL", 40))
	if db, err = pgxpool.NewWithConfig(ctx, config); err != nil {
		log.Fatal(err)
	}

	opcoes, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatal(err)
	}
	opcoes.PoolSize = envInt("REDIS_POOL", 100)
	rdb = redis.NewClient(opcoes)
}

func env(nome, padrao string) string {
	if valor := os.Getenv(nome); valor != "" {
		return valor
	}
	return padrao
}

func envInt(nome string, padrao int) int {
	if valor, err := strconv.Atoi(os.Getenv(nome)); err == nil {
		return valor
	}
	return padrao
}
