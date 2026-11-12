def normalizar(cpf: str) -> str:
    return "".join(c for c in cpf if c.isdigit())


def cpf_valido(cpf: str) -> bool:
    """Valida os dois dígitos verificadores do CPF."""
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = soma * 10 % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True
