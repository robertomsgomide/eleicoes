"""Apuração ao longo do tempo: votos acumulados a cada minuto, no Brasil e em cada região.

Exata quando o TSE publica a hora de chegada de cada boletim de urna (2022 em diante): cada seção entra na
curva no minuto em que o boletim dela chegou ao TSE. Para 2018, que não tem esse dado, a chegada é estimada
(`chegadas_estimadas`) e `validar_estimativa` mede o erro do método onde a chegada real é conhecida.

Boletins que chegaram antes do início da divulgação (o exterior, sobretudo) entram no primeiro minuto.
"""
import datetime as dt

from eleicoes import config
from eleicoes.tratamento import boletins

ORDEM = ["Brasil", *config.REGIOES]


def _secoes(ano, turno):
    return boletins.saida("secoes", ano, turno).as_posix()


def tem_chegada_exata(ano, turno):
    return boletins.saida("secoes", ano, turno).exists() and ano >= 2022


def chegadas_exatas(con, ano, turno):
    """Tabela `chegadas`: uma linha por seção com boletim, com a hora de chegada (Brasília) e os votos."""
    con.execute(f"""CREATE OR REPLACE TEMP TABLE chegadas AS
        SELECT regiao, sg_uf, cd_municipio, nr_zona, nr_secao, dt_bu_recebido AS chegada,
               votos_validos, votos_petismo, votos_bolsonarismo
        FROM '{_secoes(ano, turno)}' WHERE dt_bu_recebido IS NOT NULL""")


def chegadas_estimadas(con, ano, turno, ref_ano, ref_turno):
    """Tabela `chegadas` com a chegada estimada de cada seção.

    chegada = encerramento da urna (horário local) + atraso mediano entre encerramento e chegada (Brasília)
    na mesma zona eleitoral na eleição de referência; sem a zona, o do município; sem ele, o da UF.
    A diferença de fuso vem embutida no atraso: nas duas eleições o encerramento está no horário local.
    Seção sem horário de encerramento usa a mediana do encerramento na zona dela; se ninguém na zona tem
    (cidades do exterior com uma seção só), recebe a chegada estimada mediana da sua UF.
    """
    con.execute(f"""CREATE OR REPLACE TEMP TABLE chegadas AS
        WITH ref AS (SELECT sg_uf, cd_municipio, nr_zona, epoch(dt_bu_recebido) - epoch(dt_encerramento) AS d
                     FROM '{_secoes(ref_ano, ref_turno)}'
                     WHERE dt_bu_recebido IS NOT NULL AND dt_encerramento IS NOT NULL),
             z AS (SELECT cd_municipio, nr_zona, median(d) AS dz FROM ref GROUP BY ALL),
             m AS (SELECT cd_municipio, median(d) AS dm FROM ref GROUP BY ALL),
             u AS (SELECT sg_uf, median(d) AS du FROM ref GROUP BY ALL),
             alvo AS (SELECT *, make_timestamp(median(epoch_us(dt_encerramento))
                                 OVER (PARTITION BY cd_municipio, nr_zona)::BIGINT) AS enc_zona
                      FROM '{_secoes(ano, turno)}' WHERE qt_comparecimento > 0),
             est AS (SELECT a.regiao, a.sg_uf, a.cd_municipio, a.nr_zona, a.nr_secao,
                            coalesce(a.dt_encerramento, a.enc_zona)
                                + to_seconds(round(coalesce(z.dz, m.dm, u.du))::BIGINT) AS chegada,
                            a.votos_validos, a.votos_petismo, a.votos_bolsonarismo
                     FROM alvo a
                     LEFT JOIN z USING (cd_municipio, nr_zona) LEFT JOIN m USING (cd_municipio) LEFT JOIN u USING (sg_uf))
        SELECT * REPLACE (coalesce(chegada, make_timestamp(median(epoch_us(chegada))
                                   OVER (PARTITION BY sg_uf)::BIGINT)) AS chegada)
        FROM est""")


def serie(con, inicio):
    """Lê a tabela `chegadas` e devolve a série acumulada.

    {"t": minutos desde o início, "regioes": {"Brasil"|região: {"secoes", "validos", "petismo",
    "bolsonarismo": [acumulados em cada t]}}, "totais": {...: valores finais}}
    """
    linhas = con.execute(f"""
        SELECT regiao, greatest(date_trunc('minute', chegada), TIMESTAMP '{inicio:%Y-%m-%d %H:%M:%S}') AS minuto,
               count(*), sum(votos_validos), sum(votos_petismo), sum(votos_bolsonarismo)
        FROM chegadas GROUP BY ALL ORDER BY minuto""").fetchall()
    minutos = sorted({l[1] for l in linhas})
    pos = {m: i for i, m in enumerate(minutos)}
    medidas = ("secoes", "validos", "petismo", "bolsonarismo")
    passo = {r: {k: [0] * len(minutos) for k in medidas} for r in ORDEM}
    for regiao, minuto, *valores in linhas:
        for r in ("Brasil", regiao):
            for k, v in zip(medidas, valores):
                passo[r][k][pos[minuto]] += int(v)
    regioes, totais = {}, {}
    for r in ORDEM:
        acum = {}
        for k in medidas:
            soma, acum[k] = 0, []
            for v in passo[r][k]:
                soma += v
                acum[k].append(soma)
        regioes[r] = acum
        totais[r] = {k: acum[k][-1] if acum[k] else 0 for k in medidas}
    t = [int((m - inicio).total_seconds() // 60) for m in minutos]
    return {"t": t, "regioes": regioes, "totais": totais}


def viradas(s, minimo=0.01):
    """Momentos em que muda o líder no Brasil, depois de apurado `minimo` das seções."""
    b, total, out, lider = s["regioes"]["Brasil"], s["totais"]["Brasil"]["secoes"], [], None
    for i, t in enumerate(s["t"]):
        if b["secoes"][i] < minimo * total:
            continue
        atual = "petismo" if b["petismo"][i] > b["bolsonarismo"][i] else "bolsonarismo" if b["petismo"][i] < b["bolsonarismo"][i] else lider
        if lider is not None and atual != lider:
            out.append({"t": t, "pct_secoes": round(100 * b["secoes"][i] / total, 2), "lider": atual})
        lider = atual
    return out


def minuto_quase_total(s, fracao=0.999):
    b, total = s["regioes"]["Brasil"]["secoes"], s["totais"]["Brasil"]["secoes"]
    return next(t for t, n in zip(s["t"], b) if n >= fracao * total)


def gerar(con, ano, turno):
    """Série da apuração de um turno, exata se houver hora de chegada e estimada (por 2022) se não."""
    inicio = config.inicio_divulgacao(ano, turno)
    if tem_chegada_exata(ano, turno):
        chegadas_exatas(con, ano, turno)
        tipo, referencia = "exata", None
    else:
        chegadas_estimadas(con, ano, turno, 2022, turno)
        tipo, referencia = "estimada", f"atrasos de cada zona no {turno}º turno de 2022"
    s = serie(con, inicio)
    e = config.carregar()["eleicoes"][str(ano)]
    return {
        "ano": ano, "turno": turno, "tipo": tipo, "referencia": referencia,
        "inicio": f"{inicio:%Y-%m-%dT%H:%M}",
        "campos": {c: e[c] for c in config.carregar()["campos"]},
        "viradas": viradas(s), "t999": minuto_quase_total(s), **s,
    }


def _pct_validos_por_apurado(s, campo, grade):
    """Participação do campo nos válidos quando o Brasil atinge cada % de seções apuradas da grade."""
    b, total = s["regioes"]["Brasil"], s["totais"]["Brasil"]["secoes"]
    out, i = [], 0
    for g in grade:
        while i < len(s["t"]) - 1 and b["secoes"][i] < g / 100 * total:
            i += 1
        out.append(100 * b[campo][i] / b["validos"][i] if b["validos"][i] else None)
    return out


def _pct_apurado_por_hora(s, minutos):
    b, total, out, i = s["regioes"]["Brasil"]["secoes"], s["totais"]["Brasil"]["secoes"], [], 0
    for m in minutos:
        while i < len(s["t"]) - 1 and s["t"][i + 1] <= m:
            i += 1
        out.append(100 * b[i] / total if s["t"][i] <= m else 0.0)
    return out


TESTES_ESTIMATIVA = [  # (ano, turno) estimado com os atrasos de (ano, turno) de referência
    ((2022, 1), (2022, 2)),
    ((2022, 2), (2022, 1)),
    ((2026, 1), (2022, 1)),  # mesmo turno, outra eleição: o caso mais parecido com o de 2018
]


def validar_estimativa(con):
    """Aplica o método de 2018 a turnos com a chegada real conhecida e mede o erro.

    Cada turno de TESTES_ESTIMATIVA que tem boletins é estimado com os atrasos do turno de referência e comparado
    com a série exata:
    - erro na participação de cada campo nos votos válidos, a cada 1% de seções apuradas (de 5% a 100%);
    - erro no % de seções apuradas, a cada 15 minutos até 99,9% do total.
    """
    resultado = []
    for (ano, turno), (ref_ano, ref) in TESTES_ESTIMATIVA:
        if not (tem_chegada_exata(ano, turno) and tem_chegada_exata(ref_ano, ref)):
            continue
        inicio = config.inicio_divulgacao(ano, turno)
        chegadas_exatas(con, ano, turno)
        exata = serie(con, inicio)
        chegadas_estimadas(con, ano, turno, ref_ano, ref)
        estimada = serie(con, inicio)
        grade = list(range(5, 101))
        erros_campo = {}
        for campo in ("petismo", "bolsonarismo"):
            a, b = _pct_validos_por_apurado(exata, campo, grade), _pct_validos_por_apurado(estimada, campo, grade)
            difs = [abs(x - y) for x, y in zip(a, b) if x is not None and y is not None]
            erros_campo[campo] = {"max": round(max(difs), 3), "media": round(sum(difs) / len(difs), 3)}
        minutos = list(range(0, minuto_quase_total(exata) + 1, 15))
        a, b = _pct_apurado_por_hora(exata, minutos), _pct_apurado_por_hora(estimada, minutos)
        difs = [abs(x - y) for x, y in zip(a, b)]
        resultado.append({
            "alvo": f"{ano}, {turno}º turno", "referencia": f"atrasos de cada zona no {ref}º turno de {ref_ano}",
            "erro_pct_validos": erros_campo,
            "erro_pct_apurado": {"max": round(max(difs), 2), "media": round(sum(difs) / len(difs), 2)},
            "curvas": {"minutos": minutos, "exata": [round(x, 2) for x in a], "estimada": [round(x, 2) for x in b]},
        })
    return resultado
