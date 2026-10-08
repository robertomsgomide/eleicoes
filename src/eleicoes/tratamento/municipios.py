"""Códigos de município TSE -> IBGE, com nome oficial do IBGE e região (referencia/municipios.parquet)."""
import json

from eleicoes import config
from eleicoes.tratamento import conexao

ARQ_TSE = config.BRUTO / "tse" / "municipios" / "mun-e006257-cm.json"
ARQ_IBGE = config.BRUTO / "ibge" / "municipios.json"
SAIDA = config.PROCESSADO / "referencia" / "municipios.parquet"


def processar(log=print):
    tse = json.loads(ARQ_TSE.read_text("utf-8"))
    ibge = {m["id"]: m for m in json.loads(ARQ_IBGE.read_text("utf-8"))}
    linhas, divergentes = [], []
    for abr in tse["abr"]:
        uf = abr["cd"].upper()
        for m in abr["mu"]:
            cd_ibge = int(m["cdi"]) if m.get("cdi") else None
            i = ibge.get(cd_ibge)
            if cd_ibge and (not i or str(cd_ibge)[:2] != str(i["id"])[:2]):
                divergentes.append(m["cd"])
            linhas.append((m["cd"], cd_ibge, i["nome"] if i else m["nm"].title(), m["nm"], uf, config.REGIAO_DA_UF[uf]))
    if divergentes:
        raise ValueError(f"códigos IBGE do TSE que não existem no IBGE: {divergentes[:10]}")

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    con = conexao()
    con.execute("""CREATE TABLE m (cd_municipio VARCHAR, cd_ibge INTEGER, nm_municipio VARCHAR,
                   nm_municipio_tse VARCHAR, sg_uf VARCHAR, regiao VARCHAR)""")
    con.executemany("INSERT INTO m VALUES (?, ?, ?, ?, ?, ?)", linhas)
    con.execute(f"COPY (SELECT * FROM m ORDER BY sg_uf, cd_municipio) TO '{SAIDA.as_posix()}' (FORMAT parquet)")
    sem = sum(1 for l in linhas if l[1] is None and l[4] != "ZZ")
    log(f"   {len(linhas)} municípios ({sum(l[4] == 'ZZ' for l in linhas)} no exterior); "
        f"sem código IBGE fora do exterior: {sem}")
