"""Testes da projeção do 2º turno: a lógica com dados sintéticos e a validação com 2018 e 2022 (pulam sem os dados)."""
import datetime as dt

import numpy as np
import pytest

from eleicoes.analises import pesquisas as analise
from eleicoes.modelos import projecao as P
from eleicoes.tratamento import votacao_secao


def _secoes():
    """Quatro seções: duas petistas, duas bolsonaristas, com outros candidatos em todas."""
    return P.Secoes(uf=np.array(["BA", "BA", "SC", "SC"], dtype=object), regiao=np.array(["Nordeste", "Nordeste", "Sul", "Sul"], dtype=object),
                    municipio=np.array(["1", "2", "3", "4"], dtype=object), petismo=np.array([200.0, 150.0, 60.0, 90.0]),
                    bolsonarismo=np.array([60.0, 100.0, 200.0, 150.0]), outros=np.array([40.0, 50.0, 40.0, 60.0]))


def _total(s, partes):
    return (partes * s.validos).sum() / s.validos.sum()


@pytest.mark.parametrize("alvo", [0.42, 0.45, 0.50, 0.57])  # o petismo pode ir de 41,7% (500/1200) a 57,5% (690/1200)
def test_distribuir_soma_o_total_e_so_reparte_os_votos_dos_outros(alvo):
    s = _secoes()
    partes = P.distribuir(s, alvo)
    assert _total(s, partes) == pytest.approx(alvo, abs=1e-9)
    # cada seção fica entre "nenhum voto dos outros" e "todos os votos dos outros" para o petismo
    assert np.all(partes >= s.petismo / s.validos - 1e-12) and np.all(partes <= (s.petismo + s.outros) / s.validos + 1e-12)
    # onde o petismo é mais forte, ele leva uma parte maior dos votos dos outros
    parte_dos_outros = (partes * s.validos - s.petismo) / s.outros
    assert parte_dos_outros[0] > parte_dos_outros[1] > parte_dos_outros[3] > parte_dos_outros[2]


def test_distribuir_alem_dos_votos_dos_outros_desloca_todas_as_secoes():
    s = _secoes()
    minimo = s.petismo.sum() / s.validos.sum()
    partes = P.distribuir(s, minimo - 0.03)
    assert _total(s, partes) == pytest.approx(minimo - 0.03, abs=1e-9)
    assert np.all(partes < s.petismo / s.validos)
    assert np.all(np.diff(P.distribuir(s, 0.47) - P.distribuir(s, 0.46)) != 0)  # o total move todas as seções


def test_por_lugar_tem_intervalo_maior_onde_os_outros_pesam_mais():
    s = _secoes()
    s.outros = np.array([10.0, 10.0, 80.0, 80.0])
    r = P.por_lugar(s, 50.0, 2.0)["ufs"]
    assert r["BA"]["inf"] < r["BA"]["petismo"] < r["BA"]["sup"]
    assert r["SC"]["sup"] - r["SC"]["inf"] > r["BA"]["sup"] - r["BA"]["inf"]
    assert r["BA"]["chance"] > 0.5 > r["SC"]["chance"]


def _pesquisa(turno, petismo, bolsonarismo, fim, instituto="X", inicio=None, amostra=2000):
    fim = dt.date.fromisoformat(fim)
    return {"turno": turno, "instituto": instituto, "inicio": inicio or fim - dt.timedelta(days=2), "fim": fim,
            "amostra": amostra, "petismo_validos": petismo, "bolsonarismo_validos": bolsonarismo}


def test_ponto_de_partida_aplica_as_urnas_a_divisao_dos_outros_nas_pesquisas_pareadas():
    """Pesquisa: 1º turno 40 × 45 (outros 15), 2º turno 49 × 51: o petismo leva 9 de 15 = 60% dos outros.
    Urnas no 1º turno: 42% e outros 10% -> ponto de partida 48%. Pesquisa sem par ou fora da semana não entra."""
    ps = [_pesquisa(1, 40, 45, "2026-10-01"), _pesquisa(2, 49, 51, "2026-10-01"),
          _pesquisa(2, 55, 45, "2026-10-01", instituto="Sem par"),
          _pesquisa(1, 30, 50, "2026-09-20", instituto="Antiga"), _pesquisa(2, 60, 40, "2026-09-20", instituto="Antiga")]
    p = P.partida(ps, 2026, {"petismo": 42.0, "bolsonarismo": 48.0, "outros": 10.0})
    assert len(p["pares"]) == 1 and p["parte_dos_outros"] == pytest.approx(0.6)
    assert p["petismo"] == pytest.approx(48.0)


def test_sem_pesquisas_depois_do_primeiro_turno_vale_o_ponto_de_partida():
    eleicao = dt.date(2026, 10, 25)
    r = P.projetar(48.0, None, eleicao)
    assert (r["petismo"], r["desvio"], r["peso_pesquisas"]) == (48.0, P.DESVIOS.partida, 0.0)
    assert r["chance"] == pytest.approx(1 - P._normal(2 / P.DESVIOS.partida), abs=1e-3)


def test_pesquisas_pesam_mais_quanto_mais_perto_da_eleicao():
    eleicao = dt.date(2026, 10, 25)
    media = lambda ultima: {"petismo": 52.0, "quadrados": 0.05, "pesquisas": 20, "ultima": ultima}  # noqa: E731
    longe, perto = P.projetar(48.0, media(dt.date(2026, 10, 8)), eleicao), P.projetar(48.0, media(dt.date(2026, 10, 24)), eleicao)
    assert 48 < longe["petismo"] < perto["petismo"] < 52 and perto["desvio"] < longe["desvio"] < P.DESVIOS.partida
    assert perto["peso_pesquisas"] > 0.5 > longe["peso_pesquisas"]
    # um desvio maior para o ponto de partida dá mais peso às pesquisas
    assert P.projetar(48.0, media(dt.date(2026, 10, 8)), eleicao, P.Desvios(partida=5))["peso_pesquisas"] > longe["peso_pesquisas"]


def test_media_das_pesquisas_so_usa_as_feitas_depois_do_primeiro_turno():
    ps = [_pesquisa(2, 60, 40, "2026-10-02", inicio=dt.date(2026, 9, 30))]  # antes do 1º turno (4/10)
    assert P.media_pesquisas(ps, 2026, dt.date(2026, 10, 10)) is None
    ps += [_pesquisa(2, 48, 52, "2026-10-08", "A"), _pesquisa(2, 50, 50, "2026-10-09", "B")]
    m = P.media_pesquisas(ps, 2026, dt.date(2026, 10, 10))
    assert m["pesquisas"] == 2 and 48 < m["petismo"] < 50 and m["ultima"] == dt.date(2026, 10, 9)
    # menos de MINIMO pesquisas: média ponderada, com a soma dos quadrados dos pesos entre 1/2 (pesos iguais) e 1
    assert 0.5 <= m["quadrados"] < 1
    assert P.media_pesquisas(ps, 2026, dt.date(2026, 10, 8))["pesquisas"] == 1


def test_reta_local_soma_dos_pesos_ao_quadrado():
    """Média ponderada de n pesquisas iguais no mesmo dia: pesos 1/n, soma dos quadrados 1/n."""
    ps = [_pesquisa(2, 50 + i, 50 - i, "2026-10-10", instituto=str(i)) for i in range(4)]
    (estimativa, quadrados) = analise.reta_local(ps, dt.date(2026, 10, 10))
    assert estimativa["petismo"] == pytest.approx(51.5) and quadrados == pytest.approx(0.25)


# ---- Com os dados reais -------------------------------------------------------------

@pytest.fixture(scope="module")
def anos():
    for ano in (2018, 2022):
        if not (votacao_secao.fonte_secoes(ano, 1) and votacao_secao.fonte_secoes(ano, 2) and analise.carregar(ano)):
            pytest.skip("rode `uv run eleicoes processar` e `uv run eleicoes pesquisas`")
    from eleicoes.analises import resultados
    from eleicoes.tratamento import conexao
    con = conexao()
    res = resultados.gerar(con)
    feitos = {str(a): P.projecao_do_ano(con, res, a) for a in (2018, 2022)}
    return feitos, P.validar(con, res, feitos)


@pytest.mark.parametrize("ano,limite", [("2018", 1.0), ("2022", 1.5)])
def test_projecao_da_vespera_fica_perto_das_urnas(anos, ano, limite):
    """Na véspera, refeita só com o que se sabia: 2018 a −0,1 p.p. e 2022 a +0,8 p.p. do resultado."""
    feitos, validacao = anos
    v = validacao[ano]["projecao"]
    assert abs(v["vespera"]) < limite and v["dias_no_intervalo"] >= 0.9
    assert feitos[ano]["serie"][-1]["data"] == (P.data(int(ano), 2) - dt.timedelta(days=1)).isoformat()


@pytest.mark.parametrize("ano,limite", [("2018", 2.5), ("2022", 1.0)])
def test_distribuicao_pelo_pais_com_o_total_verdadeiro(anos, ano, limite):
    """Só a geografia: com o total nacional das urnas, o desvio típico por UF fica perto do esperado."""
    d = anos[1][ano]["distribuicao"]
    assert d["ufs"] < limite and d["municipios"] < limite + 0.6 and d["ufs_no_intervalo"] >= 0.7


def test_ponto_de_partida_erra_menos_que_as_pesquisas_de_segundo_turno_da_vespera(anos):
    for v in anos[1].values():
        assert abs(v["partida"]) < abs(v["segundo_turno_nas_pesquisas"])


def test_projecao_de_2026_distribui_o_total_do_pais():
    if not votacao_secao.fonte_secoes(2026, 1):
        pytest.skip("rode `uv run eleicoes processar`")
    from eleicoes.tratamento import conexao
    s = P.secoes(conexao(), 2026)
    for alvo in (0.44, 0.482, 0.52, 0.56):
        assert _total(s, P.distribuir(s, alvo)) == pytest.approx(alvo, abs=1e-9)
    assert len(set(s.uf)) == 28
