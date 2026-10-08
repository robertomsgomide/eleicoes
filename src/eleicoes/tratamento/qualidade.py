"""Relatório de qualidade das tabelas processadas -> docs/qualidade_dados.md (gerado; não editar à mão)."""
import datetime as dt

from eleicoes import config
from eleicoes.tratamento import boletins, conexao, coordenadas, locais, oficial, votacao_secao
from eleicoes.tratamento import municipios as tab_municipios

SAIDA = config.RAIZ / "docs" / "qualidade_dados.md"


def _n(x):
    return f"{x:,}".replace(",", ".")


def _p(x):
    return "–" if x is None else f"{x:.2%}".replace(".", ",")


def _km(x):
    return f"{x:.2f} km".replace(".", ",")


def gerar(log=print):
    con = conexao()
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731
    secao = lambda a, t: boletins.saida("secoes", a, t).as_posix()  # noqa: E731
    anos = config.anos()
    pares = [(a, t) for a in anos for t in (1, 2) if boletins.saida("secoes", a, t).exists()]
    # Turnos sem boletins de urna, só com a votação por seção (2026, até os boletins saírem)
    pares_vs = [(a, t) for a in anos for t in (1, 2) if votacao_secao.saida(a, t).exists() and (a, t) not in pares]

    linhas = ["# Qualidade dos dados", "",
              f"> Gerado por `uv run eleicoes processar` em {dt.datetime.now():%d/%m/%Y %H:%M}. Não editar à mão.", "",
              "## 1. Boletins de urna × totais oficiais do TSE", "",
              "Soma dos votos dos boletins de cada seção comparada com o total oficial do TSE "
              "(votação nominal por município e zona), candidato a candidato, no Brasil, em cada UF e em cada zona.", "",
              "| Ano | Turno | Seções | Aptos | Comparecimento | Votos válidos | Petismo | Bolsonarismo | Diferença do oficial |",
              "|---|---|--:|--:|--:|--:|--:|--:|---|"]
    inexplicadas = []
    for a, t in pares:
        n, aptos, comp, val, pt, bo = q(f"""SELECT count(*), sum(qt_aptos), sum(qt_comparecimento), sum(votos_validos),
                                            sum(votos_petismo), sum(votos_bolsonarismo) FROM '{secao(a, t)}'""")[0]
        chave = ("cd_municipio", "nr_zona")
        if not oficial.saida(a).exists():
            situacao = "total oficial ainda não publicado"
        elif (achadas := oficial.diferencas(con, a, t, chave)) == (conhecidas := oficial.esperadas(a, t, chave)) and not achadas:
            situacao = "nenhuma ✅"
        elif achadas == conhecidas:
            zonas = {k[:2] for k in achadas}
            situacao = f"{_n(sum(achadas.values()))} votos em {len(zonas)} zona(s), já conhecida ✅"
        else:
            novas = {k: d for k, d in achadas.items() if conhecidas.get(k) != d}
            inexplicadas += [(a, t, k, d) for k, d in list(novas.items())[:20]]
            situacao = f"❌ {len({k[:2] for k in novas})} zona(s) com diferença não explicada"
        linhas.append(f"| {a} | {t}º | {_n(n)} | {_n(aptos)} | {_n(comp)} | {_n(val)} | {_p(pt / val)} | {_p(bo / val)} "
                      f"| {situacao} |")
    if inexplicadas:
        linhas += ["", "Diferenças não explicadas (até 20 por turno): " + "; ".join(
            f"{a} {t}º turno, município {k[0]} zona {k[1]} candidato {k[2]}: {d:+}" for a, t, k, d in inexplicadas)]
    linhas += ["", "Divergências conhecidas, conferidas uma a uma (`DIVERGENCIAS_CONHECIDAS` em "
               "`src/eleicoes/tratamento/oficial.py`):", ""]
    for (a, t, uf, mun, zona), difs in oficial.DIVERGENCIAS_CONHECIDAS.items():
        detalhe = ", ".join(f"{nr}: {d:+}" for nr, d in difs.items())
        linhas.append(f"- {a}, {t}º turno, {uf}, município {mun}, zona {zona}: boletins − oficial = {detalhe}.")
    linhas += ["", "Votos anulados de candidatos com candidatura indeferida (`nulos_tecnicos` em `config/eleicoes.toml`) "
               "são nominais nos boletins, mas o total oficial não os traz: contam como nulos, fora da conferência."]

    # Turnos com as duas fontes de votos por seção (2026): os boletins e a votação por seção, seção a seção
    pares_dois = [(a, t) for a, t in pares if votacao_secao.saida(a, t).exists()]
    if pares_dois:
        linhas += ["", "### Boletins de urna × votação por seção", "",
                   "O TSE publica os votos de cada seção em dois arquivos: a votação por seção, um dia depois da eleição, "
                   "e os boletins de urna, dias depois. Comparados seção a seção, nos votos de cada campo, dos outros "
                   "candidatos, brancos e nulos.", "",
                   "| Ano | Turno | Seções | Seções com alguma diferença |", "|---|---|--:|---|"]
        for a, t in pares_dois:
            d = votacao_secao.diferencas_dos_boletins(con, a, t)
            secoes = len({linha[:4] for linha in d["diferentes"]})
            linhas.append(f"| {a} | {t}º | {_n(d['secoes'])} | {'nenhuma ✅' if not secoes else f'❌ {_n(secoes)}'} |")

    if pares_vs:
        linhas += ["", "### Turnos ainda sem boletins de urna: votação por seção × resultado final", "",
                   "Enquanto o TSE não publica os boletins de urna, os votos de cada seção vêm do arquivo de votação "
                   "por seção. O total oficial por município e zona de 2026 saiu sem os votos de Presidente; a "
                   "conferência é com o resultado final da totalização em cada UF (arquivos do site de resultados), "
                   "para os votos de cada campo, dos outros candidatos, brancos e nulos (com os votos anulados de "
                   "candidatos indeferidos, como no resultado oficial).", "",
                   "| Ano | Turno | Seções | Votos válidos | Petismo | Bolsonarismo | Diferença do resultado final |",
                   "|---|---|--:|--:|--:|--:|---|"]
        for a, t in pares_vs:
            arq = votacao_secao.saida(a, t).as_posix()
            n, val, pt, bo = q(f"SELECT count(*), sum(votos_validos), sum(votos_petismo), sum(votos_bolsonarismo) FROM '{arq}'")[0]
            if not votacao_secao.pasta_final(a, t).exists():
                situacao = "sem resultado final para conferir"
            elif difs := votacao_secao.diferencas_do_resultado_final(con, a, t):
                situacao = f"❌ {len({k[0] for k in difs})} UF(s) com diferença"
            else:
                situacao = "nenhuma, em todas as UFs ✅"
            linhas.append(f"| {a} | {t}º | {_n(n)} | {_n(val)} | {_p(pt / val)} | {_p(bo / val)} | {situacao} |")

    linhas += ["", "## 2. Horários", "",
               "A chegada do boletim ao TSE está no horário de Brasília; abertura, encerramento e emissão do "
               "boletim estão no horário local da seção. O TSE só publica a chegada a partir de 2022.", "",
               "| Ano | Turno | Seções com chegada do boletim | Primeira chegada | Última chegada | Seções com encerramento da urna |",
               "|---|---|--:|---|---|--:|"]
    for a, t in pares:
        n, com, ini, fim, enc = q(f"""SELECT count(*), count(dt_bu_recebido), min(dt_bu_recebido), max(dt_bu_recebido),
                                          count(dt_encerramento) FROM '{secao(a, t)}'""")[0]
        linhas.append(f"| {a} | {t}º | {_p(com / n)} | {ini or '–'} | {fim or '–'} | {_p(enc / n)} |")

    linhas += ["", "## 3. Tipos de urna", "", "| Ano | Turno | Tipo | Seções | Boletins por seção |", "|---|---|---|--:|--:|"]
    for a, t in pares:
        for tipo, qtd, n in q(f"SELECT tipo_urna, qt_boletins, count(*) FROM '{secao(a, t)}' GROUP BY ALL ORDER BY 3 DESC"):
            linhas.append(f"| {a} | {t}º | {tipo} | {_n(n)} | {qtd} |")

    linhas += _locais(q, [*pares, *pares_vs], log)

    mun = tab_municipios.SAIDA.as_posix()
    total, ext, sem = q(f"""SELECT count(*), count(*) FILTER (sg_uf = 'ZZ'),
                               count(*) FILTER (sg_uf <> 'ZZ' AND cd_ibge IS NULL) FROM '{mun}'""")[0]
    sem_secoes = sum(q(f"""SELECT count(DISTINCT cd_municipio) FROM '{votacao_secao.fonte_secoes(a, t).as_posix()}'
                          WHERE sg_uf <> 'ZZ' AND cd_ibge IS NULL""")[0][0] for a, t in [*pares, *pares_vs])
    linhas += ["", "## 6. Municípios", "",
               f"- Tabela de códigos TSE → IBGE: {_n(total)} municípios, {_n(ext)} deles no exterior.",
               f"- Municípios brasileiros sem código IBGE: {_n(sem)} na tabela; {_n(sem_secoes)} nas tabelas de seções.", ""]
    SAIDA.write_text("\n".join(linhas), "utf-8")


def _locais(q, pares, log):
    """Seções 4 e 5: as seções no arquivo de locais de votação, as coordenadas completadas e o erro de cada método."""
    linhas = ["", "## 4. Locais de votação", "",
              "Cada seção com votos procurada no arquivo de locais de votação do mesmo ano e turno. Coordenada "
              "válida: informada pelo TSE, a até 2 km do município (malha do IBGE) e não repetida em 3 ou mais "
              "locais de nomes diferentes do município.", "",
              "| Ano | Turno | Seções com votos | Achadas no arquivo de locais | Votos válidos em seções com coordenada válida do TSE |",
              "|---|---|--:|--:|--:|"]
    for a, t in pares:
        fonte = votacao_secao.fonte_secoes(a, t).as_posix()
        lv = locais.saida(a).as_posix()
        mapa = coordenadas.saida(a)
        n, achadas, val, val_tse = q(f"""
            WITH l AS (SELECT DISTINCT ON (cd_municipio, nr_zona, nr_secao) * FROM '{lv}'
                       ORDER BY cd_municipio, nr_zona, nr_secao, abs(turno - {t})),
                 m AS (SELECT cd_municipio, nr_zona, nr_local_votacao, nivel FROM '{mapa.as_posix()}')
            SELECT count(*), count(l.nr_secao), sum(s.votos_validos), sum(s.votos_validos) FILTER (m.nivel = 0)
            FROM '{fonte}' s
            LEFT JOIN l ON l.cd_municipio = s.cd_municipio AND l.nr_zona = s.nr_zona AND l.nr_secao = s.nr_secao
            LEFT JOIN m ON m.cd_municipio = s.cd_municipio AND m.nr_zona = s.nr_zona
                       AND m.nr_local_votacao = coalesce(l.nr_local_votacao, s.nr_local_votacao)
            WHERE s.sg_uf <> 'ZZ'""")[0]
        linhas.append(f"| {a} | {t}º | {_n(n)} | {_p(achadas / n)} | {_p((val_tse or 0) / val)} |")

    anos = sorted({a for a, _ in pares if coordenadas.saida(a).exists()})
    linhas += ["", "## 5. Coordenadas completadas para o mapa", "",
               "Como cada local de votação recebeu a posição (`src/eleicoes/tratamento/coordenadas.py`), em % do "
               "eleitorado dos locais (fora o exterior). Métodos em ordem de preferência.", "",
               "| Método | " + " | ".join(str(a) for a in anos) + " |", "|---|" + "--:|" * len(anos)]
    por_ano = {a: dict((nivel, (n, el or 0)) for nivel, n, el in q(
        f"SELECT nivel, count(*), sum(eleitores) FROM '{coordenadas.saida(a).as_posix()}' GROUP BY 1")) for a in anos}
    for nivel, (_, descricao, _) in coordenadas.METODOS.items():
        celulas = []
        for a in anos:
            n, el = por_ano[a].get(nivel, (0, 0))
            total = sum(e for _, e in por_ano[a].values())
            celulas.append(f"{_p(el / total)} ({_n(n)} locais)" if n else "–")
        linhas.append(f"| {nivel}. {descricao} | " + " | ".join(celulas) + " |")

    v = coordenadas.ler_validacao()
    if v is None or not set(anos) <= set(v):
        log("   validando os métodos de coordenadas (escondendo a coordenada de quem a tem)")
        v = coordenadas.validar(anos, log)
    linhas += ["", "Erro de cada método, medido nos locais que têm coordenada do TSE: a coordenada é escondida e "
               "o método tenta encontrá-la. Distância entre a posição dada pelo método e a do TSE; n = locais em que "
               "o método se aplica.", "",
               "| Método | " + " | ".join(f"{a}: mediana · 90% até · acima de 1 km" for a in anos) + " |",
               "|---|" + "---|" * len(anos)]
    for nivel in sorted({k for a in anos for k in v[a]}):
        celulas = [(f"{_km(r['mediana_km'])} · {_km(r['p90_km'])} · {_p(r['acima_1km'])} (n = {_n(r['n'])})"
                    if (r := v[a].get(nivel)) else "–") for a in anos]
        linhas.append(f"| {nivel}. {coordenadas.METODOS[nivel][1]} | " + " | ".join(celulas) + " |")
    return linhas
