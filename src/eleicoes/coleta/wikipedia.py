"""Páginas de pesquisas eleitorais da Wikipedia em português, guardadas como HTML junto com a revisão usada.

O texto da Wikipedia é licenciado sob CC BY-SA 4.0: a base de pesquisas derivada dele herda a licença
(ver docs/dados.md).
"""
import datetime as dt
import json
import urllib.parse

from eleicoes import config
from eleicoes.coleta import manifesto, rede

API = "https://pt.wikipedia.org/w/api.php"
PAGINA = "Pesquisas de opinião para a eleição presidencial no Brasil em {ano}"


def arquivo(ano):
    return config.BRUTO / "wikipedia" / f"pesquisas_presidente_{ano}.html"


def revisao(ano):
    """Metadados da revisão guardada: título, revid, url fixa, data do download e, depois de uma conferência do
    `uv run eleicoes atualizar`, `consultado_em`: até quando ela ainda tinha as mesmas pesquisas da página atual."""
    meta = arquivo(ano).with_suffix(".json")
    return json.loads(meta.read_text("utf-8")) if meta.exists() else None


def _agora():
    return dt.datetime.now().isoformat(timespec="seconds")


def ultima_revisao(ano):
    """Número da revisão atual da página, sem baixar o texto (consulta leve, para saber se ela mudou).
    Se a página for renomeada, segue o redirecionamento."""
    url = API + "?" + urllib.parse.urlencode({"action": "query", "prop": "revisions", "titles": PAGINA.format(ano=ano),
                                             "redirects": 1, "rvprop": "ids", "format": "json", "formatversion": 2})
    return rede.ler_json(url)["query"]["pages"][0]["revisions"][0]["revid"]


def buscar(ano, revid=None):
    """(html, metadados) de uma revisão da página (sem `revid`, a atual), sem gravar nada."""
    titulo = PAGINA.format(ano=ano)
    url = API + "?" + urllib.parse.urlencode({"action": "parse", **({"oldid": revid} if revid else {"page": titulo, "redirects": 1}),
                                             "prop": "text|revid", "format": "json", "formatversion": 2})
    r = rede.ler_json(url)["parse"]
    return r["text"], {"titulo": titulo, "revid": r["revid"], "url": f"https://pt.wikipedia.org/w/index.php?oldid={r['revid']}",
                       "baixado_em": _agora()}


def guardar(ano, html, meta, log=print):
    destino = arquivo(ano)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, "utf-8")
    destino.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    (sha,) = rede.hashes(destino, "sha512")
    manifesto.registrar(destino, meta["url"], sha, "revisão da Wikipedia")
    log(f"   Wikipedia {ano}: revisão {meta['revid']} ({destino.stat().st_size / 1e6:.1f} MB)")


def consultada(ano):
    """Anota que a revisão guardada continua com as mesmas pesquisas da página atual (a projeção vai até hoje)."""
    meta = {**revisao(ano), "consultado_em": _agora()}
    arquivo(ano).with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")


def baixar(ano, atualizar=False, log=print):
    """Guarda a página do ano. Sem `atualizar`, mantém a revisão já baixada (reprodutibilidade)."""
    if arquivo(ano).exists() and not atualizar:
        log(f"   Wikipedia {ano}: revisão {revisao(ano)['revid']} já baixada (use --atualizar para pegar a atual)")
        return
    guardar(ano, *buscar(ano), log=log)
