"""Totais oficiais de Presidente por município, zona e candidato: o gabarito contra o qual os boletins são conferidos."""
from eleicoes import config
from eleicoes.tratamento import cabecalho, conexao, ler_csv


# Diferenças entre a soma dos boletins de urna publicados e o total oficial, conferidas uma a uma.
# Qualquer diferença fora desta lista faz os testes falharem.
# (ano, turno, UF, município TSE, zona) -> {candidato: boletins − oficial}
DIVERGENCIAS_CONHECIDAS = {
    # Pastos Bons (MA), zona 17: o total oficial tem 76 votos a mais que os 48 boletins da zona. Todas as seções
    # principais estão nos boletins e cada uma tem comparecimento = votos; as que faltam são agregadas (votam na
    # urna da principal). A origem dos 76 votos não aparece nos arquivos publicados.
    (2018, 1, "MA", "08591", 17): {13: -46, 17: -20, 12: -5, 15: -2, 30: -1, 45: -1, 18: -1},
}


def saida(ano):
    return config.PROCESSADO / "tse" / "totais_oficiais" / f"{ano}.parquet"


def diferencas(con, ano, turno, chave=()):
    """{(valores da chave..., candidato): boletins − oficial} onde não bate; candidato ausente conta como 0 voto.

    chave: () para o Brasil, ("sg_uf",) por UF, ("cd_municipio", "nr_zona") por zona. Os votos anulados de
    candidatos indeferidos (`nulos_tecnicos`) são nominais nos boletins, mas o total oficial não os traz.
    """
    from eleicoes.tratamento import boletins  # evita import circular
    votos = boletins.saida("votos_secao", ano, turno).as_posix()
    sel = "".join(f"{c}, " for c in chave)
    tecnicos = ", ".join(map(str, config.nulos_tecnicos(ano, turno) or [-1]))
    linhas = con.execute(f"""
        WITH b AS (SELECT {sel}nr_votavel AS nr, sum(qt_votos) AS v FROM '{votos}'
                   WHERE cd_tipo_votavel = 1 AND nr_votavel NOT IN ({tecnicos}) GROUP BY ALL),
             o AS (SELECT {sel}nr_candidato AS nr, sum(qt_votos) AS v FROM '{saida(ano).as_posix()}'
                   WHERE turno = {turno} GROUP BY ALL)
        SELECT {sel}nr, coalesce(b.v, 0) - coalesce(o.v, 0) AS d
        FROM b FULL JOIN o USING ({sel}nr) WHERE d <> 0""").fetchall()
    return {tuple(l[:-1]): l[-1] for l in linhas}


def esperadas(ano, turno, chave=()):
    """As diferenças de DIVERGENCIAS_CONHECIDAS somadas no nível da chave, no formato de diferencas()."""
    soma = {}
    for (a, t, uf, mun, zona), difs in DIVERGENCIAS_CONHECIDAS.items():
        if (a, t) != (ano, turno):
            continue
        valores = {"sg_uf": uf, "cd_municipio": mun, "nr_zona": zona}
        for nr, d in difs.items():
            k = (*(valores[c] for c in chave), nr)
            soma[k] = soma.get(k, 0) + d
    return {k: d for k, d in soma.items() if d}


def origem(ano):
    return config.BRUTO / "tse" / "totais_oficiais" / str(ano) / f"votacao_candidato_munzona_{ano}_BR.csv"


def processar(ano, log=print):
    origem_ = origem(ano)
    colunas = cabecalho(origem_)
    transito = "ST_VOTO_EM_TRANSITO" if "ST_VOTO_EM_TRANSITO" in colunas else "NULL"
    destino = saida(ano)
    destino.parent.mkdir(parents=True, exist_ok=True)
    con = conexao()
    con.execute(f"""COPY (
        SELECT ANO_ELEICAO::SMALLINT AS ano, NR_TURNO::TINYINT AS turno, SG_UF AS sg_uf,
               lpad(CD_MUNICIPIO, 5, '0') AS cd_municipio, NR_ZONA::SMALLINT AS nr_zona,
               NR_CANDIDATO::INTEGER AS nr_candidato, NM_URNA_CANDIDATO AS nm_urna_candidato,
               QT_VOTOS_NOMINAIS::INTEGER AS qt_votos, {transito} AS st_voto_em_transito,
               DS_SIT_TOT_TURNO AS ds_sit_tot_turno
        FROM {ler_csv(origem_, colunas)}
        WHERE CD_CARGO = '1'
        ORDER BY ALL
    ) TO '{destino.as_posix()}' (FORMAT parquet)""")
    for turno, votos in con.execute(f"SELECT turno, sum(qt_votos) FROM '{destino.as_posix()}' GROUP BY 1 ORDER BY 1").fetchall():
        log(f"   {turno}º turno: {votos:,} votos nominais".replace(",", "."))
