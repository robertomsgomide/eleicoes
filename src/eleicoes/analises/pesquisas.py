"""Pesquisas × resultado: tendência, última pesquisa de cada instituto e erro em relação às urnas.

Tudo em % dos votos válidos (sem brancos, nulos e indecisos), a mesma base do resultado oficial.

Tendência: regressão linear local das pesquisas, com pesos de um núcleo gaussiano no tempo (desvio de JANELA
dias, pela data de fim do campo) e da raiz da amostra, limitada a TETO_AMOSTRA entrevistas para que uma pesquisa
enorme não domine. Só existe nos dias com pelo menos MINIMO pesquisas a até duas janelas de distância. No 2º turno,
a tendência recomeça depois do 1º turno: as pesquisas feitas antes dele testavam um confronto hipotético, e o
resultado das urnas muda a disputa de um dia para o outro.
"""
import datetime as dt
import math

import duckdb

from eleicoes import config
from eleicoes.tratamento import pesquisas as tratamento

JANELA = 7
TETO_AMOSTRA = 5000
MINIMO = 3
SEMANA_FINAL = 7  # dias antes da eleição considerados "última pesquisa" de cada instituto
CAMPOS = ("petismo", "bolsonarismo")


def carregar(ano):
    """As pesquisas do ano (dados/processado/pesquisas), uma por turno, em ordem de turno e fim do campo."""
    arq = tratamento.saida("pesquisas", ano)
    if not arq.exists():
        return []
    con = duckdb.connect()
    linhas = con.execute(f"SELECT * FROM '{arq.as_posix()}' ORDER BY turno, fim").fetchall()
    colunas = [d[0] for d in con.description]
    return [dict(zip(colunas, l)) for l in linhas]


def peso(p, dia):
    """Peso de uma pesquisa na tendência do dia: núcleo gaussiano pela distância no tempo × raiz da amostra."""
    return math.exp(-0.5 * ((p["fim"] - dia).days / JANELA) ** 2) * math.sqrt(min(p["amostra"] or 1000, TETO_AMOSTRA))


def reta_local(pesquisas, dia):
    """({campo: estimativa}, soma dos quadrados dos pesos) da tendência no dia, ou None sem pesquisas suficientes.

    Regressão linear local: a reta que melhor passa pelas pesquisas próximas (pesos de `peso`), avaliada no dia.
    Uma média ponderada simples fica para trás nas pontas da série, onde só há pesquisas de um lado: na véspera
    da eleição ela ainda reflete a semana anterior. A reta local corrige esse atraso. Com as pesquisas
    concentradas em poucos dias (variância das datas abaixo de 1 dia²), vale a média ponderada.

    A estimativa é uma soma ponderada das pesquisas, Σ lᵢ·yᵢ; com pesquisas independentes de desvio σ em torno
    da verdade, o desvio da estimativa é σ·√(Σ lᵢ²). É o segundo valor devolvido (a projeção do 2º turno usa).
    """
    perto = [p for p in pesquisas if abs((p["fim"] - dia).days) <= 3 * JANELA]
    if sum(abs((p["fim"] - dia).days) <= 2 * JANELA for p in perto) < MINIMO:
        return None
    w = [peso(p, dia) for p in perto]
    x = [(p["fim"] - dia).days for p in perto]
    s0, s1, s2 = sum(w), sum(wi * xi for wi, xi in zip(w, x)), sum(wi * xi * xi for wi, xi in zip(w, x))
    if s0 <= 0:
        return None
    if s2 / s0 - (s1 / s0) ** 2 >= 1:
        l = [wi * (s2 - s1 * xi) / (s0 * s2 - s1 * s1) for wi, xi in zip(w, x)]
    else:
        l = [wi / s0 for wi in w]
    return {c: sum(li * p[f"{c}_validos"] for li, p in zip(l, perto)) for c in CAMPOS}, sum(li * li for li in l)


def tendencia(pesquisas, ate):
    """{datas, petismo, bolsonarismo} diários, da primeira pesquisa até `ate` (inclusive): a `reta_local` de cada dia."""
    if not pesquisas:
        return None
    t0 = min(p["fim"] for p in pesquisas)
    out = {"datas": [], **{c: [] for c in CAMPOS}}
    for i in range((ate - t0).days + 1):
        d = t0 + dt.timedelta(days=i)
        if (r := reta_local(pesquisas, d)) is not None:
            out["datas"].append(d.isoformat())
            for c in CAMPOS:
                out[c].append(round(r[0][c], 2))
    return out


def depois_do_primeiro_turno(pesquisas, ano):
    """As pesquisas de 2º turno com o campo inteiro depois do 1º turno."""
    primeiro = dt.date.fromisoformat(config.turno(ano, 1)["data"])
    return [p for p in pesquisas if p["turno"] == 2 and p["inicio"] > primeiro]


def tendencia_segundo_turno(pesquisas, ano, ate):
    """A tendência do 2º turno em dois trechos, antes e depois do 1º turno; `segmento` diz de qual é cada dia (0, 1)."""
    primeiro = dt.date.fromisoformat(config.turno(ano, 1)["data"])
    depois = depois_do_primeiro_turno(pesquisas, ano)
    antes = [p for p in pesquisas if p["fim"] < primeiro]
    out = {"datas": [], **{c: [] for c in CAMPOS}, "segmento": []}
    for segmento, ps, fim in ((0, antes, primeiro - dt.timedelta(days=1)), (1, depois, ate)):
        if ps and (t := tendencia(ps, min(fim, max(p["fim"] for p in ps)))):
            for k in ("datas", *CAMPOS):
                out[k] += t[k]
            out["segmento"] += [segmento] * len(t["datas"])
    return out if out["datas"] else None


def ultimas_por_instituto(pesquisas, eleicao, resultado):
    """A última pesquisa de cada instituto na semana final, com o erro em relação ao resultado (p.p.)."""
    ultimas = {}
    for p in pesquisas:
        if (eleicao - p["fim"]).days <= SEMANA_FINAL:
            if p["instituto"] not in ultimas or p["fim"] > ultimas[p["instituto"]]["fim"]:
                ultimas[p["instituto"]] = p
    out = []
    for p in ultimas.values():
        item = {"instituto": p["instituto"], "fim": p["fim"].isoformat(), "amostra": p["amostra"], "registro": p["registro"],
                "petismo": p["petismo_validos"], "bolsonarismo": p["bolsonarismo_validos"]}
        if resultado:
            item["erro_petismo"] = round(p["petismo_validos"] - resultado["petismo"], 2)
            item["erro_bolsonarismo"] = round(p["bolsonarismo_validos"] - resultado["bolsonarismo"], 2)
            item["erro_vantagem"] = round(item["erro_petismo"] - item["erro_bolsonarismo"], 2)
        out.append(item)
    return sorted(out, key=lambda i: abs(i.get("erro_vantagem", 0)))


def _resultado(resultados, ano, turno):
    """{"petismo", "bolsonarismo"} em % dos votos válidos do turno no Brasil, ou None antes da eleição."""
    r = (resultados.get(str(ano), {}).get(str(turno)) or {}).get("Brasil")
    return {c: round(100 * r[c] / r["validos"], 2) for c in CAMPOS} if r else None


def gerar(ano, resultados):
    """Dados de pesquisas do ano para o site: pesquisas, tendência, resultado e erros, por turno.

    No 2º turno, também a data e o resultado do 1º turno (em % dos válidos, com os outros candidatos), para o
    gráfico marcar onde as urnas deixaram a disputa no meio da série de pesquisas.
    """
    todas = carregar(ano)
    if not todas:
        return None
    from eleicoes.coleta import wikipedia
    # sem a data da última conferência, que muda a cada rodada do `atualizar`: o JSON só muda com a revisão
    rev = {k: v for k, v in (wikipedia.revisao(ano) or {}).items() if k != "consultado_em"}
    turnos = {}
    for turno in (1, 2):
        ps = [p for p in todas if p["turno"] == turno]
        if not ps:
            continue
        eleicao = dt.date.fromisoformat(config.turno(ano, turno)["data"])
        resultado = _resultado(resultados, ano, turno)
        fim_tendencia = min(eleicao - dt.timedelta(days=1), max(p["fim"] for p in ps))
        tend = tendencia(ps, fim_tendencia) if turno == 1 else tendencia_segundo_turno(ps, ano, fim_tendencia)
        semana = [p for p in ps if (eleicao - p["fim"]).days <= SEMANA_FINAL]
        media_final = ({c: round(sum(p[f"{c}_validos"] for p in semana) / len(semana), 2) for c in ("petismo", "bolsonarismo")}
                       if semana else None)
        turnos[str(turno)] = {
            "eleicao": eleicao.isoformat(),
            "resultado": resultado,
            "pesquisas": [{"instituto": p["instituto"], "contratante": p["contratante"], "inicio": p["inicio"].isoformat(),
                           "fim": p["fim"].isoformat(), "amostra": p["amostra"], "registro": p["registro"],
                           "ligacao": p["ligacao"], "petismo": p["petismo"], "bolsonarismo": p["bolsonarismo"],
                           "petismo_validos": p["petismo_validos"], "bolsonarismo_validos": p["bolsonarismo_validos"]}
                          for p in ps],
            "tendencia": tend,
            **({"primeiro_turno": config.turno(ano, 1)["data"], "resultado_primeiro_turno": _resultado(resultados, ano, 1)}
               if turno == 2 else {}),
            "media_semana_final": media_final,
            "pesquisas_semana_final": len(semana),
            "ultimas": ultimas_por_instituto(ps, eleicao, resultado),
        }
    return {"ano": ano, "fonte": {"wikipedia": rev}, "janela_dias": JANELA, "turnos": turnos}
