"""Relógio das pesquisas: os tiques de cada rodada, a passagem de vez e o que cada rodada dispara."""
import datetime as dt
import json
import subprocess

from eleicoes import relogio as R

FIM = dt.datetime(2026, 10, 25, 17, 0)
ENSAIO = {k: R.ENSAIO[k] for k in ("passo", "deslocamento", "duracao")}


def h(dia, hora, minuto=0, segundo=0):
    return dt.datetime(2026, 10, dia, hora, minuto, segundo)


def _corrente(inicio, fim, passagem=dt.timedelta(seconds=50), **ritmo):
    """Os tiques de uma corrente inteira e quantas rodadas ela teve. Cada rodada começa `passagem` depois do último
    tique da anterior (o tempo de o GitHub pôr a seguinte para rodar e de ela instalar o ambiente)."""
    agora, todos, n = inicio, [], 0
    while True:
        p = R.plano(agora, fim, **ritmo)
        n += 1
        todos += p["tiques"]
        if not p["seguinte"]:
            return todos, n
        agora = p["tiques"][-1] + passagem


def test_tiques_aos_17_minutos_e_so_depois_do_inicio():
    assert R.tiques(h(14, 14, 16, 30), h(14, 16, 17)) == [h(14, 14, 17), h(14, 15, 17), h(14, 16, 17)]
    # começando num tique, o próximo é o da hora seguinte: aquele já foi da rodada anterior
    assert R.tiques(h(14, 14, 17), h(14, 15, 30)) == [h(14, 15, 17)]
    assert R.tiques(h(14, 23, 50), h(15, 0, 20)) == [h(15, 0, 17)]  # virando o dia


def test_rodada_acaba_no_ultimo_tique_que_cabe_em_5h40():
    p = R.plano(h(14, 9, 0), FIM)
    assert p["tiques"] == [h(14, hora, 17) for hora in range(9, 15)] and p["seguinte"]
    # a última rodada não deixa sucessora; no fim (ou depois), nada
    assert R.plano(h(25, 12, 0), FIM) == {"tiques": [h(25, hora, 17) for hora in range(12, 17)], "seguinte": False}
    assert R.plano(FIM, FIM) == {"tiques": [], "seguinte": False}


def test_corrente_dispara_toda_hora_ate_a_apuracao_sem_buraco_nem_repeticao():
    todos, n = _corrente(h(14, 15, 2), FIM)
    assert todos[0] == h(14, 15, 17) and todos[-1] == h(25, 16, 17)
    assert all(b - a == dt.timedelta(hours=1) for a, b in zip(todos, todos[1:]))
    assert n == 53  # a primeira rodada pega 6 tiques; as outras, que começam logo depois de um tique, 5


def test_ensaio_sao_tres_rodadas_curtas_em_12_minutos():
    inicio = h(14, 15, 0, 20)
    todos, n = _corrente(inicio, inicio + R.ENSAIO["total"], **ENSAIO)
    assert n == 3 and todos == [h(14, 15, m) for m in range(1, 13)]


def test_corrente_que_cria_rodadas_demais_esta_em_loop():
    agora = h(14, 15, 0)
    assert not R.em_loop([agora - dt.timedelta(hours=5), agora - dt.timedelta(seconds=40)], agora, R.LIMITE[False])
    uma_a_cada_5_min = [agora - dt.timedelta(minutes=m) for m in range(0, 60, 5)]
    assert R.em_loop(uma_a_cada_5_min, agora, R.LIMITE[False])


# ---- A rodada inteira, com um GitHub e um relógio de mentira ------------------------------------------------------

class Relogio:
    def __init__(self, t):
        self.t = t

    def agora(self):
        return self.t

    def dormir(self, segundos):
        self.t += dt.timedelta(seconds=segundos)


class GitHub:
    """Registra os disparos e as issues e responde a lista de rodadas do relogio.yml, como o `gh`."""

    def __init__(self, relogio, falham=()):
        self.relogio, self.falham = relogio, set(falham)
        self.rodadas, self.disparos, self.issues = [], [], []

    def rodada(self, status, nome=R.NOMES[False], criada=None):
        criada = (criada or self.relogio.t).astimezone(dt.timezone.utc)  # o GitHub responde em UTC
        self.rodadas.append({"databaseId": len(self.rodadas) + 1, "status": status, "displayTitle": nome,
                             "createdAt": criada.strftime("%Y-%m-%dT%H:%M:%SZ")})

    def __call__(self, *args):
        ok = lambda saida="": subprocess.CompletedProcess(args, 0, saida, "")  # noqa: E731
        if args[:2] == ("workflow", "run"):
            if args[2] in self.falham:
                return subprocess.CompletedProcess(args, 1, "", "HTTP 502")
            campos = dict(x.split("=", 1) for x in args[6::2])
            self.disparos.append((args[2], campos))
            if args[2] == "relogio.yml":
                self.rodada("pending", R.NOMES[campos.get("ensaio") == "true"])
            return ok()
        if args[:2] == ("run", "list"):
            return ok(json.dumps(self.rodadas))
        if args[:2] == ("issue", "list"):
            return ok(json.dumps([{"number": i + 1, "title": t} for i, (t, _) in enumerate(self.issues)]))
        if args[:2] == ("issue", "create"):
            self.issues.append((args[3], [args[5]]))
            return ok()
        if args[:2] == ("issue", "comment"):
            self.issues[int(args[2]) - 1][1].append(args[4])
            return ok()
        raise AssertionError(args)


def _rodar(relogio, gh, **kw):
    return R.rodar(log=lambda *_: None, agora=relogio.agora, dormir=relogio.dormir, gh=gh, **kw)


def test_rodada_ligada_a_mao_dispara_o_site_ao_comecar_e_a_cada_tique():
    r = Relogio(h(25, 12, 30))
    gh = GitHub(r)
    assert _rodar(r, gh) == 0
    # ao começar e às 13h17, 14h17, 15h17 e 16h17; é a última rodada (a apuração começa às 17h): sem seguinte
    assert gh.disparos == [("site.yml", {"relogio": "true"})] * 5
    assert r.t == h(25, 16, 17)


def test_ligada_a_mao_perto_de_um_tique_nao_dispara_duas_vezes():
    r = Relogio(h(25, 14, 12))
    gh = GitHub(r)
    _rodar(r, gh)
    assert len(gh.disparos) == 3  # 14h17, 15h17 e 16h17


def test_rodada_da_corrente_deixa_a_seguinte_na_fila_uma_vez_so():
    r = Relogio(h(14, 15, 0, 40))
    gh = GitHub(r)
    gh.rodada("in_progress")  # a anterior, que o GitHub ainda mostra em curso por um instante: não é a seguinte
    assert _rodar(r, gh, fim="2026-10-25T17:00:00") == 0
    assert [d for d in gh.disparos if d[0] == "relogio.yml"] == [("relogio.yml", {"fim": "2026-10-25T17:00:00"})]
    # sem disparo ao começar (a anterior acabou de disparar), e um a cada tique: 15h17 a 20h17
    assert len([d for d in gh.disparos if d[0] == "site.yml"]) == 6


def test_nao_dispara_outra_seguinte_se_ja_ha_uma_na_fila():
    r = Relogio(h(14, 15, 0, 40))
    gh = GitHub(r)
    gh.rodada("pending")
    gh.rodada("pending", R.NOMES[True])  # a de um ensaio não conta
    _rodar(r, gh, fim="2026-10-25T17:00:00")
    assert not [d for d in gh.disparos if d[0] == "relogio.yml"]


def test_disparo_que_falha_vira_uma_issue_so_e_a_rodada_termina_com_erro():
    r = Relogio(h(25, 14, 30))
    gh = GitHub(r, falham={"site.yml"})
    assert _rodar(r, gh) == 1
    ((titulo, corpos),) = gh.issues
    assert titulo == R.TITULO and len(corpos) == 3  # ao começar, 15h17 e 16h17: a issue e dois comentários


def test_ensaio_dispara_o_site_uma_vez_e_passa_a_vez_com_o_mesmo_fim():
    r = Relogio(h(14, 15, 0, 20))
    gh = GitHub(r)
    assert _rodar(r, gh, ensaio=True) == 0
    assert gh.disparos == [("relogio.yml", {"fim": "2026-10-14T15:12:20", "ensaio": "true"}),
                           ("site.yml", {"relogio": "true"})]


def test_corrente_em_loop_para_e_avisa():
    r = Relogio(h(14, 15, 0))
    gh = GitHub(r)
    for i in range(10):
        gh.rodada("completed", criada=h(14, 14, 55) - dt.timedelta(minutes=5 * i))
    assert _rodar(r, gh, fim="2026-10-25T17:00:00") == 1
    assert not gh.disparos and len(gh.issues) == 1


def test_depois_do_fim_a_rodada_nao_faz_nada():
    r = Relogio(h(25, 17, 5))
    gh = GitHub(r)
    assert _rodar(r, gh, fim="2026-10-25T17:00:00") == 0 and not gh.disparos
