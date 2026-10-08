"""Testes do mapa: coordenadas completadas, votos por local e os arquivos do site. Pulam sem os dados processados."""
import json

import duckdb
import numpy as np
import pytest
import shapely

from eleicoes import config
from eleicoes.analises import mapa
from eleicoes.tratamento import coordenadas, conexao, locais, votacao_secao

ANOS = [a for a in config.anos() if coordenadas.saida(a).exists()]
SITE = config.RAIZ / "site" / "src" / "data" / "mapa"


def _exige_mapa(ano):
    if not coordenadas.saida(ano).exists():
        pytest.skip(f"rode `uv run eleicoes processar` (mapa de {ano} não existe)")
    return coordenadas.saida(ano).as_posix()


def _turnos(arq):
    colunas = [c[0] for c in duckdb.sql(f"DESCRIBE SELECT * FROM '{arq}'").fetchall()]
    return [t for t in (1, 2) if f"t{t}_validos" in colunas]


@pytest.mark.parametrize("ano", ANOS or [2022])
def test_todo_local_tem_coordenada_no_brasil_e_metodo_conhecido(ano):
    arq = _exige_mapa(ano)
    sem, fora, metodo = duckdb.sql(f"""SELECT count(*) FILTER (lat IS NULL OR lon IS NULL),
        count(*) FILTER (NOT (lat BETWEEN {locais.LAT_BR[0]} AND {locais.LAT_BR[1]}
                              AND lon BETWEEN {locais.LON_BR[0]} AND {locais.LON_BR[1]})),
        count(*) FILTER (nivel NOT BETWEEN 0 AND 7) FROM '{arq}'""").fetchone()
    assert (sem, fora, metodo) == (0, 0, 0)
    precisao = {n: p for n, (_, _, p) in coordenadas.METODOS.items()}
    for nivel, p in duckdb.sql(f"SELECT DISTINCT nivel, precisao FROM '{arq}'").fetchall():
        assert precisao[nivel] == p


@pytest.mark.parametrize("ano", ANOS or [2022])
def test_posicoes_do_proprio_local_ficam_no_municipio(ano):
    """Métodos 0 a 3 (posição do próprio local): a até 2 km do polígono do município. As aproximações (4 a 7)
    caem no máximo a algumas dezenas de km, porque são medianas de outros locais do mesmo município."""
    arq = _exige_mapa(ano)
    r = duckdb.sql(f"SELECT cd_ibge, lat, lon, nivel FROM '{arq}'").fetchnumpy()
    poli = coordenadas.poligonos()
    km = np.zeros(len(r["nivel"]))
    for c in np.unique(r["cd_ibge"]):
        if (g := poli.get(int(c))) is not None:
            i = np.flatnonzero(r["cd_ibge"] == c)
            km[i] = shapely.distance(g, shapely.points(r["lon"][i], r["lat"][i])) * 111.2
    proprio = r["nivel"] <= 3
    assert km[proprio].max() <= coordenadas.TOLERANCIA_KM + 0.01
    assert km[~proprio].max() < 30


@pytest.mark.parametrize("ano", ANOS or [2022])
def test_votos_dos_locais_somam_os_das_secoes_no_brasil(ano):
    arq = _exige_mapa(ano)
    for t in _turnos(arq):
        fonte = votacao_secao.fonte_secoes(ano, t).as_posix()
        esperado = duckdb.sql(f"""SELECT count(*), sum(votos_validos), sum(votos_petismo), sum(votos_bolsonarismo)
                                  FROM '{fonte}' WHERE sg_uf <> 'ZZ'""").fetchone()
        achado = duckdb.sql(f"""SELECT sum(t{t}_secoes), sum(t{t}_validos), sum(t{t}_petismo), sum(t{t}_bolsonarismo)
                                FROM '{arq}'""").fetchone()
        assert achado == esperado


@pytest.mark.parametrize("ano", ANOS or [2022])
def test_um_local_por_linha(ano):
    arq = _exige_mapa(ano)
    n, distintos = duckdb.sql(f"""SELECT count(*), count(DISTINCT (cd_municipio, nr_zona, nr_local_votacao))
                                  FROM '{arq}'""").fetchone()
    assert n == distintos


def test_metodos_que_dao_a_posicao_do_proprio_local_quase_nao_erram():
    v = coordenadas.ler_validacao()
    if not v:
        pytest.skip("rode `uv run eleicoes processar` (validação das coordenadas não existe)")
    for ano, metodos in v.items():
        for nivel in (1, 2, 3):
            assert metodos[nivel]["mediana_km"] < 0.1, (ano, nivel)
        assert metodos[1]["acima_1km"] < 0.02, ano
        assert metodos[4]["mediana_km"] < 1, ano  # bairro: aproximação de ~0,5 km
        assert metodos[4]["mediana_km"] < metodos[5]["mediana_km"] < metodos[6]["mediana_km"] + 0.5, ano


def test_votacao_por_secao_bate_com_o_resultado_final_por_uf():
    pares = [(a, t) for a in config.anos() for t in (1, 2)
             if votacao_secao.saida(a, t).exists() and votacao_secao.pasta_final(a, t).exists()]
    if not pares:
        pytest.skip("sem votação por seção processada com resultado final para conferir")
    con = conexao()
    for a, t in pares:
        assert votacao_secao.diferencas_do_resultado_final(con, a, t) == {}, (a, t)


@pytest.mark.parametrize("ano", ANOS or [2022])
def test_arquivo_do_site_tem_os_votos_dos_locais(ano):
    arq = _exige_mapa(ano)
    site = SITE / f"locais_{ano}.json"
    if not site.exists():
        pytest.skip("rode `uv run eleicoes site`")
    d = json.loads(site.read_text("utf-8"))
    nomes = json.loads((SITE / f"nomes_{ano}.json").read_text("utf-8"))
    assert d["n"] == len(nomes) == len(d["precisao"]) == len(d["lon"]) == len(d["lat"]) == len(d["municipio"])
    for t in d["turnos"]:
        v = d["votos"][str(t)]
        esperado = duckdb.sql(f"SELECT sum(t{t}_petismo), sum(t{t}_bolsonarismo) FROM '{arq}'").fetchone()
        assert (sum(v["petismo"]), sum(v["bolsonarismo"])) == esperado
    municipios = json.loads((SITE / "municipios.json").read_text("utf-8"))
    assert 0 <= min(np.cumsum(d["municipio"])) and max(np.cumsum(d["municipio"])) < len(municipios["codigo"])


def test_malha_do_site_tem_todos_os_municipios_do_ibge():
    malha = SITE / "malha.json"
    if not malha.exists():
        pytest.skip("rode `uv run eleicoes site`")
    t = json.loads(malha.read_text("utf-8"))
    geometrias = t["objects"]["municipios"]["geometries"]
    assert len(geometrias) >= 5570 and all(len(g["id"]) == 7 for g in geometrias)
    usados = {abs(~i if i < 0 else i) for g in geometrias for poli in ([g["arcs"]] if g["type"] == "Polygon" else g["arcs"])
              for anel in poli for i in anel}
    assert usados == set(range(len(t["arcs"])))


@pytest.mark.parametrize("entrada, saida", [
    ("ESCOLA ESTADUAL PROFESSOR JOÃO DA SILVA", "Escola Estadual Professor João da Silva"),
    ("EMEF DOM PEDRO II", "EMEF Dom Pedro II"),
    ("E.E. 7 DE SETEMBRO", "E.E. 7 de Setembro"),
    ("COLÉGIO SANTA-MARIA", "Colégio Santa-Maria"),
    ("", ""),
])
def test_titulo_dos_nomes_dos_locais(entrada, saida):
    assert mapa.titulo(entrada) == saida
