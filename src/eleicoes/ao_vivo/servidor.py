"""Serve o painel da apuração (painel.html) em http://localhost:8765.

O próprio servidor busca os dados no TSE a cada 60 s (via historico.py),
reconstrói o histórico da apuração e entrega tudo pronto em /dados.json.
Quem abre o painel nunca fala com o TSE pelo seu computador: só lê esse JSON.

Uso:
    uv run eleicoes ao-vivo             só no seu computador
    uv run eleicoes ao-vivo --publico   também gera um link https para
                                        compartilhar (precisa do cloudflared)
Ctrl+C encerra tudo, inclusive o link público.
A eleição acompanhada vem de [ao_vivo] em config/eleicoes.toml.
"""
import base64
import datetime as dt
import hashlib
import http.server
import json
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from eleicoes.ao_vivo import historico as H

PORTA = H.AV.porta
INTERVALO = 60          # o TSE marca os arquivos com cache de ~60 s; menos que isso não traz nada novo
LIMITE_MUN = 400        # resultados municipais por rodada, para não martelar o TSE
FOLGA_MUN = 0.15        # só relê um município quando ele recebeu 15% a mais de seções
REVISITA_MUN = 180      # e no máximo uma vez a cada 3 minutos
PAGINA = pathlib.Path(__file__).with_name("painel.html")
ARQ_OFICIAIS = H.AV.bruto / "leituras_oficiais.json"  # dado bruto: não dá para baixar de novo depois

estado = {"json": None, "ok": 0.0, "erro": None}


def agora():
    return dt.datetime.now().strftime("%H:%M:%S")


# ---- Coleta em segundo plano ----------------------------------------------------
def carregar_oficiais():
    try:
        return json.loads(ARQ_OFICIAIS.read_text("utf-8"))
    except (OSError, ValueError):
        return []


def registrar_oficial(oficiais, serie):
    """Guarda cada novo retrato do arquivo nacional do TSE (vira os pontos do gráfico)."""
    of = serie["oficial"]
    if of["dv"] == "n" or not of["vv"]:
        return
    h = dt.datetime.strptime(f"{of['dt']} {of['ht']}", "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%S")
    if any(o["h"] == h for o in oficiais):
        return
    oficiais.append({"h": h, "pst": of["pst"], "cand": {c["n"]: {"p": c["p"], "v": c["v"]} for c in of["cand"]}})
    oficiais.sort(key=lambda o: o["h"])
    ARQ_OFICIAIS.parent.mkdir(parents=True, exist_ok=True)
    ARQ_OFICIAIS.write_text(json.dumps(oficiais), "utf-8")


def coletar_sempre():
    oficiais = carregar_oficiais()
    while True:
        inicio = time.time()
        try:
            c = H.coletar(limite=LIMITE_MUN, folga=FOLGA_MUN, revisita=REVISITA_MUN, log=lambda *_: None)
            s = H.reconstruir(c, max_cand=4)
            registrar_oficial(oficiais, s)
            s["t"] = [t.strftime("%Y-%m-%dT%H:%M") for t in s["t"]]
            s["oficiais"] = oficiais
            s["municipios_atrasados"] = c["atrasados"]
            estado["json"] = json.dumps(s, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            estado["ok"], estado["erro"] = time.time(), None
            of = s["oficial"]
            print(f"[{agora()}] TSE {of['ht']}: {of['pst']:.2f}% totalizadas · "
                  f"{s['recebidas'][-1] / s['total_secoes'] * 100:.2f}% com boletim recebido · "
                  f"{c['baixados']} municípios consultados"
                  + (f", {c['atrasados']} aguardando o TSE publicar resultado novo" if c["atrasados"] else ""))
        except Exception as e:  # rede fora, TSE fora do ar etc.: tenta de novo na próxima rodada
            estado["erro"] = str(e) or e.__class__.__name__
            print(f"[{agora()}] sem dados novos do TSE: {estado['erro']}")
        time.sleep(max(5, INTERVALO - (time.time() - inicio)))


# ---- HTTP ---------------------------------------------------------------------------
def pagina_e_politica():
    html = PAGINA.read_bytes()
    # A política de segurança só deixa rodar o script embutido desta página (pelo hash dele)
    # e o Chart.js do cdnjs; a página só consegue buscar dados do próprio servidor.
    scripts = re.findall(rb"<script>(.*?)</script>", html, re.S)
    hashes = " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(s).digest()).decode()}'" for s in scripts)
    csp = ("default-src 'none'; "
           f"script-src {hashes} https://cdnjs.cloudflare.com; "
           "style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
           "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return html, csp


class Painel(http.server.BaseHTTPRequestHandler):
    server_version = "painel"
    sys_version = ""

    def do_GET(self):
        caminho = self.path.split("?", 1)[0]
        if caminho in ("/", "/index.html"):
            html, csp = pagina_e_politica()
            self._enviar(200, html, "text/html; charset=utf-8", {"Content-Security-Policy": csp})
        elif caminho == "/dados.json":
            if estado["json"] is None:
                corpo = json.dumps({"carregando": True, "erro": estado["erro"]}).encode()
                self._enviar(503, corpo, "application/json; charset=utf-8")
                return
            idade = int(time.time() - estado["ok"])
            erro = json.dumps(estado["erro"]).encode()
            corpo = b'{"idade":%d,"erro":%s,"dados":%s}' % (idade, erro, estado["json"])
            self._enviar(200, corpo, "application/json; charset=utf-8")
        else:
            self._enviar(404, b"", "text/plain")

    def _enviar(self, codigo, corpo, tipo, extra=None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args):
        pass


# ---- Link público (Cloudflare Quick Tunnel) ------------------------------------------
def abrir_tunel():
    exe = shutil.which("cloudflared")
    for p in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe"):
        if not exe and pathlib.Path(p).exists():
            exe = p
    if not exe:
        print("\n  Não achei o cloudflared. Instale uma vez com:\n"
              "      winget install --id Cloudflare.cloudflared\n"
              "  feche e abra o terminal, e rode de novo com --publico.\n"
              "  O painel segue funcionando só neste computador.\n")
        return None
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORTA}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace")

    def ler():
        for linha in proc.stdout:
            m = re.search(r"https://[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com", linha)
            if m:
                print("\n  ┌──────────────────────────────────────────────────────────────┐")
                print(f"     Link para compartilhar:  {m.group(0)}")
                print("     Funciona enquanto este programa estiver aberto.")
                print("  └──────────────────────────────────────────────────────────────┘\n")
            elif re.search(r"\b(ERR|error)\b", linha) and "trycloudflare" not in linha:
                print("  [cloudflared] " + linha.strip()[-160:])

    threading.Thread(target=ler, daemon=True).start()
    return proc


def rodar(publico=False, abrir_navegador=True):
    sys.stdout.reconfigure(line_buffering=True)  # mostra cada rodada na hora, mesmo fora de um terminal
    threading.Thread(target=coletar_sempre, daemon=True).start()
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", PORTA), Painel)
    servidor.daemon_threads = True
    url = f"http://localhost:{PORTA}/"
    print(f"Painel da eleição {H.ELEICAO} ({H.AV.turno}º turno {H.AV.ano}) em {url}  (Ctrl+C para encerrar)")
    print("Buscando os dados do TSE; a primeira leitura pode levar até um minuto…")
    tunel = abrir_tunel() if publico else None
    if abrir_navegador:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if tunel:
            tunel.terminate()
        print("Encerrado.")
