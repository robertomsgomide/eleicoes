"""Projeção do 2º turno a partir do 1º turno (seção por seção) e das pesquisas de 2º turno, com incerteza.

Tudo em % dos votos válidos, a base do resultado oficial. Duas partes:

1. O total do país (`projetar`) junta duas estimativas, cada uma com o peso da sua precisão:
   - o ponto de partida (`partida`), que só usa o que se sabe na noite do 1º turno: o resultado das urnas e a
     divisão dos eleitores dos outros candidatos que as pesquisas da última semana mostravam. Cada pesquisa que
     perguntou o 1º e o 2º turno à mesma amostra diz que parte dos eleitores dos outros candidatos iria para o
     petismo no confronto direto; a média dessa parte é aplicada aos votos que os outros tiveram nas urnas.
     Comparar os dois turnos dentro da mesma pesquisa tira o viés que ela tenha igual nos dois;
   - a tendência das pesquisas de 2º turno feitas depois do 1º turno (`media_pesquisas`): a mesma reta local da
     página de pesquisas (`analises.pesquisas.reta_local`), no dia da última pesquisa.
   A incerteza das pesquisas soma três partes (`Desvios`): a dispersão entre elas (que pesa menos com mais
   pesquisas), o erro que a média ainda tem na véspera e quanto a opinião pode mudar até a eleição (por raiz de
   dia). O ponto de partida tem o seu próprio desvio. Chance de vitória: a probabilidade de passar de 50% numa
   normal com a média e o desvio combinados.

2. Como esse total se distribui pelo país (`distribuir`), seção por seção. Quem votou no petismo ou no
   bolsonarismo no 1º turno continua com ele; os votos dos outros candidatos se dividem numa proporção que
   acompanha a inclinação da seção: parte do petismo = logística(a + INCLINACAO · logit(petismo / (petismo +
   bolsonarismo))). `a` é o que faz o país somar o total projetado. Se o total pedido sai do que os votos dos
   outros permitem, o que falta vira um deslocamento igual em todas as seções, em logit. O erro dessa
   distribuição, medido em 2018 e 2022 com o total nacional verdadeiro, é proporcional à parte dos outros
   candidatos no 1º turno: ERRO_UF e ERRO_REGIAO pontos para cada ponto dos outros.

Os parâmetros foram escolhidos refazendo a projeção em 2018 e 2022 dia a dia, só com o que se sabia em cada dia
(`validar`; relatório em docs/validacao_projecao.md, com a sensibilidade a cada desvio). Com duas eleições, são
números redondos e conservadores, não um ajuste fino.
"""
import dataclasses
import datetime as dt
import functools
import json
import math

import numpy as np

from eleicoes import config
from eleicoes.analises import pesquisas as analise
from eleicoes.tratamento import votacao_secao

INCLINACAO = 0.5        # quanto a divisão dos outros acompanha a inclinação da seção (em 2018 e 2022, 0,5 a 0,75)
ERRO_UF = 0.09          # desvio do modelo numa UF, por ponto percentual dos outros candidatos no 1º turno
ERRO_REGIAO = 0.06      # idem numa região
SEMANA_PAREADAS = 7     # pesquisas pareadas: fim do campo até 7 dias antes do 1º turno


@dataclasses.dataclass(frozen=True)
class Desvios:
    """Desvios do total do país, em pontos percentuais da parte do petismo nos votos válidos."""
    partida: float = 2.5    # do ponto de partida (errou +0,4 em 2018 e +2,3 em 2022)
    pesquisa: float = 2.0   # de uma pesquisa em torno da média: amostra e estilo de cada instituto
    vespera: float = 1.5    # erro comum a todas as pesquisas, que não diminui com mais pesquisas
    deriva: float = 0.7     # por raiz de dia: quanto a opinião ainda pode mudar até a eleição


DESVIOS = Desvios()
Z80 = 1.2816            # metade do intervalo de 80% de uma normal, em desvios
NIVEIS = (("regioes", "regiao", ERRO_REGIAO), ("ufs", "uf", ERRO_UF))
SITE = config.RAIZ / "site" / "src" / "data" / "projecao.json"
RELATORIO = config.RAIZ / "docs" / "validacao_projecao.md"


def _logit(p):
    return np.log(p / (1 - p))


def _expit(x):
    return 1 / (1 + np.exp(-x))


def _normal(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _raiz(f, lo, hi, passos=60):
    """Zero de uma função crescente entre lo e hi (bisseção)."""
    for _ in range(passos):
        meio = (lo + hi) / 2
        lo, hi = (meio, hi) if f(meio) < 0 else (lo, meio)
    return (lo + hi) / 2


def data(ano, turno):
    return dt.date.fromisoformat(config.turno(ano, turno)["data"])


# ---- Distribuição pelo país ---------------------------------------------------------

@dataclasses.dataclass
class Secoes:
    """Votos válidos de cada seção no 1º turno, em arrays alinhados (chaves e votos de cada campo)."""
    uf: np.ndarray
    regiao: np.ndarray
    municipio: np.ndarray
    petismo: np.ndarray
    bolsonarismo: np.ndarray
    outros: np.ndarray
    _indices: dict = dataclasses.field(default_factory=dict, repr=False)

    @functools.cached_property
    def validos(self):
        return self.petismo + self.bolsonarismo + self.outros

    @functools.cached_property
    def inclinacao(self):
        """logit da parte do petismo entre os dois campos (meio voto a mais para não dar 0 nem 100%)."""
        return _logit((self.petismo + 0.5) / (self.petismo + self.bolsonarismo + 1))

    def agregar(self, valores, nivel):
        """{chave: soma dos valores} por "uf", "regiao" ou "municipio"."""
        if nivel not in self._indices:
            self._indices[nivel] = np.unique(getattr(self, nivel), return_inverse=True)
        chaves, i = self._indices[nivel]
        return dict(zip(chaves.tolist(), np.bincount(i, valores).tolist()))

    def parte(self, partes, nivel):
        """{chave: % do petismo nos válidos} dadas as partes de cada seção (frações)."""
        votos, validos = self.agregar(partes * self.validos, nivel), self.agregar(self.validos, nivel)
        return {k: 100 * votos[k] / validos[k] for k in validos}


def secoes(con, ano):
    """O 1º turno de cada seção com votos válidos: boletins de urna ou, sem eles, a votação por seção."""
    arq = votacao_secao.fonte_secoes(ano, 1).as_posix()
    d = con.execute(f"""SELECT sg_uf AS uf, regiao, cd_municipio AS municipio, votos_petismo::DOUBLE AS petismo,
                               votos_bolsonarismo::DOUBLE AS bolsonarismo, votos_outros::DOUBLE AS outros
                        FROM '{arq}' WHERE votos_validos > 0""").fetchnumpy()
    return Secoes(**{k: np.asarray(v) for k, v in d.items()})


def _partes(s, a, deslocamento):
    p = (s.petismo + _expit(a + INCLINACAO * s.inclinacao) * s.outros) / s.validos
    return _expit(_logit(np.clip(p, 1e-9, 1 - 1e-9)) + deslocamento) if deslocamento else p


def ajuste(s, total):
    """(a, deslocamento) com que as seções somam `total` (fração dos válidos do país para o petismo)."""
    v, pt, outros = s.validos.sum(), s.petismo.sum(), s.outros.sum()
    if pt / v < total < (pt + outros) / v:
        return _raiz(lambda a: (pt + (_expit(a + INCLINACAO * s.inclinacao) * s.outros).sum()) / v - total, -30, 30), 0.0
    a = -30.0 if total <= pt / v else 30.0  # os outros todos para um lado só e, além disso, o deslocamento
    z = _logit(np.clip(_partes(s, a, 0.0), 1e-9, 1 - 1e-9))
    return a, _raiz(lambda d: (_expit(z + d) * s.validos).sum() / v - total, -15, 15)


def distribuir(s, total):
    """Parte do petismo nos votos válidos de cada seção no 2º turno, para um total do país (fração)."""
    return _partes(s, *ajuste(s, total))


def por_lugar(s, media, desvio):
    """Região e UF: projeção, intervalo de 80% e chance de vitória do petismo, para um total do país N(media, desvio).

    Desvio em cada lugar: o do país, transmitido pela distribuição (derivada numérica), somado ao erro do modelo,
    proporcional à parte dos outros candidatos no 1º turno daquele lugar.
    """
    h = 0.5
    centro, mais, menos = (distribuir(s, (media + d) / 100) for d in (0, h, -h))
    out = {}
    for nome, nivel, erro in NIVEIS:
        c, m, n = (s.parte(x, nivel) for x in (centro, mais, menos))
        validos = s.agregar(s.validos, nivel)
        primeiro = {campo: s.agregar(getattr(s, campo), nivel) for campo in ("petismo", "bolsonarismo", "outros")}
        out[nome] = {}
        for k in sorted(c):
            outros = 100 * primeiro["outros"][k] / validos[k]
            sd = math.hypot((m[k] - n[k]) / (2 * h) * desvio, erro * outros)
            out[nome][k] = {"petismo": round(c[k], 2), "inf": round(c[k] - Z80 * sd, 2), "sup": round(c[k] + Z80 * sd, 2),
                            "chance": round(1 - _normal((50 - c[k]) / sd), 3),
                            "primeiro_turno": {campo: round(100 * v[k] / validos[k], 2) for campo, v in primeiro.items()}}
    return out


# ---- Total do país ------------------------------------------------------------------

def primeiro_turno(res, ano):
    """{"petismo", "bolsonarismo", "outros"} em % dos válidos do 1º turno no Brasil (resultado oficial)."""
    b = res[str(ano)]["1"]["Brasil"]
    return {c: 100 * b[c] / b["validos"] for c in ("petismo", "bolsonarismo", "outros")}


def partida(pesquisas, ano, primeiro):
    """O ponto de partida: o 1º turno das urnas mais a parte dos outros que as pesquisas pareadas dão ao petismo.

    Pesquisas pareadas: as da semana anterior ao 1º turno que trazem o 1º e o 2º turno (mesmo instituto e mesmas
    datas de campo). Em cada uma, parte = (petismo no 2º turno − petismo no 1º) / outros no 1º, limitada a [0, 1].
    """
    d1 = data(ano, 1)
    t1 = {(p["instituto"], p["inicio"], p["fim"]): p for p in pesquisas
          if p["turno"] == 1 and 0 < (d1 - p["fim"]).days <= SEMANA_PAREADAS}
    pares = []
    for p in pesquisas:
        if p["turno"] != 2 or (a := t1.get((p["instituto"], p["inicio"], p["fim"]))) is None:
            continue
        outros = 100 - a["petismo_validos"] - a["bolsonarismo_validos"]
        if outros > 0:
            parte = min(1.0, max(0.0, (p["petismo_validos"] - a["petismo_validos"]) / outros))
            pares.append({"instituto": p["instituto"], "fim": p["fim"].isoformat(), "primeiro_petismo": a["petismo_validos"],
                          "primeiro_outros": round(outros, 2), "segundo_petismo": p["petismo_validos"], "parte": round(parte, 3)})
    if not pares:
        return None
    parte = sum(p["parte"] for p in pares) / len(pares)
    return {"petismo": round(primeiro["petismo"] + parte * primeiro["outros"], 2), "parte_dos_outros": round(parte, 3),
            # o que essas pesquisas davam diretamente para o 2º turno, para comparação
            "segundo_turno_nas_pesquisas": round(sum(p["segundo_petismo"] for p in pares) / len(pares), 2),
            "pares": sorted(pares, key=lambda p: (p["fim"], p["instituto"]))}


def media_pesquisas(pesquisas, ano, dia):
    """A tendência das pesquisas de 2º turno feitas depois do 1º turno e concluídas até `dia`, no dia da última delas.

    {"petismo", "quadrados" (soma dos quadrados dos pesos: o desvio da média é o de uma pesquisa × √quadrados),
    "pesquisas", "ultima"} ou None sem pesquisas. Com menos de `analise.MINIMO` pesquisas por perto, vale a média
    ponderada delas.
    """
    ps = [p for p in analise.depois_do_primeiro_turno(pesquisas, ano) if p["fim"] <= dia]
    if not ps:
        return None
    ultima = max(p["fim"] for p in ps)
    if (r := analise.reta_local(ps, ultima)) is not None:
        estimativa, quadrados = r[0]["petismo"], r[1]
    else:
        w = [analise.peso(p, ultima) for p in ps]
        estimativa = sum(wi * p["petismo_validos"] for wi, p in zip(w, ps)) / sum(w)
        quadrados = sum(wi * wi for wi in w) / sum(w) ** 2
    return {"petismo": estimativa, "quadrados": quadrados, "pesquisas": len(ps), "ultima": ultima}


def projetar(partida_petismo, media, eleicao, d=DESVIOS):
    """O total do país no dia da eleição: ponto de partida e pesquisas, cada um com o peso da sua precisão."""
    precisao, soma, peso = 1 / d.partida ** 2, partida_petismo / d.partida ** 2, 0.0
    if media:
        dias = (eleicao - media["ultima"]).days
        var = d.pesquisa ** 2 * media["quadrados"] + d.vespera ** 2 + d.deriva ** 2 * dias
        precisao, soma = precisao + 1 / var, soma + media["petismo"] / var
        peso = (1 / var) / precisao
    m, sd = soma / precisao, precisao ** -0.5
    return {"petismo": round(m, 2), "desvio": round(sd, 2), "inf": round(m - Z80 * sd, 2), "sup": round(m + Z80 * sd, 2),
            "chance": round(1 - _normal((50 - m) / sd), 3), "peso_pesquisas": round(peso, 3)}


def serie(pesquisas, ano, partida_petismo, ate, d=DESVIOS):
    """A projeção de cada dia, do 1º turno até `ate`, só com as pesquisas concluídas até aquele dia."""
    eleicao, out = data(ano, 2), []
    for i in range((ate - data(ano, 1)).days + 1):
        dia = data(ano, 1) + dt.timedelta(days=i)
        m = media_pesquisas(pesquisas, ano, dia)
        out.append({"data": dia.isoformat(), "dias": (eleicao - dia).days, "pesquisas": m["pesquisas"] if m else 0,
                    "media": round(m["petismo"], 2) if m else None, **projetar(partida_petismo, m, eleicao, d)})
    return out


def ultimo_dia(ano):
    """Último dia da projeção: a véspera da eleição ou, antes dela, o último dia em que as pesquisas foram
    conferidas na Wikipedia (baixadas, ou vistas iguais pelo `uv run eleicoes atualizar`)."""
    vespera = data(ano, 2) - dt.timedelta(days=1)
    from eleicoes.coleta import wikipedia
    rev = wikipedia.revisao(ano)
    conferido = dt.date.fromisoformat((rev.get("consultado_em") or rev["baixado_em"])[:10]) if rev else vespera
    return max(data(ano, 1), min(vespera, conferido))


# ---- Resultado de cada ano ----------------------------------------------------------

def _real(res, ano):
    """O 2º turno das urnas (% do petismo nos válidos): Brasil, regiões e UFs; None antes da eleição."""
    r = res.get(str(ano), {}).get("2")
    if not r:
        return None
    pct = lambda d: round(100 * d["petismo"] / d["validos"], 2)  # noqa: E731
    return {"petismo": pct(r["Brasil"]), "regioes": {k: pct(v) for k, v in r["regioes"].items() if v["validos"]},
            "ufs": {k: pct(v) for k, v in r["ufs"].items()}}


def projecao_do_ano(con, res, ano):
    """Tudo o que o site mostra de um ano: ponto de partida, projeção dia a dia, regiões e UFs no último dia."""
    pesquisas = analise.carregar(ano)
    if "1" not in res.get(str(ano), {}) or not votacao_secao.fonte_secoes(ano, 1) or not any(p["turno"] == 2 for p in pesquisas):
        return None
    primeiro = primeiro_turno(res, ano)
    ponto = partida(pesquisas, ano, primeiro)
    if ponto is None:
        return None
    dias = serie(pesquisas, ano, ponto["petismo"], ultimo_dia(ano))
    atual = dias[-1]
    precisa = (50 - primeiro["petismo"]) / primeiro["outros"]
    return {
        "ano": ano, "primeiro_turno": {"data": data(ano, 1).isoformat(), **{k: round(v, 2) for k, v in primeiro.items()}},
        "eleicao": data(ano, 2).isoformat(), "partida": ponto, "serie": dias, "atual": atual,
        "parte_dos_outros": {"projetada": round((atual["petismo"] - primeiro["petismo"]) / primeiro["outros"], 3),
                             "necessaria": round(precisa, 3) if 0 < precisa < 1 else None},
        **por_lugar(secoes(con, ano), atual["petismo"], atual["desvio"]),
        "resultado": _real(res, ano),
    }


def gerar(con, res):
    """O JSON do site (site/src/data/projecao.json): cada ano com 1º turno e pesquisas de 2º turno, e a validação."""
    anos = {str(a): p for a in config.anos() if (p := projecao_do_ano(con, res, a)) is not None}
    return {"parametros": {"inclinacao": INCLINACAO, "erro_uf": ERRO_UF, "erro_regiao": ERRO_REGIAO,
                           **{f"desvio_{k}": v for k, v in dataclasses.asdict(DESVIOS).items()},
                           "semana_pareadas": SEMANA_PAREADAS, "intervalo": 0.8, "janela_dias": analise.JANELA},
            "anos": anos, "validacao": validar(con, res, anos)}


# ---- Validação em 2018 e 2022 -------------------------------------------------------

def _municipios_2t(con, ano):
    """{município: % do petismo nos válidos} no 2º turno, pelas seções."""
    arq = votacao_secao.fonte_secoes(ano, 2).as_posix()
    return {m: 100 * p / v for m, p, v in con.execute(
        f"SELECT cd_municipio, sum(votos_petismo), sum(votos_validos) FROM '{arq}' GROUP BY 1 HAVING sum(votos_validos) > 0").fetchall()}


def _rms(erros, pesos=None):
    pesos = pesos or [1] * len(erros)
    return math.sqrt(sum(w * e * e for w, e in zip(pesos, erros)) / sum(pesos))


def validar(con, res, anos):
    """Os erros de cada parte da projeção nos anos que já tiveram 2º turno (2018 e 2022).

    - distribuição: dado o total nacional verdadeiro, quanto erra a % do petismo em cada região, UF e município
      (desvio típico; municípios ponderados pelos votos) e quantas UFs caem no intervalo de 80% do modelo;
    - total do país: o erro do ponto de partida (e, para comparar, o das pesquisas de 2º turno em que ele se baseia,
      tomadas diretamente), o da projeção a cada dia e quantos dias o resultado caiu no intervalo de 80%;
    - véspera: com a projeção da véspera, quantas UFs caíram no intervalo de 80% e o erro típico por UF.
    """
    out = {}
    for ano, p in anos.items():
        real = p["resultado"]
        if real is None or not votacao_secao.fonte_secoes(int(ano), 2):
            continue
        s = secoes(con, int(ano))
        partes = distribuir(s, real["petismo"] / 100)
        validos = s.agregar(s.validos, "municipio")
        mun_real, mun = _municipios_2t(con, int(ano)), s.parte(partes, "municipio")
        comuns = [m for m in mun if m in mun_real]
        distribuicao = {"municipios": round(_rms([mun[m] - mun_real[m] for m in comuns], [validos[m] for m in comuns]), 2)}
        for nome, nivel, erro in NIVEIS:
            proj = s.parte(partes, nivel)
            outros = s.parte(s.outros / s.validos, nivel)
            erros = {k: proj[k] - real[nome][k] for k in real[nome]}
            distribuicao[nome] = round(_rms(list(erros.values())), 2)
            distribuicao[f"{nome}_no_intervalo"] = round(
                sum(abs(e) <= Z80 * erro * outros[k] for k, e in erros.items()) / len(erros), 3)
        erros_dia = [d["petismo"] - real["petismo"] for d in p["serie"]]
        dentro = [d["inf"] <= real["petismo"] <= d["sup"] for d in p["serie"]]
        vespera = {k: (v["petismo"] - real["ufs"][k], v["inf"] <= real["ufs"][k] <= v["sup"]) for k, v in p["ufs"].items()}
        out[ano] = {
            "distribuicao": distribuicao,
            "partida": round(p["partida"]["petismo"] - real["petismo"], 2),
            "segundo_turno_nas_pesquisas": round(p["partida"]["segundo_turno_nas_pesquisas"] - real["petismo"], 2),
            "projecao": {"medio": round(sum(map(abs, erros_dia)) / len(erros_dia), 2), "maximo": round(max(map(abs, erros_dia)), 2),
                         "vespera": round(erros_dia[-1], 2), "dias_no_intervalo": round(sum(dentro) / len(dentro), 3)},
            "vespera_ufs": {"erro": round(_rms([e for e, _ in vespera.values()]), 2),
                            "no_intervalo": round(sum(d for _, d in vespera.values()) / len(vespera), 3)},
        }
    return out


def sensibilidade(dados, fatores=(0.6, 1.4)):
    """Cada desvio do total do país 40% menor e 40% maior, com os outros como no modelo: [(desvio, valor, {ano: ...})].

    Nos anos já decididos, o erro médio da projeção e a parte dos dias com as urnas na faixa de 80%; nos outros, a
    chance do petismo no último dia.
    """
    pesquisas = {a: analise.carregar(int(a)) for a in dados["anos"]}

    def medir(d):
        out = {}
        for a, p in dados["anos"].items():
            s = serie(pesquisas[a], int(a), p["partida"]["petismo"], dt.date.fromisoformat(p["serie"][-1]["data"]), d)
            if (real := p["resultado"]) is None:
                out[a] = {"chance": s[-1]["chance"]}
            else:
                out[a] = {"erro": sum(abs(x["petismo"] - real["petismo"]) for x in s) / len(s),
                          "na_faixa": sum(x["inf"] <= real["petismo"] <= x["sup"] for x in s) / len(s)}
        return out

    linhas = [(None, None, medir(DESVIOS))]
    for campo in dataclasses.fields(Desvios):
        for fator in fatores:
            valor = round(getattr(DESVIOS, campo.name) * fator, 2)
            linhas.append((campo.name, valor, medir(dataclasses.replace(DESVIOS, **{campo.name: valor}))))
    return linhas


# ---- Comando ------------------------------------------------------------------------

def _num(v, casas=2, sinal=False):
    return f"{v:{'+' if sinal else ''}.{casas}f}".replace(".", ",").replace("-", "−")


def _pct(v, casas=1):
    return _num(v, casas) + "%"


def relatorio(dados):
    """docs/validacao_projecao.md: a projeção atual e os erros do método em 2018 e 2022."""
    v = dados["validacao"]
    linhas = ["# Validação da projeção do 2º turno", "",
              f"> Gerado por `uv run eleicoes projecao` (ou `atualizar`) em {dt.datetime.now():%d/%m/%Y %H:%M}. Não editar à mão.", "",
              "Método em `src/eleicoes/modelos/projecao.py` e na Metodologia do site. Cada ano é refeito dia a dia, "
              "só com o que se sabia em cada dia (o 1º turno das urnas e as pesquisas concluídas até ali).", "",
              "## Projeção de cada ano", "",
              "| Ano | Último dia | Pesquisas depois do 1º turno | Ponto de partida | Projeção do petismo | Intervalo de 80% | Chance do petismo | 2º turno das urnas |",
              "|---|---|--:|--:|--:|---|--:|--:|"]
    for ano, p in dados["anos"].items():
        a = p["atual"]
        real = _pct(p["resultado"]["petismo"], 2) if p["resultado"] else "–"
        linhas.append(f"| {ano} | {dt.date.fromisoformat(a['data']):%d/%m} | {a['pesquisas']} | {_pct(p['partida']['petismo'], 2)} | "
                      f"{_pct(a['petismo'], 2)} | {_pct(a['inf'])} a {_pct(a['sup'])} | {_pct(100 * a['chance'], 0)} | {real} |")
    linhas += ["", "## Erros em 2018 e 2022", "",
               "Erro = projeção − urnas, em pontos percentuais da parte do petismo nos votos válidos.", "",
               "| Ano | Pesquisas de 2º turno da véspera do 1º | Ponto de partida | Projeção: erro médio · máximo · na véspera | Dias com o resultado no intervalo de 80% | Véspera, UFs: erro típico · no intervalo de 80% |",
               "|---|--:|--:|---|--:|---|"]
    for ano, e in v.items():
        pr, uf = e["projecao"], e["vespera_ufs"]
        linhas.append(f"| {ano} | {_num(e['segundo_turno_nas_pesquisas'], sinal=True)} | {_num(e['partida'], sinal=True)} | "
                      f"{_num(pr['medio'])} · {_num(pr['maximo'])} · "
                      f"{_num(pr['vespera'], sinal=True)} | {_pct(100 * pr['dias_no_intervalo'], 0)} | "
                      f"{_num(uf['erro'])} · {_pct(100 * uf['no_intervalo'], 0)} |")
    linhas += ["", "### Distribuição pelo país, com o total nacional verdadeiro", "",
               "Quanto o modelo de distribuição erra só na geografia: o total do país é o das urnas e o modelo reparte "
               "esse total pelas seções a partir do 1º turno. Desvio típico em p.p. (municípios ponderados pelos votos) e "
               "a parte dos lugares cujo resultado caiu no intervalo de 80% do modelo.", "",
               "| Ano | Regiões | UFs | Municípios | Regiões no intervalo | UFs no intervalo |", "|---|--:|--:|--:|--:|--:|"]
    for ano, e in v.items():
        d = e["distribuicao"]
        linhas.append(f"| {ano} | {_num(d['regioes'])} | {_num(d['ufs'])} | {_num(d['municipios'])} | "
                      f"{_pct(100 * d['regioes_no_intervalo'], 0)} | {_pct(100 * d['ufs_no_intervalo'], 0)} |")
    sens = sensibilidade(dados)
    anos = list(dados["anos"])
    linhas += ["", "## Sensibilidade aos desvios do total do país", "",
               "Cada desvio 40% menor e 40% maior, com os outros como no modelo. Nos anos já decididos: erro médio da "
               "projeção (p.p.) e parte dos dias com as urnas na faixa de 80%; nos outros, a chance do petismo no último dia.", "",
               "| Desvio | Valor | " + " | ".join(anos) + " |", "|---|--:|" + "--:|" * len(anos)]
    nomes = {"partida": "ponto de partida", "pesquisa": "uma pesquisa", "vespera": "erro comum na véspera",
             "deriva": "mudança por raiz de dia"}
    for campo, valor, medidas in sens:
        celulas = [f"{_num(m['erro'])} · {_pct(100 * m['na_faixa'], 0)}" if "erro" in m else _pct(100 * m["chance"], 0)
                   for m in medidas.values()]
        rotulo = "**como no modelo**" if campo is None else nomes[campo]
        linhas.append(f"| {rotulo} | {'' if valor is None else _num(valor, 2)} | " + " | ".join(celulas) + " |")
    linhas += ["", "## Parâmetros", "", "| Parâmetro | Valor |", "|---|--:|"]
    linhas += [f"| `{k}` | {str(val).replace('.', ',')} |" for k, val in dados["parametros"].items()]
    RELATORIO.write_text("\n".join(linhas) + "\n", "utf-8")


def gravar():
    """Gera site/src/data/projecao.json e docs/validacao_projecao.md; devolve os dados do JSON."""
    from eleicoes.analises import resultados
    from eleicoes.tratamento import conexao
    con = conexao()
    dados = gerar(con, resultados.gerar(con))
    SITE.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), "utf-8")
    relatorio(dados)
    return dados


def resumo(p):
    """A projeção do último dia de um ano em uma linha: "Lula 48,2% (80%: 45,0% a 51,4%) × ... · chance de ..."."""
    a, nomes = p["atual"], config.nomes(p["ano"])
    lider = "petismo" if a["petismo"] >= 50 else "bolsonarismo"
    chance = a["chance"] if lider == "petismo" else 1 - a["chance"]
    return (f"{nomes['petismo']} {_pct(a['petismo'])} (80%: {_pct(a['inf'])} a {_pct(a['sup'])}) × "
            f"{nomes['bolsonarismo']} {_pct(100 - a['petismo'])} · chance de {nomes[lider]}: {_pct(100 * chance, 0)}")


def rodar(log=print):
    """uv run eleicoes projecao: gera site/src/data/projecao.json e docs/validacao_projecao.md e resume a projeção."""
    dados = gravar()
    for ano, p in dados["anos"].items():
        a = p["atual"]
        quando = f"com as pesquisas até {dt.date.fromisoformat(a['data']):%d/%m/%Y}"
        log(f"\n{ano}, 2º turno · projeção {quando} ({a['pesquisas']} pesquisas depois do 1º turno)")
        log(f"   {resumo(p)}")
        if p["resultado"]:
            log(f"   urnas: {config.nomes(ano)['petismo']} {_pct(p['resultado']['petismo'], 2)}")
    log(f"\nsite/src/data/projecao.json · validação em {RELATORIO.relative_to(config.RAIZ).as_posix()}")
