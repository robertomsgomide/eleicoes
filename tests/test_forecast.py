"""Testes do forecast da apuração com dados sintéticos: a conta da árvore de normais contra a conta direta, o que o
forecast dá com nada e com tudo apurado, e um país inventado com swings conhecidos."""
import math

import numpy as np
import pytest

from eleicoes.modelos import forecast as F


# ---- A árvore de normais ---------------------------------------------------------------------------------------

def _arvore_direta(d, s2, mun_uf, reg_uf, taus, tau_pais, k):
    """A mesma posterior pela conta direta: o vetor (país, regiões, UFs, municípios) é uma transformação linear de
    efeitos independentes, e os municípios com dados são observados com ruído."""
    tr, tu, tm = taus
    R, U, M = int(reg_uf.max()) + 1, len(reg_uf), len(mun_uf)
    n = 1 + R + U + M
    T = np.zeros((n, n))  # x = T e
    T[0, 0] = 1
    for r in range(R):
        T[1 + r, [0, 1 + r]] = 1
    for u in range(U):
        T[1 + R + u] = T[1 + reg_uf[u]]
        T[1 + R + u, 1 + R + u] = 1
    for m in range(M):
        T[1 + R + U + m] = T[1 + R + mun_uf[m]]
        T[1 + R + U + m, 1 + R + U + m] = 1
    var_e = np.array([tau_pais ** 2] + [tr ** 2] * R + [tu ** 2] * U + [tm ** 2] * M)
    S = T @ np.diag(var_e) @ T.T
    obs = [m for m in range(M) if np.isfinite(d[m])]
    H = np.zeros((len(obs), n))
    for j, m in enumerate(obs):
        H[j, 1 + R + U + m] = 1
    Rn = np.diag([s2[m] for m in obs])
    K = S @ H.T @ np.linalg.inv(H @ S @ H.T + Rn)
    media = K @ np.array([d[m] for m in obs])
    post = S - K @ H @ S
    dm = slice(1 + R + U, n)
    return media[dm], k @ post[dm, dm] @ k


def test_arvore_e_a_conta_direta():
    rng = np.random.default_rng(1)
    reg_uf = np.array([0, 0, 1, 1, 2])
    mun_uf = np.array([0, 0, 1, 2, 2, 3, 4, 4, 4])
    d = rng.normal(0, 0.2, 9)
    d[[1, 4, 8]] = np.nan  # municípios sem nada apurado
    s2 = np.where(np.isfinite(d), rng.uniform(0.001, 0.05, 9), 0)
    taus, tau_pais = (0.1, 0.08, 0.15), 0.07
    k = rng.uniform(0, 1, 9)
    a = F.Arvore.ajustar(d, s2, mun_uf, reg_uf, taus, tau_pais)
    media, var = _arvore_direta(d, s2, mun_uf, reg_uf, taus, tau_pais, k)
    assert a.media_mun == pytest.approx(media, abs=1e-10)
    assert a.variancias(k, mun_uf, reg_uf, np.zeros(9, int))[0, 0, 0] == pytest.approx(var, rel=1e-9)
    # por grupo (só os municípios do grupo entram na soma) e com duas somas de uma vez (covariância)
    grupos = np.array([0, 0, 0, 1, 1, 1, -1, 2, 2])
    k2 = np.column_stack([k, k[::-1]])
    v = a.variancias(k2, mun_uf, reg_uf, grupos)
    for g in range(3):
        kg = np.where(grupos == g, 1.0, 0.0)
        _, v11 = _arvore_direta(d, s2, mun_uf, reg_uf, taus, tau_pais, k * kg)
        _, v22 = _arvore_direta(d, s2, mun_uf, reg_uf, taus, tau_pais, k[::-1] * kg)
        _, vss = _arvore_direta(d, s2, mun_uf, reg_uf, taus, tau_pais, (k + k[::-1]) * kg)
        assert v[g, 0, 0] == pytest.approx(v11, rel=1e-9) and v[g, 1, 1] == pytest.approx(v22, rel=1e-9)
        assert v[g, 0, 1] == pytest.approx((vss - v11 - v22) / 2, rel=1e-8)
    # os sorteios vêm da mesma posterior
    s = a.sortear(20000, mun_uf, reg_uf, np.random.default_rng(2))
    assert s.mean(0) == pytest.approx(media, abs=0.01)
    assert np.var(s @ k) == pytest.approx(var, rel=0.05)


# ---- Um país inventado -----------------------------------------------------------------------------------------

UFS_TESTE = ["BA", "PE", "SP", "MG", "RS", "ZZ"]


def _primeiro_turno(n_mun=12, secoes=20, semente=3):
    """Seções de um país pequeno: municípios em seis UFs, com o 1º turno e a hora de chegada."""
    rng = np.random.default_rng(semente)
    linhas = []
    for j in range(n_mun):
        uf = UFS_TESTE[j % len(UFS_TESTE)]
        base = {"BA": 0.65, "PE": 0.6, "SP": 0.42, "MG": 0.48, "RS": 0.38, "ZZ": 0.4}[uf]
        for s in range(secoes):
            v = rng.integers(150, 350)
            pt = rng.binomial(v, np.clip(base + rng.normal(0, 0.08), 0.05, 0.95) * 0.92)
            ou = rng.binomial(v - pt, 0.12)
            linhas.append((uf, f"{j:05d}", 1, s + 1, pt, v - pt - ou, ou, 400, v + 30, rng.uniform(0, 200)))
    col = list(zip(*linhas))
    nomes = ["uf", "municipio", "zona", "secao", "petismo", "bolsonarismo", "outros", "aptos", "comparecimento", "chegada"]
    t1 = {k: np.array(v) for k, v in zip(nomes, col)}
    t1["regiao"] = np.array([F.config.REGIAO_DA_UF[u] for u in t1["uf"]])
    t1["ibge"] = np.where(t1["uf"] == "ZZ", np.nan, 1000000.0)
    return t1


def _segundo_turno(prior, swings, comparecimento=0.0, semente=4):
    """O 2º turno verdadeiro: o prior deslocado pelo swing da UF de cada seção, com ruído de seção."""
    rng = np.random.default_rng(semente)
    uf = np.array([F.UFS[u] for u in prior.uf_mun[prior.mun]])
    L = prior.logit + np.array([swings.get(u, 0.0) for u in uf]) + rng.normal(0, 0.1, prior.n)
    v = np.round(prior.peso * np.exp(comparecimento + rng.normal(0, 0.05, prior.n)))
    pt = rng.binomial(v.astype(int), F._expit(L))
    return pt.astype(float), (v - pt).astype(float)


def _apurado(prior, pt, bo, chegada, ate):
    """O que se sabe quando chegaram as seções com chegada <= ate (o resultado de cada município já com elas)."""
    m = len(prior.municipios)
    c = chegada <= ate
    return F.Apurado(np.bincount(prior.mun, pt * c, m), np.bincount(prior.mun, bo * c, m),
                     np.bincount(prior.mun, c.astype(int), m), np.where(c, chegada, np.inf))


# os desvios do país inventado: swings de UF bem maiores que os de 2022
DESVIOS = F.Desvios(regiao=0.2, uf=0.2, municipio=0.1, secao=0.15)


@pytest.fixture
def pais():
    t1 = _primeiro_turno()
    prior = F.Prior.criar(t1, 0.50, 2.0)
    pt, bo = _segundo_turno(prior, {"ba": 0.25, "pe": 0.2, "sp": -0.1})
    chegada = np.random.default_rng(5).uniform(0, 100, prior.n)
    return prior, pt, bo, chegada


def test_sem_nada_apurado_o_forecast_e_a_projecao(pais):
    prior, *_ = pais
    f = F.prever(prior, F.Apurado.vazio(prior))  # desvios de uma eleição como a de 2022
    assert f["brasil"]["petismo"] == pytest.approx(50.0, abs=0.05)  # o prior soma o total da projeção
    assert f["brasil"]["desvio"] == pytest.approx(2.0, rel=0.02)      # e tem a incerteza dela
    assert f["apurado"] == 0 and f["brasil"]["chance"] == pytest.approx(0.5, abs=0.01)


def test_com_tudo_apurado_o_forecast_e_o_resultado(pais):
    prior, pt, bo, chegada = pais
    f = F.prever(prior, _apurado(prior, pt, bo, chegada, np.inf), DESVIOS)
    real = 100 * pt.sum() / (pt.sum() + bo.sum())
    assert f["brasil"]["petismo"] == pytest.approx(real, abs=1e-3) and f["brasil"]["desvio"] == 0
    assert f["brasil"]["votos"] == {"petismo": pt.sum(), "bolsonarismo": bo.sum()}
    assert f["apurado"] == 100 and f["ufs"]["BA"]["apurado"] == 100


def test_o_forecast_aprende_o_swing_e_a_faixa_encolhe(pais):
    prior, pt, bo, chegada = pais
    real = 100 * pt.sum() / (pt.sum() + bo.sum())
    desvios = []
    for ate in (5, 20, 50, 80):
        f = F.prever(prior, _apurado(prior, pt, bo, chegada, ate), DESVIOS)
        assert f["brasil"]["inf"] <= real <= f["brasil"]["sup"], ate
        desvios.append(f["brasil"]["desvio"])
        contagem = 100 * (pt * (chegada <= ate)).sum() / ((pt + bo) * (chegada <= ate)).sum()
        assert abs(f["brasil"]["petismo"] - real) < abs(contagem - real) + 0.05
    assert desvios == sorted(desvios, reverse=True) and desvios[-1] < desvios[0] / 3


def test_uma_regiao_sem_nada_apurado_tem_faixa_larga(pais):
    prior, pt, bo, chegada = pais
    nordeste = np.isin(prior.uf, ["ba", "pe"])
    chegada = np.where(nordeste, chegada + 1000, chegada)  # o Nordeste chega por último
    f = F.prever(prior, _apurado(prior, pt, bo, chegada, 100), DESVIOS)
    larg = {u: f["ufs"][u]["sup"] - f["ufs"][u]["inf"] for u in ("BA", "SP")}
    assert f["ufs"]["BA"]["apurado"] == 0 and f["ufs"]["SP"]["apurado"] == 100
    assert larg["BA"] > 5 * max(larg["SP"], 0.01)
    real = {u: 100 * pt[prior.uf == u.lower()].sum() / (pt + bo)[prior.uf == u.lower()].sum() for u in ("BA",)}
    assert f["ufs"]["BA"]["inf"] <= real["BA"] <= f["ufs"]["BA"]["sup"]


def test_contadas_sao_as_primeiras_a_chegar_em_cada_municipio(pais):
    prior, pt, bo, chegada = pais
    a = _apurado(prior, pt, bo, chegada, 30)
    c = F.contadas(prior, a)
    assert (c == (chegada <= 30)).all()
    # o resultado do município pode estar atrás do -cs.json: entram as primeiras `secoes` a chegar
    a.secoes = np.maximum(a.secoes - 1, 0)
    c = F.contadas(prior, a)
    for j in range(len(prior.municipios)):
        mesmo = prior.mun == j
        if a.secoes[j]:
            assert chegada[mesmo & c].max() < chegada[mesmo & (chegada <= 30) & ~c].min()


def test_secao_agregada_no_segundo_turno_passa_os_votos_para_a_principal(pais):
    prior, *_ = pais
    n, peso = prior.n, prior.peso.sum()
    u, mu = prior.uf[0], prior.municipio[0]
    q = F._expit(prior.logit[:2])
    esperado = (prior.peso[:2] * q).sum() / prior.peso[:2].sum()
    assert prior.agregar_no_segundo_turno([(u, mu, "0001", "0002", "0001")]) == 1
    assert prior.n == n - 1 and prior.peso.sum() == pytest.approx(peso)
    assert F._expit(prior.logit[0]) == pytest.approx(esperado)
    assert (u, mu, 1, 2) not in prior.indice()


def test_atributos_nao_atrapalham_quando_nao_ha_o_que_aprender(pais):
    prior, pt, bo, chegada = pais
    real = 100 * pt.sum() / (pt.sum() + bo.sum())
    f = F.prever(prior, _apurado(prior, pt, bo, chegada, 40), DESVIOS, atributos=True)
    assert abs(f["brasil"]["petismo"] - real) < 1.0
    assert math.isfinite(f["brasil"]["desvio"])


# ---- O que os coletores gravam para o site -----------------------------------------------------------------------

def test_a_apuracao_ao_vivo_tem_o_brasil_do_arquivo_do_pais_e_as_regioes_pela_soma_das_ufs():
    import datetime as dt

    from eleicoes.ao_vivo import painel
    inicio = dt.datetime(2026, 10, 25, 17)

    def l(abr, h, st, ts, lula, flavio):
        return {"abr": abr, "h": f"2026-10-25T{h}", "st": st, "ts": ts, "vv": lula + flavio, "pst": 100 * st / ts,
                "cand": {"13": {"v": lula}, "22": {"v": flavio}}}

    br = [l("br", "17:02:10", 2, 10, 50, 70), l("br", "17:05:00", 6, 10, 200, 180)]
    ufs = {"ba": [l("ba", "17:02:00", 1, 4, 40, 10), l("ba", "17:05:00", 3, 4, 150, 60)],
           "sc": [l("sc", "17:03:00", 2, 5, 15, 60)]}
    s = painel.serie(br, ufs, inicio, {"petismo": "13", "bolsonarismo": "22"})
    assert s["t"] == [2, 3, 5] and s["inicio"] == "2026-10-25T17:00" and s["tipo"] == "ao vivo"
    assert s["regioes"]["Brasil"]["petismo"] == [50, 50, 200]          # o arquivo do país, o último de cada minuto
    assert s["regioes"]["Nordeste"]["secoes"] == [1, 1, 3]             # cada UF vale até a leitura seguinte dela
    assert s["regioes"]["Sul"]["bolsonarismo"] == [0, 60, 60]
    assert s["totais"]["Brasil"]["secoes"] == 10 and s["totais"]["Nordeste"]["secoes"] == 4
    assert s["viradas"] == [{"t": 5, "pct_secoes": 60.0, "lider": "petismo"}]


# ---- A noite de 2022 refeita (pula sem os dados) -------------------------------------------------------------------

def _tem_2022():
    from eleicoes.tratamento import boletins
    return all(boletins.saida("secoes", 2022, t).exists() for t in (1, 2))


@pytest.mark.skipif(not _tem_2022(), reason="sem as seções de 2022 em dados/processado")
def test_a_noite_de_2022_refeita_acerta_bem_antes_da_contagem():
    from eleicoes.modelos import forecast_validacao as V
    n = V.noite(2022)
    le = V.Leituras(n, n.chegada)
    t = le.minuto_com(0.05)
    m = V.medir(n, le, t)
    assert abs(m["erro"]) < 0.4 and m["dentro"]       # com 5% apurado, a poucos décimos do resultado
    assert abs(m["contagem"]) > 3                      # enquanto a contagem ainda erra por mais de 3 pontos
    a = le.apurado(t)
    assert a.uf["secoes"].sum() >= a.secoes.sum()      # o total das UFs vem antes dos municípios lidos
