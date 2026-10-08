"""Arquivos do TSE usados no estudo, baixados para dados/bruto/tse e registrados no manifesto.

- boletins de urna (bweb): votos de cada seção, todos os cargos; um zip por UF e turno, com SHA-512 publicado;
- votação por seção: votos de cada seção só de Presidente, sem horários; sai dias antes dos boletins de urna
  e é a fonte dos votos por seção enquanto eles não saem (2026);
- locais de votação: endereço e coordenadas de cada seção (também de anos sem eleição presidencial, para
  completar as coordenadas que faltam);
- totais oficiais por município e zona: só o arquivo de Presidente de dentro do zip (o gabarito dos testes);
- códigos de município TSE -> IBGE.
"""
import concurrent.futures as cf
import json
import urllib.error

from eleicoes import config
from eleicoes.coleta import manifesto, rede

CKAN = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id={}"
ODSELE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
# Só o arquivo de 2026 continua no ar (o de 2022 dá 404); os códigos de município do TSE não mudam entre eleições.
URL_MUNICIPIOS = "https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json"
PARALELO = 4


def pasta(*partes):
    return config.BRUTO.joinpath("tse", *map(str, partes))


def _ja_baixado(destino, tam=None):
    r = manifesto.registro(destino)
    return bool(r) and destino.exists() and int(r["bytes"]) == destino.stat().st_size and tam in (None, int(r["bytes"]))


def _baixar_conferindo(url, destino, sha512_tse=None):
    tam = rede.tamanho(url)
    if _ja_baixado(destino, tam):
        return "já estava baixado"
    sha_tse = sha512_tse() if sha512_tse else None
    rede.baixar(url, destino, tam)
    (sha,) = rede.hashes(destino, "sha512")
    if sha_tse and sha != sha_tse:
        destino.unlink()
        raise ValueError(f"{destino.name}: SHA-512 diferente do publicado pelo TSE (arquivo apagado; rode de novo)")
    manifesto.registrar(destino, url, sha, "sha512 do TSE" if sha_tse else "tamanho")
    return f"{tam / 1e6:.0f} MB, " + ("SHA-512 confere com o do TSE" if sha_tse else "tamanho confere")


def boletins(ano, log=print):
    """Boletins de urna do 1º e do 2º turno (todas as UFs e o exterior)."""
    recursos = rede.ler_json(CKAN.format(f"resultados-{ano}-boletim-de-urna"))["result"]["resources"]
    urls = [r["url"] for r in recursos if r["url"].lower().endswith(".zip")]
    destino = pasta("boletins_urna", ano)

    def um(url):
        nome = url.rsplit("/", 1)[1]
        sha_tse = lambda: rede.texto(url + ".sha512").split()[0].lower()  # noqa: E731
        return nome, _baixar_conferindo(url, destino / nome, sha_tse)

    falhas = []
    with cf.ThreadPoolExecutor(PARALELO) as ex:
        for f in cf.as_completed([ex.submit(um, u) for u in urls]):
            try:
                nome, situacao = f.result()
                log(f"   {nome}: {situacao}")
            except Exception as e:  # segue com os outros; rodar de novo retoma o que faltou
                falhas.append(e)
                log(f"   ERRO: {e}")
    if falhas:
        raise RuntimeError(f"{len(falhas)} boletins de {ano} não baixaram; rode o comando de novo para retomar")


def boletins_publicados(ano):
    """O TSE já publicou os boletins de urna do ano? (o conjunto só aparece no portal dias depois da eleição)"""
    try:
        rede.ler_json(CKAN.format(f"resultados-{ano}-boletim-de-urna"))
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def votacao_secao(ano, log=print):
    """Votação por seção do arquivo nacional (BR), que traz só Presidente. Sem hash publicado: confere pelo tamanho.
    O TSE republica o arquivo depois do 2º turno; o tamanho diferente faz baixar de novo."""
    url = f"{ODSELE}/votacao_secao/votacao_secao_{ano}_BR.zip"
    log(f"   votação por seção {ano}: {_baixar_conferindo(url, pasta('votacao_secao', ano) / url.rsplit('/', 1)[1])}")


def locais(ano, log=print):
    url = f"{ODSELE}/eleitorado_locais_votacao/eleitorado_local_votacao_{ano}.zip"
    log(f"   locais de votação {ano}: {_baixar_conferindo(url, pasta('locais_votacao', ano) / url.rsplit('/', 1)[1])}")


def _so_cabecalho(caminho):
    with open(caminho, "rb") as f:
        f.readline()
        return not f.readline().strip()


def totais_oficiais(ano, log=print):
    """Do zip de 'votação nominal por município e zona' (centenas de MB), só o arquivo de Presidente e o leiame.

    O de 2026 saiu em 05/10/2026 com o arquivo de Presidente vazio (só o cabeçalho; os arquivos das UFs e o
    nacional com todos os cargos também não têm Presidente). Nesse caso nada é guardado e o comando avisa.
    """
    url = f"{ODSELE}/votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip"
    for membro in (f"votacao_candidato_munzona_{ano}_BR.csv", "leiame.pdf"):
        destino = pasta("totais_oficiais", ano) / membro
        if _ja_baixado(destino):
            log(f"   {membro}: já estava baixado")
            continue
        rede.extrair_de_zip_remoto(url, membro, destino)  # o zipfile confere o CRC do arquivo extraído
        if membro.endswith(".csv") and _so_cabecalho(destino):
            destino.unlink()
            log(f"   {membro}: o TSE ainda não pôs os votos de Presidente no arquivo (só o cabeçalho); fica para depois")
            continue
        (sha,) = rede.hashes(destino, "sha512")
        manifesto.registrar(destino, f"{url}#{membro}", sha, "CRC do zip")
        log(f"   {membro}: {destino.stat().st_size / 1e6:.1f} MB extraídos do zip remoto")


def pesquisas(ano, log=print):
    """Registro de pesquisas eleitorais (PesqEle): número de registro, empresa, datas, amostra. Sem os números
    das pesquisas, que o TSE não publica. Sem hash publicado: confere pelo tamanho."""
    url = f"{ODSELE}/pesquisa_eleitoral/pesquisa_eleitoral_{ano}.zip"
    log(f"   registro de pesquisas {ano}: {_baixar_conferindo(url, pasta('pesquisas', ano) / url.rsplit('/', 1)[1])}")


def municipios(log=print):
    destino = pasta("municipios", URL_MUNICIPIOS.rsplit("/", 1)[1])
    if _ja_baixado(destino):
        log(f"   {destino.name}: já estava baixado")
        return
    rede.baixar(URL_MUNICIPIOS, destino)
    json.loads(destino.read_text("utf-8"))  # falha aqui se veio algo que não é JSON
    (sha,) = rede.hashes(destino, "sha512")
    manifesto.registrar(destino, URL_MUNICIPIOS, sha, "json válido")
    log(f"   {destino.name}: ok")
