"""A noite da apuração como foi gravada ao vivo (dados/bruto/ao_vivo/<ciclo>-<eleicao>).

- leituras_oficiais.json: cada retrato do arquivo nacional do TSE lido pelo painel ao vivo (exato);
- historico_estimado.csv: reconstrução feita durante a noite pela média municipal (estimada, só até a hora
  em que foi gerada), usada para cobrir o começo da noite, antes da primeira leitura oficial gravada.

Fica no site até o TSE publicar os boletins de urna daquele turno; aí a curva exata substitui as duas.
"""
import csv
import datetime as dt
import json

from eleicoes import config


def _num(x):
    return float(x.replace(",", ".")) if x else None


def gerar(ano, turno):
    t = config.turno(ano, turno)
    pasta = config.BRUTO / "ao_vivo" / f"ele{ano}-{t.get('eleicao')}"
    if not (pasta / "leituras_oficiais.json").exists():
        return None
    inicio = config.inicio_divulgacao(ano, turno)
    numeros = {c: n for n, c in config.candidatos(ano).items()}
    minutos = lambda h: round((h - inicio).total_seconds() / 60, 2)  # noqa: E731

    oficial = {"t": [], "pct_secoes": [], "petismo": [], "bolsonarismo": [], "votos_petismo": [], "votos_bolsonarismo": []}
    for o in json.loads((pasta / "leituras_oficiais.json").read_text("utf-8")):
        oficial["t"].append(minutos(dt.datetime.fromisoformat(o["h"])))
        oficial["pct_secoes"].append(round(o["pst"], 3))
        for campo, n in numeros.items():
            c = o["cand"][str(n)]
            oficial[campo].append(round(c["p"], 3))
            oficial[f"votos_{campo}"].append(int(c["v"]))

    estimada = {"t": [], "pct_secoes": [], "petismo": [], "bolsonarismo": [], "ate": None}
    arq = pasta / "historico_estimado.csv"
    if arq.exists():
        with open(arq, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f, delimiter=";"))
        col = lambda campo: next(k for k in linhas[0] if k.startswith(f"pct_validos_estimado_{numeros[campo]}_"))  # noqa: E731
        for l in linhas:
            h = dt.datetime.strptime(l["horario"], "%d/%m/%Y %H:%M")
            estimada["t"].append(minutos(h))
            estimada["pct_secoes"].append(_num(l["pct_recebidos_Brasil"]))
            for campo in ("petismo", "bolsonarismo"):
                v = _num(l[col(campo)])
                estimada[campo].append(None if v is None else round(v, 3))
        estimada["ate"] = linhas[-1]["horario"]
    return {"ano": ano, "turno": turno, "inicio": f"{inicio:%Y-%m-%dT%H:%M}", "oficial": oficial, "estimada": estimada}
