"""Validação do forecast da apuração (`forecast.py`): as noites do 2º turno de 2018 e 2022 refeitas seção a seção, só
com o que se sabia em cada momento, em várias ordens de chegada: `uv run eleicoes forecast`.

- `noite(ano)`: o prior (o 1º turno e a projeção da véspera daquele ano) e o 2º turno verdadeiro de cada seção, com a
  hora de chegada do boletim (2022: exata; 2018: estimada como no site, pelos atrasos de cada zona em 2022);
- `Leituras`: quando o coletor teria lido o resultado de cada município, com as regras do coletor.py (no máximo
  LIMITE_MUN municípios por minuto, os mais atrasados primeiro, cada um no máximo a cada 3 min), e o resultado do
  município só com as seções totalizadas, 2 min depois da chegada (a mediana medida no 1º turno de 2026);
- `estimar_desvios`: o desvio de cada nível do modelo, medido com o resultado verdadeiro;
- `validar`: erros e cobertura da faixa de 80% por % apurado, em cada ordem de chegada, com e sem o swing por
  atributos;
- `gravar`: docs/validacao_forecast.md e site/src/data/forecast.json (a noite de 2022 refeita minuto a minuto, para a
  página de 2022 e a Metodologia, e o resumo da validação).
"""
import dataclasses
import datetime as dt
import json
import math

import numpy as np

from eleicoes import config
from eleicoes.ao_vivo import coletor
from eleicoes.modelos import forecast as F
from eleicoes.modelos import projecao

ANOS = (2018, 2022)
ATRASO_TOTALIZACAO = 2  # min entre a chegada do boletim e a totalização (mediana no 1º turno de 2026)
MARCOS = (0.5, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98)  # % das seções que já chegaram
SITE = config.RAIZ / "site" / "src" / "data" / "forecast.json"
RELATORIO = config.RAIZ / "docs" / "validacao_forecast.md"


@dataclasses.dataclass
class Noite:
    """Uma noite de 2º turno já apurada, alinhada ao prior: o resultado verdadeiro e a chegada de cada seção."""
    ano: int
    prior: F.Prior
    petismo: np.ndarray
    bolsonarismo: np.ndarray
    chegada: np.ndarray       # minutos desde o início da divulgação do 2º turno
    chegada_t1: np.ndarray    # a ordem do 1º turno (minutos desde o início da divulgação dele)
    inicio: dt.datetime

    @property
    def real(self):
        return 100 * self.petismo.sum() / (self.petismo.sum() + self.bolsonarismo.sum())

    def real_por(self, grupos, G):
        p, v = np.bincount(grupos, self.petismo, G), np.bincount(grupos, self.petismo + self.bolsonarismo, G)
        return 100 * p / np.where(v > 0, v, 1)


def noite(ano):
    import duckdb
    from eleicoes.analises import apuracao
    from eleicoes.tratamento import boletins
    total, desvio = F.projecao_da_vespera(ano)
    prior = F.Prior.criar(F.ler_primeiro_turno(ano), total, desvio)
    con = duckdb.connect()
    inicio = config.inicio_divulgacao(ano, 2)
    arq = boletins.saida("secoes", ano, 2).as_posix()
    if apuracao.tem_chegada_exata(ano, 2):
        chegada = "s.dt_bu_recebido"
        fonte = f"'{arq}' s"
    else:  # 2018: a chegada estimada do site
        apuracao.chegadas_estimadas(con, ano, 2, 2022, 2)
        chegada = "c.chegada"
        fonte = f"'{arq}' s JOIN chegadas c USING (sg_uf, cd_municipio, nr_zona, nr_secao)"
    d = con.execute(f"""SELECT lower(sg_uf) uf, cd_municipio, nr_zona, nr_secao, s.votos_petismo::DOUBLE pt,
                               s.votos_bolsonarismo::DOUBLE bo,
                               (epoch({chegada}) - epoch(TIMESTAMP '{inicio:%Y-%m-%d %H:%M:%S}')) / 60 AS t
                        FROM {fonte}""").fetchnumpy()
    idx = prior.indice()
    linhas = np.array([idx.get(k, -1) for k in zip(d["uf"].tolist(), d["cd_municipio"].tolist(),
                                                     d["nr_zona"].astype(int).tolist(), d["nr_secao"].astype(int).tolist())])
    ok = linhas >= 0
    pt, bo = np.zeros(prior.n), np.zeros(prior.n)
    t = np.full(prior.n, np.inf)
    pt[linhas[ok]], bo[linhas[ok]] = d["pt"][ok], d["bo"][ok]
    t[linhas[ok]] = np.nan_to_num(F._sem_mascara(d["t"])[ok], nan=np.inf)
    t = np.where(np.isfinite(t), np.maximum(t, 0.0), np.nanmax(np.where(np.isfinite(t), t, np.nan)) + 1)
    return Noite(ano, prior, pt, bo, t, np.where(prior.ordem < 1e8, prior.ordem, np.inf), inicio)


# ---- O que o coletor teria lido ------------------------------------------------------------------------------------

class Leituras:
    """Quando o coletor teria lido o resultado de cada município, minuto a minuto, com as regras de coletor.py e
    historico.coletar. `apurado(t)` dá o que o forecast teria em mãos no minuto t."""

    def __init__(self, noite, chegada, atraso=ATRASO_TOTALIZACAO, limite=coletor.LIMITE_MUN,
                 folga=coletor.FOLGA_MUN, revisita=coletor.REVISITA_MUN / 60):
        p = noite.prior
        self.noite, self.chegada, self.atraso = noite, chegada, atraso
        m = len(p.municipios)
        ordem = np.lexsort((chegada, p.mun))
        self.ordem = ordem
        self.cum_p = np.concatenate([[0.0], np.cumsum(noite.petismo[ordem])])
        self.cum_b = np.concatenate([[0.0], np.cumsum(noite.bolsonarismo[ordem])])
        self.inicio_mun = np.concatenate([[0], np.cumsum(p.secoes_por_municipio)[:-1]])
        total = p.secoes_por_municipio
        fim = int(math.ceil(np.nanmax(chegada[np.isfinite(chegada)]))) + atraso + 2
        self.fim = fim
        chegada_ord = chegada[ordem]
        # seções que chegaram até cada minuto, por município: posição na ordem de chegada de cada município
        self.recebidas = np.zeros((fim + 1, m), np.int32)
        minuto = np.clip(np.ceil(chegada_ord), 0, fim).astype(int)
        np.add.at(self.recebidas, (minuto, p.mun[ordem]), 1)
        self.recebidas = np.cumsum(self.recebidas, axis=0)
        st_lido = np.zeros(m, np.int32)
        lido_em = np.full(m, -1e9)
        self.st = np.zeros((fim + 1, m), np.int32)
        for t in range(fim + 1):
            rec = self.recebidas[t]
            tot = self.recebidas[max(t - atraso, 0)] if t >= atraso else np.zeros(m, np.int32)
            pode = (t - lido_em >= revisita) & (rec > 0)
            nunca = pode & (lido_em < -1e8)
            falta = rec - st_lido
            atrasado = pode & ~nunca & (st_lido < total) & (falta > 0) & ((falta >= folga * st_lido) | (rec == total))
            prioridade = np.where(nunca, np.inf, np.where(atrasado, falta / np.maximum(st_lido, 1), -1.0))
            cand = np.flatnonzero(prioridade >= 0)
            if len(cand) > limite:
                cand = cand[np.argsort(-prioridade[cand], kind="stable")[:limite]]
            st_lido[cand] = tot[cand]
            lido_em[cand] = t
            self.st[t] = st_lido

    def apurado(self, t, ufs=True):
        """O que o forecast teria no minuto t: os resultados lidos dos municípios, o -cs.json e (ufs=True) o total
        oficial de cada UF, lido a cada minuto."""
        p = self.noite.prior
        t = int(min(max(t, 0), self.fim))
        st = self.st[t]
        fim = self.inicio_mun + st
        uf = None
        if ufs:
            tot = self.chegada <= t - self.atraso
            u = p.uf_mun[p.mun]
            uf = {"petismo": np.bincount(u, self.noite.petismo * tot, len(F.UFS)),
                  "bolsonarismo": np.bincount(u, self.noite.bolsonarismo * tot, len(F.UFS)),
                  "secoes": np.bincount(u, tot.astype(int), len(F.UFS))}
        return F.Apurado(self.cum_p[fim] - self.cum_p[self.inicio_mun], self.cum_b[fim] - self.cum_b[self.inicio_mun],
                         st.copy(), np.where(self.chegada <= t, self.chegada, np.inf), uf)

    def minuto_com(self, fracao):
        """O primeiro minuto em que `fracao` das seções do país estavam totalizadas (o "% apurado" do TSE)."""
        tot = np.concatenate([np.zeros(self.atraso), self.recebidas.sum(1)[:-self.atraso]]) / self.noite.prior.n
        return int(min(np.searchsorted(tot, fracao), self.fim))


def ordens(noite, sementes=10):
    """As ordens de chegada da validação: {nome: chegada de cada seção}."""
    p = noite.prior
    regiao = np.array(F.REGIOES)[p.reg_uf[p.uf_mun[p.mun]]]
    fim = float(np.nanmax(noite.chegada[np.isfinite(noite.chegada)]))
    out = {"real": noite.chegada}
    if np.isfinite(noite.chegada_t1).any() and noite.ano >= 2022:
        out["1º turno"] = np.where(np.isfinite(noite.chegada_t1), np.maximum(noite.chegada_t1, 0), fim)
    for r in ("Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"):
        out[f"{r} por último"] = np.where(regiao == r, noite.chegada + fim, noite.chegada)
    rng = np.random.default_rng(2026)
    for s in range(sementes):
        atraso = rng.uniform(0, 90, len(F.UFS))
        out[f"UFs em ordem sorteada {s + 1}"] = noite.chegada + atraso[p.uf_mun[p.mun]]
    out["seções embaralhadas"] = rng.permutation(noite.chegada)
    return out


# ---- Desvios do modelo, com o resultado verdadeiro ---------------------------------------------------------------

def estimar_desvios(noite):
    """O desvio de cada nível, medido no resultado verdadeiro: swing (logit) e comparecimento (log da razão)."""
    p = noite.prior
    m, U, R = len(p.municipios), len(F.UFS), len(F.REGIOES)
    v2 = noite.petismo + noite.bolsonarismo
    ok = (p.peso > 0) & (v2 > 0)
    L, w = p.logit[ok], p.peso[ok]
    mun = p.mun[ok]
    uf = p.uf_mun[mun]
    reg = p.reg_uf[uf]
    pt, vv = noite.petismo[ok], v2[ok]

    def nivel(g, G):
        alvo = (np.bincount(g, pt, G) + 0.5) / (np.bincount(g, vv, G) + 1)
        return F.deslocamento(L, w, g, G, alvo)[0], np.bincount(g, vv, G)

    pais, _ = nivel(np.zeros(len(L), int), 1)
    d_r, v_r = nivel(reg, R)
    d_u, v_u = nivel(uf, U)
    d_m, v_m = nivel(mun, m)
    d_s = np.log((pt + 0.5) / (vv - pt + 0.5)) - L
    grande = vv >= 50  # seções com poucos votos são quase só ruído de amostra

    def rms(x, pesos=None):
        x = np.asarray(x, float)
        bom = np.isfinite(x)
        return float(np.sqrt(np.average(x[bom] ** 2, weights=None if pesos is None else pesos[bom])))

    dom = np.array([r != "Exterior" for r in F.REGIOES])
    out = {"pais": float(pais[0]), "regiao": rms((d_r - pais[0])[dom]), "uf": rms(d_u[:-1] - d_r[p.reg_uf[:-1]]),
           "municipio": rms(d_m - d_u[p.uf_mun], v_m), "municipio_simples": rms(d_m - d_u[p.uf_mun]),
           "secao": rms((d_s - d_m[mun])[grande], vv[grande])}
    # comparecimento: votos dos dois no 2º turno / válidos do 1º
    lr = lambda g, G: np.log(np.maximum(np.bincount(g, vv, G), 1) / np.maximum(np.bincount(g, w, G), 1))  # noqa: E731
    c_p = lr(np.zeros(len(L), int), 1)
    c_r, c_u, c_m = lr(reg, R), lr(uf, U), lr(mun, m)
    c_s = np.log(vv / w)
    out.update({"c_pais": float(c_p[0]), "c_regiao": rms((c_r - c_p[0])[dom]),
                "c_uf": rms(c_u[:-1] - c_r[p.reg_uf[:-1]]), "c_municipio": rms(c_m - c_u[p.uf_mun], v_m),
                "c_secao": rms((c_s - c_m[mun])[grande], vv[grande])})
    return {k: round(v, 4) for k, v in out.items()}


# ---- Validação ---------------------------------------------------------------------------------------------------

def medir(noite, leituras, t, desvios=None, atributos=False):
    """O forecast no minuto t e os erros dele, no país e por UF."""
    a = leituras.apurado(t)
    f = F.prever(noite.prior, a, desvios, atributos=atributos)
    p = noite.prior
    real = noite.real
    real_uf = noite.real_por(p.uf_mun[p.mun], len(F.UFS))
    b = f["brasil"]
    erros_uf, dentro_uf, z_uf = [], [], []
    for k, u in enumerate(F.UFS):
        x = f["ufs"].get(u.upper())
        if x is None or x["apurado"] >= 100:
            continue
        erros_uf.append(x["petismo"] - real_uf[k])
        dentro_uf.append(x["inf"] <= real_uf[k] <= x["sup"])
        z_uf.append((x["petismo"] - real_uf[k]) / max(x["desvio"], 1e-6))
    contagem = 100 * a.petismo.sum() / max(a.petismo.sum() + a.bolsonarismo.sum(), 1)
    return {"t": t, "chegou": round(100 * float((leituras.chegada <= t).mean()), 2), "apurado": f["apurado"],
            "erro": b["petismo"] - real, "dentro": b["inf"] <= real <= b["sup"],
            "z": (b["petismo"] - real) / max(b["desvio"], 1e-6), "desvio": b["desvio"],
            "contagem": contagem - real, "erros_uf": erros_uf, "dentro_uf": dentro_uf, "z_uf": z_uf, "f": f}


def validar(noites, desvios=None, variantes=(False, True), sementes=10, log=print):
    """{ano: {ordem: {variante: [medida em cada marco]}}}."""
    out = {}
    for n in noites:
        out[n.ano] = {}
        for nome, chegada in ordens(n, sementes).items():
            le = Leituras(n, chegada)
            out[n.ano][nome] = {}
            for atr in variantes:
                medidas = []
                for marco in MARCOS:
                    medidas.append({**medir(n, le, le.minuto_com(marco / 100), desvios, atr), "marco": marco})
                out[n.ano][nome]["atributos" if atr else "simples"] = medidas
            log(f"   {n.ano} · {nome}: " + " ".join(f"{m['marco']}%:{m['erro']:+.2f}"
                                                     for m in out[n.ano][nome]["simples"][::4]))
    return out


def resumo(resultado, variante="simples"):
    """Por marco: erro médio absoluto e máximo no país, em todas as ordens dos dois anos; cobertura da faixa de 80%."""
    linhas = []
    for i, marco in enumerate(MARCOS):
        ms = [o[variante][i] for a in resultado.values() for o in a.values()]
        linhas.append({"marco": marco, "erro_medio": float(np.mean([abs(m["erro"]) for m in ms])),
                       "erro_max": float(np.max([abs(m["erro"]) for m in ms])),
                       "contagem_media": float(np.mean([abs(m["contagem"]) for m in ms])),
                       "dentro": float(np.mean([m["dentro"] for m in ms])),
                       "dentro_uf": float(np.mean([d for m in ms for d in m["dentro_uf"]] or [np.nan])),
                       "desvio": float(np.mean([m["desvio"] for m in ms]))})
    return linhas


def serie_da_noite(noite, passo=2, desvios=None, atributos=False):
    """O forecast a cada `passo` minutos da noite, na ordem real, para o site (formato de `forecast.json`)."""
    le = Leituras(noite, noite.chegada)
    fim = le.minuto_com(0.999) + passo
    s = {k: [] for k in ("t", "apurado", "petismo", "inf", "sup", "chance", "vantagem", "vinf", "vsup",
                         "votos_petismo", "votos_bolsonarismo")}
    for t in range(0, fim + 1, passo):
        a = le.apurado(t)
        if a.secoes.sum() == 0:
            continue
        f = F.prever(noite.prior, a, desvios, atributos=atributos)["brasil"]
        for k, v in (("t", t), ("apurado", f["apurado"]), ("petismo", f["petismo"]), ("inf", f["inf"]),
                     ("sup", f["sup"]), ("chance", f["chance"]), ("vinf", f["vantagem"][0]), ("vantagem", f["vantagem"][1]),
                     ("vsup", f["vantagem"][2]), ("votos_petismo", f["votos"]["petismo"]),
                     ("votos_bolsonarismo", f["votos"]["bolsonarismo"])):
            s[k].append(v)
    return {"ano": noite.ano, "turno": 2, "inicio": f"{noite.inicio:%Y-%m-%dT%H:%M}", "real": round(noite.real, 3),
            "projecao": round(100 * noite.prior.total, 2), **s}


# ---- Relatório e dados do site -----------------------------------------------------------------------------------

def _num(v, casas=2, sinal=False):
    return f"{v:{'+' if sinal else ''}.{casas}f}".replace(".", ",").replace("-", "−")


def _pct(v, casas=0):
    return _num(100 * v, casas) + "%"


def _outros(t1):
    v = t1["petismo"].sum() + t1["bolsonarismo"].sum() + t1["outros"].sum()
    return float(t1["outros"].sum() / v)


def gerar(log=print, sementes=10):
    """Refaz as noites, mede os desvios e devolve o que vai para o site e para o relatório."""
    noites = [noite(a) for a in ANOS]
    medidos = {n.ano: estimar_desvios(n) for n in noites}
    log("Desvios medidos com o resultado verdadeiro: " + "; ".join(f"{a}: {d}" for a, d in medidos.items()))
    resultado = validar(noites, sementes=sementes, log=log)
    outros = {str(n.ano): n.prior.outros for n in noites}
    outros["2026"] = _outros(F.ler_primeiro_turno(2026))
    usados = {a: dataclasses.asdict(F.Desvios.para(o)) for a, o in outros.items()}
    serie = serie_da_noite(next(n for n in noites if n.ano == 2022))
    validacao = {}
    for ano, ords in resultado.items():
        validacao[str(ano)] = {}
        for var in ("simples", "atributos"):
            ms = [m for o in ords.values() for m in o[var] if m["marco"] >= 1]
            validacao[str(ano)][var] = {
                "por_marco": resumo({ano: ords}, var),
                "na_faixa": float(np.mean([m["dentro"] for m in ms])),
                "ufs_na_faixa": float(np.mean([d for m in ms for d in m["dentro_uf"]])),
                "ordens": len(ords)}
    return {"parametros": {"por_outros": F.POR_OUTROS, "piso": F.PISO,
                           "outros": {a: round(o, 4) for a, o in outros.items()}, "desvios": usados,
                           "atraso_totalizacao": ATRASO_TOTALIZACAO, "limite_municipios": coletor.LIMITE_MUN},
            "desvios_medidos": {str(a): d for a, d in medidos.items()},
            "validacao": validacao, "noites": {"2022": serie}}


def _arredondar(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _arredondar(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_arredondar(v) for v in x]
    return x


NOMES_DESVIOS = {"regiao": "swing: região", "uf": "swing: UF", "municipio": "swing: município", "secao": "swing: seção",
                 "ordem": "o que falta: país", "ordem_uf": "o que falta: UF", "ordem_mun": "o que falta: município",
                 "c_pais": "comparecimento: país", "c_regiao": "comparecimento: região", "c_uf": "comparecimento: UF",
                 "c_municipio": "comparecimento: município", "c_secao": "comparecimento: seção"}


def relatorio(dados):
    """docs/validacao_forecast.md."""
    v, par = dados["validacao"], dados["parametros"]
    marco = lambda x: _num(x, 1 if x % 1 else 0) + "%"  # noqa: E731
    linhas = ["# Validação do forecast da apuração", "",
              f"> Gerado por `uv run eleicoes forecast` em {dt.datetime.now():%d/%m/%Y %H:%M}. Não editar à mão.", "",
              "Método em `src/eleicoes/modelos/forecast.py` e na Metodologia do site. Cada noite de 2º turno já apurada "
              "(2018 e 2022) é refeita seção a seção, só com o que se sabia em cada momento: o resultado de cada município "
              f"como o coletor o teria lido (no máximo {par['limite_municipios']} por minuto, os mais atrasados primeiro, "
              f"cada um com as seções totalizadas até {par['atraso_totalizacao']} min antes), o total oficial de cada UF a "
              "cada minuto e a hora de chegada de cada seção. O ponto de partida é o 1º turno de cada seção, distribuído "
              "como na projeção do 2º turno da véspera daquele ano.", "",
              "Em 2018, sem a hora de chegada de cada boletim, ela é estimada como no site, e a divulgação só começou às "
              "19h, com quase todas as seções já apuradas: a ordem real de 2018 quase não testa o forecast, e valem as "
              "ordens inventadas.", "",
              "Ordens de chegada: a real; em 2022, a do 1º turno (as mesmas seções); cada região por último; as UFs em "
              "ordem sorteada (cada uma começa com um atraso sorteado de até 90 min; 10 sorteios); e as seções "
              "embaralhadas.", "",
              "## Erro do forecast a cada % apurado", "",
              "Erro = forecast − urnas, na parte do petismo nos votos válidos, em pontos percentuais, em todas as ordens de "
              "chegada. Faixa: a metade do intervalo de 80% (média). Contagem: o erro médio de quem lesse só o que já foi "
              "apurado.", ""]
    for ano in sorted(v):
        r = v[ano]["simples"]
        linhas += [f"### {ano} ({r['ordens']} ordens de chegada)", "",
                   f"Resultado dentro da faixa de 80%: {_pct(r['na_faixa'])} das vezes no país e {_pct(r['ufs_na_faixa'])} "
                   "nas UFs ainda não apuradas por inteiro (de 1% apurado em diante).", "",
                   "| Apurado | Erro médio | Erro máximo | Faixa de 80% | Na faixa | Contagem: erro médio |",
                   "|--:|--:|--:|--:|--:|--:|"]
        for l in r["por_marco"]:
            linhas.append(f"| {marco(l['marco'])} | {_num(l['erro_medio'])} | {_num(l['erro_max'])} | "
                          f"±{_num(Z80 * l['desvio'])} | {_pct(l['dentro'])} | {_num(l['contagem_media'])} |")
        linhas.append("")
    anos = sorted(v)
    linhas += ["## Swing por atributos", "",
               "Variante testada: além do swing de cada lugar, o swing de cada seção acompanha três atributos do 1º turno "
               "(a parte dos outros candidatos, a inclinação entre os dois e o comparecimento), com coeficientes aprendidos "
               "a cada momento nos municípios já apurados. Erro médio no país e a parte das vezes com o resultado na faixa "
               "de 80%:", "",
               "| Apurado | " + " | ".join(f"{a}: simples | {a}: atributos" for a in anos) + " |",
               "|--:|" + "--:|--:|" * len(anos)]
    for i, l in enumerate(v[anos[0]]["simples"]["por_marco"]):
        celulas = [_num(v[a][var]["por_marco"][i]["erro_medio"]) for a in anos for var in ("simples", "atributos")]
        linhas.append(f"| {marco(l['marco'])} | " + " | ".join(celulas) + " |")
    linhas.append("| na faixa | " + " | ".join(_pct(v[a][var]["na_faixa"]) for a in anos for var in ("simples", "atributos")) + " |")
    melhor = sum(v[a]["atributos"]["por_marco"][i]["erro_medio"] < v[a]["simples"]["por_marco"][i]["erro_medio"]
                 for a in anos for i in range(len(MARCOS)))
    linhas += ["", f"A variante teve erro médio menor em {melhor} dos {len(anos) * len(MARCOS)} pontos acima. "
               "Só entraria no forecast se ganhasse do modelo simples nas duas eleições.", "",
               "## Desvios do modelo", "",
               "Em logit: da parte do petismo entre os dois (swing) e do log da razão entre os votos dos dois no 2º turno e "
               "os válidos do 1º (comparecimento). Medido: o desvio de cada nível em torno do nível de cima, com o "
               "resultado verdadeiro (município e seção ponderados pelos votos). Usado: proporcional à parte dos outros "
               "candidatos no 1º turno do país, com um mínimo.", "",
               "| Desvio | Medido em 2018 | Medido em 2022 | Usado em 2018 | Usado em 2022 | Usado em 2026 |",
               "|---|--:|--:|--:|--:|--:|"]
    med, us = dados["desvios_medidos"], par["desvios"]
    for k, nome in NOMES_DESVIOS.items():
        mm = [_num(med[a][k], 3) if k in med[a] else "–" for a in ("2018", "2022")]
        uu = [_num(us[a][k], 3) for a in ("2018", "2022", "2026")]
        linhas.append(f"| {nome} | {' | '.join(mm)} | {' | '.join(uu)} |")
    linhas += ["", "Parte dos outros candidatos nos válidos do 1º turno: "
               + ", ".join(f"{_pct(o, 1)} em {a}" for a, o in par["outros"].items()) + ".", "",
               "## A noite de 2022, minuto a minuto", "",
               "| Hora | Apurado | Forecast | Faixa de 80% | Chance de Lula |", "|---|--:|--:|---|--:|"]
    s = dados["noites"]["2022"]
    inicio = dt.datetime.fromisoformat(s["inicio"])
    for i, t in enumerate(s["t"]):
        if t % 10 == 0 and s["apurado"][i] < 99.5:
            chance = "mais de 99,9%" if s["chance"][i] >= 0.9995 else _pct(s["chance"][i], 1)
            linhas.append(f"| {(inicio + dt.timedelta(minutes=t)):%Hh%M} | {_num(s['apurado'][i], 1)}% | "
                          f"{_num(s['petismo'][i])}% | {_num(s['inf'][i])}% a {_num(s['sup'][i])}% | {chance} |")
    linhas += ["", f"Urnas: {_num(s['real'])}%. Projeção da véspera: {_num(s['projecao'])}%."]
    RELATORIO.write_text("\n".join(linhas) + "\n", "utf-8")


Z80 = F.Z80


def gravar(log=print):
    """uv run eleicoes forecast: gera site/src/data/forecast.json e docs/validacao_forecast.md."""
    dados = gerar(log=log)
    site = _arredondar({"parametros": dados["parametros"], "desvios_medidos": dados["desvios_medidos"],
                        "validacao": dados["validacao"], "noites": dados["noites"]})
    SITE.write_text(json.dumps(site, ensure_ascii=False, separators=(",", ":")), "utf-8")
    relatorio(dados)
    log(f"site/src/data/forecast.json · relatório em {RELATORIO.relative_to(config.RAIZ).as_posix()}")
    return dados
