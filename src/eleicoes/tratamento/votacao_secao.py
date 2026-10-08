"""Votação por seção (arquivo nacional do TSE, só Presidente) -> uma linha por seção, como em `secoes`, sem horários.

  tse/votacao_secao/<ano>_t<turno>.parquet

É a fonte dos votos por seção enquanto os boletins de urna do ano não saem (2026): o TSE publica este arquivo
um dia depois da eleição e os boletins, dias depois. Os votos são os mesmos; faltam os horários, o eleitorado
e o comparecimento de cada seção. Quando os boletins saem, `secoes` passa a ser a fonte (ver `fonte_secoes`).
"""
import json
import shutil
import zipfile

from eleicoes import config
from eleicoes.formato_tse import candidatos as votos_por_candidato
from eleicoes.formato_tse import num
from eleicoes.tratamento import TMP, boletins, cabecalho, conexao, ler_csv
from eleicoes.tratamento import municipios as tab_municipios

BRANCO, NULO = 95, 96
MEDIDAS = ("votos_petismo", "votos_bolsonarismo", "votos_outros", "votos_brancos", "votos_nulos")


def origem(ano):
    return config.BRUTO / "tse" / "votacao_secao" / str(ano) / f"votacao_secao_{ano}_BR.zip"


def saida(ano, turno):
    return config.PROCESSADO / "tse" / "votacao_secao" / f"{ano}_t{turno}.parquet"


def fonte_secoes(ano, turno):
    """Tabela com os votos de cada seção: a dos boletins de urna, se existir; senão, a da votação por seção."""
    for arq in (boletins.saida("secoes", ano, turno), saida(ano, turno)):
        if arq.exists():
            return arq
    return None


def processar(ano, log=print):
    csv = TMP / f"votacao_secao_{ano}_BR.csv"
    with zipfile.ZipFile(origem(ano)) as z, z.open(csv.name) as src, open(csv, "wb") as dst:
        shutil.copyfileobj(src, dst, 16 << 20)
    campos = config.candidatos(ano)
    pt = next(n for n, c in campos.items() if c == "petismo")
    bolso = next(n for n, c in campos.items() if c == "bolsonarismo")
    regioes = ", ".join(f"('{uf}', '{r}')" for uf, r in config.REGIAO_DA_UF.items())
    con = conexao()
    try:
        con.execute(f"""CREATE TABLE v AS
            SELECT ANO_ELEICAO::SMALLINT AS ano, NR_TURNO::TINYINT AS turno, SG_UF AS sg_uf,
                   lpad(CD_MUNICIPIO, 5, '0') AS cd_municipio, NM_MUNICIPIO AS nm_municipio,
                   NR_ZONA::SMALLINT AS nr_zona, NR_SECAO::SMALLINT AS nr_secao,
                   TRY_CAST(NR_LOCAL_VOTACAO AS INTEGER) AS nr_local_votacao,
                   NR_VOTAVEL::INTEGER AS nr_votavel, QT_VOTOS::INTEGER AS qt_votos
            FROM {ler_csv(csv, cabecalho(csv))}
            WHERE CD_CARGO = '1'""")
    finally:
        csv.unlink(missing_ok=True)
    estranhos = con.execute(f"SELECT DISTINCT nr_votavel FROM v WHERE nr_votavel > {NULO}").fetchall()
    if estranhos:
        raise ValueError(f"votáveis inesperados (nem candidato, nem branco, nem nulo): {estranhos}")
    for (turno,) in con.execute("SELECT DISTINCT turno FROM v ORDER BY 1").fetchall():
        # Votos anulados pelo TSE (candidatura indeferida) contam como nulos, como no resultado oficial
        anulados = ", ".join(map(str, [NULO, *config.nulos_tecnicos(ano, turno)]))
        destino = saida(ano, turno)
        destino.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"""COPY (
            WITH r(sg_uf, regiao) AS (VALUES {regioes})
            SELECT v.ano, v.turno, v.sg_uf, r.regiao, v.cd_municipio, m.cd_ibge, min(v.nm_municipio) AS nm_municipio,
                   v.nr_zona, v.nr_secao, min(v.nr_local_votacao) AS nr_local_votacao,
                   coalesce(sum(qt_votos) FILTER (nr_votavel = {pt}), 0)::INTEGER AS votos_petismo,
                   coalesce(sum(qt_votos) FILTER (nr_votavel = {bolso}), 0)::INTEGER AS votos_bolsonarismo,
                   coalesce(sum(qt_votos) FILTER (nr_votavel NOT IN ({pt}, {bolso}, {BRANCO}, {anulados})), 0)::INTEGER
                       AS votos_outros,
                   coalesce(sum(qt_votos) FILTER (nr_votavel NOT IN ({BRANCO}, {anulados})), 0)::INTEGER AS votos_validos,
                   coalesce(sum(qt_votos) FILTER (nr_votavel = {BRANCO}), 0)::INTEGER AS votos_brancos,
                   coalesce(sum(qt_votos) FILTER (nr_votavel IN ({anulados})), 0)::INTEGER AS votos_nulos
            FROM v JOIN r USING (sg_uf)
            LEFT JOIN '{tab_municipios.SAIDA.as_posix()}' m USING (cd_municipio)
            WHERE v.turno = {turno}
            GROUP BY v.ano, v.turno, v.sg_uf, r.regiao, v.cd_municipio, m.cd_ibge, v.nr_zona, v.nr_secao
            ORDER BY v.sg_uf, v.cd_municipio, v.nr_zona, v.nr_secao
        ) TO '{destino.as_posix()}' (FORMAT parquet)""")
        n, validos = con.execute(f"SELECT count(*), sum(votos_validos) FROM '{destino.as_posix()}'").fetchone()
        log(f"   {turno}º turno: {n:_} seções, {validos:_} votos válidos".replace("_", "."))


def diferencas_dos_boletins(con, ano, turno):
    """Seções em que a votação por seção e os boletins de urna não dão os mesmos votos (as duas tabelas existindo).

    {"secoes": seções comparadas, "diferentes": [(UF, município, zona, seção, medida, votação − boletins)]}; seção
    que está numa tabela e não na outra conta com zero votos na outra.
    """
    vs, bu = saida(ano, turno).as_posix(), boletins.saida("secoes", ano, turno).as_posix()
    chave = "sg_uf, cd_municipio, nr_zona, nr_secao"
    difs = ", ".join(f"coalesce(v.{m}, 0) - coalesce(b.{m}, 0) AS {m}" for m in MEDIDAS)
    n, = con.execute(f"SELECT count(*) FROM '{vs}' v FULL JOIN '{bu}' b USING ({chave})").fetchone()
    linhas = con.execute(f"""
        WITH d AS (SELECT {chave}, {difs} FROM '{vs}' v FULL JOIN '{bu}' b USING ({chave})),
             u AS (UNPIVOT d ON {", ".join(MEDIDAS)} INTO NAME medida VALUE diferenca)
        SELECT * FROM u WHERE diferenca <> 0 ORDER BY ALL""").fetchall()
    return {"secoes": n, "diferentes": linhas}


def pasta_final(ano, turno):
    """Arquivos finais por UF do site de resultados, gravados ao fim da apuração (dados/bruto/ao_vivo)."""
    return config.BRUTO / "ao_vivo" / f"ele{ano}-{config.turno(ano, turno).get('eleicao')}" / "final"


def resultado_final_por_uf(ano, turno):
    """{UF: {medida: votos}} pelos arquivos finais do site de resultados, nas medidas da tabela de seções."""
    campos = config.candidatos(ano)
    out = {}
    for arq in sorted(pasta_final(ano, turno).glob("*.json")):
        if arq.stem.upper() == "BR":
            continue
        d = json.loads(arq.read_text("utf-8"))
        cand = {int(n): int(v) for n, v in votos_por_candidato(d).items()}
        pt = sum(v for n, v in cand.items() if campos.get(n) == "petismo")
        bolso = sum(v for n, v in cand.items() if campos.get(n) == "bolsonarismo")
        out[arq.stem.upper()] = {"votos_petismo": pt, "votos_bolsonarismo": bolso,
                                 "votos_outros": int(num(d["v"]["vv"])) - pt - bolso,
                                 "votos_brancos": int(num(d["v"]["vb"])), "votos_nulos": int(num(d["v"]["tvn"]))}
    return out


def diferencas_do_resultado_final(con, ano, turno):
    """{(UF, medida): votação por seção − resultado final} onde não bate.

    O total oficial por município e zona é o gabarito de 2018 e 2022; o de 2026 saiu sem os votos de Presidente,
    então a conferência é por UF com os arquivos finais da totalização (site de resultados).
    """
    final = resultado_final_por_uf(ano, turno)
    soma = ", ".join(f"sum({m})" for m in MEDIDAS)
    secao = {uf: dict(zip(MEDIDAS, map(int, valores))) for uf, *valores in con.execute(
        f"SELECT sg_uf, {soma} FROM '{saida(ano, turno).as_posix()}' GROUP BY 1").fetchall()}
    difs = {}
    for uf in set(final) | set(secao):
        for m in MEDIDAS:
            d = secao.get(uf, {}).get(m, 0) - final.get(uf, {}).get(m, 0)
            if d:
                difs[(uf, m)] = d
    return difs
