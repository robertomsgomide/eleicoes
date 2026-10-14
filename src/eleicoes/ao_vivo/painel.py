"""O que o site lê durante a noite, em cada ramo de coletor (coletor.py grava a cada envio):

  dados.json   a apuração no formato de site/src/data/apuracao_*.json, montada com as leituras oficiais do país e de
               cada UF (cada ponto é uma atualização do TSE); o último total de cada UF; o forecast do resultado final
               (modelos/forecast.py) agora e o histórico dele na noite
  mapa.json    para o mapa: o que já foi apurado em cada município (na ordem de site/src/data/mapa/municipios.json) e
               o swing e o comparecimento estimados de cada um, com a divisão dos outros candidatos do prior; o site
               reparte o resultado de cada município pelos locais de votação a partir do 1º turno

O forecast precisa das seções do 1º turno (dados/processado/tse/secoes/<ano>_t1.parquet, que o job copia do ramo
`dados`) e da projeção da véspera (site/src/data/projecao.json). Sem elas, a coleta segue e os arquivos saem sem o
forecast.
"""
import datetime as dt
import json

import numpy as np

from eleicoes import config
from eleicoes.analises import apuracao
from eleicoes.modelos import forecast as F

VERSAO = 2
MUNICIPIOS_DO_MAPA = config.RAIZ / "site" / "src" / "data" / "mapa" / "municipios.json"
REGIAO_DA_UF = {uf.lower(): r for uf, r in config.REGIAO_DA_UF.items()}


def _minuto(h, inicio):
    return int((dt.datetime.fromisoformat(h) - inicio).total_seconds() // 60)


def _votos(leitura, numero):
    return int(leitura["cand"].get(numero, {}).get("v", 0))


def serie(leituras_br, leituras_uf, inicio, numeros):
    """A apuração no formato de data/apuracao_*.json, com as leituras oficiais: o Brasil pelo arquivo do país e cada
    região pela soma das suas UFs, a cada minuto em que algum arquivo mudou (o último de cada um vale até o seguinte).

    leituras_br: [leitura do país]; leituras_uf: {uf: [leitura]}; numeros: {"petismo": "13", "bolsonarismo": "22"}.
    """
    medidas = ("secoes", "validos", "petismo", "bolsonarismo")

    def valores(l):
        return (l["st"], l["vv"], _votos(l, numeros["petismo"]), _votos(l, numeros["bolsonarismo"]))

    eventos = {}  # minuto -> {abr: valores} (a última leitura de cada arquivo naquele minuto)
    totais = {}
    for abr, ls in [("br", leituras_br), *leituras_uf.items()]:
        for l in sorted(ls, key=lambda l: l["h"]):
            m = max(_minuto(l["h"], inicio), 0)
            eventos.setdefault(m, {})[abr] = valores(l)
            totais[abr] = l["ts"]
    minutos = sorted(eventos)
    ordem = ["Brasil", *config.REGIOES]
    regioes = {r: {k: [] for k in medidas} for r in ordem}
    atual = {}
    for m in minutos:
        atual.update(eventos[m])
        soma = {r: [0, 0, 0, 0] for r in config.REGIOES}
        for abr, v in atual.items():
            if abr != "br":
                soma[REGIAO_DA_UF[abr]] = [a + b for a, b in zip(soma[REGIAO_DA_UF[abr]], v)]
        brasil = atual.get("br", (0, 0, 0, 0))
        for r in ordem:
            for k, v in zip(medidas, brasil if r == "Brasil" else soma[r]):
                regioes[r][k].append(int(v))
    tot = {r: 0 for r in config.REGIOES}
    for abr, ts in totais.items():
        if abr != "br":
            tot[REGIAO_DA_UF[abr]] += ts
    s = {"t": minutos, "regioes": regioes,
         "totais": {r: {"secoes": totais.get("br", 0) if r == "Brasil" else tot[r],
                        **{k: (regioes[r][k][-1] if minutos else 0) for k in medidas[1:]}} for r in ordem}}
    br = regioes["Brasil"]["secoes"]
    total = s["totais"]["Brasil"]["secoes"]
    t999 = next((t for t, n in zip(minutos, br) if total and n >= 0.999 * total), minutos[-1] if minutos else 0)
    return {"ano": None, "turno": None, "tipo": "ao vivo", "referencia": None, "inicio": f"{inicio:%Y-%m-%dT%H:%M}",
            "viradas": apuracao.viradas(s) if minutos and total else [], "t999": t999, **s}


def _lugar(x):
    """Um lugar do forecast, só com o que o site mostra."""
    return {k: x[k] for k in ("petismo", "inf", "sup", "desvio", "chance", "votos", "vantagem", "apurado")}


class Previsor:
    """O forecast dentro de um coletor: o prior, a chegada de cada seção vista e o histórico do forecast na noite."""

    def __init__(self, prior, inicio, numeros, log=print):
        self.prior, self.inicio, self.numeros, self.log = prior, inicio, numeros, log
        self.chegada = np.full(prior.n, np.inf)
        self.historico = []
        self._mapa = None

    @classmethod
    def carregar(cls, av, agregadas=(), log=print):
        """O prior da noite acompanhada (`config.ao_vivo()`), ou None se faltam as seções do 1º turno."""
        from eleicoes.tratamento import boletins
        arq = boletins.saida("secoes", av.ano, 1)
        if not arq.exists():
            log(f"Sem {arq.relative_to(config.RAIZ).as_posix()}: a coleta segue sem o forecast.")
            return None
        segundo = av.turno == 2
        total, desvio = F.projecao_da_vespera(av.ano) if segundo else (0.5, 2.0)
        prior = F.Prior.criar(F.ler_primeiro_turno(av.ano), total, desvio, segundo_turno=segundo)
        if segundo and agregadas:
            n = prior.agregar_no_segundo_turno(agregadas)
            if n:
                log(f"   forecast: {n} seções do 1º turno agregadas a outras no 2º")
        numeros = {campo: str(n) for n, campo in config.candidatos(av.ano).items()}
        log(f"Forecast: prior de {prior.n:,} seções, projeção da véspera {100 * total:.2f}% (desvio {desvio})."
            .replace(",", "."))
        return cls(prior, av.inicio, numeros, log)

    def chegou(self, secoes):
        """secoes: [(uf, municipio, zona, secao, "dd/mm/aaaa hh:mm:ss")] vistas pela primeira vez."""
        idx = self.prior.indice()
        for uf, mu, zona, ns, recebido in secoes:
            i = idx.get((uf, mu, int(zona), int(ns)))
            if i is not None:
                quando = dt.datetime.strptime(recebido, "%d/%m/%Y %H:%M:%S")
                self.chegada[i] = min(self.chegada[i], (quando - self.inicio).total_seconds() / 60)

    def apurado(self, municipios, leituras_uf):
        """municipios: {(uf, municipio): último registro lido}; leituras_uf: {uf: [leitura]}."""
        p = self.prior
        m = len(p.municipios)
        pt, bo, st = np.zeros(m), np.zeros(m), np.zeros(m, int)
        j = p.indice_municipio()
        for chave, r in municipios.items():
            k = j.get(chave)
            if k is not None:
                pt[k] = r["cand"].get(self.numeros["petismo"], 0)
                bo[k] = r["cand"].get(self.numeros["bolsonarismo"], 0)
                st[k] = r["st"]
        U = len(F.UFS)
        uf = {"petismo": np.zeros(U), "bolsonarismo": np.zeros(U), "secoes": np.zeros(U)}
        for k, u in enumerate(F.UFS):
            ls = leituras_uf.get(u)
            if ls:
                l = max(ls, key=lambda l: l["h"])
                uf["petismo"][k] = _votos(l, self.numeros["petismo"])
                uf["bolsonarismo"][k] = _votos(l, self.numeros["bolsonarismo"])
                uf["secoes"][k] = l["st"]
        return F.Apurado(pt, bo, st, self.chegada.copy(), uf)

    def prever(self, municipios, leituras_uf, tse):
        """O forecast agora (para o dados.json) e, guardado para o mapa.json, o que vai por município."""
        return self.prever_apurado(self.apurado(municipios, leituras_uf), tse)

    def prever_apurado(self, a, tse):
        f = F.prever(self.prior, a)
        self._mapa = (a, f)
        b = f["brasil"]
        atual = {"h": tse["h"] if tse else None, "pst": tse["pst"] if tse else None, "apurado": f["apurado"],
                 "brasil": _lugar(b), "regioes": {k: _lugar(v) for k, v in f["regioes"].items()},
                 "ufs": {k: _lugar(v) for k, v in f["ufs"].items()}}
        if tse and (not self.historico or self.historico[-1]["h"] != tse["h"]):
            self.historico.append({"h": tse["h"], "pst": tse["pst"], "apurado": f["apurado"], "petismo": b["petismo"],
                                   "inf": b["inf"], "sup": b["sup"], "chance": b["chance"], "vinf": b["vantagem"][0],
                                   "vantagem": b["vantagem"][1], "vsup": b["vantagem"][2],
                                   "votos_petismo": b["votos"]["petismo"], "votos_bolsonarismo": b["votos"]["bolsonarismo"]})
        return atual

    def mapa(self):
        """O mapa.json: por município do mapa, o apurado (com o que o total da UF tem a mais, repartido pelas seções
        que chegaram) e o swing e o comparecimento estimados."""
        if self._mapa is None:
            return None
        a, f = self._mapa
        p = self.prior
        m = len(p.municipios)
        pt, bo, st = a.petismo.copy(), a.bolsonarismo.copy(), a.secoes.astype(float).copy()
        extra = f["a_mais"]["secoes"]
        if extra.any():
            q = F._expit(p.logit + f["municipios"]["swing"][p.mun])
            uf_sec = p.uf_mun[p.mun]
            for campo, alvo, peso in (("petismo", pt, p.peso * q), ("bolsonarismo", bo, p.peso * (1 - q))):
                total_uf = np.bincount(uf_sec[extra], peso[extra], len(F.UFS))
                fator = np.divide(f["a_mais"][campo], total_uf, out=np.zeros(len(F.UFS)), where=total_uf > 0)
                alvo += np.bincount(p.mun[extra], peso[extra] * fator[uf_sec[extra]], m)
            st += np.bincount(p.mun[extra], minlength=m)
        codigos = json.loads(MUNICIPIOS_DO_MAPA.read_text("utf-8"))["codigo"]
        do_ibge = {int(c): k for k, c in enumerate(p.ibge) if c}
        linhas = [do_ibge.get(int(c), -1) for c in codigos]
        tem = np.array([k >= 0 for k in linhas])
        k = np.array([max(x, 0) for x in linhas])

        def col(x, casas=0):
            return [None if not ok else round(float(v), casas) if casas else int(round(v))
                    for v, ok in zip(np.asarray(x, float)[k], tem)]
        return {"versao": 1, "h": self.historico[-1]["h"] if self.historico else None, "divisao": p.divisao,
                "municipios": {"secoes": col(st), "total": col(p.secoes_por_municipio), "petismo": col(pt),
                               "bolsonarismo": col(bo), "swing": col(f["municipios"]["swing"], 4),
                               "comparecimento": col(f["municipios"]["comparecimento"], 4)}}


def dados(coletor, job, erro, av, leituras_br, leituras_uf, previsao=None, historico=()):
    """O dados.json de um ramo de coletor."""
    numeros = {campo: str(n) for n, campo in config.candidatos(av.ano).items()}
    br = sorted(leituras_br, key=lambda l: l["h"])
    ultima = br[-1] if br else None
    ufs = {}
    for u, ls in leituras_uf.items():
        if ls:
            l = max(ls, key=lambda l: l["h"])
            ufs[u.upper()] = {"h": l["h"], "st": l["st"], "ts": l["ts"], "vv": l["vv"], "c": l["c"], "a": l["a"],
                              "petismo": _votos(l, numeros["petismo"]), "bolsonarismo": _votos(l, numeros["bolsonarismo"])}
    ap = serie(br, leituras_uf, av.inicio, numeros)
    ap.update(ano=av.ano, turno=av.turno)
    tse = None
    if ultima:
        tse = {k: ultima.get(k) for k in ("h", "pst", "st", "ts", "vv", "c", "a", "and", "tf")}
        tse.update(petismo=_votos(ultima, numeros["petismo"]), bolsonarismo=_votos(ultima, numeros["bolsonarismo"]))
    return {"versao": VERSAO, "coletor": coletor, "job": job, "atualizado": f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S}",
            "erro": erro, "eleicao": av.eleicao, "ano": av.ano, "turno": av.turno, "tse": tse, "apuracao": ap,
            "ufs": ufs, "previsao": previsao, "previsoes": list(historico)}
