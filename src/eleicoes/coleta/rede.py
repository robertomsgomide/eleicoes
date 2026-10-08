"""Downloads: arquivo inteiro com retomada, hashes e leitura de um único arquivo de dentro de um zip remoto."""
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile

AGENTE = "estudo-eleicoes/0.1 (https://github.com/robertomsgomide/eleicoes; pesquisa academica com dados publicos)"
BLOCO = 1 << 20


def abrir(url, faixa=None, metodo="GET", tentativas=4):
    cab = {"User-Agent": AGENTE}
    if faixa:
        cab["Range"] = f"bytes={faixa}"
    for i in range(tentativas):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=cab, method=metodo), timeout=60)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 416):  # o TSE bloqueia por um tempo quem insiste em 404
                raise
            erro = e
        except OSError as e:  # timeout, conexão caiu etc.
            erro = e
        time.sleep(3 * (i + 1))
    raise erro


def tamanho(url):
    with abrir(url, metodo="HEAD") as r:
        return int(r.headers["Content-Length"])


def texto(url):
    with abrir(url) as r:
        return r.read().decode("utf-8", "replace")


def ler_json(url):
    return json.loads(texto(url))


def baixar(url, destino, tamanho_esperado=None):
    """Baixa para destino passando por destino.parte; se a conexão cair, retoma de onde parou."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parte = destino.with_name(destino.name + ".parte")
    for tentativa in range(6):
        feito = parte.stat().st_size if parte.exists() else 0
        if tamanho_esperado is not None and feito == tamanho_esperado:
            break
        try:
            with abrir(url, faixa=f"{feito}-" if feito else None) as r:
                modo = "ab" if feito and r.status == 206 else "wb"  # sem suporte a Range: recomeça
                with open(parte, modo) as f:
                    while bloco := r.read(BLOCO):
                        f.write(bloco)
            break
        except OSError:
            if tentativa == 5:
                raise
            time.sleep(5 * (tentativa + 1))
    if tamanho_esperado is not None and parte.stat().st_size != tamanho_esperado:
        raise IOError(f"{destino.name}: baixou {parte.stat().st_size} bytes, esperava {tamanho_esperado}")
    parte.replace(destino)


def hashes(caminho, *algoritmos):
    hs = [hashlib.new(a) for a in algoritmos]
    with open(caminho, "rb") as f:
        while bloco := f.read(8 * BLOCO):
            for h in hs:
                h.update(bloco)
    return [h.hexdigest() for h in hs]


class ArquivoRemoto(io.RawIOBase):
    """Arquivo remoto com seek: o zipfile lê só o índice do zip e o arquivo pedido, por HTTP Range."""

    def __init__(self, url):
        self.url, self.pos, self.tam = url, 0, tamanho(url)

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, pos, whence=io.SEEK_SET):
        self.pos = {io.SEEK_SET: pos, io.SEEK_CUR: self.pos + pos, io.SEEK_END: self.tam + pos}[whence]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.tam:
            return 0
        fim = min(self.pos + len(b), self.tam) - 1
        with abrir(self.url, faixa=f"{self.pos}-{fim}") as r:
            dados = r.read()
        b[:len(dados)] = dados
        self.pos += len(dados)
        return len(dados)


def extrair_de_zip_remoto(url, membro, destino):
    """Copia um arquivo de dentro de um zip remoto sem baixar o zip inteiro."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parte = destino.with_name(destino.name + ".parte")
    remoto = io.BufferedReader(ArquivoRemoto(url), buffer_size=BLOCO)
    with zipfile.ZipFile(remoto) as z, z.open(membro) as origem, open(parte, "wb") as f:
        while bloco := origem.read(BLOCO):
            f.write(bloco)
    parte.replace(destino)
