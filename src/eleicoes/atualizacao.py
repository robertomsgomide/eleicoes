"""Atualização automática das pesquisas e da projeção do 2º turno: `uv run eleicoes atualizar`.

Cada rodada:
1. pergunta à Wikipedia qual é a revisão atual da página de pesquisas do ano (uma consulta leve);
2. se ela mudou, baixa a revisão, atualiza o registro de pesquisas do TSE e lê as pesquisas, ainda sem gravar nada;
3. compara com as pesquisas guardadas. A Wikipedia é editada por qualquer pessoa: pesquisas guardadas sumindo ou
   mudando de número, e pesquisas novas impossíveis ou longe demais da projeção, podem ser vandalismo ou uma tabela
   lida errado. Nesses casos a revisão é recusada e o site fica como estava; `--forcar` publica mesmo assim,
   depois de alguém conferir a página;
4. com pesquisas novas, guarda a revisão e refaz as pesquisas e a projeção do site. Sem nada novo, só anota a
   consulta: a projeção passa a valer "com o que se sabia" até hoje (o site muda uma vez por dia).

Quem roda o comando a cada hora, até o início da apuração do 2º turno, é o GitHub Actions
(.github/workflows/site.yml), que depois faz o commit dos dados refeitos e publica o site; uma revisão recusada
faz a rodada falhar, e o GitHub avisa por e-mail. Sem a revisão guardada (um computador novo, ou a nuvem sem o
estado da rodada anterior), o comando refaz a que está no site antes de conferir. `uv run eleicoes agendar` faz o
mesmo pelo Agendador de Tarefas do Windows, com avisos do Windows. Cada rodada fica registrada em dados/atualizar.log.
"""
import base64
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import traceback

from eleicoes import config
from eleicoes.analises import pesquisas as analise
from eleicoes.analises import resultados, site
from eleicoes.coleta import tse, wikipedia
from eleicoes.modelos import projecao
from eleicoes.tratamento import conexao
from eleicoes.tratamento import pesquisas as tratamento

LOG = config.DADOS / "atualizar.log"
ESTADO = config.CACHE / "atualizar.json"  # a última revisão conferida e a última recusada, com os motivos
TAREFA = "eleicoes-atualizar"             # nome da tarefa no Agendador de Tarefas do Windows
# Quem assina os avisos do Windows: o Windows PowerShell, registrado em todo Windows
APP_DOS_AVISOS = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

# O que a conferência aceita sem alguém olhar a página
SUMIDAS = 2       # pesquisas guardadas que podem sumir de uma vez (data ou nome corrigido, duplicata removida)
ALTERADAS = 2     # pesquisas guardadas que podem ter os números corrigidos de uma vez
MUDANCA = 3.0     # p.p.: correção maior que isso num número já publicado é suspeita
DISTANCIA = 8.0   # p.p.: pesquisa nova de 2º turno, feita depois do 1º, mais longe que isso da projeção é suspeita
NUMEROS = ("petismo", "bolsonarismo", "petismo_validos", "bolsonarismo_validos")
LISTAR = 10       # pesquisas listadas no registro da rodada, por tipo de mudança


def ano_atual():
    """A eleição acompanhada: a mais recente de config/eleicoes.toml."""
    return max(config.anos())


# ---- Comparação de duas leituras da página ------------------------------------------------

def _num(v):
    return f"{v:.1f}".replace(".", ",")


def _pct(v):
    return _num(v) + "%"


def descrever(p, nomes):
    """Uma pesquisa em uma linha: "Quaest, campo de 10/10 a 12/10 (2º turno): Lula 49,1% × ... dos válidos"."""
    campo = f"de {p['inicio']:%d/%m} a {p['fim']:%d/%m}" if p["inicio"] != p["fim"] else f"em {p['fim']:%d/%m}"
    return (f"{p['instituto']}, campo {campo} ({p['turno']}º turno): {nomes['petismo']} {_pct(p['petismo_validos'])} × "
            f"{nomes['bolsonarismo']} {_pct(p['bolsonarismo_validos'])} dos válidos")


def _chave(p):
    return p["turno"], p["instituto"], p["inicio"], p["fim"]


def _ordem(k):
    return k[0], k[3], k[1], k[2]  # turno, fim do campo, instituto


def comparar(antigas, novas):
    """O que mudou de uma leitura da página para outra: pesquisas novas, sumidas, alteradas ([(antiga, nova, maior
    mudança nos números, em p.p.)]) e ligadas a outro registro do TSE."""
    a, n = {_chave(p): p for p in antigas}, {_chave(p): p for p in novas}
    alteradas, religadas = [], []
    for k in sorted(a.keys() & n.keys(), key=_ordem):
        d = max(abs(n[k][c] - a[k][c]) for c in NUMEROS)
        if d > 0.001 or n[k]["amostra"] != a[k]["amostra"]:
            alteradas.append((a[k], n[k], round(d, 2)))
        elif n[k]["registro"] != a[k]["registro"]:
            religadas.append(n[k])
    return {"novas": [n[k] for k in sorted(n.keys() - a.keys(), key=_ordem)],
            "sumidas": [a[k] for k in sorted(a.keys() - n.keys(), key=_ordem)],
            "alteradas": alteradas, "religadas": religadas}


def problemas(m, ano, referencia=None, hoje=None):
    """O que impede publicar sem alguém conferir a página; lista vazia se pode publicar. `referencia`: % do petismo
    na projeção publicada, com que se comparam as pesquisas novas de 2º turno feitas depois do 1º turno."""
    hoje, nomes, out = hoje or dt.date.today(), config.nomes(ano), []
    if len(m["sumidas"]) > SUMIDAS:
        out.append(f"{len(m['sumidas'])} pesquisas já publicadas sumiram da página")
    if len(m["alteradas"]) > ALTERADAS:
        out.append(f"{len(m['alteradas'])} pesquisas já publicadas mudaram de uma vez")
    out += [f"{descrever(antiga, nomes)}: um número mudou {_num(d)} pontos" for antiga, _, d in m["alteradas"] if d > MUDANCA]
    depois = analise.depois_do_primeiro_turno(m["novas"], ano)
    for p in m["novas"]:
        if not (0 < p["petismo"] <= 100 and 0 < p["bolsonarismo"] <= 100 and p["petismo"] + p["bolsonarismo"] <= 100.5):
            out.append(f"{descrever(p, nomes)}: percentuais impossíveis ({p['petismo']:g} e {p['bolsonarismo']:g})")
        elif not p["inicio"] <= p["fim"] <= hoje or (p["fim"] - p["inicio"]).days > 31:
            out.append(f"{descrever(p, nomes)}: datas de campo impossíveis")
        elif p in depois and referencia is not None and abs(p["petismo_validos"] - referencia) > DISTANCIA:
            out.append(f"{descrever(p, nomes)}: longe demais da projeção publicada ({nomes['petismo']} {_pct(referencia)})")
    return out


# ---- Registro da rodada e avisos -----------------------------------------------------------

def _log(texto=""):
    """No terminal, se houver (a tarefa agendada roda sem), e em dados/atualizar.log, com data e hora."""
    print(texto)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    agora = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.writelines(f"{agora}  {linha}\n" for linha in (str(texto).splitlines() or [""]))


def _powershell(script, env=None):
    """Roda um script no Windows PowerShell, sem abrir janela; o script vai codificado, sem problemas de aspas."""
    script = "try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}\n" + script
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                           base64.b64encode(script.encode("utf-16-le")).decode()],
                          capture_output=True, encoding="utf-8", errors="replace", timeout=120, env=env,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def avisar(titulo, texto):
    """Aviso do Windows (canto da tela e central de notificações), para quem não está olhando o terminal."""
    if sys.platform != "win32":
        return
    script = """
$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime]
$titulo = [Security.SecurityElement]::Escape($env:AVISO_TITULO)
$texto = [Security.SecurityElement]::Escape($env:AVISO_TEXTO)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$titulo</text><text>$texto</text></binding></visual></toast>")
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:AVISO_APP).Show(
    [Windows.UI.Notifications.ToastNotification]::new($xml))
"""
    try:
        r = _powershell(script, env={**os.environ, "AVISO_TITULO": titulo, "AVISO_TEXTO": texto, "AVISO_APP": APP_DOS_AVISOS})
        if r.returncode:
            _log(f"   (o aviso do Windows não saiu: {r.stderr.strip()[-300:]})")
    except (OSError, subprocess.SubprocessError) as e:
        _log(f"   (o aviso do Windows não saiu: {e})")


# ---- A rodada ---------------------------------------------------------------------------------

def _estado():
    try:
        return json.loads(ESTADO.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_estado(**mudancas):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps({**_estado(), **mudancas}, ensure_ascii=False, indent=1), "utf-8")


def _publicado(nome):
    arq = site.SAIDA / nome
    return json.loads(arq.read_text("utf-8")) if arq.exists() else {}


def _projecao_publicada(ano):
    """O último dia da projeção que está no site ({"data", "petismo", ...}), ou None."""
    return ((_publicado("projecao.json").get("anos") or {}).get(str(ano)) or {}).get("atual")


def _revisao_publicada(ano):
    """A revisão da Wikipedia de onde vêm as pesquisas que estão no site, ou None."""
    return ((_publicado(f"pesquisas_{ano}.json").get("fonte") or {}).get("wikipedia") or {}).get("revid")


def _registro_do_tse(ano):
    """Atualiza o registro de pesquisas do TSE (só baixa de novo se o arquivo mudou); se falhar, segue o anterior."""
    arq = tse.pasta("pesquisas", ano) / f"pesquisa_eleitoral_{ano}.zip"
    arq.with_name(arq.name + ".parte").unlink(missing_ok=True)  # resto de um download interrompido de outra versão
    try:
        tse.pesquisas(ano, log=_log)
    except OSError as e:
        _log(f"   registro de pesquisas do TSE não atualizou ({e}); segue o anterior")


def _conferir(ano, revid, forcar, aviso):
    """Lê a revisão nova e, se a conferência deixar, guarda. Devolve (recusada?, pesquisas novas publicadas)."""
    html, meta = wikipedia.buscar(ano, revid)
    _registro_do_tse(ano)
    m = comparar(analise.carregar(ano), tratamento.montar(ano, html)[1])
    if not any(m.values()):
        _log("   Nenhuma pesquisa mudou: o site fica como está.")
        _guardar_estado(conferida=revid, recusada=None, motivos=[])
        return False, []
    nomes = config.nomes(ano)
    linhas = {"nova": [descrever(p, nomes) for p in m["novas"]],
              "sumiu": [descrever(p, nomes) for p in m["sumidas"]],
              "alterada": [f"{descrever(a, nomes)} → agora {_pct(n['petismo_validos'])} × {_pct(n['bolsonarismo_validos'])}, "
                           f"amostra {n['amostra']}" for a, n, _ in m["alteradas"]],
              "ligada a outro registro do TSE": [descrever(p, nomes) for p in m["religadas"]]}
    for rotulo, itens in linhas.items():
        for x in itens[:LISTAR]:
            _log(f"   {rotulo}: {x}")
        if len(itens) > LISTAR:
            _log(f"   ... e mais {len(itens) - LISTAR} ({rotulo})")
    motivos = problemas(m, ano, (_projecao_publicada(ano) or {}).get("petismo"))
    if motivos and not forcar:
        _log("Revisão recusada: o site continua como estava. Confira a página e, se ela estiver certa, rode  "
             "uv run eleicoes atualizar --forcar")
        for x in motivos:
            _log(f"   - {x}")
        _guardar_estado(recusada=revid, motivos=motivos)
        mais = f" (e mais {len(motivos) - 1})" if len(motivos) > 1 else ""
        aviso("Pesquisas: revisão da Wikipedia recusada", f"{motivos[0]}{mais}. O site ficou como estava.")
        return True, []
    if motivos:
        _log("Publicada mesmo assim (--forcar), apesar de: " + "; ".join(motivos))
    wikipedia.guardar(ano, html, meta, log=_log)
    tratamento.processar(ano, log=_log)
    tratamento.relatorio(config.anos())
    _guardar_estado(conferida=revid, recusada=None, motivos=[])
    return False, m["novas"]


def _publicar(ano):
    """Refaz as pesquisas e a projeção do site quando estão atrás do que está guardado. Devolve a projeção refeita."""
    if _revisao_publicada(ano) != wikipedia.revisao(ano)["revid"]:
        site.escrever(f"pesquisas_{ano}.json", analise.gerar(ano, resultados.gerar(conexao())), _log)
    elif (_projecao_publicada(ano) or {}).get("data") == projecao.ultimo_dia(ano).isoformat():
        return None
    p = projecao.gravar()["anos"].get(str(ano))
    if p:
        _log(f"   projecao.json: com o que se sabia em {dt.date.fromisoformat(p['atual']['data']):%d/%m}, "
             f"{projecao.resumo(p)}")
    return p


def _refazer_publicada(ano):
    """Guarda e processa a revisão que está no site, quando ela não está aqui: um computador novo, ou a nuvem sem o
    estado da rodada anterior. Devolve os metadados dela, ou None se o site também não tem pesquisas do ano."""
    if (publicada := _revisao_publicada(ano)) is None:
        return None
    _log(f"Sem a revisão guardada aqui: refazendo a que está no site ({publicada}).")
    wikipedia.guardar(ano, *wikipedia.buscar(ano, publicada), log=_log)
    _registro_do_tse(ano)
    tratamento.processar(ano, log=_log)
    return wikipedia.revisao(ano)


def _atualizar(ano, forcar, aviso):
    if dt.datetime.now() >= config.inicio_divulgacao(ano, 2):
        _log(f"A apuração do 2º turno de {ano} já começou: não há mais pesquisas a conferir.")
        return 0
    guardada = wikipedia.revisao(ano)
    if guardada is None or not tratamento.saida("pesquisas", ano).exists():
        if (guardada := _refazer_publicada(ano)) is None:
            _log(f"Não há pesquisas de {ano} guardadas nem no site: rode antes  uv run eleicoes pesquisas")
            return 1
    estado, ultima = _estado(), wikipedia.ultima_revisao(ano)
    recusada, recusada_agora, novas = False, False, []
    if ultima == guardada["revid"] or (ultima == estado.get("conferida") and not forcar):
        _log(f"Wikipedia: revisão {ultima}, a mesma da última conferência: nada novo.")
    elif ultima == estado.get("recusada") and not forcar:
        # a rodada que recusou já falhou e avisou; esta só espera, sem falhar de novo (seria um e-mail a cada hora)
        _log(f"Wikipedia: revisão {ultima}, recusada antes ({'; '.join(estado.get('motivos') or [])}). O site continua "
             "como estava, à espera de uma revisão nova da página ou de  uv run eleicoes atualizar --forcar")
        recusada = True
    else:
        _log(f"Wikipedia: revisão nova {ultima} (a guardada é {guardada['revid']}).")
        recusada, novas = _conferir(ano, ultima, forcar, aviso)
        recusada_agora = recusada
    if not recusada:
        wikipedia.consultada(ano)
    p = _publicar(ano)
    if novas:
        nomes = config.nomes(ano)
        titulo = f"Pesquisa nova: {novas[0]['instituto']}" if len(novas) == 1 else f"{len(novas)} pesquisas novas"
        curtas = [f"{x['instituto']} ({x['fim']:%d/%m}): {nomes['petismo']} {_pct(x['petismo_validos'])} × "
                  f"{nomes['bolsonarismo']} {_pct(x['bolsonarismo_validos'])}" for x in novas[:2]]
        texto = "; ".join(curtas) + (f" e mais {len(novas) - 2}" if len(novas) > 2 else "")
        aviso(titulo, texto + (f". Projeção: {projecao.resumo(p)}" if p else ""))
    return 1 if recusada_agora else 0


def rodar(forcar=False, avisos=False):
    """uv run eleicoes atualizar. Devolve 0 (nada novo, o site atualizado, ou uma revisão recusada antes que continua
    a mesma) ou 1 (revisão recusada nesta rodada, ou erro)."""
    aviso = avisar if avisos else (lambda *_: None)
    try:
        return _atualizar(ano_atual(), forcar, aviso)
    except OSError as e:  # sem internet, Wikipedia ou TSE fora do ar: a próxima rodada tenta de novo
        _log(f"Sem conexão com a Wikipedia ou o TSE ({e}); tenta de novo na próxima rodada.")
        return 1
    except Exception:
        _log("Erro:\n" + traceback.format_exc())
        aviso("Atualização das pesquisas falhou", f"O site ficou como estava. Detalhes em dados/{LOG.name}.")
        return 1


# ---- Tarefa agendada do Windows ----------------------------------------------------------------

def _texto_ps(s):
    """Texto entre aspas simples do PowerShell."""
    return "'" + str(s).replace("'", "''") + "'"


def script_da_tarefa(horas, fim, pythonw, raiz):
    """PowerShell que cria (ou refaz) a tarefa: `pythonw -m eleicoes atualizar --avisar` (sem janela) a cada `horas`
    horas enquanto o usuário estiver logado, também na bateria; se o computador estava desligado ou dormindo na hora,
    roda assim que puder; acaba em `fim`."""
    descricao = (f"Confere a cada {horas} horas se há pesquisa nova na Wikipedia e refaz as pesquisas e a projeção do "
                 f"site (uv run eleicoes atualizar). Acaba em {fim:%d/%m/%Y às %H:%M}. Registro em dados/atualizar.log.")
    return "\n".join([
        f"$acao = New-ScheduledTaskAction -Execute {_texto_ps(pythonw)} -Argument '-m eleicoes atualizar --avisar' "
        f"-WorkingDirectory {_texto_ps(raiz)}",
        f"$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours {horas})",
        f"$gatilho.EndBoundary = {_texto_ps(fim.isoformat())}",
        "$regras = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)",
        f"$null = Register-ScheduledTask -TaskName {_texto_ps(TAREFA)} -Description {_texto_ps(descricao)} "
        "-Action $acao -Trigger $gatilho -Settings $regras -Force",
        f"(Get-ScheduledTaskInfo -TaskName {_texto_ps(TAREFA)}).NextRunTime.ToString('dd/MM HH:mm')",
    ])


def agendar(horas=2, log=print):
    """uv run eleicoes agendar: cria (ou refaz) a tarefa agendada, que acaba no início da apuração do 2º turno."""
    if sys.platform != "win32":
        raise SystemExit("A tarefa agendada é do Windows. Em outro sistema, ponha no cron:  uv run eleicoes atualizar")
    ano = ano_atual()
    fim = config.inicio_divulgacao(ano, 2)
    if fim <= dt.datetime.now():
        raise SystemExit(f"A apuração do 2º turno de {ano} já começou: não há mais pesquisas a esperar.")
    pythonw = pathlib.Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        raise SystemExit(f"Não achei {pythonw}: rode pelo uv (uv run eleicoes agendar).")
    r = _powershell(script_da_tarefa(horas, fim, pythonw, config.RAIZ))
    if r.returncode:
        raise SystemExit(f"Não consegui criar a tarefa agendada:\n{r.stderr.strip()}")
    log(f'Tarefa "{TAREFA}" no Agendador de Tarefas do Windows: `atualizar` a cada {horas} horas, sem janela, até '
        f"{fim:%d/%m às %H:%M}. Primeira rodada: {r.stdout.strip()}.")
    log(f"Cada rodada fica em {LOG.relative_to(config.RAIZ).as_posix()}. Para apagar a tarefa:  uv run eleicoes agendar --remover")


def remover(log=print):
    if sys.platform != "win32":
        raise SystemExit("A tarefa agendada é do Windows.")
    r = _powershell(f"Unregister-ScheduledTask -TaskName {_texto_ps(TAREFA)} -Confirm:$false")
    if r.returncode:
        raise SystemExit(f"Não consegui apagar a tarefa agendada:\n{r.stderr.strip()}")
    log(f'Tarefa "{TAREFA}" apagada.')
