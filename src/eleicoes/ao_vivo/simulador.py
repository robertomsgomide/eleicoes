"""Simulador da noite, para desenvolver e conferir a página de 2026 sem esperar o dia 25: `uv run eleicoes simular`.

Refaz a noite do 2º turno de 2022 (ou de 2018) seção a seção, como na validação do forecast
(modelos/forecast_validacao.py: os municípios lidos com as regras do coletor e o total de cada UF a cada minuto), e
serve, num endereço local, o que a página lê na noite de verdade:

  /ramo-a/dados.json, /ramo-a/mapa.json (e -b, -c)   o que os coletores gravam (painel.py), com o forecast a cada 3 min
  /tse/dados/<abr>/<abr>-c0001-e006258-u.json        o arquivo de resultado do país ("br") e de cada UF, como o do TSE

O relógio da noite começa em `inicio` minutos depois das 17h e anda `velocidade` vezes mais rápido que o real;
/relogio?t=<minuto> põe o relógio num minuto (e /relogio, sem nada, diz em que minuto está). A página, em localhost:

  http://localhost:3000/2026?ao-vivo=http://localhost:8765/ramo-{c}/&tse=http://localhost:8765/tse/

Os nomes na página são os de 2026; os números, os da noite refeita. Só para desenvolver: nada disso vai para o site.
"""
import datetime as dt
import http.server
import json
import threading
import time
import types
import urllib.parse

import numpy as np

from eleicoes.ao_vivo import painel
from eleicoes.modelos import forecast as F
from eleicoes.modelos import forecast_validacao as V

INICIO = dt.datetime(2026, 10, 25, 17, 0)  # a noite refeita é mostrada como se fosse a de 2026
NUMEROS = {"petismo": "13", "bolsonarismo": "22"}
NOMES = {"13": "LULA", "22": "FLAVIO BOLSONARO"}
A_CADA = 3  # min entre dois forecasts, como os envios dos coletores
BRANCOS_E_NULOS = 0.04  # para o comparecimento dos arquivos simulados (os da noite refeita só têm os votos dos dois)
ABSTENCAO = 0.21


class Noite:
    """A noite refeita, minuto a minuto: os totais oficiais de cada UF e do país, e o forecast."""

    def __init__(self, ano=2022, log=print):
        log(f"Refazendo a noite do 2º turno de {ano}…")
        self.noite = V.noite(ano)
        self.leituras = V.Leituras(self.noite, self.noite.chegada)
        p = self.noite.prior
        self.fim = self.leituras.fim
        uf_sec = p.uf_mun[p.mun]
        U = len(F.UFS)
        # seções totalizadas, votos de cada um, por UF e minuto
        minuto = np.clip(np.ceil(self.noite.chegada + V.ATRASO_TOTALIZACAO), 0, self.fim).astype(int)
        forma = (self.fim + 1, U)
        self.st, self.pt, self.bo = (np.zeros(forma) for _ in range(3))
        np.add.at(self.st, (minuto, uf_sec), 1)
        np.add.at(self.pt, (minuto, uf_sec), self.noite.petismo)
        np.add.at(self.bo, (minuto, uf_sec), self.noite.bolsonarismo)
        self.st, self.pt, self.bo = (np.cumsum(x, axis=0) for x in (self.st, self.pt, self.bo))
        self.ts = np.bincount(uf_sec, minlength=U)
        self.previsor = self.atual = None
        self.feito = -1
        self.cache = {}
        self.trava = threading.Lock()

    def leitura(self, m, k=None):
        """A leitura (formato do coletor) do país (k=None) ou da UF k no minuto m; None antes de haver votos."""
        if k is None:
            st, pt, bo, ts = self.st[m].sum(), self.pt[m].sum(), self.bo[m].sum(), self.ts.sum()
        else:
            st, pt, bo, ts = self.st[m, k], self.pt[m, k], self.bo[m, k], self.ts[k]
        vv = pt + bo
        if not vv:
            return None
        c = round(vv / (1 - BRANCOS_E_NULOS))
        fim = st >= ts
        return {"abr": "br" if k is None else F.UFS[k], "h": f"{INICIO + dt.timedelta(minutes=int(m)):%Y-%m-%dT%H:%M:%S}",
                "pst": round(100 * st / ts, 4), "st": int(st), "ts": int(ts), "and": "f" if fim else "p",
                "tf": "s" if fim else "n", "c": int(c), "a": int(round(c * ABSTENCAO / (1 - ABSTENCAO))),
                "tv": int(c), "vv": int(vv), "vb": 0, "tvn": int(c - vv),
                "cand": {NUMEROS["petismo"]: {"v": int(pt)}, NUMEROS["bolsonarismo"]: {"v": int(bo)}}}

    def _mudou(self, m, k=None):
        """O arquivo mudou no minuto m? (o TSE só publica versão nova quando há seção nova)"""
        if m == 0:
            return True
        x = self.st[:, k] if k is not None else self.st.sum(1)
        return x[m] != x[m - 1]

    def leituras_ate(self, m):
        br = [l for t in range(m + 1) if self._mudou(t) and (l := self.leitura(t))]
        ufs = {F.UFS[k]: [l for t in range(m + 1) if self._mudou(t, k) and (l := self.leitura(t, k))]
               for k in range(len(F.UFS))}
        return br, {u: ls for u, ls in ufs.items() if ls}

    def avancar(self, m):
        """O forecast de cada envio até o minuto m (refaz do começo se o relógio voltou)."""
        if self.previsor is None or m < self.feito:
            self.previsor = painel.Previsor(self.noite.prior, INICIO, NUMEROS, log=lambda *_: None)
            self.feito, self.atual = -1, None
        for t in range(self.feito + 1, m + 1):
            if t % A_CADA == 0:
                br = self.leitura(t)
                if br:
                    self.atual = self.previsor.prever_apurado(self.leituras.apurado(t), br)
        self.feito = m

    def arquivos(self, m):
        """{nome: conteúdo} do minuto m: dados.json, mapa.json e os arquivos do TSE."""
        m = int(min(max(m, 0), self.fim))
        with self.trava:
            if m in self.cache:
                return self.cache[m]
            self.avancar(m)
            br, ufs = self.leituras_ate(m)
            av = types.SimpleNamespace(ano=2026, turno=2, inicio=INICIO, eleicao="6258")
            out = {"dados.json": painel.dados("simulador", f"minuto {m}", None, av, br, ufs, self.atual,
                                              self.previsor.historico),
                   "mapa.json": self.previsor.mapa()}
            for k in [None, *range(len(F.UFS))]:
                abr = "br" if k is None else F.UFS[k]
                out[f"tse/{abr}"] = arquivo_tse(self.leitura(m, k), abr)
            self.cache = {m: out}
            return out


def arquivo_tse(l, abr):
    """Uma leitura no formato do arquivo de resultado do TSE (só os campos que o site e o coletor leem)."""
    if l is None:
        return {"cdabr": abr, "dt": "", "ht": "", "dv": "s", "tf": "n", "and": "n", "s": {"st": "0", "ts": "0"},
                "v": {"vv": "0"}, "e": {"c": "0", "a": "0"}, "carg": []}
    h = dt.datetime.fromisoformat(l["h"])
    return {"cdabr": abr, "dt": f"{h:%d/%m/%Y}", "ht": f"{h:%H:%M:%S}", "dv": "s", "tf": l["tf"], "and": l["and"],
            "s": {"st": str(l["st"]), "ts": str(l["ts"]), "pstn": f"{l['pst']:.4f}".replace(".", ",")},
            "v": {"tv": str(l["tv"]), "vv": str(l["vv"]), "vb": "0", "tvn": str(l["tvn"])},
            "e": {"c": str(l["c"]), "a": str(l["a"])},
            "carg": [{"cand": [{"n": n, "nmu": NOMES[n], "vap": str(v["v"])} for n, v in l["cand"].items()]}]}


def servir(ano=2022, porta=8765, inicio=0, velocidade=10.0, log=print):
    noite = Noite(ano, log)
    relogio = {"base": time.time(), "t0": float(inicio)}

    def agora():
        return relogio["t0"] + (time.time() - relogio["base"]) * velocidade / 60

    class Pedido(http.server.BaseHTTPRequestHandler):
        def _json(self, dados, codigo=200):
            corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            partes = [p for p in url.path.split("/") if p]
            if partes[:1] == ["relogio"]:
                q = urllib.parse.parse_qs(url.query)
                if "t" in q:
                    relogio.update(base=time.time(), t0=float(q["t"][0]))
                return self._json({"minuto": round(agora(), 1), "fim": noite.fim})
            m = int(agora())
            if len(partes) == 2 and partes[0].startswith("ramo-") and partes[1] in ("dados.json", "mapa.json"):
                return self._json(noite.arquivos(m)[partes[1]])
            if partes[:2] == ["tse", "dados"] and len(partes) == 4:
                arq = noite.arquivos(m).get(f"tse/{partes[2]}")
                return self._json(arq) if arq is not None else self._json({"erro": "não existe"}, 404)
            self._json({"erro": "não existe"}, 404)

        def log_message(self, *_):
            pass

    log(f"Simulador da noite de {ano} em http://localhost:{porta} (minuto {inicio}, {velocidade:g}× mais rápido).")
    log(f"Página: http://localhost:3000/2026?ao-vivo=http://localhost:{porta}/ramo-{{c}}/&tse=http://localhost:{porta}/tse/")
    http.server.ThreadingHTTPServer(("127.0.0.1", porta), Pedido).serve_forever()
