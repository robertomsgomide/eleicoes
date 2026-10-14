"""Forecast da apuração do 2º turno: o resultado final previsto a cada momento da noite.

Durante a apuração, o TSE publica quais seções já chegaram e o resultado de cada município; o 1º turno de cada seção
é conhecido. O resultado final é o que já foi contado mais o que as seções que faltam devem dar:

1. Ponto de partida (prior) de cada seção: a distribuição da projeção do 2º turno (`projecao.distribuir`), no total
   projetado para o país na véspera. Com 0% apurado, o forecast é a própria projeção.
2. Quanto cada lugar se afasta desse ponto de partida (o swing, em logit da parte do petismo entre os dois) é aprendido
   com a própria noite, num modelo hierárquico normal: país → região → UF → município → seção. Um município com metade
   das seções apuradas já diz muito sobre a outra metade; um sem nada apurado fica com o swing da sua UF, que, sem
   nada apurado, fica com o da região, e assim por diante. Com o comparecimento (votos dos dois no 2º turno em relação
   aos válidos do 1º turno), o mesmo modelo.
3. A conta é exata para esse modelo (a posterior de uma árvore de normais) e a incerteza do total é analítica: lugares
   do mesmo município, UF ou região se movem juntos.

O menor lugar com resultado publicado durante a noite é o município: quais seções entram no resultado dele vem da
ordem de chegada (as `secoes` totalizadas que o arquivo do município informa são as primeiras a chegar).

A "parte" é a do petismo entre os dois campos, que no 2º turno são os votos válidos. Num ensaio com uma noite de 1º
turno, o prior é o próprio 1º turno (`Prior.criar(..., segundo_turno=False)`): serve para conferir a coleta, não a
previsão. Validação em 2018 e 2022 e os desvios usados: `forecast_validacao.py` e docs/validacao_forecast.md. Lá também
está a variante com o swing de cada seção acompanhando atributos do 1º turno (`prever(..., atributos=True)`), que não
ganhou do modelo simples e fica desligada.
"""
import dataclasses
import json
import math

import numpy as np

from eleicoes import config
from eleicoes.modelos import projecao

Z80 = projecao.Z80
REGIOES = list(config.REGIOES)
UFS = [uf.lower() for ufs in config.REGIOES.values() for uf in ufs]  # o site do TSE usa minúsculas


@dataclasses.dataclass(frozen=True)
class Desvios:
    """Desvios do modelo, em logit: o swing (parte do petismo entre os dois) e o comparecimento (log da razão entre os
    votos dos dois no 2º turno e os válidos do 1º).

    - região, UF, município e seção: quanto o swing de cada um se afasta do swing do nível de cima. Varia mais quanto
      mais votos os outros candidatos tiveram no 1º turno: são eles que se dividem de um jeito diferente do esperado.
      Medidos com o resultado verdadeiro (`forecast_validacao`), os de região, UF e município foram proporcionais à
      parte dos outros no país (25% em 2018, 8% em 2022); a seção tem também o ruído de uma amostra de poucas centenas
      de votos;
    - ordem: o que falta apurar não vota exatamente como o que já foi apurado, mesmo descontado o 1º turno de cada
      seção (em 2022, a parte de cada cidade que chegou por último pendeu um pouco mais para o bolsonarismo). Um
      desvio comum a tudo o que falta no país, um a tudo o que falta em cada UF e um ao que falta em cada município já
      em parte apurado.
    `para(outros)` dá os desvios de uma eleição; os coeficientes e pisos foram conferidos refazendo 2018 e 2022."""
    regiao: float
    uf: float
    municipio: float
    secao: float
    ordem: float = 0.0
    ordem_uf: float = 0.0
    ordem_mun: float = 0.0
    c_pais: float = 0.03
    c_regiao: float = 0.03
    c_uf: float = 0.03
    c_municipio: float = 0.04
    c_secao: float = 0.06

    @classmethod
    def para(cls, outros, escala=1.0):
        """outros: a fração dos votos válidos do 1º turno que foi para os outros candidatos, no país."""
        def d(k):
            return escala * (math.hypot(PISO[k], POR_OUTROS[k] * outros) if k == "secao"
                             else max(POR_OUTROS[k] * outros, PISO[k]))
        return cls(**{k: d(k) for k in POR_OUTROS})


# desvio por fração dos outros candidatos no 1º turno, e o mínimo de cada um
POR_OUTROS = {"regiao": 0.30, "uf": 0.40, "municipio": 0.40, "secao": 0.70, "ordem": 0.15, "ordem_uf": 0.25,
              "ordem_mun": 0.25}
PISO = {"regiao": 0.0, "uf": 0.0, "municipio": 0.0, "secao": 0.10, "ordem": 0.01, "ordem_uf": 0.015, "ordem_mun": 0.015}
ATRIBUTOS = ("outros", "inclinacao", "comparecimento")  # o swing por atributos usa estes, centrados e padronizados
RIDGE = 4.0  # força da priori (normal, em torno de 0) dos coeficientes dos atributos, em unidades de 1/desvio²


def _logit(p):
    return np.log(p / (1 - p))


def _expit(x):
    return 1 / (1 + np.exp(-x))


def _normal(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# ---- Ponto de partida -----------------------------------------------------------------------------------------

@dataclasses.dataclass
class Prior:
    """O ponto de partida de cada seção da noite, em arrays alinhados (seções em ordem de UF, município, zona, seção).

    Grupos: `mun` (índice do município de cada seção), `uf_mun` (UF de cada município), `reg_uf` (região de cada UF).
    """
    uf: np.ndarray            # sigla minúscula, como no site do TSE ("sp", "zz")
    municipio: np.ndarray     # código do TSE (5 dígitos)
    zona: np.ndarray          # int
    secao: np.ndarray         # int
    peso: np.ndarray          # votos válidos do 1º turno (ensaio de 1º turno: os dos dois campos)
    logit: np.ndarray         # logit da parte esperada do petismo entre os dois
    ordem: np.ndarray         # minutos de chegada do boletim no 1º turno: desempate e ordem de reserva
    atributos: np.ndarray     # (seções × len(ATRIBUTOS)), centrados e padronizados
    mun: np.ndarray
    municipios: list          # [(uf, municipio)]
    ibge: np.ndarray          # código do IBGE de cada município (0 no exterior)
    uf_mun: np.ndarray
    reg_uf: np.ndarray
    total: float              # parte do petismo no país que o prior soma (fração)
    desvio: float             # desvio da projeção na véspera, em pontos percentuais
    outros: float             # parte dos outros candidatos nos válidos do 1º turno, no país (fração)
    divisao: dict             # como os votos dos outros se dividem (para o mapa refazer a conta por local de votação)

    @property
    def n(self):
        return len(self.peso)

    @property
    def secoes_por_municipio(self):
        return np.bincount(self.mun, minlength=len(self.municipios))

    def indice(self):
        """{(uf, municipio, zona, secao): linha}; zona e seção como inteiros."""
        if not hasattr(self, "_indice"):
            self._indice = {k: i for i, k in enumerate(zip(self.uf.tolist(), self.municipio.tolist(),
                                                              self.zona.tolist(), self.secao.tolist()))}
        return self._indice

    def indice_municipio(self):
        if not hasattr(self, "_indice_mun"):
            self._indice_mun = {k: j for j, k in enumerate(self.municipios)}
        return self._indice_mun

    @classmethod
    def criar(cls, t1, total, desvio, segundo_turno=True):
        """Prior a partir das seções do 1º turno (`ler_primeiro_turno`) e da projeção do país na véspera (total, em
        fração; desvio, em pontos percentuais)."""
        ordem = np.lexsort((t1["secao"], t1["zona"], t1["municipio"], t1["uf"]))
        t = {k: np.asarray(v)[ordem] for k, v in t1.items()}
        pt, bo, ou = (t[c].astype(float) for c in ("petismo", "bolsonarismo", "outros"))
        validos = pt + bo + ou
        ok = validos > 0
        p = np.full(len(pt), 0.5)
        divisao = {"inclinacao": projecao.INCLINACAO, "a": 0.0, "deslocamento": 0.0}
        if segundo_turno:
            s = projecao.Secoes(uf=t["uf"][ok], regiao=t["regiao"][ok], municipio=t["municipio"][ok],
                                petismo=pt[ok], bolsonarismo=bo[ok], outros=ou[ok])
            a, deslocamento = projecao.ajuste(s, total)
            p[ok] = projecao.distribuir(s, total)
            divisao.update(a=round(float(a), 6), deslocamento=round(float(deslocamento), 6))
            peso = validos
        else:
            p = (pt + 0.5) / (pt + bo + 1)
            peso = pt + bo
            total = float(pt.sum() / max(pt.sum() + bo.sum(), 1))
        p = np.clip(p, 1e-4, 1 - 1e-4)

        uf = np.char.lower(t["uf"].astype(str))
        chaves = list(zip(uf.tolist(), t["municipio"].tolist()))
        municipios = list(dict.fromkeys(chaves))
        j = {k: i for i, k in enumerate(municipios)}
        mun = np.fromiter((j[k] for k in chaves), int, len(chaves))
        ibge = np.zeros(len(municipios), int)
        ibge[mun] = np.nan_to_num(t["ibge"].astype(float)).astype(int)
        ufs_idx = {u: i for i, u in enumerate(UFS)}
        uf_mun = np.array([ufs_idx[u] for u, _ in municipios], int)
        reg_uf = np.array([REGIOES.index(config.REGIAO_DA_UF[u.upper()]) for u in UFS], int)

        # atributos de cada seção para o swing por atributos: os outros candidatos, a inclinação e o comparecimento
        compar = np.divide(t["comparecimento"].astype(float), t["aptos"].astype(float),
                           out=np.full(len(pt), np.nan), where=t["aptos"] > 0)
        cru = np.column_stack([np.divide(ou, validos, out=np.zeros_like(ou), where=ok),
                               _logit((pt + 0.5) / (pt + bo + 1)), compar])
        atributos = np.zeros_like(cru)
        for k in range(cru.shape[1]):
            x, bom = cru[:, k], np.isfinite(cru[:, k]) & (peso > 0)
            media = np.average(x[bom], weights=peso[bom])
            dp = math.sqrt(np.average((x[bom] - media) ** 2, weights=peso[bom])) or 1.0
            atributos[:, k] = np.where(np.isfinite(x), (x - media) / dp, 0.0)

        return cls(uf=uf, municipio=t["municipio"].astype(str), zona=t["zona"].astype(int),
                   secao=t["secao"].astype(int), peso=peso, logit=_logit(p),
                   ordem=np.nan_to_num(t["chegada"].astype(float), nan=1e9), atributos=atributos,
                   mun=mun, municipios=municipios, ibge=ibge, uf_mun=uf_mun, reg_uf=reg_uf,
                   total=float(total), desvio=float(desvio), outros=float(ou.sum() / max(validos.sum(), 1)),
                   divisao=divisao)

    def agregar_no_segundo_turno(self, agregadas):
        """Seções do 1º turno que viram agregadas no 2º (votam na urna de outra e não têm boletim próprio): o peso e a
        parte esperada delas passam para a seção principal, e elas saem do prior. agregadas: [(uf, municipio, zona,
        secao, principal)], como no -cs.json do 2º turno. Em 13/10/2026, o -cs.json do 2º turno trazia as mesmas
        agregações do 1º (já somadas no boletim da principal): isto só muda algo se o TSE agregar seções de novo.
        Devolve quantas seções saíram."""
        idx = self.indice()
        q = _expit(self.logit)
        sai = np.zeros(self.n, bool)
        for uf, mu, zona, ns, nsp in agregadas:
            i, k = idx.get((uf, mu, int(zona), int(ns))), idx.get((uf, mu, int(zona), int(nsp)))
            if i is None or k is None or i == k or sai[i] or sai[k]:
                continue
            votos = self.peso[i] * q[i] + self.peso[k] * q[k]
            self.peso[k] += self.peso[i]
            if self.peso[k] > 0:
                q[k] = votos / self.peso[k]
            sai[i] = True
        if sai.any():
            fica = ~sai
            self.logit = _logit(np.clip(q, 1e-4, 1 - 1e-4))
            for campo in ("uf", "municipio", "zona", "secao", "peso", "logit", "ordem", "atributos", "mun"):
                setattr(self, campo, getattr(self, campo)[fica])
            for cache in ("_indice",):
                self.__dict__.pop(cache, None)
        return int(sai.sum())


def ler_primeiro_turno(ano):
    """As seções do 1º turno de um ano (boletins de urna, em dados/processado), como arrays para `Prior.criar`."""
    import duckdb
    from eleicoes.tratamento import boletins
    arq = boletins.saida("secoes", ano, 1)
    inicio = config.inicio_divulgacao(ano, 1)
    d = duckdb.connect().execute(f"""
        SELECT sg_uf AS uf, regiao, cd_municipio AS municipio, cd_ibge AS ibge, nr_zona AS zona, nr_secao AS secao,
               votos_petismo AS petismo, votos_bolsonarismo AS bolsonarismo, votos_outros AS outros,
               qt_aptos AS aptos, qt_comparecimento AS comparecimento,
               (epoch(dt_bu_recebido) - epoch(TIMESTAMP '{inicio:%Y-%m-%d %H:%M:%S}')) / 60 AS chegada
        FROM '{arq.as_posix()}'""").fetchnumpy()
    return {k: _sem_mascara(v) for k, v in d.items()}


def _sem_mascara(v):
    """Coluna do duckdb sem a máscara de nulos: nan nos números, "" nos textos."""
    if not hasattr(v, "filled"):
        return np.asarray(v)
    if v.dtype.kind in "iuf":
        return v.astype(float).filled(np.nan)
    return v.filled("")


def projecao_da_vespera(ano, arquivo=None):
    """(total em fração, desvio em pontos) da projeção do 2º turno mais recente do ano, a do site."""
    arquivo = arquivo or projecao.SITE
    a = json.loads(arquivo.read_text("utf-8"))["anos"][str(ano)]["atual"]
    return a["petismo"] / 100, a["desvio"]


# ---- O que se sabe num momento ---------------------------------------------------------------------------------

@dataclasses.dataclass
class Apurado:
    """O que se sabe num momento, por município (na ordem de `Prior.municipios`): os votos dos dois e as seções
    totalizadas, pelo último resultado lido de cada município; por seção, quando o boletim chegou (minutos; inf se
    ainda não chegou); e, se houver, o total oficial de cada UF (na ordem de UFS), lido a cada minuto e por isso mais
    novo que o dos municípios: {"petismo", "bolsonarismo", "secoes"}."""
    petismo: np.ndarray
    bolsonarismo: np.ndarray
    secoes: np.ndarray
    chegada: np.ndarray
    uf: dict = None

    @classmethod
    def vazio(cls, prior):
        m = len(prior.municipios)
        return cls(np.zeros(m), np.zeros(m), np.zeros(m, int), np.full(prior.n, np.inf))


def contadas(prior, apurado):
    """As seções que entram no resultado lido de cada município: as primeiras `secoes` dele a chegar."""
    chave = np.lexsort((prior.ordem, apurado.chegada, prior.mun))
    inicio = np.concatenate([[0], np.cumsum(prior.secoes_por_municipio)[:-1]])
    pos = np.empty(prior.n, int)
    pos[chave] = np.arange(prior.n)
    return pos - inicio[prior.mun] < apurado.secoes[prior.mun]


def a_mais_nas_ufs(prior, apurado, contado):
    """O que o total oficial de cada UF tem a mais que a soma dos municípios lidos: (seções, votos do petismo, votos do
    bolsonarismo), as seções sendo as primeiras a chegar entre as que ainda não estão no resultado lido do município."""
    U = len(UFS)
    if apurado.uf is None:
        return np.zeros(prior.n, bool), np.zeros(U), np.zeros(U)
    uf_sec = prior.uf_mun[prior.mun]
    soma = lambda x: np.bincount(prior.uf_mun, x, U)  # noqa: E731
    faltam = np.maximum(np.asarray(apurado.uf["secoes"], float) - soma(apurado.secoes), 0)
    PE = np.where(faltam > 0, np.maximum(np.asarray(apurado.uf["petismo"], float) - soma(apurado.petismo), 0), 0)
    BE = np.where(faltam > 0, np.maximum(np.asarray(apurado.uf["bolsonarismo"], float) - soma(apurado.bolsonarismo), 0), 0)
    chave = np.lexsort((prior.ordem, apurado.chegada, uf_sec))
    livre = ~contado[chave]
    u = uf_sec[chave]
    cs = np.cumsum(livre)
    antes = np.concatenate([[0], cs])[np.searchsorted(u, np.arange(U))]
    extra = np.zeros(prior.n, bool)
    extra[chave] = livre & (cs - antes[u] - 1 < faltam[u])
    sem = np.bincount(uf_sec[extra], minlength=U) == 0
    return extra, np.where(sem, 0, PE), np.where(sem, 0, BE)


# ---- O modelo hierárquico ---------------------------------------------------------------------------------------

def deslocamento(L, w, g, G, alvo, tem=None):
    """Deslocamento (logit) de cada grupo que faz as seções dele, com pesos w, somarem a parte `alvo`.
    Devolve (deslocamento, número efetivo de seções); nan nos grupos sem dados."""
    W = np.bincount(g, w, G)
    tem = (W > 0) if tem is None else tem & (W > 0)
    d = np.zeros(G)
    for _ in range(30):
        q = _expit(L + d[g])
        f = np.bincount(g, w * q, G) / np.where(tem, W, 1)
        fl = np.bincount(g, w * q * (1 - q), G) / np.where(tem, W, 1)
        d = np.clip(d - np.where(tem, (f - alvo) / np.maximum(fl, 1e-9), 0), -8, 8)
    q = _expit(L + d[g])
    gw = w * q * (1 - q)
    n_ef = np.bincount(g, gw, G) ** 2 / np.maximum(np.bincount(g, gw * gw, G), 1e-12)
    return np.where(tem, d, np.nan), np.where(tem, n_ef, 0.0)


def _swing_observado(prior, deslocado, contado, alvo, peso_obs):
    """Swing (logit) de cada município: o deslocamento do prior que faz as seções contadas dele somarem a parte do
    petismo observada."""
    return deslocamento(deslocado[contado], prior.peso[contado], prior.mun[contado], len(prior.municipios), alvo,
                        peso_obs > 0)


@dataclasses.dataclass
class Arvore:
    """Posterior de um efeito em quatro níveis (país → região → UF → município), dados os valores observados em cada
    município (d, com variância de amostragem s2). Normal em cada nível; a conta é exata (mensagens de baixo para
    cima, médias de cima para baixo)."""
    media_pais: float
    prec_pais: float
    a: np.ndarray       # precisão de cada região dado o país
    b: np.ndarray       # de cada UF dada a região
    c: np.ndarray       # de cada município dada a UF
    media_reg: np.ndarray
    media_uf: np.ndarray
    media_mun: np.ndarray
    taus: tuple         # (região, UF, município)

    @classmethod
    def ajustar(cls, d, s2, mun_uf, reg_uf, taus, tau_pais, media_priori=0.0, extra_uf=None):
        """extra_uf: (valor, variância) observados diretamente em cada UF (as seções do total oficial dela que ainda
        não estão em nenhum resultado de município lido), ou None."""
        tr, tu, tm = taus
        tem = np.isfinite(d) & (s2 > 0)
        d0 = np.where(tem, d, 0.0)
        w_m = np.where(tem, 1 / (tm ** 2 + np.where(tem, s2, 1)), 0.0)
        U, R = len(reg_uf), int(reg_uf.max()) + 1
        P_u = np.bincount(mun_uf, w_m, U)
        S_u = np.bincount(mun_uf, w_m * d0, U)
        if extra_uf is not None:
            de, ve = extra_uf
            ok = np.isfinite(de) & (ve > 0)
            P_u = P_u + np.where(ok, 1 / np.where(ok, ve, 1), 0.0)
            S_u = S_u + np.where(ok, np.where(ok, de, 0.0) / np.where(ok, ve, 1), 0.0)
        tem_u = P_u > 0
        w_u = np.where(tem_u, 1 / (tu ** 2 + 1 / np.where(tem_u, P_u, 1)), 0.0)
        D_u = S_u / np.where(tem_u, P_u, 1)
        P_r = np.bincount(reg_uf, w_u, R)
        S_r = np.bincount(reg_uf, w_u * D_u, R)
        tem_r = P_r > 0
        w_r = np.where(tem_r, 1 / (tr ** 2 + 1 / np.where(tem_r, P_r, 1)), 0.0)
        D_r = S_r / np.where(tem_r, P_r, 1)
        prec_pais = 1 / tau_pais ** 2 + w_r.sum()
        media_pais = (media_priori / tau_pais ** 2 + (w_r * D_r).sum()) / prec_pais
        a = 1 / tr ** 2 + P_r
        b = 1 / tu ** 2 + P_u
        c = 1 / tm ** 2 + np.where(tem, 1 / np.where(tem, s2, 1), 0.0)
        media_reg = (media_pais / tr ** 2 + S_r) / a
        media_uf = (media_reg[reg_uf] / tu ** 2 + S_u) / b
        media_mun = (media_uf[mun_uf] / tm ** 2 + np.where(tem, d0 / np.where(tem, s2, 1), 0.0)) / c
        return cls(media_pais, prec_pais, a, b, c, media_reg, media_uf, media_mun, taus)

    def variancias(self, k, mun_uf, reg_uf, grupos):
        """Variância de Σ k_m·(efeito_m − média_m) em cada grupo de municípios (grupos: índice do grupo de cada
        município, ou -1 para nenhum), a partir da decomposição do sorteio de cima para baixo em normais independentes.

        k pode ter duas colunas (k1, k2): devolve a covariância entre as duas somas."""
        tr, tu, tm = self.taus
        k = np.atleast_2d(np.asarray(k, float).T).T if np.ndim(k) == 1 else np.asarray(k, float)
        alfa = (1 / tm ** 2) / self.c                     # quanto o município herda da UF
        beta = (1 / tu ** 2) / self.b                     # a UF, da região
        gama = (1 / tr ** 2) / self.a                     # a região, do país
        G = int(grupos.max()) + 1 if (grupos >= 0).any() else 0
        ok = grupos >= 0
        U, R = len(self.b), len(self.a)
        out = np.zeros((G, k.shape[1], k.shape[1]))
        # município: k_m / √c_m
        cm = k / np.sqrt(self.c)[:, None]
        # UF: Σ_m k_m α_m, dentro de cada grupo
        km_a = k * alfa[:, None]
        # chaves (grupo, UF) e (grupo, região)
        gu = grupos * U + mun_uf
        gr = grupos * R + reg_uf[mun_uf]
        for x in range(k.shape[1]):
            for y in range(x, k.shape[1]):
                v = np.bincount(grupos[ok], cm[ok, x] * cm[ok, y], G)
                Kx = np.bincount(gu[ok], km_a[ok, x], G * U).reshape(G, U)
                Ky = np.bincount(gu[ok], km_a[ok, y], G * U).reshape(G, U)
                v += (Kx * Ky / self.b[None, :]).sum(1)
                Gx = np.zeros((G, R))
                Gy = np.zeros((G, R))
                np.add.at(Gx, (np.repeat(np.arange(G), U), np.tile(reg_uf, G)), (Kx * beta[None, :]).ravel())
                np.add.at(Gy, (np.repeat(np.arange(G), U), np.tile(reg_uf, G)), (Ky * beta[None, :]).ravel())
                v += (Gx * Gy / self.a[None, :]).sum(1)
                Hx, Hy = (Gx * gama[None, :]).sum(1), (Gy * gama[None, :]).sum(1)
                v += Hx * Hy / self.prec_pais
                out[:, x, y] = out[:, y, x] = v
        return out

    def sortear(self, n, mun_uf, reg_uf, rng):
        """n sorteios do efeito de cada município (n × municípios), da posterior exata."""
        tr, tu, tm = self.taus
        pais = self.media_pais + rng.standard_normal(n) / math.sqrt(self.prec_pais)
        S_r = self.media_reg * self.a - self.media_pais / tr ** 2
        reg = (pais[:, None] / tr ** 2 + S_r) / self.a + rng.standard_normal((n, len(self.a))) / np.sqrt(self.a)
        S_u = self.media_uf * self.b - self.media_reg[reg_uf] / tu ** 2
        uf = (reg[:, reg_uf] / tu ** 2 + S_u) / self.b + rng.standard_normal((n, len(self.b))) / np.sqrt(self.b)
        S_m = self.media_mun * self.c - self.media_uf[mun_uf] / tm ** 2
        return (uf[:, mun_uf] / tm ** 2 + S_m) / self.c + rng.standard_normal((n, len(self.c))) / np.sqrt(self.c)


def _beta_atributos(prior, contado, d, s2, tau_m):
    """Coeficientes dos atributos no swing (mínimos quadrados ponderados com priori normal em 0), com os municípios
    apurados: a média de cada atributo nas seções contadas de cada um explica o swing observado dele."""
    m = len(prior.municipios)
    tem = np.isfinite(d) & (s2 > 0)
    if tem.sum() < 30:
        return np.zeros(prior.atributos.shape[1])
    w = prior.peso[contado]
    W = np.bincount(prior.mun[contado], w, m)
    X = np.column_stack([np.bincount(prior.mun[contado], w * prior.atributos[contado, k], m) / np.where(W > 0, W, 1)
                         for k in range(prior.atributos.shape[1])])[tem]
    # efeitos fixos de UF, para os atributos não aprenderem diferenças entre lugares (isso é da árvore)
    uf = prior.uf_mun[tem]
    peso = 1 / (tau_m ** 2 + s2[tem])
    y = d[tem]
    for u in np.unique(uf):
        e = uf == u
        y = y - np.where(e, np.average(y[e], weights=peso[e]), 0)
        X = X - np.where(e[:, None], np.average(X[e], axis=0, weights=peso[e]), 0)
    A = X.T @ (X * peso[:, None]) + RIDGE * np.eye(X.shape[1])
    return np.linalg.solve(A, X.T @ (peso * y))


def prever(prior, apurado, desvios=None, atributos=False):
    """O resultado final previsto, com o que se sabe agora (`apurado`).

    Devolve {"apurado", "contado", "brasil", "regioes", "ufs", "municipios"}: em cada lugar, a parte prevista do
    petismo entre os dois (%, com o intervalo de 80% e a chance de passar de 50%), os votos previstos de cada um e a
    vantagem; em "municipios", o swing e o comparecimento estimados de cada município (para o mapa).
    """
    dv = desvios or Desvios.para(prior.outros)
    m = len(prior.municipios)
    contado = contadas(prior, apurado)
    P, B = np.asarray(apurado.petismo, float), np.asarray(apurado.bolsonarismo, float)
    V = P + B
    alvo = (P + 0.5) / (V + 1)

    # coeficientes dos atributos (opcional) e o swing observado em cada município
    beta = np.zeros(prior.atributos.shape[1])
    d, n_ef = _swing_observado(prior, prior.logit, contado, alvo, V)
    if atributos:
        beta = _beta_atributos(prior, contado, d, np.where(n_ef > 0, dv.secao ** 2 / np.maximum(n_ef, 1e-9), 0), dv.municipio)
        if beta.any():
            d, n_ef = _swing_observado(prior, prior.logit + prior.atributos @ beta, contado, alvo, V)
    s2 = np.where(n_ef > 0, dv.secao ** 2 / np.maximum(n_ef, 1e-9), 0.0)

    # comparecimento: log(votos dos dois no 2º turno / válidos do 1º turno) nas seções contadas
    W1 = np.bincount(prior.mun[contado], prior.peso[contado], m)
    W2 = np.bincount(prior.mun[contado], prior.peso[contado] ** 2, m)
    temc = (W1 > 0) & (V > 0)
    r = np.where(temc, np.log(np.where(temc, V, 1) / np.where(temc, W1, 1)), np.nan)
    s2c = np.where(temc, dv.c_secao ** 2 * W2 / np.where(temc, W1, 1) ** 2, 0.0)

    # o que o total oficial de cada UF tem a mais que os municípios lidos: observado direto na UF, como uma mistura
    # dos municípios de onde as seções vêm
    U = len(UFS)
    extra, PE, BE = a_mais_nas_ufs(prior, apurado, contado)
    uf_sec = prior.uf_mun[prior.mun]
    extra_sw = extra_co = None
    if extra.any():
        L0 = prior.logit + prior.atributos @ beta
        dE, nE = deslocamento(L0[extra], prior.peso[extra], uf_sec[extra], U, (PE + 0.5) / (PE + BE + 1), PE + BE > 0)
        WE = np.bincount(uf_sec[extra], prior.peso[extra], U)
        Wm = np.bincount(prior.mun[extra], prior.peso[extra], m)
        mistura = np.bincount(prior.uf_mun, Wm ** 2, U) / np.maximum(WE, 1e-9) ** 2
        extra_sw = (dE, np.where(nE > 0, dv.secao ** 2 / np.maximum(nE, 1e-9) + dv.municipio ** 2 * mistura, 0.0))
        WE2 = np.bincount(uf_sec[extra], prior.peso[extra] ** 2, U)
        okE = (WE > 0) & (PE + BE > 0)
        rE = np.where(okE, np.log(np.where(okE, PE + BE, 1) / np.where(okE, WE, 1)), np.nan)
        extra_co = (rE, np.where(okE, dv.c_secao ** 2 * WE2 / np.where(okE, WE, 1) ** 2 + dv.c_municipio ** 2 * mistura,
                                 0.0))

    # o país: o swing a priori vem da incerteza da projeção (a variância das regiões, UFs e municípios já soma uma
    # parte dela); o comparecimento, de quanto ele costuma mudar entre os turnos
    q0 = _expit(prior.logit)
    proj = prior.desvio / 100 / max(np.average(q0 * (1 - q0), weights=prior.peso), 0.01)  # pontos → logit
    w_reg = np.bincount(prior.reg_uf[prior.uf_mun[prior.mun]], prior.peso, len(REGIOES)) / prior.peso.sum()
    w_uf = np.bincount(prior.uf_mun[prior.mun], prior.peso, len(UFS)) / prior.peso.sum()
    w_mun = np.bincount(prior.mun, prior.peso, m) / prior.peso.sum()
    resto = (w_reg ** 2).sum() * dv.regiao ** 2 + (w_uf ** 2).sum() * dv.uf ** 2 + (w_mun ** 2).sum() * dv.municipio ** 2
    tau_pais = math.sqrt(max(proj ** 2 - resto, (0.25 * proj) ** 2))
    sw = Arvore.ajustar(d, s2, prior.uf_mun, prior.reg_uf, (dv.regiao, dv.uf, dv.municipio), tau_pais,
                        extra_uf=extra_sw)
    co = Arvore.ajustar(r, s2c, prior.uf_mun, prior.reg_uf, (dv.c_regiao, dv.c_uf, dv.c_municipio), dv.c_pais,
                        extra_uf=extra_co)

    # o que falta em cada município, no swing e no comparecimento estimados
    falta = ~contado & ~extra & (prior.peso > 0)
    L = prior.logit + prior.atributos @ beta + sw.media_mun[prior.mun]
    q = _expit(L)
    Vf = prior.peso * np.exp(co.media_mun[prior.mun])
    g = q * (1 - q)
    fm = prior.mun[falta]
    soma = lambda x: np.bincount(fm, x[falta], m)  # noqa: E731
    RP, RV, Rd = soma(Vf * q), soma(Vf), soma(Vf * g)          # votos do petismo, dos dois, e a derivada no swing
    ruido_p = dv.secao ** 2 * soma((Vf * g) ** 2)              # seção a seção, independente
    parcial = np.bincount(prior.mun[contado | extra], minlength=m) > 0
    ordem_mun = dv.ordem_mun ** 2 * np.where(parcial, Rd, 0.0) ** 2  # o que falta num município já em parte apurado
    ruido_v, ruido_pv, ruido_pp = (dv.c_secao ** 2 * soma(x) for x in (Vf ** 2, q * Vf ** 2, q * q * Vf ** 2))

    # lugares: Brasil, regiões e UFs
    reg_mun = prior.reg_uf[prior.uf_mun]
    lugares = [("brasil", None, np.zeros(m, int), np.zeros(U, int)),
               ("regioes", REGIOES, reg_mun, prior.reg_uf), ("ufs", [u.upper() for u in UFS], prior.uf_mun, np.arange(U))]
    n_extra = np.bincount(uf_sec[extra], minlength=U)
    total_secoes = max(int(prior.secoes_por_municipio.sum()), 1)
    out = {"apurado": round(100 * float(apurado.secoes.sum() + n_extra.sum()) / total_secoes, 3),
           "contado": {"petismo": int(P.sum() + PE.sum()), "bolsonarismo": int(B.sum() + BE.sum())}}
    for chave, nomes, grupos, grupos_uf in lugares:
        G = int(grupos.max()) + 1
        vs = sw.variancias(Rd, prior.uf_mun, prior.reg_uf, grupos)[:, 0, 0]
        vc = co.variancias(np.column_stack([RP, RV]), prior.uf_mun, prior.reg_uf, grupos)
        X0 = np.bincount(grupos, RP, G)
        Y0 = np.bincount(grupos, RV, G)
        # o que falta pode pender diferente do que já foi apurado: em comum no país e em cada UF
        Rd_g = np.bincount(grupos, Rd, G)
        Rd_gu = np.bincount(grupos * len(UFS) + prior.uf_mun, Rd, G * len(UFS)).reshape(G, len(UFS))
        ordem = dv.ordem ** 2 * Rd_g ** 2 + dv.ordem_uf ** 2 * (Rd_gu ** 2).sum(1)
        varX = vs + ordem + vc[:, 0, 0] + np.bincount(grupos, ruido_p + ruido_pp + ordem_mun, G)
        varY = vc[:, 1, 1] + np.bincount(grupos, ruido_v, G)
        cov = vc[:, 0, 1] + np.bincount(grupos, ruido_pv, G)
        Pc = np.bincount(grupos, P, G) + np.bincount(grupos_uf, PE, G)
        Vc = np.bincount(grupos, V, G) + np.bincount(grupos_uf, PE + BE, G)
        stg = np.bincount(grupos, apurado.secoes, G) + np.bincount(grupos_uf, n_extra, G)
        tsg = np.bincount(grupos, prior.secoes_por_municipio, G)
        res = {}
        for k in range(G):
            p_fin, v_fin = Pc[k] + X0[k], Vc[k] + Y0[k]
            if v_fin <= 0:
                continue
            s = p_fin / v_fin
            var_s = max(varX[k] / v_fin ** 2 + p_fin ** 2 * varY[k] / v_fin ** 4 - 2 * p_fin * cov[k] / v_fin ** 3, 0.0)
            var_vant = max(4 * varX[k] + varY[k] - 4 * cov[k], 0.0)
            sd, sdv = math.sqrt(var_s), math.sqrt(var_vant)
            vant = 2 * p_fin - v_fin
            res[k] = {"petismo": round(100 * s, 3), "inf": round(100 * (s - Z80 * sd), 3),
                      "sup": round(100 * (s + Z80 * sd), 3), "desvio": round(100 * sd, 3),
                      "chance": round(1 - _normal((0.5 - s) / sd), 4) if sd > 0 else float(s > 0.5),
                      "votos": {"petismo": round(p_fin), "bolsonarismo": round(v_fin - p_fin)},
                      "vantagem": [round(vant - Z80 * sdv), round(vant), round(vant + Z80 * sdv)],
                      "apurado": round(100 * stg[k] / max(tsg[k], 1), 3)}
        out[chave] = res[0] if nomes is None else {nomes[k]: v for k, v in res.items()}
    out["municipios"] = {"swing": sw.media_mun + 0.0, "comparecimento": co.media_mun + 0.0}
    out["a_mais"] = {"secoes": extra, "petismo": PE, "bolsonarismo": BE}
    out["atributos"] = dict(zip(ATRIBUTOS, np.round(beta, 4).tolist()))
    return out
