"""Testes das tabelas processadas contra os totais oficiais do TSE. Pulam se os dados ainda não foram processados."""
import duckdb
import pytest

from eleicoes import config
from eleicoes.tratamento import boletins, locais, oficial, votacao_secao
from eleicoes.tratamento import municipios as tab_municipios

PARES = [(a, t) for a in (2018, 2022) for t in (1, 2)] + [(2026, 1)]
NIVEIS = {"Brasil": (), "UF": ("sg_uf",), "zona": ("cd_municipio", "nr_zona")}


def _exige(*arquivos):
    faltam = [a for a in arquivos if not a.exists()]
    if faltam:
        pytest.skip(f"rode `uv run eleicoes processar` ({faltam[0].name} não existe)")
    return [a.as_posix() for a in arquivos]


@pytest.mark.parametrize("nivel", NIVEIS)
@pytest.mark.parametrize("ano,turno", PARES)
def test_votos_batem_com_o_oficial_salvo_divergencias_conhecidas(ano, turno, nivel):
    _exige(boletins.saida("votos_secao", ano, turno), oficial.saida(ano))
    chave = NIVEIS[nivel]
    assert oficial.diferencas(duckdb.connect(), ano, turno, chave) == oficial.esperadas(ano, turno, chave)


@pytest.mark.parametrize("ano,turno", PARES)
def test_uma_linha_por_secao_e_campos_somam_os_validos(ano, turno):
    (s,) = _exige(boletins.saida("secoes", ano, turno))
    n, distintas, ruins = duckdb.sql(f"""
        SELECT count(*), count(DISTINCT (sg_uf, cd_municipio, nr_zona, nr_secao)),
               count(*) FILTER (votos_petismo + votos_bolsonarismo + votos_outros <> votos_validos
                                OR votos_validos + votos_brancos + votos_nulos > qt_comparecimento)
        FROM '{s}'""").fetchone()
    assert n == distintas and ruins == 0


@pytest.mark.parametrize("ano,turno", PARES)
def test_municipios_brasileiros_tem_codigo_ibge(ano, turno):
    (s,) = _exige(boletins.saida("secoes", ano, turno))
    assert duckdb.sql(f"SELECT count(*) FROM '{s}' WHERE sg_uf <> 'ZZ' AND cd_ibge IS NULL").fetchone() == (0,)


@pytest.mark.parametrize("ano,turno", PARES)
def test_hora_de_chegada_do_boletim_so_existe_a_partir_de_2022(ano, turno):
    (s,) = _exige(boletins.saida("secoes", ano, turno))
    com = duckdb.sql(f"SELECT avg((dt_bu_recebido IS NOT NULL)::INT) FROM '{s}' WHERE qt_comparecimento > 0").fetchone()[0]
    assert com > 0.999 if ano >= 2022 else com == 0


def test_boletins_e_votacao_por_secao_dao_os_mesmos_votos():
    """2026, 1º turno: os dois arquivos do TSE com os votos de cada seção batem em todas as seções."""
    _exige(boletins.saida("secoes", 2026, 1), votacao_secao.saida(2026, 1))
    d = votacao_secao.diferencas_dos_boletins(duckdb.connect(), 2026, 1)
    assert d["secoes"] == 499_206 and d["diferentes"] == []


def test_formato_de_2026_dos_boletins_e_lido_inteiro():
    """Datas em aaaa-mm-dd e colunas renomeadas em 2026: nenhum horário nem biometria vazios por erro de leitura."""
    (s,) = _exige(boletins.saida("secoes", 2026, 1))
    sem = duckdb.sql(f"""SELECT count(*) FILTER (dt_bu_recebido IS NULL), count(*) FILTER (dt_abertura IS NULL),
                                count(*) FILTER (qt_eleitores_biometria_nh IS NULL) FROM '{s}'""").fetchone()
    assert sem[0] == 0 and sem[1] < 100 and sem[2] < 100


@pytest.mark.parametrize("ano", [2018, 2022, 2026])
def test_coordenadas_no_brasil_ficam_dentro_do_territorio(ano):
    (lv,) = _exige(locais.saida(ano))
    fora = duckdb.sql(f"""SELECT count(*) FROM '{lv}' WHERE sg_uf <> 'ZZ' AND lat IS NOT NULL
        AND NOT (lat BETWEEN {locais.LAT_BR[0]} AND {locais.LAT_BR[1]} AND lon BETWEEN {locais.LON_BR[0]} AND {locais.LON_BR[1]})""")
    assert fora.fetchone() == (0,)


def test_tabela_de_municipios_cobre_o_brasil_inteiro():
    (m,) = _exige(tab_municipios.SAIDA)
    total, sem = duckdb.sql(f"SELECT count(*) FILTER (sg_uf <> 'ZZ'), count(*) FILTER (sg_uf <> 'ZZ' AND cd_ibge IS NULL) FROM '{m}'").fetchone()
    assert total >= 5570 and sem == 0
    assert config.REGIAO_DA_UF.keys() >= {r[0] for r in duckdb.sql(f"SELECT DISTINCT sg_uf FROM '{m}'").fetchall()}


def test_divergencias_conhecidas_estao_no_formato_certo():
    for (ano, turno, uf, mun, zona), difs in oficial.DIVERGENCIAS_CONHECIDAS.items():
        assert ano in config.anos() and turno in (1, 2) and uf in config.REGIAO_DA_UF
        assert len(mun) == 5 and isinstance(zona, int) and all(isinstance(n, int) for n in difs)
