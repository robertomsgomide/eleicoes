"""Local de votação e coordenadas de cada seção (uma linha por seção e turno)."""
import shutil
import zipfile

from eleicoes import config
from eleicoes.tratamento import TMP, cabecalho, conexao, ler_csv

# Caixa que contém o território brasileiro (com folga); coordenadas de seções no Brasil fora dela são descartadas
LAT_BR, LON_BR = (-34.0, 5.5), (-74.1, -28.8)


def saida(ano):
    return config.PROCESSADO / "tse" / "locais_votacao" / f"{ano}.parquet"


def origem(ano):
    return config.BRUTO / "tse" / "locais_votacao" / str(ano) / f"eleitorado_local_votacao_{ano}.zip"


def processar(ano, log=print):
    csv = TMP / f"eleitorado_local_votacao_{ano}.csv"
    with zipfile.ZipFile(origem(ano)) as z:
        # Até 2024, um arquivo só; em 2026, um por UF e um com o Brasil inteiro (_BRASIL), que é o usado
        membro = next(m for m in (csv.name, f"eleitorado_local_votacao_{ano}_BRASIL.csv") if m in z.namelist())
        with z.open(membro) as src, open(csv, "wb") as dst:
            shutil.copyfileobj(src, dst, 16 << 20)
    destino = saida(ano)
    destino.parent.mkdir(parents=True, exist_ok=True)
    num = lambda c: f"TRY_CAST(replace({c}, ',', '.') AS DOUBLE)"  # noqa: E731  (2026 usa vírgula decimal)
    con = conexao()
    try:
        con.execute(f"""COPY (
            WITH l AS (
                SELECT AA_ELEICAO::SMALLINT AS ano, NR_TURNO::TINYINT AS turno, SG_UF AS sg_uf,
                       lpad(CD_MUNICIPIO, 5, '0') AS cd_municipio, NR_ZONA::SMALLINT AS nr_zona,
                       NR_SECAO::SMALLINT AS nr_secao, DS_TIPO_SECAO_AGREGADA AS tipo_secao,
                       NULLIF(TRY_CAST(NR_SECAO_PRINCIPAL AS SMALLINT), -1) AS nr_secao_principal,
                       TRY_CAST(NR_LOCAL_VOTACAO AS INTEGER) AS nr_local_votacao, NM_LOCAL_VOTACAO AS nm_local_votacao,
                       DS_TIPO_LOCAL AS tipo_local, DS_ENDERECO AS endereco, NM_BAIRRO AS bairro, NR_CEP AS cep,
                       {num('NR_LATITUDE')} AS lat, {num('NR_LONGITUDE')} AS lon,
                       TRY_CAST(QT_ELEITOR_SECAO AS INTEGER) AS qt_eleitores, DS_SITU_SECAO AS situacao_secao
                FROM {ler_csv(csv, cabecalho(csv))}
            )
            SELECT * REPLACE (
                CASE WHEN coord_ok THEN lat END AS lat,
                CASE WHEN coord_ok THEN lon END AS lon)
            FROM (SELECT *, lat IS NOT NULL AND lon IS NOT NULL AND lat <> -1 AND lon <> -1 AND NOT (lat = 0 AND lon = 0)
                            AND lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180
                            AND (sg_uf = 'ZZ' OR (lat BETWEEN {LAT_BR[0]} AND {LAT_BR[1]}
                                                  AND lon BETWEEN {LON_BR[0]} AND {LON_BR[1]})) AS coord_ok
                  FROM l)
            ORDER BY turno, sg_uf, cd_municipio, nr_zona, nr_secao
        ) TO '{destino.as_posix()}' (FORMAT parquet)""")
    finally:
        csv.unlink(missing_ok=True)
    n, com = con.execute(f"SELECT count(*), count(*) FILTER (coord_ok) FROM '{destino.as_posix()}'").fetchone()
    log(f"   {n:,} seções × turno; {com / n:.1%} com coordenadas válidas".replace(",", "."))
