"""Leitura das tabelas de pesquisas e ligação com o registro do TSE."""
import datetime as dt

import pytest

from eleicoes.tratamento import pesquisas as P


@pytest.mark.parametrize("texto,esperado", [
    ("30 Set–01 Out", (30, 9, None, 1, 10, None)),
    ("28–29 Out 2022", (28, 10, None, 29, 10, 2022)),
    ("5–6 de outubro de 2018", (5, 10, None, 6, 10, 2018)),
    ("3 Out", (3, 10, None, 3, 10, None)),
    ("22 Fev - 25 Fev", (22, 2, None, 25, 2, None)),
    ("31–1 Abr", (31, 3, None, 1, 4, None)),        # sem o mês inicial: o dia 31 é do mês anterior
    ("28 Dez – 03 Jan", (28, 12, None, 3, 1, None)),
])
def test_datas_de_campo(texto, esperado):
    assert P._datas(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("Globo / Datafolha [28] BR-09479/2022", ("Globo", "Datafolha", "BR094792022")),
    ("CNT/MDA BR-04819/2018", ("CNT", "MDA", "BR048192018")),
    ("Arko Advice/AtlasIntel [3]", ("Arko Advice", "AtlasIntel", None)),
    ("DataFolha [ 21 ]", (None, "Datafolha", None)),
    ("XP/Ipespe BR‐ 02934/2018", ("XP", "Ipespe", "BR029342018")),   # hífen tipográfico
    ("Ipec BR-009327/2022", (None, "Ipec", "BR093272022")),               # seis dígitos
    ("Ibope BR-0446/2018", (None, "Ibope", "BR004462018")),               # quatro dígitos
])
def test_celula_da_pesquisa(texto, esperado):
    assert P._pesquisa(texto) == esperado


def test_numeros_das_celulas():
    assert P._numero("40,7%") == 40.7 and P._numero("22% (Haddad)") == 22 and P._numero("—") is None
    assert P._amostra("12.800") == 12800 and P._amostra("4 006") == 4006


def _registro(**kw):
    base = {"protocolo": "BR000012026", "empresa": "QUAEST PESQUISA E CONSULTORIA LTDA", "fantasia": "QUAEST",
            "inicio": dt.date(2026, 9, 30), "fim": dt.date(2026, 10, 2), "amostra": 3702}
    return {**base, **kw}


def test_ligacao_exige_o_mesmo_instituto():
    p = {"registro_wikipedia": None, "contratante": "Genial", "instituto": "Quaest", "amostra": 3700,
         "inicio": dt.date(2026, 9, 30), "fim": dt.date(2026, 10, 3)}
    outro = _registro(protocolo="BR000022026", empresa="OUTRO INSTITUTO LTDA", fantasia="OUTRO", amostra=3700)
    assert P.ligar(p, {}, [outro]) == (None, "Quaest", "não encontrada")
    assert P.ligar(p, {}, [outro, _registro()]) == ("BR000012026", "Quaest", "instituto, amostra e datas")
    assert P.ligar(p, {}, [_registro(amostra=4100)])[2] == "não encontrada"  # amostra 10% maior


def test_cenario_incompleto_do_primeiro_turno_fica_de_fora():
    linha = {"turno": 1, "soma_candidatos": 92.0, "outros": 0, "nao_validos": None, "n_candidatos": 2}
    assert not P.completa(linha)
    assert P.completa({**linha, "n_candidatos": 13})
    assert P.completa({**linha, "turno": 2})
    assert not P.completa({**linha, "n_candidatos": 13, "soma_candidatos": 110.0})


def test_datafolha_da_vespera_do_segundo_turno_de_2022():
    """Datafolha, 28–29/10/2022, 8.308 entrevistas: Lula 49% × Bolsonaro 45% (Wikipedia, revisão guardada)."""
    arq = P.saida("pesquisas", 2022)
    if not arq.exists():
        pytest.skip("rode `uv run eleicoes pesquisas`")
    import duckdb
    r = duckdb.sql(f"""SELECT petismo, bolsonarismo, registro FROM '{arq.as_posix()}'
                       WHERE turno = 2 AND instituto = 'Datafolha' AND fim = DATE '2022-10-29'""").fetchall()
    assert r == [(49.0, 45.0, "BR082972022")]


@pytest.mark.parametrize("ano,minimo", [(2018, 1.0), (2022, 0.94), (2026, 0.85)])
def test_cobertura_da_ligacao_com_o_registro(ano, minimo):
    arq = P.saida("pesquisas", ano)
    if not arq.exists():
        pytest.skip("rode `uv run eleicoes pesquisas`")
    import duckdb
    (cobertura,) = duckdb.sql(f"SELECT avg((registro IS NOT NULL)::INT) FROM '{arq.as_posix()}'").fetchone()
    assert cobertura >= minimo


def test_percentual_limite_menor_que():
    assert P._numero("<0,9%") == 0.9 and P._menor("<0,9%") and P._menor(" <1%") and not P._menor("0,9%")


def test_atlasintel_ja_em_votos_validos_nao_perde_pontos_com_os_limites():
    """AtlasIntel, 27/9–2/10/2026, em votos válidos: Lula 47% × Flávio 44,1%, e oito candidatos com "<0,9%".
    Contados como 0,45% cada, os limites somariam 3,6 pontos além de 100% e tirariam ~1,2 ponto de cada um."""
    arq = P.saida("pesquisas", 2026)
    if not arq.exists():
        pytest.skip("rode `uv run eleicoes pesquisas`")
    import duckdb
    r = duckdb.sql(f"""SELECT petismo_validos, bolsonarismo_validos FROM '{arq.as_posix()}'
                       WHERE turno = 1 AND instituto = 'AtlasIntel' AND fim = DATE '2026-10-02'""").fetchall()
    assert r == [(47.0, 44.1)]
