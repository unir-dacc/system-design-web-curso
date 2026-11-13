"""
Monitor de recursos (fora do orçamento do Ingressa, como o k6).

Durante o teste de carga, acompanha a CPU e a memória de cada container da
etapa, direto do Docker, e guarda a série. No fim, o teste busca a série e o
relatório mostra quanto cada peça usou do seu limite.

- POST /reset      começa uma série nova (o teste chama no início)
- GET  /historico  a série, agrupada por serviço (as réplicas somadas)

Lê o Docker pelo socket (/var/run/docker.sock): só consulta, nunca muda nada.
Só a biblioteca padrão do Python.
"""

import http.client
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

PROJETO = "ingressa"
INTERVALO_S = 2
# Peças que não são do Ingressa: aparecem no relatório, mas fora do orçamento
EXTERNOS = {"gateway-pagamento", "sistema-cinema", "mailpit"}
# Ferramentas da aula: não aparecem
IGNORADOS = {"k6", "monitor", "pghero"}


class ConexaoDocker(http.client.HTTPConnection):
    """Uma conexão HTTP pelo socket do Docker, em vez de TCP."""

    def __init__(self):
        super().__init__("docker", timeout=None)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")


def docker(caminho: str):
    conexao = ConexaoDocker()
    conexao.request("GET", caminho)
    resposta = conexao.getresponse()
    conteudo = json.loads(resposta.read())
    conexao.close()
    return conteudo


trava = threading.Lock()
inicio = time.monotonic()
amostras: dict[str, list[tuple[float, float, float]]] = {}  # container -> [(t, cpu %, memória MB)]
acompanhados: set[str] = set()  # containers sendo lidos agora
conhecidos: dict[str, dict] = {}  # container -> serviço e limites (continua depois que ele para)


def acompanhar(cid: str) -> None:
    """Lê as estatísticas do container (o Docker manda uma por segundo) até ele parar."""
    try:
        conexao = ConexaoDocker()
        conexao.request("GET", f"/containers/{cid}/stats?stream=true")
        for linha in conexao.getresponse():
            s = json.loads(linha)
            cpu, pre = s["cpu_stats"], s["precpu_stats"]
            delta_cpu = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
            delta_sistema = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
            nucleos = cpu.get("online_cpus") or 1
            cpu_pct = delta_cpu / delta_sistema * nucleos * 100 if delta_sistema > 0 else 0.0
            # Como o "docker stats": a memória usada, sem o cache de arquivos que pode ser descartado
            memoria = s.get("memory_stats", {})
            usada = memoria.get("usage", 0) - memoria.get("stats", {}).get("inactive_file", 0)
            with trava:
                amostras.setdefault(cid, []).append((time.monotonic(), cpu_pct, usada / 2**20))
    except Exception:
        pass
    finally:
        with trava:
            acompanhados.discard(cid)


def descobrir() -> None:
    """A cada 2 s, procura containers novos da etapa (o k6 e as réplicas sobem e descem)."""
    filtro = quote(json.dumps({"label": [f"com.docker.compose.project={PROJETO}"]}))
    while True:
        try:
            for c in docker(f"/containers/json?filters={filtro}"):
                servico = c["Labels"].get("com.docker.compose.service", "?")
                if c["Id"] in acompanhados or servico in IGNORADOS:
                    continue
                detalhes = docker(f"/containers/{c['Id']}/json")["HostConfig"]
                with trava:
                    acompanhados.add(c["Id"])
                    conhecidos[c["Id"]] = {
                        "servico": servico,
                        "cpu_limite": detalhes.get("NanoCpus", 0) / 1e9 * 100 or None,
                        "mem_limite_mb": detalhes.get("Memory", 0) / 2**20 or None,
                    }
                threading.Thread(target=acompanhar, args=(c["Id"],), daemon=True).start()
        except Exception:
            pass
        time.sleep(INTERVALO_S)


def historico() -> dict:
    """A série desde o último reset, em fatias de 2 s, somando as réplicas de cada serviço."""
    with trava:
        agora = time.monotonic()
        fatias = max(1, int((agora - inicio) // INTERVALO_S))
        servicos: dict[str, dict] = {}
        for cid, pontos in amostras.items():
            info = conhecidos.get(cid)
            if not info:
                continue
            s = servicos.setdefault(info["servico"], {
                "nome": info["servico"], "externo": info["servico"] in EXTERNOS, "replicas": set(),
                "cpu_limite": 0.0, "mem_limite_mb": 0.0, "cpu": [0.0] * fatias, "mem_mb": [0.0] * fatias,
            })
            if cid not in s["replicas"]:
                s["replicas"].add(cid)
                s["cpu_limite"] = None if info["cpu_limite"] is None or s["cpu_limite"] is None else s["cpu_limite"] + info["cpu_limite"]
                s["mem_limite_mb"] = None if info["mem_limite_mb"] is None or s["mem_limite_mb"] is None else s["mem_limite_mb"] + info["mem_limite_mb"]
            # Em cada fatia, a média das amostras do container; somada às das outras réplicas
            por_fatia: dict[int, list[tuple[float, float]]] = {}
            for t, cpu, mem in pontos:
                i = int((t - inicio) // INTERVALO_S)
                if 0 <= i < fatias:
                    por_fatia.setdefault(i, []).append((cpu, mem))
            for i, valores in por_fatia.items():
                s["cpu"][i] += sum(v[0] for v in valores) / len(valores)
                s["mem_mb"][i] += sum(v[1] for v in valores) / len(valores)
        for s in servicos.values():
            s["replicas"] = len(s["replicas"])
            s["cpu"] = [round(v, 1) for v in s["cpu"]]
            s["mem_mb"] = [round(v, 1) for v in s["mem_mb"]]
        return {"intervalo_s": INTERVALO_S, "servicos": sorted(servicos.values(), key=lambda s: (s["externo"], s["nome"]))}


class Rotas(BaseHTTPRequestHandler):
    def responder(self, corpo: dict) -> None:
        conteudo = json.dumps(corpo).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)

    def do_POST(self):
        global inicio
        if self.path == "/reset":
            with trava:
                inicio = time.monotonic()
                amostras.clear()
            self.responder({"status": "série nova"})
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == "/historico":
            self.responder(historico())
        elif self.path == "/health":
            self.responder({"status": "ok"})
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=descobrir, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8000), Rotas).serve_forever()
