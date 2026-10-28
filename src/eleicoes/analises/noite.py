"""A noite da apuração como os coletores na nuvem a gravaram (dados/bruto/ao_vivo/<ciclo>-<eleicao>; ao_vivo/juntar.py).

- apuracao(ano, turno): as leituras oficiais do TSE gravadas na noite, no formato de data/apuracao_*.json, com tipo
  "gravada": o país pelo arquivo do país e cada região pela soma das suas UFs, como o site mostrava na noite
  (ao_vivo/painel.py). Vale até o TSE publicar os boletins de urna do turno; aí a curva exata a substitui;
- gerar(con, ano, turno, res): o que fica da noite também depois dos boletins: o forecast como os coletores o mostraram,
  com a contagem do TSE que ele acompanhava, o resultado das urnas e a projeção da véspera para comparar; o momento em
  que o resultado ficou matematicamente definido; a prorrogação da votação, se houve, pelos boletins de urna; e,
  enquanto não há os votos de cada seção, o mapa do fim da noite (o resultado oficial de cada município, que o site
  reparte entre os locais de votação pelo 1º turno).

A noite do 1º turno de 2026 (só o total do país, lido pelo painel que rodava no computador) saiu do site quando os
boletins daquele turno foram publicados; os arquivos dela continuam em dados/bruto/ao_vivo/ele2026-6257.
"""
import datetime as dt
import json

from eleicoes import config
from eleicoes.ao_vivo import painel
from eleicoes.modelos import forecast
from eleicoes.tratamento import boletins, votacao_secao
from eleicoes.tratamento import municipios as tab_municipios

COLUNAS = ("petismo", "inf", "sup", "chance", "vantagem", "vinf", "vsup", "votos_petismo", "votos_bolsonarismo")
MUNICIPIOS_PRORROGACAO = 5  # os municípios com mais seções abertas até o fim da prorrogação


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


def definido(leituras):
    """A primeira atualização do total do país em que quem lidera não podia mais ser alcançado: a vantagem passa do
    eleitorado das seções que faltavam (o eleitorado já apurado é o comparecimento mais a abstenção). {"h", "apurado"}
    ou None."""
    eleitorado = leituras[-1]["c"] + leituras[-1]["a"]  # a última atualização tem todas as seções
    for l in leituras:
        primeiro, segundo = sorted((int(c["v"]) for c in l["cand"].values()), reverse=True)[:2]
        if primeiro - segundo > eleitorado - l["c"] - l["a"]:
            return {"h": l["h"], "apurado": round(l["pst"], 2)}
    return None


def _depois(ano, turno, hora):
    """As seções do turno no Brasil que emitiram o boletim de urna depois de `hora` (Brasília). O exterior fica de fora:
    lá a urna segue o horário local de cada país."""
    fuso = " ".join(f"WHEN '{uf}' THEN {h}" for uf, h in config.FUSO_ATRAS.items())
    return f"""SELECT * FROM '{boletins.saida("secoes", ano, turno).as_posix()}'
               WHERE sg_uf <> 'ZZ' AND dt_emissao_bu + to_hours(CASE sg_uf {fuso} ELSE 0 END)
                                       > TIMESTAMP '{config.turno(ano, turno)["data"]} {hora}:00'"""


def prorrogacao(con, ano, turno):
    """A prorrogação da votação (`prorrogacao` do turno em config/eleicoes.toml) nos boletins de urna: quantas seções
    votaram até o fim do novo horário, pela hora em que emitiram o boletim (o critério do TSE), e onde; e, para comparar,
    o mesmo número no último turno igual com boletins, sem prorrogação. None sem prorrogação ou sem os boletins."""
    fim = config.turno(ano, turno).get("prorrogacao")
    if not fim or not boletins.saida("secoes", ano, turno).exists():
        return None
    secoes = con.execute(f"""SELECT count(*) FROM '{boletins.saida("secoes", ano, turno).as_posix()}'
                             WHERE sg_uf <> 'ZZ'""").fetchone()[0]
    depois = con.execute(f"SELECT count(*) FROM ({_depois(ano, turno, fim)})").fetchone()[0]
    municipios = con.execute(f"""
        SELECT m.nm_municipio, s.sg_uf, count(*) AS n FROM ({_depois(ano, turno, fim)}) s
        JOIN '{tab_municipios.SAIDA.as_posix()}' m USING (cd_municipio)
        GROUP BY ALL ORDER BY n DESC, 1 LIMIT {MUNICIPIOS_PRORROGACAO}""").fetchall()
    # o último turno igual com a hora de chegada dos boletins (2022 em diante), quando o país já votava no horário de
    # Brasília
    anterior = max((a for a in config.anos() if 2022 <= a < ano and boletins.saida("secoes", a, turno).exists()),
                   default=None)
    return {"ate": fim, "secoes": secoes, "depois": depois,
            "municipios": [{"nome": nome, "uf": uf, "secoes": n} for nome, uf, n in municipios],
            "anterior": anterior and {"ano": anterior, "depois": con.execute(
                f"SELECT count(*) FROM ({_depois(anterior, turno, fim)})").fetchone()[0]}}


def gerar(con, ano, turno, res):
    """O forecast da noite em colunas, como as noites refeitas de data/forecast.json (t: minutos desde o início da
    divulgação; apurado: o % das seções no arquivo do país naquela leitura; contagem: o % do petismo nos válidos nela,
    a contagem que o forecast acompanhava), o resultado matematicamente definido, a prorrogação e o mapa do fim, se
    ainda faz falta; None sem o forecast gravado ou sem o resultado do turno."""
    p = pasta(ano, turno)
    r = res.get(str(ano), {}).get(str(turno))
    if not (p / "previsoes.json").exists() or r is None:
        return None
    inicio = config.inicio_divulgacao(ano, turno)
    previsoes = _ler(p / "previsoes.json")
    minuto = lambda h: int((dt.datetime.fromisoformat(h) - inicio).total_seconds() // 60)  # noqa: E731 (como painel.py)
    total, _ = forecast.projecao_da_vespera(ano)
    b = r["Brasil"]
    numero = next(str(n) for n, campo in config.candidatos(ano).items() if campo == "petismo")
    leituras = _ler(p / "leituras_oficiais.json")
    por_hora = {l["h"]: l for l in leituras}
    fim = definido(leituras)
    sem_secoes = votacao_secao.fonte_secoes(ano, turno) is None
    return {
        "ano": ano, "turno": turno, "inicio": f"{inicio:%Y-%m-%dT%H:%M}",
        "real": round(100 * b["petismo"] / b["validos"], 3), "projecao": round(100 * total, 2),
        "forecast": {"t": [minuto(f["h"]) for f in previsoes], "h": [f["h"] for f in previsoes],
                     "apurado": [round(f["pst"], 3) for f in previsoes],
                     **{k: [f[k] for f in previsoes] for k in COLUNAS},
                     "contagem": [round(100 * por_hora[f["h"]]["cand"][numero]["v"] / por_hora[f["h"]]["vv"], 3)
                                  for f in previsoes]},
        "definido": fim and {"t": minuto(fim["h"]), **fim},
        "encerrada": {"t": minuto(leituras[-1]["h"]), "h": leituras[-1]["h"]},
        "prorrogacao": prorrogacao(con, ano, turno),
        "mapa": _ler(p / "mapa.json") if sem_secoes and (p / "mapa.json").exists() else None,
    }
