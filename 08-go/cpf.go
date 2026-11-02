package main

import "strings"

func normalizarCPF(cpf string) string {
	var b strings.Builder
	for _, c := range cpf {
		if c >= '0' && c <= '9' {
			b.WriteRune(c)
		}
	}
	return b.String()
}

// cpfValido confere os dois dígitos verificadores do CPF
func cpfValido(cpf string) bool {
	if len(cpf) != 11 || cpf == strings.Repeat(cpf[:1], 11) {
		return false
	}
	for _, tamanho := range []int{9, 10} {
		soma := 0
		for i := 0; i < tamanho; i++ {
			soma += int(cpf[i]-'0') * (tamanho + 1 - i)
		}
		if soma*10%11%10 != int(cpf[tamanho]-'0') {
			return false
		}
	}
	return true
}
