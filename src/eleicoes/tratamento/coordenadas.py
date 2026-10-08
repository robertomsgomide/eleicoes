"""Coordenadas de cada local de votação, completando as que faltam, e os votos do local em cada turno (mapa).

  mapa/locais_<ano>.parquet   um local de votação por linha (os que tiveram seções no ano, fora o exterior)

O TSE publica a latitude e a longitude de cada seção no arquivo de locais de votação, mas não de todas: faltam em
18% das seções de 2018 (quase todo MG e ES), 6% de 2022 e 1% de 2026. Também são descartadas as coordenadas a mais
de 2 km do município (pela malha do IBGE) e as repetidas em 3 ou mais locais de nomes diferentes do mesmo
município (o centro da cidade usado como posição padrão). As que faltam são completadas, nesta ordem:

  1. mesmo local em outra eleição: mesmo município, zona e número de local, com nome parecido ou mesmo endereço,
     na eleição mais próxima, de 2016 a 2026 (as municipais entram só com os locais), com coordenada válida;
  2. mesmo nome no município: outro local do município com o mesmo nome (sem palavras genéricas como "escola
     estadual"), em qualquer eleição, desde que todos os que têm esse nome estejam no mesmo lugar;
  3. mesmo endereço no município (só endereços com número), com a mesma condição;
  4. aproximada pelo bairro: mediana dos locais do mesmo bairro, se o bairro é específico e compacto;
  5. aproximada pela zona eleitoral e 6. pelo município: mediana dos locais da zona / do município;
  7. sem nenhum local com coordenada no município: um ponto dentro do polígono do município.

Os métodos 1 a 3 dão a posição do próprio local; 4 a 7 são aproximações, com um raio (`raio_km`) que o mapa usa
para espalhar os votos do local. `validar` mede o erro de cada método escondendo a coordenada de quem a tem.
"""
import functools
import json

import numpy as np
import shapely

from eleicoes import config
from eleicoes.tratamento import conexao, locais, votacao_secao
from eleicoes.tratamento import municipios as tab_municipios

# Arquivos de locais de votação usados como referência (os que existirem em dados/processado)
ANOS_LOCAIS = (2016, 2018, 2020, 2022, 2024, 2026)
TOLERANCIA_KM = 2.0       # distância máxima até o polígono do município (a malha do IBGE é simplificada)
NOMES_NA_MESMA_COORD = 3  # tantos nomes diferentes na mesma coordenada: é a posição padrão, não a do local
SIMILARIDADE_NOME = 0.8   # nível 1: nome parecido (Jaro-Winkler) com o do mesmo número de local na outra eleição
DISPERSAO_BAIRRO_KM = 1.5
RAIO_KM = {4: (0.3, 1.5), 5: (1.0, 8.0), 6: (1.0, 8.0), 7: (2.0, 10.0)}  # limites do raio de espalhamento

PALAVRAS_GENERICAS = (
    "ESCOLA", "ESC", "ESTADUAL", "EST", "MUNICIPAL", "MUN", "E", "EE", "EM", "EMEF", "EMEI", "EEF", "EEEF", "EEEFM",
    "EMEIEF", "EEIEF", "DE", "DA", "DO", "DAS", "DOS", "COLEGIO", "COL", "CENTRO", "ENSINO", "FUNDAMENTAL", "MEDIO",
    "INFANTIL", "ENS", "FUND", "UNIDADE", "ESCOLAR", "PROFESSOR", "PROFESSORA", "PROF", "PROFA", "GRUPO", "INSTITUTO",
    "EDUCACIONAL", "CRECHE")
BAIRROS_VAGOS = ("", "ZONA RURAL", "RURAL", "AREA RURAL", "INTERIOR", "ZONA RURAL ZONA RURAL", "NAO INFORMADO",
                 "SEM BAIRRO", "POVOADO", "DISTRITO", "S N", "SN", "SITIO", "FAZENDA", "ASSENTAMENTO", "COMUNIDADE",
                 "LOCALIDADE")

# nível -> (código, descrição, precisão no mapa: 0 do TSE, 1 posição do próprio local, 2 bairro, 3 zona ou município)
METODOS = {
    0: ("tse", "coordenada do TSE para o próprio local", 0),
    1: ("outra_eleicao", "mesmo local em outra eleição", 1),
    2: ("mesmo_nome", "mesmo nome no município", 1),
    3: ("mesmo_endereco", "mesmo endereço no município", 1),
    4: ("bairro", "aproximada pelo bairro", 2),
    5: ("zona", "aproximada pela zona eleitoral", 3),
    6: ("municipio", "aproximada pelo município", 3),
    7: ("poligono", "ponto dentro do município", 3),
}


def saida(ano):
    return config.PROCESSADO / "mapa" / f"locais_{ano}.parquet"


def _norm(coluna):
    return f"trim(regexp_replace(upper(strip_accents(coalesce({coluna}, ''))), '[^A-Z0-9]+', ' ', 'g'))"


def _km(a, b):
    """Distância aproximada em km entre os pontos a e b (prefixos de colunas lat/lon), boa para poucos km."""
    return f"111.2 * sqrt(power({a}lat - {b}lat, 2) + power(({a}lon - {b}lon) * cos(radians({a}lat)), 2))"


@functools.cache
def poligonos():
    """{código IBGE: polígono do município} da malha do IBGE (qualidade intermediária)."""
    geo = json.loads((config.BRUTO / "ibge" / "malhas" / "municipios.geojson").read_text("utf-8"))
    return {int(f["properties"]["codarea"]): shapely.geometry.shape(f["geometry"]) for f in geo["features"]}


def referencias(con):
    """Tabela `ref`: cada local de votação de cada eleição de ANOS_LOCAIS, com a coordenada e se ela vale (`ok`)."""
    partes = [f"""SELECT {a} AS ano, l.sg_uf, l.cd_municipio, m.cd_ibge, l.nr_zona, l.nr_local_votacao AS nr_local,
                         min(nm_local_votacao) AS nm, min(endereco) AS endereco, min(bairro) AS bairro,
                         median(lat) FILTER (coord_ok) AS lat, median(lon) FILTER (coord_ok) AS lon,
                         sum(qt_eleitores) FILTER (turno = 1) AS eleitores
                  FROM '{locais.saida(a).as_posix()}' l
                  JOIN '{tab_municipios.SAIDA.as_posix()}' m USING (cd_municipio)
                  WHERE l.sg_uf <> 'ZZ' GROUP BY ALL"""
              for a in ANOS_LOCAIS if locais.saida(a).exists()]
    genericas = "|".join(PALAVRAS_GENERICAS)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE ref0 AS
        SELECT row_number() OVER () AS rid, *,
               {_norm('nm')} AS nm_n, {_norm('endereco')} AS end_n, {_norm('bairro')} AS bairro_n
        FROM ({' UNION ALL '.join(partes)})""")
    # Núcleo do nome: sem as palavras genéricas (duas passadas, porque o regex não sobrepõe os espaços)
    nucleo = "trim(regexp_replace(' ' || {} || ' ', ' (({}) )+', ' ', 'g'))"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE ref1 AS
        SELECT *, {nucleo.format(nucleo.format('nm_n', genericas), genericas)} AS nucleo FROM ref0""")

    # Distância de cada coordenada ao polígono do seu município (0 dentro; -1 se o IBGE não tem o polígono)
    r = con.execute("SELECT rid, cd_ibge, lat, lon FROM ref1 WHERE lat IS NOT NULL").fetchnumpy()
    km = np.full(len(r["rid"]), -1.0)
    cod = np.asarray(r["cd_ibge"])
    for c in np.unique(cod):
        if (g := poligonos().get(int(c))) is not None:
            i = np.flatnonzero(cod == c)
            km[i] = shapely.distance(g, shapely.points(r["lon"][i], r["lat"][i])) * 111.2
    distancias = {"rid": np.asarray(r["rid"]), "km": km}  # noqa: F841  (lida pelo DuckDB pelo nome)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE ref AS
        WITH repetidas AS (SELECT ano, cd_municipio, lat, lon FROM ref1 WHERE lat IS NOT NULL
                           GROUP BY ALL HAVING count(DISTINCT nm_n) >= {NOMES_NA_MESMA_COORD})
        SELECT r.* EXCLUDE (rid), d.km AS km_fora,
               rep.lat IS NOT NULL AS coord_repetida,
               r.lat IS NOT NULL AND d.km <= {TOLERANCIA_KM} AND rep.lat IS NULL AS ok
        FROM ref1 r LEFT JOIN distancias d USING (rid)
        LEFT JOIN repetidas rep ON rep.ano = r.ano AND rep.cd_municipio = r.cd_municipio
                                AND rep.lat = r.lat AND rep.lon = r.lon""")
    # Uma posição por local (a da eleição mais recente em que é válida) e os nomes de bairro de cada local
    con.execute("""CREATE OR REPLACE TEMP TABLE pontos AS
        SELECT cd_municipio, nr_zona, nr_local, arg_max(lat, ano) AS lat, arg_max(lon, ano) AS lon
        FROM ref WHERE ok GROUP BY ALL""")
    vagos = ", ".join(f"'{b}'" for b in BAIRROS_VAGOS)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE bairros AS
        SELECT DISTINCT cd_municipio, bairro_n, nr_zona, nr_local FROM ref
        WHERE bairro_n NOT IN ({vagos}) AND length(bairro_n) >= 3""")


def candidatos(con, ano):
    """Tabela `cand`: para cada local da tabela `alvo`, a coordenada que cada método (1 a 6) daria.

    Cada método ignora o próprio local (mesma zona e número) — no 1, só na própria eleição —, o que permite
    usar a mesma função para completar e para medir o erro (`validar`).
    """
    # A eleição mais próxima; no empate, a mais recente; entre locais da mesma eleição, a menor zona e número
    # (para o resultado não depender da ordem de leitura)
    ordem = f"(abs(b.ano - {ano}), -b.ano, b.nr_zona, b.nr_local)"
    outro_local = "NOT (b.nr_zona = a.nr_zona AND b.nr_local = a.nr_local)"
    chave = "a.cd_municipio, a.nr_zona, a.nr_local"
    exato = f"arg_min(b.lat, {ordem}) AS lat, arg_min(b.lon, {ordem}) AS lon, NULL::DOUBLE AS raio_km, arg_min(b.ano, {ordem}) AS ano_ref"
    mesmo_lugar = "max(b.lat) - min(b.lat) + max(b.lon) - min(b.lon) < 0.01"  # ~1 km

    def mediana(nivel, juncao, condicao="TRUE", minimo=1, dispersao_max=None):
        """Mediana das posições (`pontos`) de outros locais do mesmo grupo; raio = distância quadrática média."""
        disp = "111.2 * sqrt(var_pop(p.lat) + var_pop(p.lon * cos(radians(p.lat))))"
        lo, hi = RAIO_KM[nivel]
        filtro = f" AND coalesce({disp}, 0) <= {dispersao_max}" if dispersao_max else ""
        return f"""SELECT {chave}, {nivel} AS nivel, median(p.lat) AS lat, median(p.lon) AS lon,
                          greatest({lo}, least({hi}, coalesce({disp}, 0))) AS raio_km, NULL::SMALLINT AS ano_ref
                   FROM alvo a {juncao}
                   WHERE {condicao} AND NOT (p.nr_zona = a.nr_zona AND p.nr_local = a.nr_local)
                   GROUP BY ALL HAVING count(*) >= {minimo}{filtro}"""

    con.execute(f"""CREATE OR REPLACE TEMP TABLE cand AS
        SELECT {chave}, 1 AS nivel, {exato}
        FROM alvo a JOIN ref b ON b.cd_municipio = a.cd_municipio AND b.nr_zona = a.nr_zona AND b.nr_local = a.nr_local
        WHERE b.ano <> {ano} AND b.ok
          AND (jaro_winkler_similarity(a.nm_n, b.nm_n) >= {SIMILARIDADE_NOME} OR (a.end_n <> '' AND a.end_n = b.end_n))
        GROUP BY ALL
        UNION ALL
        SELECT {chave}, 2, {exato}
        FROM alvo a JOIN ref b ON b.cd_municipio = a.cd_municipio AND b.nucleo = a.nucleo
        WHERE b.ok AND length(a.nucleo) >= 5 AND {outro_local}
        GROUP BY ALL HAVING {mesmo_lugar}
        UNION ALL
        SELECT {chave}, 3, {exato}
        FROM alvo a JOIN ref b ON b.cd_municipio = a.cd_municipio AND b.end_n = a.end_n
        WHERE b.ok AND length(a.end_n) >= 8 AND regexp_matches(a.end_n, '[0-9]') AND {outro_local}
        GROUP BY ALL HAVING {mesmo_lugar}
        UNION ALL
        {mediana(4, '''JOIN bairros g ON g.cd_municipio = a.cd_municipio AND g.bairro_n = a.bairro_n
                       JOIN pontos p ON p.cd_municipio = g.cd_municipio AND p.nr_zona = g.nr_zona AND p.nr_local = g.nr_local''',
                 minimo=2, dispersao_max=DISPERSAO_BAIRRO_KM)}
        UNION ALL
        {mediana(5, 'JOIN pontos p ON p.cd_municipio = a.cd_municipio AND p.nr_zona = a.nr_zona')}
        UNION ALL
        {mediana(6, 'JOIN pontos p ON p.cd_municipio = a.cd_municipio')}""")


def _secoes(con, ano):
    """Tabela `secao_local`: cada seção com votos no ano (fora o exterior), com o turno e o local de votação.

    O local vem do arquivo de locais de votação, pela seção: em ~1% das seções o número do local no arquivo de
    votos difere do arquivo de locais (que o TSE regera depois), e é o do arquivo de locais que identifica o
    mesmo local nas outras eleições. Sem a seção no arquivo de locais, fica o número do arquivo de votos.
    """
    partes = [f"""SELECT turno, sg_uf, regiao, cd_municipio, cd_ibge, nr_zona, nr_secao, nr_local_votacao,
                         votos_validos, votos_petismo, votos_bolsonarismo, votos_outros
                  FROM '{f.as_posix()}' WHERE sg_uf <> 'ZZ'"""
              for t in (1, 2) if (f := votacao_secao.fonte_secoes(ano, t))]
    lv = locais.saida(ano).as_posix()
    con.execute(f"""CREATE OR REPLACE TEMP TABLE secao_local AS
        WITH l AS (SELECT turno, cd_municipio, nr_zona, nr_secao, min(nr_local_votacao) AS nr_local
                   FROM '{lv}' GROUP BY ALL),
             l1 AS (SELECT * FROM l WHERE turno = 1)
        SELECT s.* EXCLUDE (nr_local_votacao),
               coalesce(l.nr_local, l1.nr_local, s.nr_local_votacao) AS nr_local
        FROM ({' UNION ALL '.join(partes)}) s
        LEFT JOIN l ON l.turno = s.turno AND l.cd_municipio = s.cd_municipio AND l.nr_zona = s.nr_zona
                   AND l.nr_secao = s.nr_secao
        LEFT JOIN l1 ON l1.cd_municipio = s.cd_municipio AND l1.nr_zona = s.nr_zona AND l1.nr_secao = s.nr_secao""")


def _alvo(con, ano, nome):
    """Tabela `nome`: os locais com seções no ano (nos dois turnos, fora o exterior), com os dados do local."""
    _secoes(con, ano)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE {nome} AS
        WITH s AS (SELECT DISTINCT sg_uf, regiao, cd_municipio, cd_ibge, nr_zona, nr_local FROM secao_local)
        SELECT s.*, r.nm, r.endereco, r.bairro, coalesce(r.nm_n, '') AS nm_n, coalesce(r.nucleo, '') AS nucleo,
               coalesce(r.end_n, '') AS end_n, coalesce(r.bairro_n, '') AS bairro_n, r.eleitores,
               r.lat, r.lon, coalesce(r.ok, false) AS ok
        FROM s LEFT JOIN ref r ON r.ano = {ano} AND r.cd_municipio = s.cd_municipio
                               AND r.nr_zona = s.nr_zona AND r.nr_local = s.nr_local""")


def _no_poligono(con):
    """Método 7, para os locais que nenhum outro método alcançou: um ponto dentro do polígono do município."""
    falta = con.execute("""SELECT a.cd_municipio, a.nr_zona, a.nr_local, a.cd_ibge FROM alvo a
                           WHERE NOT a.ok AND NOT EXISTS (SELECT 1 FROM cand c WHERE c.cd_municipio = a.cd_municipio
                                 AND c.nr_zona = a.nr_zona AND c.nr_local = a.nr_local)""").fetchall()
    linhas = []
    lo, hi = RAIO_KM[7]
    for mun, zona, local, ibge in falta:
        g = poligonos().get(ibge)
        if g is None:
            raise ValueError(f"local sem nenhuma forma de posição: município {mun}, zona {zona}, local {local}")
        p = g.point_on_surface()
        raio = float(np.clip(np.sqrt(g.area * 111.2**2 / np.pi) / 2, lo, hi))
        linhas.append((mun, zona, local, 7, p.y, p.x, raio, None))
    con.execute("CREATE OR REPLACE TEMP TABLE cand7 AS SELECT * FROM cand WHERE false")
    if linhas:
        con.executemany("INSERT INTO cand7 VALUES (?, ?, ?, ?, ?, ?, ?, ?)", linhas)


def completar(con, ano):
    """Tabela `completo`: cada local do ano com a coordenada final e o método (0 = a do TSE)."""
    _alvo(con, ano, "alvo_todos")
    con.execute("CREATE OR REPLACE TEMP TABLE alvo AS SELECT * FROM alvo_todos WHERE NOT ok")  # só quem precisa
    candidatos(con, ano)
    _no_poligono(con)
    # arg_min_null: o raio e o ano de referência são nulos em parte dos métodos
    escolha = ", ".join(f"arg_min_null({c}, nivel) AS {c}" for c in ("lat", "lon", "raio_km", "ano_ref"))
    con.execute(f"""CREATE OR REPLACE TEMP TABLE completo AS
        WITH c AS (SELECT * FROM cand UNION ALL SELECT * FROM cand7),
             melhor AS (SELECT cd_municipio, nr_zona, nr_local, min(nivel) AS nivel, {escolha} FROM c GROUP BY ALL)
        SELECT a.* EXCLUDE (lat, lon, ok, nm_n, nucleo, end_n, bairro_n),
               CASE WHEN a.ok THEN a.lat ELSE m.lat END AS lat,
               CASE WHEN a.ok THEN a.lon ELSE m.lon END AS lon,
               CASE WHEN a.ok THEN 0 ELSE m.nivel END::TINYINT AS nivel,
               CASE WHEN a.ok THEN NULL ELSE m.raio_km END AS raio_km,
               CASE WHEN a.ok THEN NULL ELSE m.ano_ref END::SMALLINT AS ano_coordenada
        FROM alvo_todos a LEFT JOIN melhor m USING (cd_municipio, nr_zona, nr_local)""")
    sem = con.execute("SELECT count(*) FROM completo WHERE lat IS NULL").fetchone()[0]
    if sem:
        raise ValueError(f"{sem} locais de {ano} ficaram sem coordenada")


def processar(ano, log=print):
    con = conexao()
    referencias(con)
    completar(con, ano)
    metodos = ", ".join(f"({n}, '{c}', {p})" for n, (c, _, p) in METODOS.items())
    colunas, juncoes = [], []
    medidas = {"secoes": "count(*)", "validos": "sum(votos_validos)", "petismo": "sum(votos_petismo)",
               "bolsonarismo": "sum(votos_bolsonarismo)", "outros": "sum(votos_outros)"}
    for (t,) in con.execute("SELECT DISTINCT turno FROM secao_local ORDER BY 1").fetchall():
        colunas += [f"coalesce(v{t}.{k}, 0)::INTEGER AS t{t}_{k}" for k in medidas]
        juncoes.append(f"""LEFT JOIN (SELECT cd_municipio, nr_zona, nr_local,
                                      {', '.join(f'{v} AS {k}' for k, v in medidas.items())}
                                      FROM secao_local WHERE turno = {t} GROUP BY ALL) v{t}
                           ON v{t}.cd_municipio = c.cd_municipio AND v{t}.nr_zona = c.nr_zona
                              AND v{t}.nr_local = c.nr_local""")
    destino = saida(ano)
    destino.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""COPY (
        WITH m(nivel, metodo, precisao) AS (VALUES {metodos})
        SELECT {ano}::SMALLINT AS ano, c.sg_uf, c.regiao, c.cd_municipio, c.cd_ibge, mu.nm_municipio,
               c.nr_zona, c.nr_local AS nr_local_votacao, c.nm AS nm_local, c.endereco, c.bairro, c.eleitores,
               c.lat, c.lon, c.nivel, m.metodo, m.precisao::TINYINT AS precisao, c.raio_km, c.ano_coordenada,
               {', '.join(colunas)}
        FROM completo c JOIN m USING (nivel)
        JOIN '{tab_municipios.SAIDA.as_posix()}' mu ON mu.cd_municipio = c.cd_municipio
        {' '.join(juncoes)}
        ORDER BY c.sg_uf, c.cd_municipio, c.nr_zona, c.nr_local
    ) TO '{destino.as_posix()}' (FORMAT parquet)""")
    for nivel, n, eleitores in con.execute(f"""SELECT nivel, count(*), sum(eleitores) FROM '{destino.as_posix()}'
                                               GROUP BY 1 ORDER BY 1""").fetchall():
        log(f"   {METODOS[nivel][1]}: {n:_} locais, {int(eleitores or 0):_} eleitores".replace("_", "."))


def saida_validacao():
    return config.PROCESSADO / "mapa" / "validacao_coordenadas.json"


def validar(anos, log=print):
    """Erro de cada método (1 a 6) nos locais que têm coordenada do TSE, fingindo que não têm.

    {ano: {nivel: {"n", "mediana_km", "p90_km", "acima_1km"}}} — n: locais em que o método se aplica. Também
    grava o resultado em `saida_validacao()`, lido pelo relatório de qualidade e pelo site (`ler_validacao`).
    """
    con = conexao()
    referencias(con)
    out = {}
    for ano in anos:
        _alvo(con, ano, "alvo_todos")
        con.execute("CREATE OR REPLACE TEMP TABLE alvo AS SELECT * FROM alvo_todos WHERE ok")
        candidatos(con, ano)
        linhas = con.execute(f"""SELECT c.nivel, count(*), median({_km('a.', 'c.')}), quantile_cont({_km('a.', 'c.')}, 0.9),
                                        avg(({_km('a.', 'c.')} > 1)::INT)
                                 FROM alvo a JOIN cand c USING (cd_municipio, nr_zona, nr_local)
                                 GROUP BY 1 ORDER BY 1""").fetchall()
        out[ano] = {nivel: {"n": n, "mediana_km": round(med, 3), "p90_km": round(p90, 2), "acima_1km": round(acima, 3)}
                    for nivel, n, med, p90, acima in linhas}
        log(f"   {ano}: " + "; ".join(f"{METODOS[k][1]}: mediana {v['mediana_km']:.2f} km" for k, v in out[ano].items()))
    saida_validacao().parent.mkdir(parents=True, exist_ok=True)
    saida_validacao().write_text(json.dumps(out, indent=1), "utf-8")
    return out


def ler_validacao():
    """O resultado da última `validar`, com chaves inteiras como as de `validar` (ou None se nunca rodou)."""
    if not saida_validacao().exists():
        return None
    return {int(a): {int(k): v for k, v in m.items()} for a, m in json.loads(saida_validacao().read_text("utf-8")).items()}
