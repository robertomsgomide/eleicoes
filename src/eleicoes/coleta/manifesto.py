"""Registro de tudo o que foi baixado para dados/bruto: origem, tamanho e SHA-512.

O manifesto (dados/bruto/manifesto.csv) vai para o git: mesmo sem os dados, fica
documentado exatamente quais arquivos o estudo usou.
"""
import csv
import datetime as dt
import threading

from eleicoes import config

ARQ = config.BRUTO / "manifesto.csv"
CAMPOS = ["arquivo", "url", "bytes", "sha512", "conferido_com", "baixado_em"]
_trava = threading.Lock()


def ler():
    if not ARQ.exists():
        return {}
    with open(ARQ, newline="", encoding="utf-8") as f:
        return {linha["arquivo"]: linha for linha in csv.DictReader(f)}


def registro(caminho):
    return ler().get(caminho.relative_to(config.BRUTO).as_posix())


def registrar(caminho, url, sha512, conferido_com):
    """conferido_com: como o arquivo foi validado ("sha512 do TSE", "tamanho", ...)."""
    with _trava:
        linhas = ler()
        chave = caminho.relative_to(config.BRUTO).as_posix()
        linhas[chave] = {"arquivo": chave, "url": url, "bytes": caminho.stat().st_size, "sha512": sha512,
                         "conferido_com": conferido_com, "baixado_em": dt.datetime.now().isoformat(timespec="seconds")}
        ARQ.parent.mkdir(parents=True, exist_ok=True)
        with open(ARQ, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, CAMPOS)
            w.writeheader()
            w.writerows(linhas[k] for k in sorted(linhas))
