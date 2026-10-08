"""Pesquisas eleitorais: tabelas da Wikipedia -> uma linha por pesquisa e turno, ligada ao registro do TSE.

Saídas em dados/processado/pesquisas/:
  linhas_<ano>.parquet     todas as linhas lidas (cada cenário de cada pesquisa), para auditoria
  pesquisas_<ano>.parquet  uma linha por pesquisa e turno: o cenário com os dois campos, em % do total e dos
                           votos válidos, com o número de registro no TSE e como a ligação foi feita

Ligação com o registro do TSE (PesqEle): pelo número de registro citado na Wikipedia; sem ele, pela
amostra idêntica e datas de campo coincidentes (± 2 dias), desempatando pelo nome do instituto.
"""
import csv
import datetime as dt
import io
import re
import unicodedata
import zipfile

import lxml.html

from eleicoes import config
from eleicoes.coleta import tse, wikipedia
from eleicoes.tratamento import conexao

MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
# BR-09479/2022; na Wikipedia também aparece com hífen tipográfico, travessão, 4 ou 6 dígitos
REGISTRO = re.compile(r"\b([A-Z]{2})[\s\-‐‑–—]*(\d{3,6})\s*/\s*(\d{4})")
NAO_VALIDOS = ("indecis", "absten", "abst", "branco", "nulo", "naodecid", "absent", "nenhum", "naosabe")
# Grafias diferentes do mesmo instituto (a chave é o nome sem acento, minúsculo e só com letras e números)
INSTITUTOS = {
    "datafolha": "Datafolha", "ibope": "Ibope", "ipec": "Ipec", "quaest": "Quaest", "atlasintel": "AtlasIntel",
    "atlas": "AtlasIntel", "atlasinstel": "AtlasIntel", "ipespe": "Ipespe", "mda": "MDA", "fsb": "FSB",
    "fsbpesquisa": "FSB", "futura": "Futura", "futurainteligencia": "Futura", "paranapesquisas": "Paraná Pesquisas",
    "poderdata": "PoderData", "datapoder360": "PoderData", "realtimebigdata": "Real Time Big Data", "ideia": "Ideia",
    "ideiabigdata": "Ideia", "btg": "BTG Pactual", "btgpactual": "BTG Pactual", "verita": "Veritá",
    "institutoverita": "Veritá",
}
# Como o instituto aparece no nome da empresa no registro do TSE, quando não é o próprio nome
NO_REGISTRO = {
    "Paraná Pesquisas": ["paranadepesquisas", "paranapesquisas"],
    "Ipec": ["ipec", "inteligenciaempesquisa"],
    "Vox": ["voxbrasil", "voxdobrasil"],
    "BTG Pactual": ["nexus"],  # as pesquisas BTG Pactual de 2026 são feitas pela Nexus
}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def chave(s):
    return re.sub(r"[^a-z0-9]", "", sem_acento(s or "").lower())


def _texto(el):
    return re.sub(r"\s+", " ", " ".join(el.itertext())).strip()


def _sem_refs(s):
    return re.sub(r"\[\s*[^\]]*\]", "", s).strip()  # [28], [ a ], [nota 3]


def _grade(tabela):
    """Linhas da tabela com as células mescladas (rowspan/colspan) repetidas em cada posição."""
    linhas, ocupadas = [], {}
    for i, tr in enumerate(tabela.xpath("./tr|./thead/tr|./tbody/tr")):
        linha, j = [], 0
        for c in tr.xpath("./th|./td"):
            while (i, j) in ocupadas:
                linha.append(ocupadas.pop((i, j)))
                j += 1
            rs, cs = int(c.get("rowspan", 1) or 1), int(c.get("colspan", 1) or 1)
            for dj in range(cs):
                linha.append(c)
                for di in range(1, rs):
                    ocupadas[(i + di, j + dj)] = c
                j += 1
        while (i, j) in ocupadas:
            linha.append(ocupadas.pop((i, j)))
            j += 1
        linhas.append(linha)
    return linhas


def _tabelas(html):
    """(caminho de títulos, tabela) na ordem do documento."""
    doc = lxml.html.fromstring(html)
    secao = {}
    for el in doc.iter("h2", "h3", "h4", "h5", "table"):
        if el.tag != "table":
            n = int(el.tag[1])
            secao[n] = _texto(el)
            for k in [k for k in secao if k > n]:
                del secao[k]
        elif "wikitable" in (el.get("class") or ""):
            yield [secao[k] for k in sorted(secao)], el


def _papel(rotulo):
    k = chave(rotulo)
    if not k:
        return "ignorar"
    if "data" in k or "periodo" in k:
        return "datas"
    if "amostra" in k or "entrevistad" in k:
        return "amostra"
    if "margem" in k:
        return "margem"
    if any(p in k for p in ("contratante", "instituto", "publicacao")) or k.startswith("pesquisa"):
        return "pesquisa"
    if "vantagem" in k or k.startswith("lead") or "agregador" in k or "atualizacao" in k:
        return "ignorar"
    if k.startswith("outro"):
        return "outros"
    if any(p in k for p in NAO_VALIDOS):
        return "nao_validos"
    return "candidato"


def _numero(s):
    """Percentual ou número de uma célula: "40,7%" -> 40.7; "—", "-" ou "N/A" -> None."""
    s = _sem_refs(s).replace(" ", "").replace("\xa0", " ")
    m = re.search(r"\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))  # em "<0,9%", o limite: ver _menor e ler_wikipedia


def _menor(s):
    """A célula traz um limite ("<1%", "<0,9%") em vez do percentual?"""
    return _sem_refs(s).strip().startswith("<")


def _amostra(s):
    s = re.sub(r"[\s. \xa0]", "", _sem_refs(s))
    m = re.match(r"\d+", s)
    return int(m.group(0)) if m else None


def _datas(s):
    """(dia1, mes1, ano1, dia2, mes2, ano2) com None onde faltar; "30 Set–01 Out", "28–29 Out 2022", "3 Out"."""
    s = sem_acento(_sem_refs(s)).lower()
    s = re.sub(r"\bde\b", " ", re.sub(r"[–—]", "-", s))
    m = re.fullmatch(r"\s*(\d{1,2})[ºo]?\s*([a-z]+)?\.?\s*(\d{4})?\s*(?:-\s*(\d{1,2})[ºo]?\s*([a-z]+)?\.?\s*(\d{4})?)?\s*", s)
    if not m:
        return None
    d1, m1, a1, d2, m2, a2 = m.groups()
    mes = lambda t: MESES.get(t[:3]) if t else None  # noqa: E731
    m1, m2 = mes(m1), mes(m2)
    if d2 is None:
        d2, m2, a2 = d1, m1, a1
    if not m2:
        return None
    if not m1:  # "31–1 Abr": sem o mês inicial, um dia inicial maior que o final é do mês anterior
        m1 = m2 if int(d1) <= int(d2) else (m2 - 2) % 12 + 1
    return int(d1), m1, int(a1) if a1 else None, int(d2), m2, int(a2) if a2 else None


def _pesquisa(s):
    """(contratante, instituto, registro) de "Globo / Datafolha [28] BR-09479/2022"."""
    r = REGISTRO.search(s)
    registro = f"{r[1]}{int(r[2]):05d}{r[3]}" if r else None  # formato do TSE: BR094792022
    nome = _sem_refs(REGISTRO.sub("", s)).strip(" /-")
    partes = [p.strip() for p in re.split(r"\s*/\s*", nome) if p.strip()]
    instituto = partes[-1] if partes else nome
    return " / ".join(partes[:-1]) or None, INSTITUTOS.get(chave(instituto), instituto), registro


def ler_wikipedia(ano, html=None):
    """Todas as linhas de pesquisa das tabelas de 1º e 2º turno da página do ano (sem agregadores nem boca de urna).
    Sem `html`, a revisão guardada em dados/bruto."""
    html = wikipedia.arquivo(ano).read_text("utf-8") if html is None else html
    alvos = {campo: chave(config.carregar()["eleicoes"][str(ano)][campo]["nas_pesquisas"]) for campo in ("petismo", "bolsonarismo")}
    linhas, ignoradas = [], 0
    contexto, ano_atual, mes_anterior = None, ano, None
    for n_tabela, (caminho, tabela) in enumerate(_tabelas(html)):
        topo = chave(caminho[0]) if caminho else ""
        turno = 1 if topo.startswith("primeiroturno") else 2 if topo.startswith("segundoturno") else None
        # agregadores e gráficos saem pelas colunas (não têm instituto nem datas de campo), não pelo título:
        # em 2022 a tabela principal do 2º turno fica logo abaixo do subtítulo "Agregação de pesquisas"
        if turno is None or "bocadeurna" in chave(" ".join(caminho)):
            continue
        g = _grade(tabela)
        n_cab = 0
        while n_cab < len(g) and g[n_cab] and all(c.tag == "th" for c in g[n_cab]):
            n_cab += 1
        if not n_cab:
            continue
        largura = max(len(l) for l in g[:n_cab])
        rotulos = []
        for j in range(largura):
            partes = []
            for l in g[:n_cab]:
                t = _sem_refs(_texto(l[j])) if j < len(l) else ""
                if t and t not in partes:
                    partes.append(t)
            rotulos.append(" ".join(partes))
        papeis = [_papel(r) for r in rotulos]
        if not {"pesquisa", "datas"} <= set(papeis):
            continue
        # o ano das datas sem ano: título de ano mais próximo; as tabelas vão do mais recente ao mais antigo
        anos_titulo = [int(t) for t in caminho if re.fullmatch(r"\d{4}", t)]
        novo_contexto = (turno, caminho[1] if len(caminho) > 1 and not anos_titulo else None, anos_titulo[-1] if anos_titulo else None)
        if novo_contexto != contexto:
            contexto, ano_atual, mes_anterior = novo_contexto, (anos_titulo[-1] if anos_titulo else ano), None
        for n_linha, l in enumerate(g[n_cab:]):
            celulas = {}
            for j, p in enumerate(papeis):
                if j < len(l):
                    celulas.setdefault(p, []).append((rotulos[j], _texto(l[j])))
            datas = _datas(celulas["datas"][0][1]) if "datas" in celulas else None
            if not datas or "pesquisa" not in celulas:
                ignoradas += 1
                continue
            d1, m1, a1, d2, m2, a2 = datas
            if a2:
                ano_atual = a2
            elif mes_anterior is not None and m2 - mes_anterior >= 3:  # voltou para o fim do ano anterior
                ano_atual -= 1
            mes_anterior = m2
            try:
                fim = dt.date(a2 or ano_atual, m2, d2)
                inicio = dt.date(a1 or (fim.year if m1 <= m2 else fim.year - 1), m1, d1)
            except ValueError:  # data impossível na tabela (ex.: 31 de abril)
                ignoradas += 1
                continue
            candidatos, limites = [], {}  # limites: posição do candidato -> x de "<x%"
            for rotulo, valor in celulas.get("candidato", []):
                v = _numero(valor)
                if v is None:
                    continue
                nome = (re.search(r"\(([^)]+)\)", valor) or [None, rotulo])[1].strip()
                if _menor(valor):
                    limites[len(candidatos)] = v
                candidatos.append([nome, v])
            if not candidatos:
                ignoradas += 1
                continue
            contratante, instituto, registro = _pesquisa(celulas["pesquisa"][0][1])
            num = lambda papel: _numero(celulas[papel][0][1]) if papel in celulas else None  # noqa: E731
            celulas_outros = [(_numero(x), _menor(x)) for _, x in celulas.get("outros", [])]
            celulas_outros = [(v, m) for v, m in celulas_outros if v is not None]
            nao_validos = [v for v in (_numero(x) for _, x in celulas.get("nao_validos", [])) if v is not None]
            # "<x%" vale metade de x, mas os limites juntos não passam do que falta para 100%: há tabelas já em
            # votos válidos (as da AtlasIntel, por exemplo), em que oito "<0,9%" somariam 3,6% a mais que o total
            # e diminuiriam a parte de todos os outros candidatos na conversão para votos válidos.
            definidos = (sum(v for i, (_, v) in enumerate(candidatos) if i not in limites)
                         + sum(v for v, m in celulas_outros if not m) + sum(nao_validos))
            n_limites = len(limites) + sum(m for _, m in celulas_outros)
            folga = max(0.0, 100 - definidos) / n_limites if n_limites else 0.0
            for i, x in limites.items():
                candidatos[i][1] = round(min(x / 2, folga), 3)
            outros = sum(round(min(v / 2, folga), 3) if m else v for v, m in celulas_outros)
            campos = {}
            for nome, v in candidatos:
                for campo, alvo in alvos.items():
                    if chave(nome).startswith(alvo):
                        campos[campo] = v
            linhas.append({
                "ano": ano, "turno": turno, "secao": " > ".join(caminho), "tabela": n_tabela, "linha": n_linha,
                "contratante": contratante, "instituto": instituto, "registro_wikipedia": registro,
                "inicio": inicio, "fim": fim,
                "amostra": _amostra(celulas["amostra"][0][1]) if "amostra" in celulas else None,
                "margem": num("margem"), "n_candidatos": len(candidatos),
                "soma_candidatos": round(sum(v for _, v in candidatos), 2), "outros": outros,
                "nao_validos": round(sum(nao_validos), 2) if nao_validos else None,
                "petismo": campos.get("petismo"), "bolsonarismo": campos.get("bolsonarismo"),
                "candidatos": "; ".join(f"{n} {v:g}" + (f" (<{limites[i]:g})" if i in limites else "")
                                        for i, (n, v) in enumerate(candidatos)),
            })
    return linhas, ignoradas


def ler_registro(ano):
    """Pesquisas para Presidente com abrangência nacional registradas no TSE."""
    arq = tse.pasta("pesquisas", ano) / f"pesquisa_eleitoral_{ano}.zip"
    vistas, out = set(), []
    with zipfile.ZipFile(arq) as z:
        for membro in z.namelist():
            if not membro.lower().endswith(".csv"):
                continue
            with z.open(membro) as f:
                for r in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";"):
                    cargos = r.get("DS_CARGO") or r.get("DS_CARGOS") or ""  # 2018: DS_CARGOS e QT_ENTREVISTADOS
                    if r.get("SG_UF") != "BR" or "presidente" not in cargos.lower():
                        continue
                    protocolo = chave(r["NR_PROTOCOLO_REGISTRO"]).upper()
                    if protocolo in vistas:
                        continue
                    vistas.add(protocolo)
                    data = lambda c: _data_tse(r.get(c))  # noqa: E731
                    out.append({"protocolo": protocolo, "empresa": r.get("NM_EMPRESA"), "fantasia": r.get("NM_EMPRESA_FANTASIA"),
                                "cnpj": r.get("NR_CNPJ_EMPRESA"), "inicio": data("DT_INICIO_PESQUISA"),
                                "fim": data("DT_FIM_PESQUISA"), "divulgacao": data("DT_DIVULGACAO"),
                                "amostra": int(q) if (q := r.get("QT_ENTREVISTADO") or r.get("QT_ENTREVISTADOS") or "").isdigit() else None,
                                "metodologia": r.get("DS_METODOLOGIA_PESQUISA")})
    return out


def _data_tse(s):
    if not s:
        return None
    for formato in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(s.strip(), formato).date()
        except ValueError:
            pass
    return None


def _mesmo_instituto(parte, r):
    """A parte do nome na Wikipedia (instituto ou contratante) é a empresa registrada?"""
    nome = INSTITUTOS.get(chave(parte), parte)
    empresa = chave(r["empresa"]) + chave(r["fantasia"])
    fantasia = chave(r["fantasia"]) if chave(r["fantasia"]) != "nulo" else ""
    return any(t and t in empresa for t in NO_REGISTRO.get(nome, [chave(nome)])) or (len(fantasia) >= 3 and fantasia in chave(parte))


def ligar(p, por_protocolo, registros):
    """(protocolo, parte do nome que é o instituto registrado, como).

    Pelo número de registro citado na Wikipedia; sem ele (ou se não existir no TSE), pela mesma empresa com
    amostra a até 3% da registrada e fim de campo a até 3 dias: o registro traz o planejado, a Wikipedia o feito.
    Amostra e datas sozinhas não bastam: amostras de 2.000 entrevistas são comuns a muitos institutos.
    """
    partes = [x for x in (p["contratante"] or "").split(" / ") if x] + [p["instituto"]]
    if p["registro_wikipedia"] and p["registro_wikipedia"] in por_protocolo:
        r = por_protocolo[p["registro_wikipedia"]]
        return r["protocolo"], next((x for x in reversed(partes) if _mesmo_instituto(x, r)), p["instituto"]), "número"
    if not p["amostra"]:
        return None, p["instituto"], "não encontrada"
    achados = []
    for r in registros:
        if not (r["fim"] and r["amostra"] and abs((r["fim"] - p["fim"]).days) <= 3
                and abs(r["amostra"] - p["amostra"]) <= max(0.03 * p["amostra"], 10)):
            continue
        parte = next((x for x in reversed(partes) if _mesmo_instituto(x, r)), None)
        if parte:
            achados.append(((abs(r["amostra"] - p["amostra"]), abs((r["fim"] - p["fim"]).days)), r, parte))
    if not achados:
        return None, p["instituto"], "não encontrada"
    achados.sort(key=lambda a: a[0])
    # registros idênticos (mesma empresa, amostra e datas) são a mesma pesquisa registrada mais de uma vez
    iguais = sum(a[0] == achados[0][0] for a in achados)
    como = "instituto, amostra e datas" + (f" ({iguais} registros iguais)" if iguais > 1 else "")
    return achados[0][1]["protocolo"], achados[0][2], como


def saida(nome, ano):
    return config.PROCESSADO / "pesquisas" / f"{nome}_{ano}.parquet"


def completa(l):
    """A linha permite calcular votos válidos? No 1º turno precisa trazer os demais candidatos (ou "outros"):
    a Wikipedia às vezes lista só os dois primeiros. Soma acima de 103% indica coluna lida errado."""
    if l["soma_candidatos"] + l["outros"] + (l["nao_validos"] or 0) > 103:
        return False
    return l["turno"] == 2 or l["n_candidatos"] >= 3 or l["outros"] > 0


_TIPOS = {int: "BIGINT", float: "DOUBLE", str: "VARCHAR", dt.date: "DATE", bool: "BOOLEAN"}


def _gravar(con, dados, destino):
    """Lista de dicionários -> Parquet, com o tipo de cada coluna tirado do primeiro valor não vazio."""
    colunas = list(dados[0])
    tipos = [_TIPOS.get(type(next((d[c] for d in dados if d[c] is not None), "")), "VARCHAR") for c in colunas]
    con.execute("CREATE OR REPLACE TABLE t (" + ", ".join(f'"{c}" {t}' for c, t in zip(colunas, tipos)) + ")")
    con.executemany(f"INSERT INTO t VALUES ({', '.join('?' * len(colunas))})", [[d[c] for c in colunas] for d in dados])
    destino.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY t TO '{destino.as_posix()}' (FORMAT parquet)")


def montar(ano, html=None):
    """(linhas lidas, pesquisas, contagens) da página da Wikipedia (sem `html`, a revisão guardada) e do registro
    do TSE, sem gravar nada."""
    linhas, ignoradas = ler_wikipedia(ano, html)
    registros = ler_registro(ano)
    por_protocolo = {r["protocolo"]: r for r in registros}
    datas = {t: dt.date.fromisoformat(config.turno(ano, t)["data"]) for t in (1, 2)}
    inicio_ano = dt.date(ano, 1, 1)

    # uma pesquisa = mesmo turno e registro (ou mesmo instituto, datas e amostra); fica o cenário mais completo
    grupos, incompletas = {}, 0
    for l in linhas:
        if l["petismo"] is None or l["bolsonarismo"] is None:
            continue
        if not (inicio_ano <= l["fim"] < datas[l["turno"]]):
            continue
        if not completa(l):
            incompletas += 1
            continue
        k = (l["turno"], l["registro_wikipedia"] or (chave(l["instituto"]), l["inicio"], l["fim"], l["amostra"]))
        if k not in grupos or l["n_candidatos"] > grupos[k]["n_candidatos"]:
            grupos[k] = l
    pesquisas = []
    for l in grupos.values():
        validos = l["soma_candidatos"] + (l["outros"] if l["turno"] == 1 else 0)
        if l["turno"] == 2:
            validos = l["petismo"] + l["bolsonarismo"]
        protocolo, instituto, como = ligar(l, por_protocolo, registros)
        reg = por_protocolo.get(protocolo, {})
        partes = [x for x in (l["contratante"] or "").split(" / ") + [l["instituto"]] if x and x != instituto]
        pesquisas.append({**{k: l[k] for k in ("ano", "turno", "inicio", "fim", "amostra", "margem", "petismo",
                                               "bolsonarismo", "nao_validos", "secao", "tabela", "linha")},
                          "instituto": INSTITUTOS.get(chave(instituto), instituto),
                          "contratante": " / ".join(partes) or None,
                          "petismo_validos": round(100 * l["petismo"] / validos, 2),
                          "bolsonarismo_validos": round(100 * l["bolsonarismo"] / validos, 2),
                          "registro": protocolo, "ligacao": como,
                          "registro_wikipedia": l["registro_wikipedia"], "empresa_tse": reg.get("empresa"),
                          "amostra_tse": reg.get("amostra"), "metodologia": reg.get("metodologia")})
    pesquisas.sort(key=lambda p: (p["turno"], p["fim"], p["instituto"]))
    return linhas, pesquisas, {"ignoradas": ignoradas, "incompletas": incompletas, "registros": len(registros)}


def processar(ano, log=print):
    linhas, pesquisas, n = montar(ano)
    con = conexao()
    for nome, dados in (("linhas", linhas), ("pesquisas", pesquisas)):
        if dados:
            _gravar(con, dados, saida(nome, ano))
    rev = wikipedia.revisao(ano)
    for t in (1, 2):
        ps = [p for p in pesquisas if p["turno"] == t]
        if ps:
            numero = sum(p["ligacao"] == "número" for p in ps)
            atributos = sum(p["ligacao"].startswith("instituto") for p in ps)
            log(f"   {t}º turno: {len(ps)} pesquisas em {ano} · ligadas ao registro do TSE pelo número {numero}, "
                f"por instituto, amostra e datas {atributos}, sem registro encontrado {len(ps) - numero - atributos}")
    log(f"   ({len(linhas)} linhas lidas da revisão {rev['revid']}, {n['ignoradas']} ignoradas, {n['incompletas']} "
        f"cenários incompletos descartados; {n['registros']} registros nacionais no TSE)")
    return pesquisas


def relatorio(anos):
    """docs/qualidade_pesquisas.md: cobertura da ligação com o registro do TSE e as pesquisas sem registro."""
    import duckdb
    linhas = ["# Qualidade das pesquisas", "",
              f"> Gerado por `uv run eleicoes pesquisas` (ou `atualizar`) em {dt.datetime.now():%d/%m/%Y %H:%M}. Não editar à mão.", "",
              "| Ano | Turno | Pesquisas | Pelo número de registro | Por instituto, amostra e datas | Sem registro encontrado | Amostra ≠ registro (> 3%) | Revisão da Wikipedia |",
              "|---|---|--:|--:|--:|--:|--:|---|"]
    sem = []
    for ano in anos:
        arq = saida("pesquisas", ano)
        if not arq.exists():
            continue
        rev = wikipedia.revisao(ano)
        for turno, n, numero, atributos, nenhum, diferente in duckdb.sql(f"""
                SELECT turno, count(*), count(*) FILTER (ligacao = 'número'),
                       count(*) FILTER (ligacao LIKE 'instituto%'), count(*) FILTER (registro IS NULL),
                       count(*) FILTER (amostra_tse IS NOT NULL AND abs(amostra - amostra_tse) > 0.03 * amostra)
                FROM '{arq.as_posix()}' GROUP BY 1 ORDER BY 1""").fetchall():
            linhas.append(f"| {ano} | {turno}º | {n} | {numero} | {atributos} | {nenhum} | {diferente} | [{rev['revid']}]({rev['url']}) |")
        sem += [(ano, *r) for r in duckdb.sql(f"""SELECT turno, instituto, inicio, fim, amostra FROM '{arq.as_posix()}'
                                                  WHERE registro IS NULL ORDER BY turno, fim""").fetchall()]
    linhas += ["", "## Pesquisas sem registro encontrado", "",
               "Não aparecem no registro nacional do TSE com a mesma empresa, amostra (± 3%) e fim do campo (± 3 dias). "
               "Ficam no estudo, marcadas como \"sem registro\".", "",
               "| Ano | Turno | Instituto | Campo | Amostra |", "|---|---|---|---|--:|"]
    linhas += [f"| {a} | {t}º | {i} | {ini:%d/%m} a {fim:%d/%m} | {amostra or '–'} |" for a, t, i, ini, fim, amostra in sem]
    (config.RAIZ / "docs" / "qualidade_pesquisas.md").write_text("\n".join(linhas) + "\n", "utf-8")
