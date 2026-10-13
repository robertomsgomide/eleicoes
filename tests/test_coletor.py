"""Testes da coleta na nuvem sem rede: o calendário dos três coletores, o que cada rodada grava (com um TSE falso),
o envio pelo git e a junção das gravações."""
import copy
import dataclasses
import datetime as dt
import gzip
import json
import shutil
import subprocess
import urllib.error

import pytest

from eleicoes import config
from eleicoes.analises import noite
from eleicoes.ao_vivo import coletor as C
from eleicoes.ao_vivo import historico as H
from eleicoes.ao_vivo import juntar as J

DIA = dt.datetime(2026, 10, 25)


def h(hora, minuto, segundo=0, dia=DIA):
    return dia.replace(hour=hora, minute=minuto, second=segundo)


# ---- Calendário ---------------------------------------------------------------------------------------------------

def test_leituras_defasadas_de_20_s():
    t = h(17, 0, 5)
    assert [C.proxima_leitura(t, c) for c in "abc"] == [h(17, 1), h(17, 0, 20), h(17, 0, 40)]
    assert C.proxima_leitura(h(17, 0, 20), "b") == h(17, 1, 20)  # nunca o próprio instante: o seguinte


def test_trocas_de_job_defasadas_e_cada_job_dentro_de_6_h():
    trocas = {}
    for c in "abc":
        t, jobs = C.LIBERAR, 0
        while t < C.FIM_MAXIMO:
            fim = C.prazo(c, t, C.EPOCA, C.PERIODO, C.FIM_MAXIMO)
            assert dt.timedelta(minutes=5) <= fim - t <= dt.timedelta(hours=5, minutes=50) or fim == C.FIM_MAXIMO
            trocas.setdefault(c, []).append(fim)
            t, jobs = fim + dt.timedelta(minutes=2), jobs + 1  # o job seguinte começa uns 2 min depois
        assert jobs <= 5, c  # o apuracao.yml tem 5 jobs por coletor
    assert trocas["a"][0] == C.EPOCA == h(16, 20)
    meio = [t for c in "abc" for t in trocas[c] if t < C.FIM_MAXIMO]
    # nunca dois coletores trocando de job perto um do outro: os outros dois seguem lendo
    assert min(abs(x - y) for i, x in enumerate(meio) for y in meio[i + 1:]) >= dt.timedelta(minutes=100)
    assert not any(h(16, 50) <= t <= h(18, 0) for t in meio)  # nem perto das 17h


def test_plano_da_rodada():
    assert C.plano(C.LIBERAR - dt.timedelta(hours=8))["acao"] == "esperar"
    p = C.plano(C.LIBERAR - dt.timedelta(hours=2))
    assert (p["acao"], p["espera"]) == ("coletar", 7200)
    assert C.plano(C.LIBERAR + dt.timedelta(hours=3))["espera"] == 0
    assert C.plano(C.FIM_MAXIMO)["acao"] == "juntar"
    assert C.plano(C.LIBERAR, juntado=True)["acao"] == "nada"
    assert C.plano(C.LIBERAR, juntar=True)["acao"] == "juntar"
    e = C.plano(h(9, 0) - dt.timedelta(days=12), ensaio=True)
    assert (e["acao"], e["espera"], e["fim"] - e["epoca"]) == ("coletar", 0, dt.timedelta(minutes=30))


def test_coleta_acaba_1_h_depois_de_o_tse_fechar_a_totalizacao():
    leituras = [{"h": "2026-10-25T20:00:00", "pst": 99.9}, {"h": "2026-10-25T23:10:00", "pst": 100.0}]
    assert C.fim_da_apuracao(leituras) == h(23, 10)
    assert not C.acabou(leituras, h(0, 9, dia=DIA + dt.timedelta(days=1)))
    assert C.acabou(leituras, h(0, 11, dia=DIA + dt.timedelta(days=1)))
    assert not C.acabou(leituras[:1], h(5, 59, dia=DIA + dt.timedelta(days=1)))
    assert C.acabou(leituras[:1], C.FIM_MAXIMO)


# ---- Um TSE falso ------------------------------------------------------------------------------------------------

def resultado(abr, hora, st, ts, lula, flavio, pst=None):
    vv = lula + flavio
    pst = 100 * st / ts if pst is None else pst
    return {"cdabr": abr, "dt": "25/10/2026" if hora else "", "ht": hora, "dv": "s", "tf": "n", "and": "p",
            "s": {"st": str(st), "ts": str(ts), "pstn": f"{pst:.3f}".replace(".", ",")},
            "e": {"c": str(vv + 10), "a": "5"}, "v": {"tv": str(vv + 10), "vv": str(vv), "vb": "4", "tvn": "6"},
            "carg": [{"cand": [{"n": "13", "nmu": "LULA", "vap": str(lula)},
                               {"n": "22", "nmu": "FLAVIO BOLSONARO", "vap": str(flavio)}]}]}


def config_secoes(uf, secoes):
    """-cs.json com as seções {(municipio, zona, secao): "dd/mm/aaaa hh:mm:ss" ou None (ainda não recebida)}."""
    mus = {}
    for (mu, zona, ns), quando in secoes.items():
        s = {"ns": ns, **(dict(zip(("da", "ha"), quando.split())) if quando else {})}
        mus.setdefault(mu, {}).setdefault(zona, []).append(s)
    return {"abr": [{"cd": uf, "mu": [{"cd": mu, "zon": [{"cd": z, "sec": ss} for z, ss in zonas.items()]}
                                      for mu, zonas in mus.items()]}]}


class TSEFalso:
    """Serve arquivos por URL como o TSE: etag, 304 quando não mudou, 403 quando não existe."""

    def __init__(self):
        self.arquivos = {}

    def publicar(self, url, doc):
        self.arquivos[url] = (f'"{len(self.arquivos)}-{hash(json.dumps(doc, sort_keys=True))}"', copy.deepcopy(doc))

    def baixar(self, url, etag=None, tentativas=4):
        if url not in self.arquivos:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        e, doc = self.arquivos[url]
        return (None, etag) if etag == e else (copy.deepcopy(doc), e)


@pytest.fixture
def tse(monkeypatch, tmp_path):
    falso = TSEFalso()
    monkeypatch.setattr(H, "baixar", falso.baixar)
    for nome, vazio in (("_cs", {}), ("_chegadas", {}), ("_lido", {}), ("_mun", None), ("_erro_cs", {}),
                        ("_municipios", None), ("_erro_municipios", 0.0)):
        monkeypatch.setattr(H, nome, vazio)
    monkeypatch.setattr(H, "CACHE", tmp_path / "cache")
    # a divulgação já começou: as rodadas leem os municípios
    monkeypatch.setattr(C, "AV", dataclasses.replace(C.AV, inicio=dt.datetime.now() - dt.timedelta(hours=1)))
    for uf in H.UFS:  # todas as UFs existem; só o Acre tem seções neste teste
        falso.publicar(H.url_secoes(uf), config_secoes(uf, {}))
    return falso


def coletor(raiz, nome="a", job="1.1-1"):
    c = C.Coletor(nome, raiz, "ao-vivo-" + nome, job, C.EPOCA, C.PERIODO, C.FIM_MAXIMO, usar_git=False, log=lambda *_: None)
    c.retomar()
    c.grav = C.Gravador(raiz / job)
    return c


def test_rodadas_gravam_o_primeiro_horario_de_cada_secao_e_cada_versao_nova(tse, tmp_path):
    s1, s2 = ("00001", "0001", "0001"), ("00001", "0001", "0002")
    tse.publicar(H.url_secoes("ac"), config_secoes("ac", {s1: "25/10/2026 17:01:10", s2: None}))
    tse.publicar(H.URL_BR, resultado("br", "17:02:00", 1, 2, 60, 40))
    tse.publicar(H.url_resultado("ac"), resultado("ac", "17:02:00", 1, 2, 60, 40))
    tse.publicar(H.url_resultado("ac00001"), resultado("00001", "17:02:00", 1, 2, 60, 40))
    raiz = tmp_path / "ramo-a"
    c = coletor(raiz)
    c.rodada()
    c.rodada()  # nada mudou no TSE: nada novo gravado
    # o TSE recebe a segunda seção e reescreve o horário da primeira (como faz depois da apuração)
    tse.publicar(H.url_secoes("ac"), config_secoes("ac", {s1: "25/10/2026 23:59:00", s2: "25/10/2026 17:05:00"}))
    tse.publicar(H.URL_BR, resultado("br", "17:06:00", 2, 2, 110, 90))
    tse.publicar(H.url_resultado("ac00001"), resultado("00001", "17:06:00", 2, 2, 110, 90))
    H._lido.clear()  # sem esperar os 3 min entre duas leituras do mesmo município
    c.rodada()

    secoes = list(C.registros([raiz], "secoes"))
    assert [(s[:4], s[4]) for s in secoes] == [(("ac", *s1), "25/10/2026 17:01:10"), (("ac", *s2), "25/10/2026 17:05:00")]
    pais = list(C.registros([raiz], "leituras_br"))
    assert [(l["h"], l["pst"], l["cand"]["13"]["p"]) for l in pais] == [("2026-10-25T17:02:00", 50.0, 60.0),
                                                                        ("2026-10-25T17:06:00", 100.0, 55.0)]
    assert [l["abr"] for l in C.registros([raiz], "leituras_uf")] == ["ac"]  # as outras UFs dão 403: contadas, não gravadas
    assert [(r["h"], r["st"]) for r in C.registros([raiz], "municipios")] == [("2026-10-25T17:02:00", 1),
                                                                              ("2026-10-25T17:06:00", 2)]
    rodadas = list(C.registros([raiz], "rodadas"))
    assert [r["novas"] for r in rodadas] == [1, 0, 1]
    # as UFs sem arquivo de resultado deram erro uma vez e só são lidas de novo 10 min depois
    assert len(rodadas[0]["falhas_uf"]) == len(H.UFS) - 1 and rodadas[1]["falhas_uf"] == []

    p = c.painel()["dados"]  # o mesmo formato do painel local
    assert p["recebidas"][-1] == 2 and [o["h"] for o in p["oficiais"]] == ["2026-10-25T17:02:00", "2026-10-25T17:06:00"]

    # o job seguinte retoma do ramo: não grava de novo o que este já gravou
    c.grav.fechar()
    seguinte = coletor(raiz, job="1.1-2")
    assert len(seguinte.vistas) == 2 and len(seguinte.br) == 2 and seguinte.mun[("ac", "00001")]["st"] == 2
    assert H._mun[("ac", "00001")]["st"] == 2


def test_uf_sem_arquivo_de_secoes_nao_derruba_a_rodada(tse, tmp_path):
    # em 13/10, o -cs.json do 2º turno de Tocantins dava 404: os municípios de lá vêm da configuração da eleição
    del tse.arquivos[H.url_secoes("to")]
    tse.publicar(H.URL_MUNICIPIOS, {"abr": [{"cd": "TO", "mu": [{"cd": "73440"}]}]})
    tse.publicar(H.url_resultado("to73440"), resultado("73440", "17:10:00", 3, 4, 70, 30))
    tse.publicar(H.URL_BR, resultado("br", "17:10:00", 3, 4, 70, 30))
    c = coletor(tmp_path / "ramo-a")
    c.rodada()
    c.rodada()  # o -cs.json de TO não é pedido de novo antes de 10 min
    assert [r["falhas_secoes"] for r in C.registros([c.raiz], "rodadas")] == [["to"], []]
    assert [(r["uf"], r["mu"], r["st"]) for r in C.registros([c.raiz], "municipios")] == [("to", "73440", 3)]


def test_antes_da_divulgacao_nao_le_municipios(tse, tmp_path, monkeypatch):
    monkeypatch.setattr(C, "AV", dataclasses.replace(C.AV, inicio=dt.datetime.now() + dt.timedelta(hours=1)))
    tse.publicar(H.url_secoes("zz"), config_secoes("zz", {("29998", "9001", "0001"): "25/10/2026 09:12:00"}))
    tse.publicar(H.URL_BR, resultado("br", "", 0, 2, 0, 0))  # antes das 17h: zerado, sem horário
    c = coletor(tmp_path / "ramo-a")
    c.rodada()
    assert [s[0] for s in C.registros([c.raiz], "secoes")] == ["zz"]  # o exterior chega cedo e já fica gravado
    assert not list(C.registros([c.raiz], "municipios")) and not list(C.registros([c.raiz], "leituras_br"))


def test_leitura_do_arquivo_do_tse():
    l = C.leitura(resultado("br", "17:02:00", 1, 4, 52, 48), h(17, 2, 30))
    assert {k: l[k] for k in ("abr", "h", "pst", "st", "ts", "vv", "c", "visto")} == {
        "abr": "br", "h": "2026-10-25T17:02:00", "pst": 25.0, "st": 1, "ts": 4, "vv": 100, "c": 110,
        "visto": "2026-10-25T17:02:30"}
    assert list(l["cand"]) == ["13", "22"] and l["cand"]["22"] == {"p": 48.0, "v": 48}
    assert C.leitura(resultado("br", "", 0, 4, 0, 0), h(16, 0)) is None  # zerado, antes da divulgação


# ---- Git e junção ------------------------------------------------------------------------------------------------

def _git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="sem git")
def test_envio_pelo_git_e_retomada_num_clone_novo(tmp_path):
    remoto, ramo = tmp_path / "remoto.git", tmp_path / "ramo"
    _git("init", "-q", "--bare", str(remoto))
    _git("init", "-q", "-b", "ao-vivo-a", str(ramo))
    for k, v in (("user.name", "teste"), ("user.email", "teste@exemplo.org"), ("core.autocrlf", "false")):
        _git("-C", str(ramo), "config", k, v)
    _git("-C", str(ramo), "remote", "add", "origin", str(remoto))
    g = C.Gravador(ramo / "1.1-1")
    g.json("leituras_br", {"h": "2026-10-25T17:02:00", "pst": 1.0, "visto": "2026-10-25T17:02:20"})
    assert C.enviar(ramo, "ao-vivo-a", "primeiro envio", log=pytest.fail)
    g.fechar()
    g.json("leituras_br", {"h": "2026-10-25T17:03:00", "pst": 2.0, "visto": "2026-10-25T17:03:20"})
    assert C.enviar(ramo, "ao-vivo-a", "segundo envio", log=pytest.fail)
    assert C.enviar(ramo, "ao-vivo-a", "nada novo", log=pytest.fail)
    clone = tmp_path / "clone"
    _git("clone", "-q", "--branch", "ao-vivo-a", str(remoto), str(clone))
    assert [l["h"] for l in C.registros([clone], "leituras_br")] == ["2026-10-25T17:02:00", "2026-10-25T17:03:00"]
    assert sorted(a.name for a in (clone / "1.1-1").iterdir()) == ["leituras_br-0001.jsonl", "leituras_br-0002.jsonl"]


def test_juntar_fica_com_o_que_cada_coletor_viu_primeiro_e_o_noite_le(tmp_path, monkeypatch):
    def lida(hora, pst, lula, visto):
        return {**C.leitura(resultado("br", hora, 1, 1, lula, 100 - lula, pst=pst), visto)}

    ga, gb = C.Gravador(tmp_path / "ramo-a" / "1.1-1"), C.Gravador(tmp_path / "ramo-b" / "1.1-1")
    ga.json("leituras_br", lida("17:02:00", 10.0, 55, h(17, 2, 20)), lida("17:06:00", 30.0, 52, h(17, 6, 20)))
    gb.json("leituras_br", lida("17:02:00", 10.0, 55, h(17, 2, 40)), lida("17:04:00", 20.0, 53, h(17, 4, 40)))
    ga.secoes([("ac", "00001", "0001", "0001", "25/10/2026 17:01:10", "2026-10-25T17:01:20")])
    gb.secoes([("ac", "00001", "0001", "0001", "25/10/2026 23:59:00", "2026-10-26T00:10:40"),
               ("ac", "00001", "0001", "0002", "25/10/2026 17:05:00", "2026-10-25T17:05:40")])
    for g in (ga, gb):
        g.json("leituras_uf", lida("17:02:00", 10.0, 55, h(17, 2, 30)) | {"abr": "ac"})
    monkeypatch.setattr(J, "_finais", lambda destino, log: None)  # sem rede
    destino = tmp_path / "bruto" / "ao_vivo" / "ele2026-6258"
    nada = lambda *_: None  # noqa: E731

    assert J.juntar([tmp_path / "ramo-a", tmp_path / "ramo-b"], destino, log=nada) == J.NAO_ACABOU
    assert J.juntar([tmp_path / "ramo-a", tmp_path / "ramo-b", tmp_path / "sem-ramo"], destino, forcar=True,
                    log=nada) == 0
    br = json.loads((destino / "leituras_oficiais.json").read_text("utf-8"))
    assert [(l["h"], l["visto"]) for l in br] == [("2026-10-25T17:02:00", "2026-10-25T17:02:20"),
                                                  ("2026-10-25T17:04:00", "2026-10-25T17:04:40"),
                                                  ("2026-10-25T17:06:00", "2026-10-25T17:06:20")]
    with gzip.open(destino / "secoes.csv.gz", "rt", encoding="utf-8") as f:
        assert f.read().splitlines() == ["uf,municipio,zona,secao,recebido,visto",
                                         "ac,00001,0001,0001,25/10/2026 17:01:10,2026-10-25T17:01:20",
                                         "ac,00001,0001,0002,25/10/2026 17:05:00,2026-10-25T17:05:40"]
    assert len(json.loads((destino / "leituras_ufs.json").read_text("utf-8"))["ac"]) == 1
    assert json.loads((destino / "coleta.json").read_text("utf-8"))["secoes"] == 2
    assert J.juntar([tmp_path / "ramo-a"], destino, ensaio=True, log=nada) == J.RECUSADO  # não refaz sem --forcar

    monkeypatch.setattr(config, "BRUTO", tmp_path / "bruto")
    n = noite.gerar(2026, 2)  # a mesma leitura do 1º turno vale para o 2º
    assert n["oficial"]["petismo"] == [55.0, 53.0, 52.0] and n["oficial"]["t"] == [2.0, 4.0, 6.0]
