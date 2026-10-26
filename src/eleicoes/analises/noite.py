"""A noite da apuração como os coletores na nuvem a gravaram (dados/bruto/ao_vivo/<ciclo>-<eleicao>; ao_vivo/juntar.py).

- apuracao(ano, turno): as leituras oficiais do TSE gravadas na noite, no formato de data/apuracao_*.json, com tipo
  "gravada": o país pelo arquivo do país e cada região pela soma das suas UFs, como o site mostrava na noite
  (ao_vivo/painel.py). Vale até o TSE publicar os boletins de urna do turno; aí a curva exata a substitui;
- gerar(ano, turno, res): o que fica da noite também depois dos boletins: o forecast como os coletores o mostraram,
  com o resultado das urnas e a projeção da véspera para comparar; e, enquanto não há os votos de cada seção, o mapa do
  fim da noite (o resultado oficial de cada município, que o site reparte entre os locais de votação pelo 1º turno).

A noite do 1º turno de 2026 (só o total do país, lido pelo painel que rodava no computador) saiu do site quando os
boletins daquele turno foram publicados; os arquivos dela continuam em dados/bruto/ao_vivo/ele2026-6257.
"""
import datetime as dt
import json

from eleicoes import config
from eleicoes.ao_vivo import painel
from eleicoes.modelos import forecast
from eleicoes.tratamento import votacao_secao

COLUNAS = ("petismo", "inf", "sup", "chance", "vantagem", "vinf", "vsup", "votos_petismo", "votos_bolsonarismo")


def pasta(ano, turno):
    return config.BRUTO / "ao_vivo" / f"ele{ano}-{config.turno(ano, turno).get('eleicao')}"


def _ler(arq):
    return json.loads(arq.read_text("utf-8"))


def apuracao(ano, turno):
    """A apuração pelas leituras oficiais gravadas; None sem as leituras do país e das UFs."""
    p = pasta(ano, turno)
    if not ((p / "leituras_oficiais.json").exists() and (p / "leituras_ufs.json").exists()):
        return None
    numeros = {campo: str(n) for n, campo in config.candidatos(ano).items()}
    s = painel.serie(_ler(p / "leituras_oficiais.json"), _ler(p / "leituras_ufs.json"),
                     config.inicio_divulgacao(ano, turno), numeros)
    return {**s, "ano": ano, "turno": turno, "tipo": "gravada"}


def gerar(ano, turno, res):
    """O forecast da noite em colunas, como as noites refeitas de data/forecast.json (t: minutos desde o início da
    divulgação; apurado: o % das seções no arquivo do país naquela leitura), e o mapa do fim, se ainda faz falta; None
    sem o forecast gravado ou sem o resultado do turno."""
    p = pasta(ano, turno)
    r = res.get(str(ano), {}).get(str(turno))
    if not (p / "previsoes.json").exists() or r is None:
        return None
    inicio = config.inicio_divulgacao(ano, turno)
    previsoes = _ler(p / "previsoes.json")
    minuto = lambda h: int((dt.datetime.fromisoformat(h) - inicio).total_seconds() // 60)  # noqa: E731 (como painel.py)
    total, _ = forecast.projecao_da_vespera(ano)
    b = r["Brasil"]
    sem_secoes = votacao_secao.fonte_secoes(ano, turno) is None
    return {
        "ano": ano, "turno": turno, "inicio": f"{inicio:%Y-%m-%dT%H:%M}",
        "real": round(100 * b["petismo"] / b["validos"], 3), "projecao": round(100 * total, 2),
        "forecast": {"t": [minuto(f["h"]) for f in previsoes], "h": [f["h"] for f in previsoes],
                     "apurado": [round(f["pst"], 3) for f in previsoes],
                     **{k: [f[k] for f in previsoes] for k in COLUNAS}},
        "mapa": _ler(p / "mapa.json") if sem_secoes and (p / "mapa.json").exists() else None,
    }
