"""Resultado final de cada turno: Brasil, regiões e UFs.

Votos de candidatos: total oficial do TSE (votação nominal por município e zona). Eleitorado, comparecimento,
brancos e nulos: soma dos boletins de urna. Turno ainda sem boletins ou sem total oficial (o 2º turno de 2026,
nos dias depois da eleição): arquivos finais do site de resultados (dados/bruto/ao_vivo/<ciclo>-<eleicao>/final).
"""
import json

from eleicoes import config
from eleicoes.formato_tse import candidatos as votos_por_candidato
from eleicoes.formato_tse import nomes as nomes_do_arquivo
from eleicoes.formato_tse import num
from eleicoes.tratamento import boletins, oficial


def _vazio():
    return {"aptos": 0, "comparecimento": 0, "validos": 0, "brancos": 0, "nulos": 0,
            "petismo": 0, "bolsonarismo": 0, "outros": 0, "candidatos": {}}


def _somar(destino, origem):
    for k, v in origem.items():
        if k == "candidatos":
            for n, votos in v.items():
                destino["candidatos"][n] = destino["candidatos"].get(n, 0) + votos
        else:
            destino[k] += v


def _agregar(por_uf, ano):
    """{UF: números} -> {"Brasil": ..., "regioes": {...}, "ufs": {...}}, com candidatos ordenados por votos."""
    campos = config.candidatos(ano)
    brasil, regioes = _vazio(), {r: _vazio() for r in config.REGIOES}
    for uf, d in por_uf.items():
        d["petismo"] = sum(v for n, v in d["candidatos"].items() if campos.get(n) == "petismo")
        d["bolsonarismo"] = sum(v for n, v in d["candidatos"].items() if campos.get(n) == "bolsonarismo")
        d["outros"] = d["validos"] - d["petismo"] - d["bolsonarismo"]
        _somar(brasil, d)
        _somar(regioes[config.REGIAO_DA_UF[uf]], d)

    def fechar(d):  # empate em votos: pelo número, para o JSON não mudar de uma geração para outra
        d["candidatos"] = [{"numero": n, "votos": v} for n, v in sorted(d["candidatos"].items(), key=lambda x: (-x[1], x[0]))]
        return d

    return {"Brasil": fechar(brasil), "regioes": {r: fechar(d) for r, d in regioes.items()},
            "ufs": {uf: fechar(d) for uf, d in sorted(por_uf.items())}}


def de_boletins(con, ano, turno):
    secoes = boletins.saida("secoes", ano, turno).as_posix()
    por_uf = {uf: {**_vazio(), "aptos": int(a), "comparecimento": int(c), "brancos": int(b), "nulos": int(n)}
              for uf, a, c, b, n in con.execute(f"""
                  SELECT sg_uf, sum(qt_aptos), sum(qt_comparecimento), sum(votos_brancos), sum(votos_nulos)
                  FROM '{secoes}' GROUP BY 1""").fetchall()}
    anulados = set(config.nulos_tecnicos(ano, turno))  # já estão nos nulos dos boletins
    for uf, n, v in con.execute(f"""SELECT sg_uf, nr_candidato, sum(qt_votos) FROM '{oficial.saida(ano).as_posix()}'
                                    WHERE turno = {turno} GROUP BY ALL""").fetchall():
        if int(n) in anulados:
            continue
        por_uf[uf]["candidatos"][int(n)] = int(v)
        por_uf[uf]["validos"] += int(v)
    return _agregar(por_uf, ano)


def de_arquivos_finais(pasta, ano):
    """Arquivos finais por UF do site de resultados do TSE (formato -u.json)."""
    por_uf = {}
    for arq in sorted(pasta.glob("*.json")):
        uf = arq.stem.upper()
        if uf == "BR":
            continue
        d = json.loads(arq.read_text("utf-8"))
        cand = {int(n): int(v) for n, v in votos_por_candidato(d).items()}
        por_uf[uf] = {**_vazio(), "aptos": int(num(d["e"]["te"])), "comparecimento": int(num(d["e"]["c"])),
                      "validos": int(num(d["v"]["vv"])), "brancos": int(num(d["v"]["vb"])),
                      "nulos": int(num(d["v"]["tvn"])), "candidatos": cand}
    return _agregar(por_uf, ano)


def nomes_candidatos(con, ano, turno, pasta_final=None):
    """{número: nome na urna} pelo arquivo oficial ou, sem ele, pelo arquivo final do site de resultados."""
    arq = oficial.saida(ano)
    if arq.exists():
        return {int(n): nome.title() for n, nome in con.execute(f"""
            SELECT nr_candidato, any_value(nm_urna_candidato) FROM '{arq.as_posix()}' WHERE turno = {turno} GROUP BY 1""").fetchall()}
    if pasta_final and (br := pasta_final / "br.json").exists():
        return {int(n): nome for n, nome in nomes_do_arquivo(json.loads(br.read_text("utf-8"))).items()}
    return {}


def gerar(con):
    """{ano: {turno: {...}}} com o que estiver disponível."""
    out = {}
    for ano in config.anos():
        for turno in (1, 2):
            pasta = config.BRUTO / "ao_vivo" / f"ele{ano}-{config.turno(ano, turno).get('eleicao')}" / "final"
            if boletins.saida("secoes", ano, turno).exists() and oficial.saida(ano).exists():
                r = de_boletins(con, ano, turno)
                fonte = "boletins de urna e total oficial do TSE"
            elif pasta.exists():
                r = de_arquivos_finais(pasta, ano)
                fonte = "arquivos finais do site de resultados do TSE"
            else:
                continue
            nomes = nomes_candidatos(con, ano, turno, pasta)
            for c in r["Brasil"]["candidatos"]:
                c["nome"] = nomes.get(c["numero"])
            r["fonte"] = fonte
            out.setdefault(str(ano), {})[str(turno)] = r
    return out
