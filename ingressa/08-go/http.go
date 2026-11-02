package main

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"
)

// erroHTTP é um erro que vira uma resposta com status e "detail", no mesmo
// formato da versão em Python (FastAPI)
type erroHTTP struct {
	status int
	detail any
}

func (e erroHTTP) Error() string { return http.StatusText(e.status) }

func responderJSON(w http.ResponseWriter, status int, corpo any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(corpo)
}

// jsonPronto devolve uma resposta que já está em JSON (vinda do cache)
func jsonPronto(w http.ResponseWriter, conteudo []byte) {
	w.Header().Set("Content-Type", "application/json")
	w.Write(conteudo)
}

func responderErro(w http.ResponseWriter, err error) {
	var e erroHTTP
	if errors.As(err, &e) {
		responderJSON(w, e.status, map[string]any{"detail": e.detail})
		return
	}
	log.Printf("Erro: %v", err)
	responderJSON(w, http.StatusInternalServerError, map[string]any{"detail": "Internal Server Error"})
}
