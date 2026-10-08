"""Boletins de urna (bweb, todos os cargos) -> tabelas por seção, só Presidente.

  tse/votos_secao/<ano>_t<turno>.parquet  uma linha por seção e votável (candidato; 95 = branco; 96 = nulo)
  tse/secoes/<ano>_t<turno>.parquet       uma linha por seção: eleitorado, comparecimento, votos de cada campo,
                                          tipo de urna e horários (abertura, encerramento, emissão e chegada do boletim)

Horários como vêm do TSE, sem conversão de fuso (ver docs/dados.md): a abertura, o encerramento e a emissão
do boletim estão no horário local da seção; a chegada do boletim (só existe a partir de 2022), no de Brasília.

Formato de 2026: datas em "aaaa-mm-dd hh:mm:ss" (antes, "dd/mm/aaaa hh:mm:ss") e duas colunas com outro nome
(DS_SECOES_AGREGADAS, antes DS_AGREGADAS; QT_ELEI_BIOM_SEM_HABILITACAO, antes QT_ELEITORES_BIOMETRIA_NH).
"""
import re
import shutil
import zipfile

from eleicoes import config
from eleicoes.tratamento import TMP, cabecalho, conexao, ler_csv
from eleicoes.tratamento import municipios as tab_municipios


def saida(tabela, ano, turno):
    return config.PROCESSADO / "tse" / tabela / f"{ano}_t{turno}.parquet"


def zips(ano, turno):
    pasta = config.BRUTO / "tse" / "boletins_urna" / str(ano)
    return sorted(p for p in pasta.glob("*.zip") if re.search(rf"_{turno}t_", p.name, re.I))


def _data(colunas, nome):
    if nome not in colunas:
        return "NULL::TIMESTAMP"
    return f"coalesce(try_strptime({nome}, '%d/%m/%Y %H:%M:%S'), try_strptime({nome}, '%Y-%m-%d %H:%M:%S'))"


def _coluna(colunas, *nomes):
    """O primeiro dos nomes que o arquivo tem (o TSE renomeou colunas entre as eleições), ou None."""
    return next((n for n in nomes if n in colunas), None)


def _parte_uf(con, arq_zip, ano, turno):
    """Extrai o CSV da UF para o disco, guarda só as linhas de Presidente num Parquet e apaga o CSV."""
    uf = re.search(r"_\dt_([A-Z]{2})_", arq_zip.name, re.I).group(1).upper()
    with zipfile.ZipFile(arq_zip) as z:
        membro = next(m for m in z.namelist() if m.lower().endswith(".csv"))
        csv = TMP / membro
        with z.open(membro) as src, open(csv, "wb") as dst:
            shutil.copyfileobj(src, dst, 16 << 20)
    parte = TMP / f"bu_{ano}_t{turno}_{uf}.parquet"
    try:
        colunas = cabecalho(csv)
        int_ou_nulo = lambda c: f"NULLIF(TRY_CAST({c} AS INTEGER), -1)" if c in colunas else "NULL::INTEGER"  # noqa: E731
        agregadas = _coluna(colunas, "DS_AGREGADAS", "DS_SECOES_AGREGADAS")
        biometria = _coluna(colunas, "QT_ELEITORES_BIOMETRIA_NH", "QT_ELEI_BIOM_SEM_HABILITACAO")
        con.execute(f"""COPY (
            SELECT ANO_ELEICAO::SMALLINT AS ano, NR_TURNO::TINYINT AS turno, SG_UF AS sg_uf,
                   lpad(CD_MUNICIPIO, 5, '0') AS cd_municipio, NM_MUNICIPIO AS nm_municipio,
                   NR_ZONA::SMALLINT AS nr_zona, NR_SECAO::SMALLINT AS nr_secao,
                   TRY_CAST(NR_LOCAL_VOTACAO AS INTEGER) AS nr_local_votacao,
                   QT_APTOS::INTEGER AS qt_aptos, QT_COMPARECIMENTO::INTEGER AS qt_comparecimento,
                   QT_ABSTENCOES::INTEGER AS qt_abstencoes,
                   TRY_CAST(CD_TIPO_URNA AS TINYINT) AS cd_tipo_urna, DS_TIPO_URNA AS ds_tipo_urna,
                   TRY_CAST(CD_TIPO_VOTAVEL AS TINYINT) AS cd_tipo_votavel, DS_TIPO_VOTAVEL AS ds_tipo_votavel,
                   TRY_CAST(NR_VOTAVEL AS INTEGER) AS nr_votavel, NM_VOTAVEL AS nm_votavel,
                   TRY_CAST(QT_VOTOS AS INTEGER) AS qt_votos,
                   {f"NULLIF({agregadas}, '#NULO#')" if agregadas else "NULL::VARCHAR"} AS ds_agregadas,
                   {int_ou_nulo('NR_URNA_EFETIVADA')} AS nr_urna_efetivada,
                   {int_ou_nulo(biometria)} AS qt_eleitores_biometria_nh,
                   {int_ou_nulo('NR_JUNTA_APURADORA')} AS nr_junta_apuradora,
                   {_data(colunas, 'DT_ABERTURA')} AS dt_abertura,
                   {_data(colunas, 'DT_ENCERRAMENTO')} AS dt_encerramento,
                   {_data(colunas, 'DT_EMISSAO_BU')} AS dt_emissao_bu,
                   {_data(colunas, 'DT_BU_RECEBIDO')} AS dt_bu_recebido
            FROM {ler_csv(csv, colunas, aspas_soltas=True)}
            WHERE CD_CARGO_PERGUNTA = '1'
        ) TO '{parte.as_posix()}' (FORMAT parquet)""")
    finally:
        csv.unlink(missing_ok=True)
    return uf, parte


def processar(ano, turno, log=print):
    arquivos = zips(ano, turno)
    if len(arquivos) != 28:
        raise FileNotFoundError(f"esperava 28 boletins (27 UFs + exterior) de {ano}, {turno}º turno; achei {len(arquivos)}")
    con = conexao()
    partes = []
    for arq in arquivos:
        uf, parte = _parte_uf(con, arq, ano, turno)
        partes.append(parte)
    lista = "[" + ", ".join(f"'{p.as_posix()}'" for p in partes) + "]"
    con.execute(f"CREATE TABLE bu AS SELECT * FROM read_parquet({lista})")
    for p in partes:
        p.unlink()
    # Seções sem votação (urna "Não instalada" ou "Não apurada") vêm numa linha só, sem votável nem votos:
    # entram em `secoes` com zero votos e ficam fora de `votos_secao`. Em qualquer outra seção, isso seria erro.
    sem_voto = "cd_tipo_votavel IS NULL OR nr_votavel IS NULL OR qt_votos IS NULL"
    estranhas = con.execute(f"""SELECT sg_uf, cd_municipio, nr_zona, nr_secao, ds_tipo_urna FROM bu
                                WHERE ({sem_voto}) AND (qt_comparecimento > 0
                                       OR lower(ds_tipo_urna) NOT IN ('não instalada', 'não apurada'))""").fetchall()
    if estranhas:
        raise ValueError(f"linhas de Presidente sem votos legíveis em seções que votaram: {estranhas[:5]}")
    for tipo, n in con.execute(f"SELECT ds_tipo_urna, count(DISTINCT (sg_uf, cd_municipio, nr_zona, nr_secao)) "
                               f"FROM bu WHERE {sem_voto} GROUP BY 1").fetchall():
        log(f"   {n} seções sem votação ({tipo})")

    campos = config.candidatos(ano)
    pt = next(n for n, c in campos.items() if c == "petismo")
    bolso = next(n for n, c in campos.items() if c == "bolsonarismo")
    # Votos anulados pelo TSE (candidatura indeferida) são nominais no boletim, mas contam como nulos no resultado
    tecnicos = ", ".join(map(str, config.nulos_tecnicos(ano, turno) or [-1]))
    regioes = ", ".join(f"('{uf}', '{r}')" for uf, r in config.REGIAO_DA_UF.items())

    votos, secoes = saida("votos_secao", ano, turno), saida("secoes", ano, turno)
    votos.parent.mkdir(parents=True, exist_ok=True)
    secoes.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""COPY (
        SELECT ano, turno, sg_uf, cd_municipio, nr_zona, nr_secao, nr_votavel,
               any_value(nm_votavel) AS nm_votavel, any_value(cd_tipo_votavel) AS cd_tipo_votavel,
               sum(qt_votos)::INTEGER AS qt_votos
        FROM bu WHERE NOT ({sem_voto}) GROUP BY ALL ORDER BY ALL
    ) TO '{votos.as_posix()}' (FORMAT parquet)""")
    con.execute(f"""COPY (
        WITH r(sg_uf, regiao) AS (VALUES {regioes})
        SELECT b.ano, b.turno, b.sg_uf, r.regiao, b.cd_municipio, m.cd_ibge, any_value(b.nm_municipio) AS nm_municipio,
               b.nr_zona, b.nr_secao, any_value(b.nr_local_votacao) AS nr_local_votacao,
               max(b.qt_aptos) AS qt_aptos, max(b.qt_comparecimento) AS qt_comparecimento,
               max(b.qt_abstencoes) AS qt_abstencoes,
               coalesce(sum(b.qt_votos) FILTER (b.nr_votavel = {pt}), 0)::INTEGER AS votos_petismo,
               coalesce(sum(b.qt_votos) FILTER (b.nr_votavel = {bolso}), 0)::INTEGER AS votos_bolsonarismo,
               coalesce(sum(b.qt_votos) FILTER (b.cd_tipo_votavel = 1 AND b.nr_votavel NOT IN ({pt}, {bolso}, {tecnicos})),
                        0)::INTEGER AS votos_outros,
               coalesce(sum(b.qt_votos) FILTER (b.cd_tipo_votavel = 1 AND b.nr_votavel NOT IN ({tecnicos})), 0)::INTEGER
                   AS votos_validos,
               coalesce(sum(b.qt_votos) FILTER (b.nr_votavel = 95), 0)::INTEGER AS votos_brancos,
               coalesce(sum(b.qt_votos) FILTER (b.nr_votavel = 96 OR b.cd_tipo_votavel = 1 AND b.nr_votavel IN ({tecnicos})),
                        0)::INTEGER AS votos_nulos,
               count(DISTINCT coalesce(b.nr_urna_efetivada, -1)) AS qt_boletins,
               string_agg(DISTINCT b.ds_tipo_urna, ' + ') AS tipo_urna,
               any_value(b.ds_agregadas) AS secoes_agregadas,
               any_value(b.qt_eleitores_biometria_nh) AS qt_eleitores_biometria_nh,
               min(b.dt_abertura) AS dt_abertura, max(b.dt_encerramento) AS dt_encerramento,
               max(b.dt_emissao_bu) AS dt_emissao_bu, max(b.dt_bu_recebido) AS dt_bu_recebido
        FROM bu b
        JOIN r USING (sg_uf)
        LEFT JOIN '{tab_municipios.SAIDA.as_posix()}' m USING (cd_municipio)
        GROUP BY b.ano, b.turno, b.sg_uf, r.regiao, b.cd_municipio, m.cd_ibge, b.nr_zona, b.nr_secao
        ORDER BY b.sg_uf, b.cd_municipio, b.nr_zona, b.nr_secao
    ) TO '{secoes.as_posix()}' (FORMAT parquet)""")
    n, dup = con.execute(f"SELECT count(*), count(*) FILTER (qt_boletins > 1) FROM '{secoes.as_posix()}'").fetchone()
    log(f"   {n:,} seções".replace(",", ".") + (f"; {dup} com mais de um boletim" if dup else ""))
