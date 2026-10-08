"""Testes das séries da apuração no tempo: lógica com dados sintéticos e coerência com os dados reais."""
import datetime as dt

import duckdb
import pytest

from eleicoes.analises import apuracao, resultados
from eleicoes.tratamento import boletins, conexao

INICIO = dt.datetime(2022, 10, 2, 17, 0)


def _chegadas(con, linhas):
    con.execute("""CREATE OR REPLACE TEMP TABLE chegadas (regiao VARCHAR, sg_uf VARCHAR, cd_municipio VARCHAR,
                   nr_zona SMALLINT, nr_secao SMALLINT, chegada TIMESTAMP, votos_validos INT, votos_petismo INT,
                   votos_bolsonarismo INT)""")
    con.executemany("INSERT INTO chegadas VALUES (?, 'XX', '00001', 1, ?, ?, ?, ?, ?)", linhas)


def test_serie_acumula_por_minuto_e_junta_o_que_chegou_antes_do_inicio():
    con = duckdb.connect()
    _chegadas(con, [
        ("Exterior", 1, dt.datetime(2022, 10, 2, 9, 0), 10, 2, 8),      # antes das 17h: entra no 1º minuto
        ("Sul", 2, dt.datetime(2022, 10, 2, 17, 5, 30), 100, 30, 70),
        ("Nordeste", 3, dt.datetime(2022, 10, 2, 17, 9), 100, 80, 20),
        ("Nordeste", 4, dt.datetime(2022, 10, 2, 17, 9, 59), 100, 80, 20),
    ])
    s = apuracao.serie(con, INICIO)
    assert s["t"] == [0, 5, 9]
    assert s["regioes"]["Brasil"]["secoes"] == [1, 2, 4]
    assert s["regioes"]["Brasil"]["petismo"] == [2, 32, 192]
    assert s["regioes"]["Nordeste"]["validos"] == [0, 0, 200]
    assert s["totais"]["Brasil"] == {"secoes": 4, "validos": 310, "petismo": 192, "bolsonarismo": 118}
    # depois de 1% das seções: bolsonarismo à frente no começo, petismo passa à frente às 17h09
    assert apuracao.viradas(s) == [{"t": 9, "pct_secoes": 100.0, "lider": "petismo"}]
    assert apuracao.minuto_quase_total(s) == 9


PARES = [(a, t) for a in (2018, 2022) for t in (1, 2)] + [(2026, 1)]


def _exige(ano, turno):
    if not boletins.saida("secoes", ano, turno).exists():
        pytest.skip("rode `uv run eleicoes processar`")


@pytest.mark.parametrize("ano,turno", PARES)
def test_serie_real_termina_no_total_dos_boletins_e_nunca_diminui(ano, turno):
    _exige(ano, turno)
    con = conexao()
    s = apuracao.gerar(con, ano, turno)
    secoes = boletins.saida("secoes", ano, turno).as_posix()
    validos, pt, bo = con.execute(f"""SELECT sum(votos_validos), sum(votos_petismo), sum(votos_bolsonarismo)
                                      FROM '{secoes}' WHERE qt_comparecimento > 0""").fetchone()
    assert (s["totais"]["Brasil"]["validos"], s["totais"]["Brasil"]["petismo"], s["totais"]["Brasil"]["bolsonarismo"]) == (validos, pt, bo)
    for regiao in s["regioes"].values():
        for valores in regiao.values():
            assert all(a <= b for a, b in zip(valores, valores[1:]))
    assert s["tipo"] == ("exata" if ano >= 2022 else "estimada")


def test_virada_do_2o_turno_de_2022_bate_com_a_historia():
    """Lula passou Bolsonaro às 18h44 de 30/10/2022, com cerca de 68% das urnas apuradas (horário do TSE)."""
    _exige(2022, 2)
    (v,) = apuracao.gerar(conexao(), 2022, 2)["viradas"]
    assert v["lider"] == "petismo" and 66 < v["pct_secoes"] < 70 and 100 <= v["t"] <= 106


def test_chegada_dos_boletins_de_2026_nao_foi_reescrita():
    """Na noite de 04/10/2026, o painel ao vivo viu 62% das seções recebidas até 19h; depois da apuração, o TSE
    reescreveu os horários do arquivo de seções do site de resultados, que passou a dar 12%. A chegada nos boletins
    de urna tem de bater com a noite, não com o arquivo reescrito: é ela que faz a curva de 2026 ser exata."""
    _exige(2026, 1)
    s = apuracao.gerar(conexao(), 2026, 1)
    ate_19h = next(n for t, n in zip(reversed(s["t"]), reversed(s["regioes"]["Brasil"]["secoes"])) if t <= 120)
    assert 0.58 < ate_19h / s["totais"]["Brasil"]["secoes"] < 0.65


def test_metodo_de_2018_testado_em_2026_com_os_atrasos_de_2022():
    _exige(2026, 1)
    v = {x["alvo"]: x for x in apuracao.validar_estimativa(conexao())}
    erro = v["2026, 1º turno"]["erro_pct_validos"]
    assert max(erro["petismo"]["media"], erro["bolsonarismo"]["media"]) < 1


def test_resultado_final_usa_o_total_oficial():
    _exige(2022, 2)
    r = resultados.gerar(conexao())["2022"]["2"]["Brasil"]
    assert (r["petismo"], r["bolsonarismo"], r["outros"]) == (60345999, 58206354, 0)
    assert sum(reg["validos"] for reg in resultados.gerar(conexao())["2022"]["2"]["regioes"].values()) == r["validos"]


def test_tendencia_nao_fica_para_tras_no_fim_da_serie():
    """Pesquisas subindo 0,2 ponto por dia: a regressão linear local acompanha até a última data, enquanto uma
    média ponderada (só com pesquisas do passado na ponta) ficaria ~1 ponto atrás."""
    from eleicoes.analises import pesquisas as A
    d0 = dt.date(2026, 9, 1)
    ps = [{"fim": d0 + dt.timedelta(days=i), "amostra": 2000, "petismo_validos": 40 + 0.2 * i,
           "bolsonarismo_validos": 50 - 0.2 * i} for i in range(0, 31, 2)]
    t = A.tendencia(ps, d0 + dt.timedelta(days=30))
    assert t["datas"][-1] == "2026-10-01"
    assert t["petismo"][-1] == pytest.approx(46.0, abs=0.01) and t["bolsonarismo"][-1] == pytest.approx(44.0, abs=0.01)
    assert t["petismo"][15] == pytest.approx(43.0, abs=0.01)
