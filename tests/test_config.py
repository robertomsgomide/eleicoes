import datetime as dt

from eleicoes import config


def test_cada_eleicao_tem_os_dois_campos_e_os_dois_turnos():
    eleicoes = config.carregar()["eleicoes"]
    assert set(eleicoes) == {"2018", "2022", "2026"}
    for ano, e in eleicoes.items():
        assert e["petismo"]["numero"] == 13, ano
        assert e["bolsonarismo"]["numero"] in (17, 22), ano
        assert dt.date.fromisoformat(e["turno1"]["data"]) < dt.date.fromisoformat(e["turno2"]["data"]), ano


def test_ao_vivo_aponta_para_uma_eleicao_completa():
    av = config.ao_vivo()
    assert av.ciclo == f"ele{av.ano}"
    assert av.pleito and av.eleicao
    assert av.inicio.hour == 17
    assert av.cache.is_relative_to(config.CACHE)
    assert av.bruto.is_relative_to(config.BRUTO)
