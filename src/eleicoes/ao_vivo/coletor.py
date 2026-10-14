"""Coleta da apuração na nuvem, sem depender de um computador ligado: `uv run eleicoes coletar`.

Quem roda é o GitHub Actions (.github/workflows/apuracao.yml). Grava o que o TSE não deixa baixar depois:
  * cada atualização do total do país e de cada UF (o arquivo de resultado só guarda o último retrato);
  * cada atualização do resultado de cada município;
  * de cada seção, o horário de chegada do boletim como o TSE mostrava na primeira vez que ela apareceu (o TSE
    reescreve esses horários quando a apuração acaba; ver docs/ROADMAP.md).

Três coletores (a, b, c) rodam ao mesmo tempo, cada um no seu job, com atrasos simétricos entre si, para um cobrir
o outro:
  * leem o TSE a cada 60 s, defasados de 20 s: a no segundo 0 de cada minuto, b no 20, c no 40;
  * um job do Actions dura no máximo 6 h, então cada coletor passa a vez para um job novo nas suas "fronteiras", a
    cada 5h40; as fronteiras dos três ficam defasadas de 1h53, e enquanto um troca de job os outros dois seguem lendo.
Cada coletor grava no seu ramo do git (ao-vivo-a, -b, -c), só acrescentando arquivos, e envia a cada 3 min; o job
seguinte retoma do ramo. Quando a apuração acaba, juntar.py junta os três em dados/bruto/ao_vivo/<ciclo>-<eleicao>.

O que cada job grava, em <ramo>/<job>/ (cada envio fecha os pedaços abertos; os registros seguintes vão para outros):
  leituras_br-NNNN.jsonl   cada versão nova do arquivo do país (h: horário do TSE; visto: quando o coletor leu)
  leituras_uf-NNNN.jsonl   idem, de cada UF e do exterior (zz)
  municipios-NNNN.jsonl    cada versão nova do resultado de um município
  secoes-NNNN.csv          uf,municipio,zona,secao,recebido,visto: cada seção na primeira vez que aparece recebida
  rodadas-NNNN.jsonl       cada leitura do TSE: duração, erro, % totalizado
  job.json                 quem, quando, até quando
E, refeitos a cada envio, o que o site lê para acompanhar a noite (painel.py): <ramo>/dados.json (a apuração com as
leituras oficiais do país e das UFs e o forecast do resultado final) e <ramo>/mapa.json (o apurado e o swing estimado
de cada município).
"""
import concurrent.futures as cf
import datetime as dt
import json
import math
import os
import pathlib
import subprocess
import sys
import time
import urllib.error

from eleicoes.ao_vivo import historico as H
from eleicoes.ao_vivo import painel as P
from eleicoes.formato_tse import candidatos, num

AV = H.AV
COLETORES = "abc"
INTERVALO = 60                                   # s entre duas leituras de um coletor (o TSE guarda os arquivos ~60 s)
LIMITE_MUN = 400                                 # resultados municipais por rodada, para não martelar o TSE
FOLGA_MUN = 0.15                                 # só relê um município quando ele recebeu 15% a mais de seções
REVISITA_MUN = 180                               # e no máximo uma vez a cada 3 minutos
DEFASAGEM = INTERVALO // len(COLETORES)          # 20 s entre um coletor e o seguinte
ENVIO = 180                                      # s entre dois envios para o ramo
PERIODO = 340                                    # min entre duas trocas de job de um coletor (um job dura até 6 h)
EPOCA = AV.inicio - dt.timedelta(minutes=40)     # troca do coletor a às 16h20; as do b e do c, 1h53 e 3h47 depois
LIBERAR = AV.inicio - dt.timedelta(minutes=90)   # os coletores começam às 15h30
ESPERA_MAXIMA = 345                              # min que a rodada do workflow espera antes de disparar a si mesma
ARMAR = dt.timedelta(hours=24)                   # antes disso, ligar o workflow não faz nada (não fica dias esperando)
FIM_MAXIMO = AV.inicio + dt.timedelta(hours=13)  # a coleta vai no máximo até as 6h do dia seguinte
MARGEM_FIM = dt.timedelta(hours=1)               # e continua 1 h depois de o TSE fechar a totalização
ANTECEDENCIA = dt.timedelta(minutes=5)           # um job nunca termina a menos disso de quando começou
BLOQUEIO = 10                                    # rodadas seguidas com 403: o job sai e o próximo vem em outro runner
ENSAIO = {"periodo": 12, "duracao": dt.timedelta(minutes=30), "antecedencia": dt.timedelta(minutes=2),
          "limite_mun": 40}
TIPOS = ("leituras_br", "leituras_uf", "municipios", "secoes", "rodadas")


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def horario(d):
    """O horário do TSE num arquivo de resultado (campos dt e ht), em ISO; "" se ainda não há."""
    if not (d.get("dt") and d.get("ht")):
        return ""
    return iso(dt.datetime.strptime(f"{d['dt']} {d['ht']}", "%d/%m/%Y %H:%M:%S"))


# ---- Quando: o plano da rodada do workflow e as fronteiras de cada coletor ---------------------------------

def plano(agora, ensaio=False, juntado=False, juntar=False):
    """O que a rodada do workflow faz: {"acao", "espera" (s), "epoca", "periodo" (min), "fim"}.

    acao: "coletar" (depois de esperar `espera`, os três coletores começam), "esperar" (cedo demais: espera e dispara o
    workflow de novo), "juntar" (a coleta acabou: só junta o que foi gravado) ou "nada" (já foi juntado, ou faltam
    mais de 24 h para os coletores começarem).
    """
    p = {"acao": "coletar", "espera": 0, "epoca": EPOCA, "periodo": PERIODO, "fim": FIM_MAXIMO}
    if ensaio:
        return {**p, "epoca": agora, "periodo": ENSAIO["periodo"], "fim": agora + ENSAIO["duracao"]}
    if juntar:
        return {**p, "acao": "juntar"}
    if juntado or LIBERAR - agora > ARMAR:
        return {**p, "acao": "nada"}
    if agora >= FIM_MAXIMO:
        return {**p, "acao": "juntar"}
    espera = max(0, round((LIBERAR - agora).total_seconds()))
    if espera > ESPERA_MAXIMA * 60:
        return {**p, "acao": "esperar", "espera": ESPERA_MAXIMA * 60}
    return {**p, "espera": espera}


def prazo(coletor, agora, epoca, periodo, fim, antecedencia=ANTECEDENCIA):
    """Quando o job atual do coletor passa a vez: a primeira fronteira dele a pelo menos `antecedencia` de agora.

    As fronteiras do coletor a ficam em epoca + n·periodo; as do b, um terço de período depois; as do c, dois terços.
    Nunca depois do fim da coleta.
    """
    passo = dt.timedelta(minutes=periodo)
    base = epoca + COLETORES.index(coletor) * passo / len(COLETORES)
    n = math.ceil((agora + antecedencia - base) / passo)
    return min(base + n * passo, fim)


def proxima_leitura(agora, coletor):
    """O próximo instante de leitura do coletor: no segundo 0 (a), 20 (b) ou 40 (c) de cada minuto."""
    t = agora.replace(second=0, microsecond=0) + dt.timedelta(seconds=COLETORES.index(coletor) * DEFASAGEM)
    while t <= agora:
        t += dt.timedelta(seconds=INTERVALO)
    return t


def fim_da_apuracao(leituras):
    """Horário (do TSE) da primeira leitura do país com a totalização fechada, ou None."""
    fechadas = [l["h"] for l in leituras if l["pst"] >= 100 or l.get("tf") == "s" or l.get("and") == "f"]
    return dt.datetime.fromisoformat(min(fechadas)) if fechadas else None


def acabou(leituras, agora, fim=FIM_MAXIMO):
    """A coleta acabou? No fim máximo, ou 1 h depois de o TSE fechar a totalização do país."""
    fechou = fim_da_apuracao(leituras)
    return agora >= fim or (fechou is not None and agora >= fechou + MARGEM_FIM)


# ---- O que se grava ------------------------------------------------------------------------------------------

def leitura(d, visto):
    """Uma versão do arquivo de resultado do país ou de uma UF, resumida; None antes de haver votos divulgados.
    Tem os campos das leituras do 1º turno (h, pst, cand) e mais os totais do arquivo."""
    v, s, e = d.get("v", {}), d.get("s", {}), d.get("e", {})
    vv = num(v.get("vv"))
    if not (horario(d) and vv) or d.get("dv") == "n":
        return None
    cand = sorted(candidatos(d).items(), key=lambda nv: -nv[1])
    return {"abr": d.get("cdabr", ""), "h": horario(d), "pst": num(s.get("pstn") or s.get("pst")),
            "st": int(num(s.get("st"))), "ts": int(num(s.get("ts"))), "and": d.get("and", ""), "tf": d.get("tf", ""),
            "c": int(num(e.get("c"))), "a": int(num(e.get("a"))), "tv": int(num(v.get("tv"))), "vv": int(vv),
            "vb": int(num(v.get("vb"))), "tvn": int(num(v.get("tvn"))),
            "cand": {n: {"p": round(100 * x / vv, 3), "v": int(x)} for n, x in cand}, "visto": iso(visto)}


def registro_municipio(uf, mu, r, visto):
    """Uma versão do resultado de um município (o resumo de historico.resumo_resultado)."""
    return {"uf": uf, "mu": mu, "h": horario(r), "st": r["st"], "ts": r["ts"], "and": r["and"], "vv": int(r["vv"]),
            "cand": {n: int(v) for n, v in r["cand"].items()}, "visto": iso(visto)}


def resumo_do_registro(r):
    """O inverso de registro_municipio: o resumo que historico.coletar usa (sem etag: a primeira leitura é inteira)."""
    h = dt.datetime.fromisoformat(r["h"]) if r["h"] else None
    return {"st": r["st"], "ts": r["ts"], "and": r["and"], "vv": float(r["vv"]),
            "cand": {n: float(v) for n, v in r["cand"].items()}, "dt": f"{h:%d/%m/%Y}" if h else "",
            "ht": f"{h:%H:%M:%S}" if h else "", "etag": None}


class Gravador:
    """Os arquivos de um job, só acrescentados. Cada envio fecha os pedaços abertos: os registros seguintes vão para
    pedaços novos, e o git guarda cada pedaço uma vez só."""

    def __init__(self, pasta):
        self.pasta = pathlib.Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        numeros = [int(a.stem.rsplit("-", 1)[1]) for a in self.pasta.glob("*-[0-9][0-9][0-9][0-9].*")]
        self.pedaco = max(numeros, default=0) + 1  # um job repetido continua a numeração

    def _arquivo(self, tipo):
        return self.pasta / f"{tipo}-{self.pedaco:04d}.{'csv' if tipo == 'secoes' else 'jsonl'}"

    def json(self, tipo, *registros):
        if registros:
            with open(self._arquivo(tipo), "a", encoding="utf-8", newline="\n") as f:
                f.writelines(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in registros)

    def secoes(self, linhas):
        if linhas:
            with open(self._arquivo("secoes"), "a", encoding="utf-8", newline="\n") as f:
                f.writelines(",".join(l) + "\n" for l in linhas)

    def fechar(self):
        self.pedaco += 1


def registros(pastas, tipo):
    """Os registros de um tipo gravados nas pastas de ramo dadas (por todos os jobs), na ordem em que foram gravados.
    Seções vêm como tuplas (uf, municipio, zona, secao, recebido, visto)."""
    ext = "csv" if tipo == "secoes" else "jsonl"
    for raiz in pastas:
        arquivos = pathlib.Path(raiz).glob(f"*/{tipo}-[0-9][0-9][0-9][0-9].{ext}")
        for arq in sorted(arquivos, key=lambda a: (a.parent.name, a.name)):
            for linha in arq.read_text("utf-8").splitlines():
                if linha:
                    yield tuple(linha.split(",")) if ext == "csv" else json.loads(linha)


# ---- Git: cada coletor envia para o próprio ramo ---------------------------------------------------------------

def git(pasta, *args):
    return subprocess.run(["git", "-C", str(pasta), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)


def enviar(pasta, ramo, mensagem, log=print):
    """Commit de tudo o que mudou na pasta do ramo e push (também de commits que um envio anterior não conseguiu
    mandar). False se não deu: fica para o próximo envio."""
    try:
        git(pasta, "add", "-A")
        if git(pasta, "diff", "--cached", "--quiet").returncode:
            r = git(pasta, "commit", "-q", "-m", mensagem)
            if r.returncode:
                log(f"   commit no ramo {ramo} falhou: {r.stderr.strip()[-200:]}")
                return False
        for tentativa in range(3):
            r = git(pasta, "push", "-q", "origin", f"HEAD:refs/heads/{ramo}")
            if r.returncode == 0:
                return True
            if "rejected" in r.stderr or "fetch first" in r.stderr:  # não deveria: só este job envia para o ramo
                git(pasta, "pull", "-q", "--rebase", "origin", ramo)
            time.sleep(5 * (tentativa + 1))
        log(f"   envio para {ramo} falhou ({r.stderr.strip()[-200:]}); tenta de novo no próximo")
    except (OSError, subprocess.SubprocessError) as e:
        log(f"   envio para {ramo} falhou ({e}); tenta de novo no próximo")
    return False


# ---- O coletor -------------------------------------------------------------------------------------------------

class Coletor:
    def __init__(self, nome, pasta, ramo, job, epoca, periodo, fim, ensaio=False, usar_git=True, log=print):
        self.nome, self.raiz, self.ramo, self.job = nome, pathlib.Path(pasta), ramo, job
        self.epoca, self.periodo, self.fim, self.ensaio, self.usar_git, self.log = epoca, periodo, fim, ensaio, usar_git, log
        self.antecedencia = ENSAIO["antecedencia"] if ensaio else ANTECEDENCIA
        self.limite_mun = ENSAIO["limite_mun"] if ensaio else LIMITE_MUN
        self.vistas = set()   # seções já gravadas neste ramo ("uf,municipio,zona,secao")
        self.br = {}          # h -> leitura do país
        self.ufs = set()      # (abr, h) das leituras de UF já gravadas
        self.leituras_uf = {} # abr -> [leituras da UF], para a apuração por região no dados.json
        self.chegadas = []    # seções vistas desde a última conta do forecast: (uf, municipio, zona, secao, recebido)
        self.previsor = None  # o forecast (painel.Previsor), montado no primeiro envio
        self.sem_previsor = False
        self.previsoes = []   # o histórico do forecast que um job anterior deixou no dados.json
        self.mun = {}         # (uf, municipio) -> último registro gravado
        self.etags = {}       # uf -> etag do arquivo de resultado da UF
        self.erro_uf = {}     # uf -> quando o arquivo de resultado dela deu erro pela última vez
        self.c = None         # a última coleta (para o painel)
        self.erro = None      # o último erro, para o painel
        self.rodadas = self.falhas = 0
        self.grav = None

    def retomar(self):
        """Começa do que os jobs anteriores deste coletor gravaram no ramo."""
        pastas = [self.raiz]
        for l in registros(pastas, "leituras_br"):
            self.br[l["h"]] = l
        for l in registros(pastas, "leituras_uf"):
            if (l["abr"], l["h"]) not in self.ufs:
                self.ufs.add((l["abr"], l["h"]))
                self.leituras_uf.setdefault(l["abr"], []).append(l)
        for r in registros(pastas, "municipios"):
            antigo = self.mun.get((r["uf"], r["mu"]))
            if antigo is None or r["h"] >= antigo["h"]:
                self.mun[(r["uf"], r["mu"])] = r
        for s in registros(pastas, "secoes"):
            self.vistas.add(",".join(s[:4]))
            self.chegadas.append(s[:5])
        H.iniciar_municipios({k: resumo_do_registro(r) for k, r in self.mun.items()})
        try:
            self.previsoes = json.loads((self.raiz / "dados.json").read_text("utf-8")).get("previsoes") or []
        except (OSError, ValueError):
            self.previsoes = []
        if self.br or self.vistas:
            self.log(f"Retomando o ramo {self.ramo}: {len(self.br)} leituras do país, {len(self.mun):,} municípios e "
                     f"{len(self.vistas):,} seções já gravados.".replace(",", "."))

    def acabou(self, agora):
        if self.ensaio:  # o ensaio usa arquivos de uma apuração que já acabou: vai até o fim marcado
            return agora >= self.fim
        return acabou(self.br.values(), agora, self.fim)

    def _ufs(self):
        """Arquivos de resultado das UFs que mudaram desde a última rodada, e as UFs que deram erro. Uma UF com erro só
        é lida de novo depois de H.ESPERA_ERRO (o TSE bloqueia IPs que acumulam erros)."""
        def uma(uf):
            if time.time() - self.erro_uf.get(uf, 0) < H.ESPERA_ERRO:
                return uf, None, self.etags.get(uf), None
            try:
                return uf, *H.baixar(H.url_resultado(uf), self.etags.get(uf)), None
            except Exception as e:
                self.erro_uf[uf] = time.time()
                return uf, None, self.etags.get(uf), e
        with cf.ThreadPoolExecutor(H.PARALELO) as ex:
            resultado = list(ex.map(uma, H.UFS))
        for uf, _, etag, _ in resultado:
            self.etags[uf] = etag
        return [d for _, d, _, _ in resultado if d], [uf for uf, *_, e in resultado if e]

    def rodada(self):
        visto = dt.datetime.now()
        antes = visto < AV.inicio  # antes da divulgação, os municípios estão zerados
        c = H.coletar(limite=0 if antes else self.limite_mun, folga=FOLGA_MUN, revisita=REVISITA_MUN,
                      log=lambda *_: None)
        self.c = c
        novas = []
        for uf, chegadas in c["chegadas"].items():
            for mu, zona, secao, recebido in chegadas:
                chave = f"{uf},{mu},{zona},{secao}"
                if chave not in self.vistas:
                    self.vistas.add(chave)
                    novas.append((uf, mu, zona, secao, recebido, iso(visto)))
        self.grav.secoes(novas)
        self.chegadas.extend(s[:5] for s in novas)

        municipios = []
        for uf, mu in c["mun_novos"]:
            r = registro_municipio(uf, mu, c["mun"][(uf, mu)], visto)
            antigo = self.mun.get((uf, mu))
            if not r["h"]:  # ainda zerado: o TSE não divulgou nada deste município
                continue
            if antigo is None or (antigo["h"], antigo["st"], antigo["vv"]) != (r["h"], r["st"], r["vv"]):
                self.mun[(uf, mu)] = r
                municipios.append(r)
        self.grav.json("municipios", *municipios)

        pais = leitura(c["br"], visto)
        if pais and pais["h"] not in self.br:
            self.br[pais["h"]] = pais
            self.grav.json("leituras_br", pais)

        docs, erros_uf = self._ufs()
        ufs = [l for l in (leitura(d, visto) for d in docs) if l and (l["abr"], l["h"]) not in self.ufs]
        self.ufs.update((l["abr"], l["h"]) for l in ufs)
        for l in ufs:
            self.leituras_uf.setdefault(l["abr"], []).append(l)
        self.grav.json("leituras_uf", *ufs)

        recebidas = sum(sum(ch.values()) for m in c["secoes"].values() for _, ch in m.values())
        total = sum(t for m in c["secoes"].values() for t, _ in m.values())
        of = H.resumo_resultado(c["br"])
        pst = num(c["br"].get("s", {}).get("pstn") or c["br"].get("s", {}).get("pst"))
        self.grav.json("rodadas", {"h": iso(visto), "s": round((dt.datetime.now() - visto).total_seconds(), 1),
                                   "ok": True, "pst": pst, "rec": recebidas, "novas": len(novas),
                                   "mun": c["baixados"], "falhas_mun": c["falhas"], "atrasados": c["atrasados"],
                                   "ufs": len(ufs), "falhas_uf": erros_uf, "falhas_secoes": sorted(c["erros_secoes"])})
        avisos = [f"resultado de {', '.join(erros_uf).upper()} com erro" if erros_uf else "",
                  f"seções de {', '.join(sorted(c['erros_secoes'])).upper()} com erro" if c["erros_secoes"] else ""]
        self.log(f"[{visto:%H:%M:%S}] {self.nome} · TSE {of['ht'] or '--:--:--'}: {pst:.2f}% totalizadas · "
                 f"{100 * recebidas / max(total, 1):.2f}% com boletim recebido · {len(novas):,} seções novas · "
                 f"{c['baixados']} municípios · {len(ufs)} UFs".replace(",", ".")
                 + "".join(f" · {a}" for a in avisos if a))

    def prever(self):
        """O forecast agora (painel.Previsor), ou None. Na primeira vez, monta o prior (alguns segundos)."""
        if self.previsor is None and not self.sem_previsor:
            try:
                self.previsor = P.Previsor.carregar(AV, H.agregadas(), log=self.log)
            except Exception as e:  # sem o forecast, a coleta segue
                self.log(f"   forecast indisponível: {e!r}")
            if self.previsor is None:
                self.sem_previsor = True
            else:
                self.previsor.historico = list(self.previsoes)
        if self.previsor is None:
            self.chegadas = []
            return None
        self.previsor.chegou(self.chegadas)
        self.chegadas = []
        br = max(self.br.values(), key=lambda l: l["h"]) if self.br else None
        try:
            return self.previsor.prever(self.mun, self.leituras_uf, br)
        except Exception as e:  # o forecast não pode derrubar a coleta
            self.log(f"   forecast não saiu: {e!r}")
            return None

    def painel(self):
        """O dados.json (painel.dados): a apuração com as leituras oficiais, o forecast e o histórico dele."""
        previsao = self.prever()
        historico = self.previsor.historico if self.previsor else self.previsoes
        return P.dados(self.nome, self.job, self.erro, AV, list(self.br.values()), self.leituras_uf, previsao, historico)

    def enviar(self, final=False):
        if self.c is not None:
            try:
                (self.raiz / "dados.json").write_text(json.dumps(self.painel(), ensure_ascii=False,
                                                                 separators=(",", ":")), "utf-8")
                mapa = self.previsor.mapa() if self.previsor else None
                if mapa:
                    (self.raiz / "mapa.json").write_text(json.dumps(mapa, ensure_ascii=False, separators=(",", ":")),
                                                         "utf-8")
            except Exception as e:  # o painel não pode derrubar a coleta
                self.log(f"   dados.json não saiu: {e!r}")
        self.grav.fechar()
        if self.usar_git:
            quando = "fim do job" if final else f"{dt.datetime.now():%H:%M}"
            enviar(self.raiz, self.ramo, f"Coletor {self.nome}: {len(self.br)} leituras do país, "
                                         f"{len(self.vistas)} seções ({quando}, job {self.job})", self.log)

    def _job(self, **mais):
        info = {"coletor": self.nome, "job": self.job, "eleicao": AV.eleicao, "pleito": AV.pleito,
                "fase_s": COLETORES.index(self.nome) * DEFASAGEM, "prazo": iso(self.prazo), "ensaio": self.ensaio,
                "runner": os.environ.get("RUNNER_NAME", ""), **mais}
        (self.grav.pasta / "job.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")

    def rodar(self):
        """Lê o TSE até o prazo do job ou o fim da apuração. Devolve 0, ou 2 se o TSE recusou este runner (o job
        seguinte vem em outro)."""
        self.retomar()
        inicio = dt.datetime.now()
        self.prazo = prazo(self.nome, inicio, self.epoca, self.periodo, self.fim, self.antecedencia)
        if self.acabou(inicio):
            self.log("A coleta já acabou: nada a fazer neste job.")
            return 0
        self.grav = Gravador(self.raiz / self.job)
        self._job(inicio=iso(inicio))
        self.log(f"Coletor {self.nome} (eleição {AV.eleicao}, {AV.turno}º turno {AV.ano}): lê o TSE no segundo "
                 f"{COLETORES.index(self.nome) * DEFASAGEM} de cada minuto até {self.prazo:%d/%m %H:%M}.")
        ultimo_envio, bloqueios, codigo = time.monotonic(), 0, 0
        while True:
            t = proxima_leitura(dt.datetime.now(), self.nome)
            if t >= self.prazo or self.acabou(t):
                break
            time.sleep(max(0.0, (t - dt.datetime.now()).total_seconds()))
            self.rodadas += 1
            try:
                self.rodada()
                self.erro, bloqueios = None, 0
            except Exception as e:  # rede fora, TSE fora do ar etc.: tenta de novo na próxima rodada
                self.falhas += 1
                self.erro = str(e) or e.__class__.__name__
                bloqueios = bloqueios + 1 if isinstance(e, urllib.error.HTTPError) and e.code == 403 else 0
                self.log(f"[{dt.datetime.now():%H:%M:%S}] {self.nome} · sem dados novos do TSE: {self.erro}")
                self.grav.json("rodadas", {"h": iso(t), "ok": False, "erro": self.erro})
                if bloqueios >= BLOQUEIO:
                    self.log(f"O TSE recusou {BLOQUEIO} rodadas seguidas (403): este job sai e o próximo vem em outro "
                             "runner, com outro IP.")
                    codigo = 2
                    break
            if time.monotonic() - ultimo_envio >= ENVIO:
                self.enviar()
                ultimo_envio = time.monotonic()
        fim = dt.datetime.now()
        self._job(inicio=iso(inicio), fim=iso(fim), rodadas=self.rodadas, falhas=self.falhas, codigo=codigo,
                  acabou=self.acabou(fim))
        self.enviar(final=True)
        self.log(f"Fim do job: {self.rodadas} rodadas ({self.falhas} sem dados), {len(self.br)} leituras do país, "
                 f"{len(self.vistas):,} seções gravadas no ramo.".replace(",", "."))
        return codigo


# ---- Linha de comando --------------------------------------------------------------------------------------------

def imprimir_plano(ensaio=False, juntar=False):
    """uv run eleicoes coletar --plano: o plano da rodada em linhas chave=valor (as saídas do job no GitHub Actions)."""
    juntado = (AV.bruto / "coleta.json").exists()
    p = plano(dt.datetime.now(), ensaio=ensaio, juntado=juntado, juntar=juntar)
    saidas = {**p, "epoca": iso(p["epoca"]), "fim": iso(p["fim"]), "ensaio": "true" if ensaio else "false",
              "turno": os.environ.get("ELEICOES_TURNO_AO_VIVO", ""), "prefixo": "ensaio" if ensaio else "ao-vivo"}
    for k, v in saidas.items():
        print(f"{k}={v}")
    print(f"Plano: {p['acao']}" + (f", depois de esperar {p['espera'] // 60} min" if p["espera"] else ""),
          file=sys.stderr)


def main(coletor, pasta, ramo, job, epoca=None, periodo=None, fim=None, ensaio=False, usar_git=True):
    p = plano(dt.datetime.now(), ensaio=ensaio)
    epoca = dt.datetime.fromisoformat(epoca) if epoca else p["epoca"]
    fim = dt.datetime.fromisoformat(fim) if fim else p["fim"]
    c = Coletor(coletor, pasta, ramo or "", job or f"local-{coletor}", epoca, periodo or p["periodo"], fim,
                ensaio=ensaio, usar_git=usar_git and bool(ramo))
    return c.rodar()
