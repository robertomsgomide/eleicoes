"""O relógio das pesquisas: dispara a atualização do site a cada hora, até o início da apuração do 2º turno.

`uv run eleicoes relogio`, no GitHub Actions (.github/workflows/relogio.yml). O agendamento do próprio GitHub (o cron
do `schedule`) é "melhor esforço": de 08 a 14/10/2026, o cron de hora em hora do site.yml rodou em só 18% das horas,
com 3 a 9,5 h entre uma rodada e a seguinte. Um disparo pela API (workflow_dispatch) começa na hora. Então o relógio é
uma corrente de rodadas do relogio.yml, ligada uma vez com "Run workflow":

- cada rodada fica acordada até DURACAO (um job do Actions dura no máximo 6 h) e dispara o site.yml aos MINUTO minutos
  de cada hora. Ela acaba logo depois do último tique que cabe nela, e a seguinte pega o próximo. A rodada ligada à
  mão dispara o site.yml também ao começar;
- ao começar, e de novo depois de cada tique, a rodada garante a seguinte: se não houver uma na fila, dispara o
  relogio.yml, que espera (concurrency) e assume quando esta acabar, mesmo que esta caia no meio;
- a corrente acaba no início da apuração do 2º turno, quando o `atualizar` também para;
- um disparo que falha, ou uma corrente que cria rodadas demais (um erro que derruba cada rodada logo ao começar),
  vira uma issue no repositório: nas rodadas disparadas pelo robô do GitHub, o e-mail de falha não chega a ninguém.

Ensaio (`--ensaio`): a mesma corrente por 12 min, com rodadas de até 4 min e tiques de minuto em minuto que só
registram. A primeira rodada dispara o site.yml uma vez, para conferir a permissão.
"""
import datetime as dt
import json
import os
import subprocess
import time

from eleicoes import config

MINUTO = 17                                  # o site.yml roda aos 17 min de cada hora
DURACAO = dt.timedelta(minutes=340)          # uma rodada fica acordada até 5h40 (um job do Actions dura até 6 h)
PERTO = dt.timedelta(minutes=10)             # ligada à mão a menos disso de um tique, a rodada não dispara ao começar
ENSAIO = {"passo": dt.timedelta(minutes=1), "deslocamento": dt.timedelta(0), "duracao": dt.timedelta(minutes=4),
          "total": dt.timedelta(minutes=12)}
LIMITE = {False: 8, True: 20}                # rodadas criadas na última hora acima disso: a corrente está em loop
TENTATIVAS = 5                               # de cada disparo, com espera crescente entre elas
FILA = ("queued", "pending", "waiting", "requested")  # estados de uma rodada que ainda vai começar
NOMES = {False: "Relógio das pesquisas", True: "Ensaio do relógio das pesquisas"}  # o run-name do relogio.yml
TITULO = "Relógio das pesquisas: precisa de atenção"


# ---- Quando ----------------------------------------------------------------------------------------------------

def tiques(inicio, ate, passo=dt.timedelta(hours=1), deslocamento=dt.timedelta(minutes=MINUTO)):
    """Os instantes `deslocamento` + n·`passo`, contados da meia-noite, depois de `inicio` e até `ate` (inclusive)."""
    base = inicio.replace(hour=0, minute=0, second=0, microsecond=0) + deslocamento
    t, out = base + ((inicio - base) // passo + 1) * passo, []
    while t <= ate:
        out.append(t)
        t += passo
    return out


def plano(agora, fim, duracao=DURACAO, **ritmo):
    """{"tiques", "seguinte"} da rodada que começa `agora`: os tiques até `duracao` depois (e antes de `fim`) e se a
    corrente continua depois dela, isto é, se sobra algum tique antes de `fim`."""
    limite = min(agora + duracao, fim)
    return {"tiques": [t for t in tiques(agora, limite, **ritmo) if t < fim],
            "seguinte": any(t < fim for t in tiques(limite, fim, **ritmo))}


def em_loop(criadas, agora, limite):
    """A corrente criou rodadas demais na última hora? `criadas`: quando cada rodada recente foi criada."""
    return sum(agora - c <= dt.timedelta(hours=1) for c in criadas) > limite


# ---- O GitHub --------------------------------------------------------------------------------------------------

def _gh(*args):
    """O GitHub CLI; no Actions, com o GH_TOKEN da rodada."""
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)


def _local(iso):
    """Um horário do GitHub ("2026-10-14T16:01:05Z", UTC) no fuso local e sem fuso, como dt.datetime.now()."""
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


def rodadas(nome, gh=_gh):
    """As rodadas recentes desta corrente, [{"id", "status", "criada"}], ou None se o GitHub não respondeu."""
    try:
        r = gh("run", "list", "--workflow", "relogio.yml", "--limit", "30",
               "--json", "databaseId,status,createdAt,displayTitle")
        if r.returncode:
            return None
        return [{"id": x["databaseId"], "status": x["status"], "criada": _local(x["createdAt"])}
                for x in json.loads(r.stdout) if x["displayTitle"] == nome]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None


def disparar(workflow, ref, campos, log, gh=_gh, dormir=time.sleep):
    """`gh workflow run`, com até TENTATIVAS tentativas; True se o GitHub aceitou o disparo."""
    args = ["workflow", "run", workflow, "--ref", ref, *(x for k, v in campos.items() for x in ("-f", f"{k}={v}"))]
    for i in range(TENTATIVAS):
        try:
            r = gh(*args)
            if r.returncode == 0:
                return True
            erro = (r.stderr or r.stdout or "").strip()
        except (OSError, subprocess.SubprocessError) as e:
            erro = str(e)
        log(f"   o disparo do {workflow} falhou ({erro[-200:]}); tentativa {i + 1} de {TENTATIVAS}")
        if i + 1 < TENTATIVAS:
            dormir(15 * (i + 1))
    return False


def avisar(texto, log, gh=_gh):
    """Abre a issue do relógio, ou comenta na que já está aberta, mencionando o dono do repositório."""
    e = os.environ
    rodada = (f"{e.get('GITHUB_SERVER_URL', 'https://github.com')}/{e.get('GITHUB_REPOSITORY', '')}"
              f"/actions/runs/{e.get('GITHUB_RUN_ID', '')}")
    corpo = f"@{e.get('GITHUB_REPOSITORY_OWNER', '')} {texto}\n\nRodada do relógio: {rodada}"
    try:
        r = gh("issue", "list", "--state", "open", "--limit", "100", "--json", "number,title")
        abertas = json.loads(r.stdout) if r.returncode == 0 else []
        numero = next((i["number"] for i in abertas if i["title"] == TITULO), None)
        r = (gh("issue", "comment", str(numero), "--body", corpo) if numero
             else gh("issue", "create", "--title", TITULO, "--body", corpo))
        if r.returncode:
            log(f"   (a issue não saiu: {(r.stderr or '').strip()[-200:]})")
    except (OSError, subprocess.SubprocessError, ValueError) as ex:
        log(f"   (a issue não saiu: {ex})")


# ---- A rodada --------------------------------------------------------------------------------------------------

def rodar(ensaio=False, fim=None, log=print, agora=dt.datetime.now, dormir=time.sleep, gh=_gh):
    """uv run eleicoes relogio [--ensaio] [--fim ISO]. Sem `fim`, é a rodada ligada à mão: a corrente vai até o início
    da apuração do 2º turno (no ensaio, 12 min). Devolve 0, ou 1 se algum disparo falhou ou se a corrente parou por
    criar rodadas demais (nos dois casos, com uma issue)."""
    inicio, nome, ref = agora(), NOMES[ensaio], os.environ.get("GITHUB_REF_NAME", "main")
    ritmo = {k: ENSAIO[k] for k in ("passo", "deslocamento", "duracao")} if ensaio else {}
    continuacao = bool(fim)
    if fim:
        fim = dt.datetime.fromisoformat(fim)
    else:
        fim = inicio + ENSAIO["total"] if ensaio else config.inicio_divulgacao(max(config.anos()), 2)
    if inicio >= fim:
        log(f"{nome}: a corrente acabou em {fim:%d/%m às %H:%M}; esta rodada não faz nada.")
        return 0

    recentes = rodadas(nome, gh)
    if recentes is not None and em_loop([r["criada"] for r in recentes], inicio, LIMITE[ensaio]):
        log(f"{nome}: rodadas demais criadas na última hora; a corrente para aqui.")
        avisar("a corrente do relógio criou rodadas demais na última hora e parou. Confira a aba Actions e, "
               'depois de corrigir, ligue de novo com "Run workflow".', log, gh)
        return 1

    p = plano(inicio, fim, **ritmo)
    log(f"{nome}: {len(p['tiques'])} tiques nesta rodada"
        + (f", de {p['tiques'][0]:%d/%m %H:%M} a {p['tiques'][-1]:%d/%m %H:%M}" if p["tiques"] else "")
        + (f"; a corrente segue até {fim:%d/%m às %H:%M}" if p["seguinte"] else "; é a última rodada da corrente"))
    falhas = []

    def garantir_seguinte():
        if not p["seguinte"]:
            return
        proprio = os.environ.get("GITHUB_RUN_ID")
        fila = rodadas(nome, gh)
        if fila is not None and any(r["status"] in FILA and str(r["id"]) != proprio for r in fila):
            return
        campos = {"fim": fim.isoformat(timespec="seconds"), **({"ensaio": "true"} if ensaio else {})}
        if disparar("relogio.yml", ref, campos, log, gh, dormir):
            log("   a rodada seguinte do relógio está na fila")
        else:
            falhas.append("seguinte")
            avisar("não consegui disparar a rodada seguinte do relógio. Se esta rodada acabar sem que outra tenha "
                   'entrado na fila, a corrente para: ligue de novo com "Run workflow".', log, gh)

    def site(quando):
        if disparar("site.yml", ref, {"relogio": "true"}, log, gh, dormir):
            log(f"   {quando:%d/%m %H:%M}: site.yml disparado")
        else:
            falhas.append("site")
            avisar(f"não consegui disparar a atualização das pesquisas (site.yml) de {quando:%d/%m às %H:%M}. O "
                   "relógio tenta de novo no próximo tique.", log, gh)

    garantir_seguinte()
    if not continuacao and (ensaio or not p["tiques"] or p["tiques"][0] - inicio > PERTO):
        site(inicio)
    for t in p["tiques"]:
        dormir(max(0.0, (t - agora()).total_seconds()))
        if ensaio:
            log(f"   {t:%H:%M}: tique (no ensaio, o site.yml não é disparado)")
        else:
            site(t)
        garantir_seguinte()
    log(f"{nome}: rodada encerrada" + ("; a seguinte assume." if p["seguinte"] else "; a corrente acabou."))
    return 1 if falhas else 0
