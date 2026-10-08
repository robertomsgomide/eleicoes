"""Malhas (fronteiras) e lista de municípios do IBGE, para mapas e para conferir os códigos de município."""
import gzip
import json

from eleicoes import config
from eleicoes.coleta import manifesto, rede

MALHA = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
         "?formato=application/vnd.geo%2Bjson&qualidade=intermediaria&intrarregiao={}")
# A mesma malha de municípios em TopoJSON (fronteiras compartilhadas, coordenadas quantizadas): 1 MB em vez de 12,
# é a que vai para o mapa do site
TOPOJSON = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
            "?formato=application/json&qualidade=intermediaria&intrarregiao=municipio")
NIVEIS = {"municipios": "municipio", "ufs": "UF", "regioes": "regiao"}
LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
ARQ_TOPOJSON = config.BRUTO / "ibge" / "malhas" / "municipios.topojson"


def baixar(log=print):
    pasta = config.BRUTO / "ibge"
    alvos = {pasta / "malhas" / f"{nome}.geojson": MALHA.format(nivel) for nome, nivel in NIVEIS.items()}
    alvos[ARQ_TOPOJSON] = TOPOJSON
    alvos[pasta / "municipios.json"] = LOCALIDADES
    for destino, url in alvos.items():
        if manifesto.registro(destino) and destino.exists():
            log(f"   {destino.name}: já estava baixado")
            continue
        rede.baixar(url, destino)
        conteudo = destino.read_bytes()
        if conteudo[:2] == b"\x1f\x8b":  # a API do IBGE responde em gzip mesmo sem pedir
            destino.write_bytes(conteudo := gzip.decompress(conteudo))
        json.loads(conteudo.decode("utf-8"))
        (sha,) = rede.hashes(destino, "sha512")
        manifesto.registrar(destino, url, sha, "json válido")
        log(f"   {destino.name}: {destino.stat().st_size / 1e6:.1f} MB")
