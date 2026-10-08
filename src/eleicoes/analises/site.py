"""Gera os dados do site (site/src/data/*.json) a partir de dados/processado e dados/bruto/ao_vivo.

Os JSON gerados vão para o git: assim o site pode ser montado sem os gigabytes de dados brutos.
"""
import json

from eleicoes import config
from eleicoes.analises import apuracao, mapa, noite, resultados
from eleicoes.analises import pesquisas as analise_pesquisas
from eleicoes.modelos import projecao
from eleicoes.tratamento import boletins, conexao

SAIDA = config.RAIZ / "site" / "src" / "data"


def escrever(nome, dados, log=print):
    arq = SAIDA / nome
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), "utf-8")
    log(f"   {nome}: {arq.stat().st_size / 1e3:.0f} KB")


def gerar(log=print):
    SAIDA.mkdir(parents=True, exist_ok=True)
    con = conexao()
    c = config.carregar()
    escrever("eleicoes.json", {"campos": c["campos"], "eleicoes": c["eleicoes"], "regioes": list(config.REGIOES)}, log)
    res = resultados.gerar(con)
    escrever("resultados.json", res, log)
    for ano in config.anos():
        if (p := analise_pesquisas.gerar(ano, res)) is not None:
            escrever(f"pesquisas_{ano}.json", p, log)
    escrever("projecao.json", projecao.gerar(con, res), log)
    for ano in config.anos():
        for turno in (1, 2):
            if boletins.saida("secoes", ano, turno).exists():
                escrever(f"apuracao_{ano}_t{turno}.json", apuracao.gerar(con, ano, turno), log)
            elif (n := noite.gerar(ano, turno)) is not None:  # a noite gravada ao vivo, até os boletins saírem
                escrever(f"noite_{ano}_t{turno}.json", n, log)
    escrever("validacao_estimativa.json", apuracao.validar_estimativa(con), log)
    mapa.gerar(lambda nome, dados: escrever(nome, dados, log), log)
