"""Dados do mapa do site (site/src/data/mapa/*.json), a partir de dados/processado/mapa e da malha do IBGE.

  malha.json          municípios do IBGE em TopoJSON simplificado (fronteiras compartilhadas; id = código IBGE)
  municipios.json     nome, UF e posição (centro dos locais de votação, pelo eleitorado) de cada município
  locais_<ano>.json   cada ponto de votação: posição, precisão da posição e votos de cada turno
  nomes_<ano>.json    nome de cada ponto (o site só carrega quando alguém passa o mouse ou toca no mapa)
  resumo.json         o voto por local de votação: distribuição dos locais pela parte de cada campo, por ano e turno

Um "ponto" junta os locais de votação do mesmo prédio (mesmo nome e mesma coordenada, em zonas diferentes).
Coordenadas em graus × 10⁴ (cerca de 10 m) e, como os pontos vêm ordenados por município, município e coordenadas
são gravados como diferenças para o ponto anterior: o arquivo fica bem menor.
"""
import json
import re

import numpy as np
import shapely

from eleicoes import config
from eleicoes.coleta import ibge
from eleicoes.tratamento import conexao, coordenadas
from eleicoes.tratamento import municipios as tab_municipios

ESCALA = 10_000
TOLERANCIA_MALHA = 20  # simplificação das fronteiras, em unidades da quantização do IBGE (~20 m cada; os
                       # vértices da malha intermediária já ficam a ~1 km uns dos outros)
FAIXA_HISTOGRAMA = 5    # largura das faixas de % do bolsonarismo entre os dois campos, em pontos percentuais

MINUSCULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "NA", "NO", "NAS", "NOS", "A", "O", "AS", "OS", "AO", "AOS",
              "PARA", "COM", "SOB", "À", "ÀS"}
SIGLAS = {"EE", "EM", "EMEF", "EMEI", "EEF", "EEEF", "EEEFM", "EMEIEF", "EEIEF", "EEM", "EEFM", "EMEB", "EEB", "EMEIF",
          "EMEFM", "CEMEF", "CEI", "CMEI", "CEMEI", "CIEP", "CAIC", "CEU", "CE", "CEE", "CEEP", "CEJA", "EJA", "CETI",
          "CEPI", "ETEC", "FATEC", "IF", "IFMG", "IFSP", "IFBA", "IFCE", "IFPE", "IFRN", "IFPB", "IFPI", "IFMA", "IFPA",
          "UFMG", "USP", "UNESP", "UNICAMP", "UFRJ", "UFPE", "UFBA", "UFPB", "UFC", "UFRN", "UFPR", "UFSC", "UFRGS",
          "UFG", "UNB", "UNEB", "UEPB", "UERJ", "UEL", "UEM", "PUC", "SESC", "SESI", "SENAI", "SENAC", "CTG", "APAE",
          "CRAS", "CREAS", "UBS", "PSF", "CEFET", "ETE", "EREM", "CMEB", "EMEIEF", "CEMEB", "EMEFI", "CEFAM", "CAPS"}
ROMANOS = re.compile(r"^(I{1,3}|IV|VI{0,3}|IX|XI{0,3}|XIV|XV|XVI{0,3}|XIX|XX)$")


def titulo(texto):
    """Nome em maiúsculas do TSE -> "Escola Estadual Professor João da Silva", mantendo siglas e números romanos."""
    if not texto:
        return ""
    palavras = []
    for i, p in enumerate(texto.split()):
        nua = p.strip(".,;:()-/\"'")
        if nua in SIGLAS or ROMANOS.match(nua) or "." in p.strip(".") or any(c.isdigit() for c in p):
            palavras.append(p)
        elif i > 0 and nua in MINUSCULAS:
            palavras.append(p.lower())
        else:
            palavras.append("-".join(s[:1].upper() + s[1:].lower() for s in p.split("-")))
    return " ".join(palavras)


def _diferencas(valores):
    v = np.asarray(valores, dtype=np.int64)
    return np.diff(v, prepend=0).tolist()


def malha(log=print):
    """TopoJSON dos municípios do IBGE simplificado (Douglas-Peucker em cada fronteira, que continua compartilhada)."""
    t = json.loads(ibge.ARQ_TOPOJSON.read_text("utf-8"))
    (nome, obj), = t["objects"].items()
    arcos, antes, depois = [], 0, 0
    for arco in t["arcs"]:
        pts = np.cumsum(np.asarray(arco, dtype=np.int64), axis=0)
        antes += len(pts)
        if len(pts) > 2:
            s = np.asarray(shapely.simplify(shapely.LineString(pts), TOLERANCIA_MALHA).coords, dtype=np.int64)
            fechado = (pts[0] == pts[-1]).all()
            if len(s) >= (4 if fechado else 2):
                pts = s
        depois += len(pts)
        arcos.append(np.diff(pts, axis=0, prepend=[[0, 0]]).tolist())
    geometrias = [{"type": g["type"], "arcs": g["arcs"], "id": g["properties"]["codarea"]} for g in obj["geometries"]]
    log(f"   malha: {antes:_} → {depois:_} vértices".replace("_", "."))
    return {"type": "Topology", "transform": t["transform"], "arcs": arcos,
            "objects": {"municipios": {"type": "GeometryCollection", "geometries": geometrias}}}


def municipios(con):
    """Municípios brasileiros na ordem do código IBGE, com a posição do rótulo: o centro dos locais de votação,
    ponderado pelo eleitorado (o da eleição mais recente com locais)."""
    anos = [a for a in config.anos() if coordenadas.saida(a).exists()]
    locais = "[" + ", ".join(f"'{coordenadas.saida(a).as_posix()}'" for a in anos) + "]"
    linhas = con.execute(f"""
        WITH c AS (SELECT cd_ibge, arg_max(lon, ano) AS lon, arg_max(lat, ano) AS lat, arg_max(eleitores, ano) AS eleitores
                   FROM (SELECT ano, cd_ibge, sum(lon * eleitores) / sum(eleitores) AS lon,
                                sum(lat * eleitores) / sum(eleitores) AS lat, sum(eleitores) AS eleitores
                         FROM read_parquet({locais}) WHERE eleitores > 0 GROUP BY ALL)
                   GROUP BY ALL)
        SELECT m.cd_ibge, m.nm_municipio, m.sg_uf, c.lon, c.lat, coalesce(c.eleitores, 0)
        FROM '{tab_municipios.SAIDA.as_posix()}' m LEFT JOIN c USING (cd_ibge)
        WHERE m.sg_uf <> 'ZZ' ORDER BY m.cd_ibge""").fetchall()
    poli = coordenadas.poligonos()
    out = {"codigo": [], "nome": [], "uf": [], "lon": [], "lat": [], "eleitores": []}
    for cod, nome, uf, lon, lat, eleitores in linhas:
        if lon is None:  # sem local de votação com eleitorado: o centro do polígono
            p = poli[cod].point_on_surface()
            lon, lat = p.x, p.y
        for k, v in zip(out, (cod, nome, uf, round(lon * ESCALA), round(lat * ESCALA), int(eleitores))):
            out[k].append(v)
    return out


def _turnos(colunas):
    return [t for t in (1, 2) if f"t{t}_validos" in colunas]


def locais(con, ano, indice_municipio):
    """(dados do mapa, nomes) de um ano: um ponto por prédio, ordenado por município e posição."""
    arq = coordenadas.saida(ano).as_posix()
    colunas = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM '{arq}'").fetchall()]
    turnos = _turnos(colunas)
    medidas = {t: ["petismo", "bolsonarismo"] + (["outros"] if t == 1 else []) for t in turnos}
    somas = ", ".join(f"sum(t{t}_{m})::BIGINT AS t{t}_{m}" for t in turnos for m in medidas[t])
    # Locais com posição aproximada não se juntam: cada um espalha os próprios votos em volta da posição estimada
    linhas = con.execute(f"""
        SELECT cd_ibge, round(lon * {ESCALA})::BIGINT AS x, round(lat * {ESCALA})::BIGINT AS y,
               max(precisao) AS precisao, round(max(coalesce(raio_km, 0)) * 1000)::BIGINT AS raio_m,
               min(nm_local) AS nome, {somas}
        FROM '{arq}'
        GROUP BY cd_ibge, x, y, upper(strip_accents(coalesce(nm_local, ''))),
                 CASE WHEN precisao >= 2 THEN concat(cd_municipio, '-', nr_zona, '-', nr_local_votacao) END
        ORDER BY cd_ibge, y, x, min(concat(cd_municipio, '-', nr_zona, '-', nr_local_votacao))""").fetchall()
    dados = {
        "ano": ano, "turnos": turnos, "n": len(linhas), "escala": ESCALA,
        "municipio": _diferencas([indice_municipio[l[0]] for l in linhas]),
        "lon": _diferencas([l[1] for l in linhas]), "lat": _diferencas([l[2] for l in linhas]),
        "precisao": "".join(str(l[3]) for l in linhas),
        "raio": {str(i): l[4] for i, l in enumerate(linhas) if l[4]},  # m, só dos pontos com posição aproximada
        "votos": {},
    }
    i = 6  # primeira coluna de votos
    for t in turnos:
        dados["votos"][str(t)] = {}
        for m in medidas[t]:
            dados["votos"][str(t)][m] = [l[i] for l in linhas]
            i += 1
    return dados, [titulo(l[5]) for l in linhas]


def resumo(con):
    """Por ano e turno: quantos votos dos dois campos foram dados em locais com cada % de bolsonarismo (entre os
    dois campos), e a parte dos votos em locais onde um dos campos passou de 60% e de 70%. Também: como cada local
    recebeu a posição (por precisão e por método) e o erro de cada método (`coordenadas.validar`)."""
    anos = [a for a in config.anos() if coordenadas.saida(a).exists()]
    validacao = coordenadas.ler_validacao()
    if validacao is None or not set(anos) <= set(validacao):
        validacao = coordenadas.validar(anos)
    out = {"faixa": FAIXA_HISTOGRAMA, "anos": {},
           "metodos": {str(n): {"descricao": d, "precisao": p} for n, (_, d, p) in coordenadas.METODOS.items()},
           "validacao": {str(a): {str(n): v for n, v in validacao[a].items()} for a in anos}}
    for ano in anos:
        arq = coordenadas.saida(ano).as_posix()
        colunas = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM '{arq}'").fetchall()]
        precisao = con.execute(f"SELECT precisao, count(*), sum(eleitores) FROM '{arq}' GROUP BY 1 ORDER BY 1").fetchall()
        metodos = con.execute(f"SELECT nivel, count(*), sum(eleitores) FROM '{arq}' GROUP BY 1 ORDER BY 1").fetchall()
        out["anos"][str(ano)] = {"precisao": {str(p): {"locais": n, "eleitores": int(e or 0)} for p, n, e in precisao},
                                 "metodos": {str(m): {"locais": n, "eleitores": int(e or 0)} for m, n, e in metodos},
                                 "turnos": {}}
        for t in _turnos(colunas):
            pt, bo = f"t{t}_petismo", f"t{t}_bolsonarismo"
            r = con.execute(f"""
                WITH l AS (SELECT {pt} AS pt, {bo} AS bo, {pt} + {bo} AS dois,
                                  100.0 * {bo} / nullif({pt} + {bo}, 0) AS p FROM '{arq}' WHERE {pt} + {bo} > 0)
                SELECT least(floor(p / {FAIXA_HISTOGRAMA}), {100 // FAIXA_HISTOGRAMA - 1})::INT AS faixa,
                       sum(pt)::BIGINT, sum(bo)::BIGINT, count(*) FROM l GROUP BY 1 ORDER BY 1""").fetchall()
            hist = {int(f): {"petismo": int(a), "bolsonarismo": int(b), "locais": n} for f, a, b, n in r}
            total, acima60, acima70, locais_pt, locais_bo = con.execute(f"""
                WITH l AS (SELECT {pt} + {bo} AS dois, greatest({pt}, {bo}) / nullif({pt} + {bo}, 0) AS lider, {pt} AS pt,
                                  {bo} AS bo FROM '{arq}' WHERE {pt} + {bo} > 0)
                SELECT sum(dois), sum(dois) FILTER (lider >= 0.6), sum(dois) FILTER (lider >= 0.7),
                       count(*) FILTER (pt > bo), count(*) FILTER (bo > pt) FROM l""").fetchone()
            out["anos"][str(ano)]["turnos"][str(t)] = {
                "histograma": [hist.get(f, {"petismo": 0, "bolsonarismo": 0, "locais": 0}) | {"inicio": f * FAIXA_HISTOGRAMA}
                               for f in range(100 // FAIXA_HISTOGRAMA)],
                "votos_dois_campos": int(total), "acima_60": int(acima60) / int(total), "acima_70": int(acima70) / int(total),
                "locais_petismo": locais_pt, "locais_bolsonarismo": locais_bo}
    return out


def gerar(escrever, log=print):
    """Escreve os arquivos do mapa com a função escrever(nome, dados) de analises/site.py."""
    con = conexao()
    escrever("mapa/malha.json", malha(log))
    mun = municipios(con)
    escrever("mapa/municipios.json", mun)
    indice = {c: i for i, c in enumerate(mun["codigo"])}
    for ano in config.anos():
        if coordenadas.saida(ano).exists():
            dados, nomes = locais(con, ano, indice)
            escrever(f"mapa/locais_{ano}.json", dados)
            escrever(f"mapa/nomes_{ano}.json", nomes)
    escrever("mapa/resumo.json", resumo(con))
