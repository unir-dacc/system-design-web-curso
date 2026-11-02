package main

// Comunicação com os sistemas externos: cinema e gateway de pagamento.

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

// Reaproveita as conexões com cada sistema externo
var transporte = &http.Transport{MaxIdleConns: 512, MaxIdleConnsPerHost: 256, IdleConnTimeout: 90 * time.Second}

// ⚠️ PROPOSITAL: sem timeout para o cinema (como na versão em Python).
var httpCinema = &http.Client{Transport: transporte}

// A cobrança tem timeout: sem ele, um gateway travado prenderia o assento para sempre.
var httpGateway = &http.Client{Transport: transporte, Timeout: 10 * time.Second}

type assentosIndisponiveis struct{ assentos []string }

func (e assentosIndisponiveis) Error() string { return "assentos indisponíveis" }

type assentosInexistentes struct{ assentos []string }

func (e assentosInexistentes) Error() string { return "assentos inexistentes" }

// O gateway falhou e confirmou que nada foi cobrado
var errPagamentoNaoRealizado = errors.New("pagamento não realizado")

func chamar(ctx context.Context, cliente *http.Client, metodo, endereco string, corpo any, cabecalhos map[string]string) (*http.Response, error) {
	var leitor *bytes.Reader
	if corpo != nil {
		conteudo, _ := json.Marshal(corpo)
		leitor = bytes.NewReader(conteudo)
	} else {
		leitor = bytes.NewReader(nil)
	}
	req, err := http.NewRequestWithContext(ctx, metodo, endereco, leitor)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	for nome, valor := range cabecalhos {
		req.Header.Set(nome, valor)
	}
	return cliente.Do(req)
}

func lerJSON(resposta *http.Response, destino any) error {
	defer resposta.Body.Close()
	if resposta.StatusCode >= 400 {
		return fmt.Errorf("%s respondeu %d", resposta.Request.URL, resposta.StatusCode)
	}
	if destino == nil {
		return nil
	}
	return json.NewDecoder(resposta.Body).Decode(destino)
}

// --- Sistema de assentos do cinema ---

type assento struct {
	Codigo string `json:"codigo"`
	Status string `json:"status"`
}

func buscarMapa(ctx context.Context, sessaoID int) ([]assento, error) {
	resposta, err := chamar(ctx, httpCinema, "GET", fmt.Sprintf("%s/sessoes/%d/assentos", cinemaURL, sessaoID), nil, nil)
	if err != nil {
		return nil, err
	}
	var mapa struct {
		Assentos []assento `json:"assentos"`
	}
	return mapa.Assentos, lerJSON(resposta, &mapa)
}

func reservarAssentos(ctx context.Context, sessaoID int, assentos []string) (string, error) {
	resposta, err := chamar(ctx, httpCinema, "POST", fmt.Sprintf("%s/sessoes/%d/reservas", cinemaURL, sessaoID), map[string]any{"assentos": assentos}, nil)
	if err != nil {
		return "", err
	}
	switch resposta.StatusCode {
	case http.StatusConflict:
		var erro struct {
			Detail struct {
				Indisponiveis []string `json:"indisponiveis"`
			} `json:"detail"`
		}
		json.NewDecoder(resposta.Body).Decode(&erro)
		resposta.Body.Close()
		return "", assentosIndisponiveis{erro.Detail.Indisponiveis}
	case http.StatusUnprocessableEntity:
		var erro struct {
			Detail struct {
				Assentos []string `json:"assentos"`
			} `json:"detail"`
		}
		json.NewDecoder(resposta.Body).Decode(&erro)
		resposta.Body.Close()
		return "", assentosInexistentes{erro.Detail.Assentos}
	}
	var reserva struct {
		ReservaID string `json:"reserva_id"`
	}
	return reserva.ReservaID, lerJSON(resposta, &reserva)
}

func confirmarReserva(ctx context.Context, reservaID string) error {
	resposta, err := chamar(ctx, httpCinema, "POST", fmt.Sprintf("%s/reservas/%s/confirmar", cinemaURL, reservaID), nil, nil)
	if err != nil {
		return err
	}
	return lerJSON(resposta, nil)
}

func cancelarReserva(ctx context.Context, reservaID string) error {
	resposta, err := chamar(ctx, httpCinema, "DELETE", fmt.Sprintf("%s/reservas/%s", cinemaURL, reservaID), nil, nil)
	if err != nil {
		return err
	}
	return lerJSON(resposta, nil)
}

// --- Gateway de pagamento ---

type cobranca struct {
	ID     string `json:"id"`
	Status string `json:"status"`
}

func cobrar(ctx context.Context, valorCentavos int, cartaoToken, referencia string) (cobranca, error) {
	var c cobranca
	corpo := map[string]any{"valor_centavos": valorCentavos, "cartao_token": cartaoToken, "referencia": referencia}
	// Se a mesma cobrança for enviada de novo, o gateway não cobra duas vezes
	resposta, err := chamar(ctx, httpGateway, "POST", gatewayURL+"/cobrancas", corpo, map[string]string{"Idempotency-Key": referencia})
	if err == nil {
		if err = lerJSON(resposta, &c); err == nil {
			return c, nil
		}
	}
	// Erro ou timeout: a cobrança pode ter acontecido ou não.
	// Antes de liberar o assento, pergunta ao gateway.
	existente, err := buscarCobranca(ctx, referencia)
	if err != nil {
		return c, err
	}
	if existente == nil {
		return c, errPagamentoNaoRealizado
	}
	return *existente, nil
}

func buscarCobranca(ctx context.Context, referencia string) (*cobranca, error) {
	resposta, err := chamar(ctx, httpGateway, "GET", gatewayURL+"/cobrancas?referencia="+url.QueryEscape(referencia), nil, nil)
	if err != nil {
		return nil, err
	}
	var cobrancas []cobranca
	if err := lerJSON(resposta, &cobrancas); err != nil {
		return nil, err
	}
	if len(cobrancas) == 0 {
		return nil, nil
	}
	return &cobrancas[0], nil
}
