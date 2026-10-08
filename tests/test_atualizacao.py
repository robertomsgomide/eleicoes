"""Atualização automática: o que a conferência deixa publicar sozinho, até quando vai a projeção e a tarefa agendada."""
import datetime as dt
import pathlib

from eleicoes import atualizacao as A
from eleicoes.coleta import wikipedia
from eleicoes.modelos import projecao

HOJE = dt.date(2026, 10, 14)


def _p(instituto="Quaest", petismo=47.0, bolsonarismo=49.0, inicio=(10, 10), fim=(12, 10), turno=2, amostra=2000,
       registro="BR012342026"):
    validos = petismo + bolsonarismo
    return {"turno": turno, "instituto": instituto, "inicio": dt.date(2026, inicio[1], inicio[0]),
            "fim": dt.date(2026, fim[1], fim[0]), "amostra": amostra, "registro": registro,
            "petismo": petismo, "bolsonarismo": bolsonarismo,
            "petismo_validos": round(100 * petismo / validos, 2), "bolsonarismo_validos": round(100 * bolsonarismo / validos, 2)}


ANTIGAS = [_p("Datafolha", 45, 47, (1, 10), (3, 10)), _p("Quaest", 44, 46, (2, 10), (3, 10)),
           _p("AtlasIntel", 47, 50, (28, 9), (2, 10)), _p("Futura", 44, 49, (29, 9), (3, 10))]


def test_mesma_leitura_nao_muda_nada():
    assert not any(A.comparar(ANTIGAS, [dict(p) for p in ANTIGAS]).values())


def test_pesquisa_nova_perto_da_projecao_entra_sozinha():
    nova = _p("Quaest", 47, 49, (10, 10), (12, 10))
    m = A.comparar(ANTIGAS, ANTIGAS + [nova])
    assert m["novas"] == [nova] and not m["sumidas"] and not m["alteradas"]
    assert A.problemas(m, 2026, referencia=48.2, hoje=HOJE) == []


def test_pesquisa_nova_longe_demais_da_projecao_espera_alguem_conferir():
    longe = _p("Instituto X", 60, 35, (10, 10), (12, 10))  # 63% dos válidos, a 15 pontos da projeção
    (motivo,) = A.problemas(A.comparar(ANTIGAS, ANTIGAS + [longe]), 2026, referencia=48.2, hoje=HOJE)
    assert "Instituto X" in motivo and "longe demais" in motivo
    # feita antes do 1º turno, ela não se compara com a projeção (era outro confronto)
    antiga = _p("Instituto X", 60, 35, (25, 9), (27, 9))
    assert A.problemas(A.comparar(ANTIGAS, ANTIGAS + [antiga]), 2026, referencia=48.2, hoje=HOJE) == []


def test_pesquisa_nova_impossivel():
    futuro = _p("Quaest", 47, 49, (13, 10), (16, 10))
    assert "datas de campo" in A.problemas(A.comparar(ANTIGAS, ANTIGAS + [futuro]), 2026, hoje=HOJE)[0]
    soma = _p("Quaest", 60, 50, (10, 10), (12, 10))
    assert "percentuais impossíveis" in A.problemas(A.comparar(ANTIGAS, ANTIGAS + [soma]), 2026, hoje=HOJE)[0]


def test_pesquisas_guardadas_sumindo_seguram_a_revisao():
    m = A.comparar(ANTIGAS, ANTIGAS[:1])
    assert len(m["sumidas"]) == 3
    assert A.problemas(m, 2026, hoje=HOJE) == ["3 pesquisas já publicadas sumiram da página"]
    assert A.problemas(A.comparar(ANTIGAS, ANTIGAS[:2]), 2026, hoje=HOJE) == []  # uma data corrigida, uma duplicata


def test_correcao_pequena_passa_e_mudanca_grande_num_numero_antigo_nao():
    pequena = [_p("Datafolha", 45.5, 47, (1, 10), (3, 10)), *ANTIGAS[1:]]
    m = A.comparar(ANTIGAS, pequena)
    assert [(a["instituto"], d) for a, _, d in m["alteradas"]] == [("Datafolha", 0.5)]
    assert A.problemas(m, 2026, hoje=HOJE) == []
    grande = [_p("Datafolha", 52, 40, (1, 10), (3, 10)), *ANTIGAS[1:]]
    (motivo,) = A.problemas(A.comparar(ANTIGAS, grande), 2026, hoje=HOJE)
    assert motivo.startswith("Datafolha") and "mudou" in motivo


def test_mudanca_so_no_registro_do_tse_e_publicada_sem_problema():
    religada = [{**ANTIGAS[3], "registro": "BR055552026"}, *ANTIGAS[:3]]
    m = A.comparar(ANTIGAS, religada)
    assert [p["instituto"] for p in m["religadas"]] == ["Futura"] and not m["alteradas"]
    assert A.problemas(m, 2026, hoje=HOJE) == []


def test_projecao_vai_ate_a_ultima_conferencia_da_pagina(monkeypatch):
    rev = {"revid": 1, "baixado_em": "2026-10-07T16:55:07"}
    monkeypatch.setattr(wikipedia, "revisao", lambda ano: rev)
    assert projecao.ultimo_dia(2026) == dt.date(2026, 10, 7)
    rev["consultado_em"] = "2026-10-12T09:00:01"
    assert projecao.ultimo_dia(2026) == dt.date(2026, 10, 12)
    rev["consultado_em"] = "2026-10-25T09:00:01"  # no dia da eleição, a projeção para na véspera
    assert projecao.ultimo_dia(2026) == dt.date(2026, 10, 24)


def test_script_da_tarefa_agendada():
    pythonw = pathlib.PureWindowsPath(r"C:\Users\x\Vibe Coding\d'Ávila\.venv\Scripts\pythonw.exe")
    s = A.script_da_tarefa(2, dt.datetime(2026, 10, 25, 17), pythonw, pythonw.parents[2])
    assert r"-Execute 'C:\Users\x\Vibe Coding\d''Ávila\.venv\Scripts\pythonw.exe'" in s  # aspas simples dobradas
    assert "-Argument '-m eleicoes atualizar --avisar'" in s
    assert "-RepetitionInterval (New-TimeSpan -Hours 2)" in s
    assert "$gatilho.EndBoundary = '2026-10-25T17:00:00'" in s
    assert "-TaskName 'eleicoes-atualizar'" in s and "-AllowStartIfOnBatteries" in s and "-StartWhenAvailable" in s
