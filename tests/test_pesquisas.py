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


@pytest.mark.parametrize("celulas,instituto", [
    (["Nexus/BTG Pactual", "BTG/Nexus", "Nexus"], "Nexus"),  # a Nexus faz as pesquisas do BTG Pactual em 2026
    (["Apex/Futura", "Futura/Apex", "Futura Inteligência"], "Futura"),
    (["Vox", "Vox Brasil"], "Vox Brasil"),
    (["Alfa", "Alfa Inteligência", "Alfa/TMC"], "Alfa Inteligência"),
    (["Indexa/Broadcast", "Broadcast/Indexa"], "Indexa"),
    (["BTG Pactual/FSB", "BTG/FSB"], "FSB"),  # 2018 e 2022
])
def test_um_nome_por_instituto_em_qualquer_ordem(celulas, instituto):
    assert {P._pesquisa(c)[1] for c in celulas} == {instituto}
    assert P._pesquisa("Nexus/BTG Pactual")[0] == "BTG Pactual" and P._pesquisa("Futura/Apex")[0] == "Apex"


@pytest.mark.parametrize("gravada,instituto", [
    ({"instituto": "BTG Pactual", "contratante": "Nexus"}, "Nexus"),
    ({"instituto": "Apex", "contratante": "Futura"}, "Futura"),
    ({"instituto": "Vox", "contratante": None}, "Vox Brasil"),
    ({"instituto": "Alfa", "contratante": "TMC"}, "Alfa Inteligência"),
    ({"instituto": "Quaest", "contratante": "Genial"}, "Quaest"),
    ({"instituto": "Arrow", "contratante": "Vetor"}, "Arrow"),  # nenhuma das duas conhecida: o instituto gravado
])
def test_nome_de_hoje_de_uma_pesquisa_gravada_com_o_nome_antigo(gravada, instituto):
    assert P.canonico(gravada) == instituto


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


def test_futura_registrada_em_nome_da_100_cidades():
    """Em 2026 as pesquisas da Futura estão no registro do TSE em nome da 100% Cidades Participações: a de 07 a
    10/10/2026, com 2.000 entrevistas, é o BR-00650/2026. Em 2022, ela registrava em nome próprio."""
    p = {"registro_wikipedia": None, "contratante": "Apex", "instituto": "Futura", "amostra": 2000,
         "inicio": dt.date(2026, 10, 7), "fim": dt.date(2026, 10, 10)}
    cidades = _registro(protocolo="BR006502026", empresa="100% CIDADES PARTICIPACOES LTDA", fantasia="100 CIDADES",
                        inicio=dt.date(2026, 10, 7), fim=dt.date(2026, 10, 10), amostra=2000)
    assert P.ligar(p, {}, [cidades]) == ("BR006502026", "Futura", "instituto, amostra e datas")
    assert P._mesmo_instituto("Futura", _registro(empresa="FUTURA CONSULTORIA E ASSESSORIA LTDA", fantasia="FUTURA"))
    assert not P._mesmo_instituto("Apex", cidades)


def test_ligacao_exige_algum_dia_de_campo_em_comum():
    """A Datafolha de 28/09 a 01/10/2026 (2.002 entrevistas na tabela do 2º turno) não é o registro de 02 a 03/10, da
    pesquisa seguinte, de 01 a 03/10. A Ipec registrava 7 dias e fazia o campo nos 3 últimos: continua ligada."""
    datafolha = _registro(protocolo="BR079332026", empresa="DATAFOLHA INSTITUTO DE PESQUISAS LTDA.", fantasia="#NULO#",
                          inicio=dt.date(2026, 10, 2), fim=dt.date(2026, 10, 3), amostra=2010)
    p = {"registro_wikipedia": None, "contratante": None, "instituto": "Datafolha", "amostra": 2002}
    assert P.ligar({**p, "inicio": dt.date(2026, 9, 28), "fim": dt.date(2026, 10, 1)}, {}, [datafolha])[0] is None
    assert P.ligar({**p, "inicio": dt.date(2026, 10, 1), "fim": dt.date(2026, 10, 3)}, {}, [datafolha])[0] == "BR079332026"
    ipec = _registro(protocolo="BR052562022", empresa="INTELIGENCIA EM PESQUISA E CONSULTORIA LTDA", fantasia="IPEC",
                     inicio=dt.date(2022, 10, 23), fim=dt.date(2022, 10, 29), amostra=4272)
    p = {"registro_wikipedia": None, "contratante": None, "instituto": "Ipec", "amostra": 4272,
         "inicio": dt.date(2022, 10, 27), "fim": dt.date(2022, 10, 29)}
    assert P.ligar(p, {}, [ipec])[0] == "BR052562022"


TABELA_DO_SEGUNDO_TURNO = """<h2>Segundo turno</h2><h3>Lula e Flávio Bolsonaro</h3><table class="wikitable">
<tr><th>Instituto</th><th>Data</th><th>Amostra</th><th>Lula</th><th>Flávio</th></tr>
<tr><td>Nexus/BTG</td><td>16–18 Out 2026</td><td>2.000</td><td>47%</td><td>48%</td></tr>
<tr><td>Nexus/BTG Pactual</td><td>10–12 Out 2026</td><td>2.000</td><td>46%</td><td>47%</td></tr>
<tr><td>Apex/Futura</td><td>7–10 Out 2026</td><td>2.000</td><td>44%</td><td>49%</td></tr>
<tr><td>Datafolha</td><td>1–3 Out 2026</td><td>2.002</td><td>46%</td><td>44%</td></tr>
<tr><td>Datafolha</td><td>28 Set–1 Out 2026</td><td>2.002</td><td>48%</td><td>45%</td></tr>
<tr><td>Futura/Apex</td><td>11–15 Set 2026</td><td>2.000</td><td>43%</td><td>48%</td></tr>
</table>"""


def test_tabela_com_o_instituto_antes_ou_depois_do_contratante(monkeypatch):
    """Da célula ao nome publicado: "Nexus/BTG" e "Nexus/BTG Pactual" são a Nexus, e "A última pesquisa de cada
    instituto" mostra uma linha só; "Futura/Apex" e "Apex/Futura" são a Futura, ligada ao registro da 100% Cidades."""
    nexus = ("NEXUS PESQUISA E INTELIGENCIA DE DADOS LTDA", "NEXUS")
    cidades = ("100% CIDADES PARTICIPACOES LTDA", "100 CIDADES")
    datafolha = ("DATAFOLHA INSTITUTO DE PESQUISAS LTDA.", "#NULO#")
    registros = [_registro(protocolo=n, empresa=e, fantasia=f, inicio=dt.date(2026, *i), fim=dt.date(2026, *fim), amostra=a)
                 for n, (e, f), i, fim, a in [("BR000012026", nexus, (10, 16), (10, 18), 2000),
                                              ("BR000022026", nexus, (10, 10), (10, 12), 2000),
                                              ("BR006502026", cidades, (10, 7), (10, 10), 2000),
                                              ("BR079332026", datafolha, (10, 2), (10, 3), 2010),
                                              ("BR007492026", cidades, (9, 11), (9, 17), 2000)]]
    monkeypatch.setattr(P, "ler_registro", lambda ano: registros)
    _, pesquisas, _ = P.montar(2026, TABELA_DO_SEGUNDO_TURNO)
    assert [(p["fim"].isoformat(), p["instituto"], p["contratante"], p["registro"]) for p in pesquisas] == [
        ("2026-09-15", "Futura", "Apex", "BR007492026"),
        ("2026-10-01", "Datafolha", None, None),  # o registro de 02 a 03/10 é o da pesquisa seguinte
        ("2026-10-03", "Datafolha", None, "BR079332026"),
        ("2026-10-10", "Futura", "Apex", "BR006502026"),
        ("2026-10-12", "Nexus", "BTG Pactual", "BR000022026"),
        ("2026-10-18", "Nexus", "BTG", "BR000012026"),
    ]


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


@pytest.mark.parametrize("ano,minimo", [(2018, 1.0), (2022, 0.94), (2026, 0.93)])
def test_cobertura_da_ligacao_com_o_registro(ano, minimo):
    arq = P.saida("pesquisas", ano)
    if not arq.exists():
        pytest.skip("rode `uv run eleicoes pesquisas`")
    import duckdb
    (cobertura,) = duckdb.sql(f"SELECT avg((registro IS NOT NULL)::INT) FROM '{arq.as_posix()}'").fetchone()
    assert cobertura >= minimo


def test_institutos_de_2026_com_um_nome_so():
    """Na revisão guardada: a Futura ligada ao registro (100% Cidades); nenhum dos nomes que dependiam da ordem na
    célula ou da grafia (BTG Pactual × Nexus, Apex × Futura, Vox × Vox Brasil, Alfa × Alfa Inteligência); e cada
    registro do TSE ligado a uma pesquisa só em cada turno (as duas Datafolha de 2002 entrevistas ficavam com um)."""
    arq = P.saida("pesquisas", 2026)
    if not arq.exists():
        pytest.skip("rode `uv run eleicoes pesquisas`")
    import duckdb
    institutos = {i for (i,) in duckdb.sql(f"SELECT DISTINCT instituto FROM '{arq.as_posix()}'").fetchall()}
    assert {"Nexus", "Futura", "Vox Brasil", "Alfa Inteligência"} <= institutos
    assert not institutos & {"BTG Pactual", "Apex", "Vox", "Alfa"}
    assert duckdb.sql(f"""SELECT registro FROM '{arq.as_posix()}'
                          WHERE turno = 2 AND instituto = 'Futura' AND fim = DATE '2026-10-10'""").fetchall() == [("BR006502026",)]
    assert duckdb.sql(f"""SELECT turno, registro FROM '{arq.as_posix()}' WHERE registro IS NOT NULL
                          GROUP BY ALL HAVING count(*) > 1""").fetchall() == []


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
