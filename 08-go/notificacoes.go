package main

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"mime"
	"net/smtp"
	"strings"

	qrcode "github.com/skip2/go-qrcode"
)

const remetente = "ingressos@ingressa.local"

// gerarQRCodePNG: gerar imagem é trabalho de CPU, não de I/O
func gerarQRCodePNG(codigo string) ([]byte, error) {
	return qrcode.Encode("INGRESSA:"+codigo, qrcode.Medium, 250)
}

func reais(centavos int) string { return fmt.Sprintf("R$ %.2f", float64(centavos)/100) }

func enviarConfirmacao(p pedido, s sessao, ingressos []ingresso) error {
	linhas := []string{
		fmt.Sprintf("Olá, %s!", p.Nome),
		"",
		fmt.Sprintf("Seu pedido #%d está confirmado.", p.ID),
		fmt.Sprintf("%s - %s, %s", s.Filme, s.Cinema, s.Sala),
		"Início: " + s.Inicio.In(fusoHorario).Format("02/01/2006 15:04"),
		"",
	}
	anexos := map[string][]byte{}
	for _, i := range ingressos {
		linhas = append(linhas, fmt.Sprintf("- Assento %s (%s): %s", i.Assento, i.Tipo, reais(i.PrecoCentavos)))
		png, err := gerarQRCodePNG(i.Codigo)
		if err != nil {
			return err
		}
		anexos["ingresso-"+i.Assento+".png"] = png
	}
	linhas = append(linhas, "", "Taxa de conveniência: "+reais(p.TaxaCentavos), "Total: "+reais(p.TotalCentavos))
	return enviarEmail(p.Email, "Seus ingressos para "+s.Filme, strings.Join(linhas, "\n"), anexos)
}

// enviarFalha avisa que a compra não deu certo: nada foi cobrado e os assentos foram liberados
func enviarFalha(p pedido, s sessao, motivo string) error {
	corpo := strings.Join([]string{
		fmt.Sprintf("Olá, %s!", p.Nome),
		"",
		fmt.Sprintf("Seu pedido #%d não foi concluído: %s.", p.ID, motivo),
		"Nada foi cobrado, e os assentos foram liberados.",
		"Se ainda quiser ir, faça uma nova compra.",
	}, "\n")
	return enviarEmail(p.Email, "Não conseguimos concluir sua compra para "+s.Filme, corpo, nil)
}

// enviarEmail monta a mensagem (texto e anexos PNG) e entrega no servidor SMTP
func enviarEmail(para, assunto, texto string, anexos map[string][]byte) error {
	var m bytes.Buffer
	divisa := "ingressa-" + novoCodigo()
	fmt.Fprintf(&m, "From: %s\r\nTo: %s\r\nSubject: %s\r\nMIME-Version: 1.0\r\n", remetente, para, mime.QEncoding.Encode("utf-8", assunto))
	fmt.Fprintf(&m, "Content-Type: multipart/mixed; boundary=%q\r\n\r\n", divisa)
	fmt.Fprintf(&m, "--%s\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n%s\r\n", divisa, texto)
	for nome, conteudo := range anexos {
		fmt.Fprintf(&m, "--%s\r\nContent-Type: image/png\r\nContent-Transfer-Encoding: base64\r\nContent-Disposition: attachment; filename=%q\r\n\r\n", divisa, nome)
		codificado := base64.StdEncoding.EncodeToString(conteudo)
		for len(codificado) > 76 {
			m.WriteString(codificado[:76] + "\r\n")
			codificado = codificado[76:]
		}
		m.WriteString(codificado + "\r\n")
	}
	fmt.Fprintf(&m, "--%s--\r\n", divisa)
	return smtp.SendMail(smtpAddr, nil, remetente, []string{para}, m.Bytes())
}
