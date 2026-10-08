"""Testes do painel ao vivo sem rede: a reconstrução com dados sintéticos e a política de segurança da página."""
import base64
import collections
import datetime as dt
import hashlib
import re

import pytest

from eleicoes.ao_vivo import historico as H
from eleicoes.ao_vivo import servidor


def minuto(h, m):
    return H.INICIO_DIVULGACAO.replace(hour=h, minute=m)


@pytest.fixture
def coleta():
    # AC: 4 seções (1 chega antes das 17h, 2 às 17h02, 1 ainda não chegou); SP: 2 seções às 17h01
    secoes = {
        "ac": {"00001": [4, collections.Counter({minuto(16, 50): 1, minuto(17, 2): 2})]},
        "sp": {"71072": [2, collections.Counter({minuto(17, 1): 2})]},
    }
    mun = {  # médias por seção: AC 60/40 (vv 100); SP 50/150 (vv 200)
        ("ac", "00001"): {"st": 3, "ts": 4, "and": "p", "vv": 300.0, "cand": {"13": 180.0, "22": 120.0}},
        ("sp", "71072"): {"st": 2, "ts": 2, "and": "f", "vv": 400.0, "cand": {"13": 100.0, "22": 300.0}},
    }
    br = {"dt": "04/10/2026", "ht": "17:05:00", "and": "p", "dv": "s",
          "s": {"st": "5", "ts": "6", "pstn": "83,333333333"}, "v": {"vv": "700"},
          "carg": [{"cand": [{"n": "13", "nmu": "LULA", "vap": "280"},
                             {"n": "22", "nmu": "FLAVIO BOLSONARO", "vap": "420"}]}]}
    return {"secoes": secoes, "mun": mun, "br": br}


def test_reconstrucao_minuto_a_minuto(coleta):
    s = H.reconstruir(coleta)
    assert s["t"] == [minuto(17, 0), minuto(17, 1), minuto(17, 2)]  # o boletim das 16h50 entra às 17h
    assert s["recebidas"] == [1, 3, 5]
    assert s["secoes"]["Brasil"] == [16.667, 50.0, 83.333]
    assert s["secoes"]["Norte"] == [25.0, 25.0, 75.0]
    assert s["secoes"]["Sudeste"] == [0.0, 100.0, 100.0]
    flavio, lula = s["cand"]  # ordenados pelo total oficial
    assert (flavio["n"], lula["n"]) == ("22", "13")
    assert lula["pct"] == [60.0, 32.0, 40.0]
    assert flavio["votos"] == [40, 340, 420]


def test_ultimo_ponto_bate_com_o_oficial_quando_os_municipios_estao_em_dia(coleta):
    s = H.reconstruir(coleta)
    for cand, of in zip(s["cand"], s["oficial"]["cand"]):
        assert cand["pct"][-1] == pytest.approx(of["p"])


def test_politica_de_seguranca_libera_so_o_script_da_pagina():
    html, csp = servidor.pagina_e_politica()
    (script,) = re.findall(rb"<script>(.*?)</script>", html, re.S)
    hash_ = base64.b64encode(hashlib.sha256(script).digest()).decode()
    assert f"'sha256-{hash_}'" in csp
    assert "connect-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
