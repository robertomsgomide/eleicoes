"""Reconstrói o histórico da apuração para Presidente, durante a própria apuração,
a partir dos arquivos públicos de resultados.tse.jus.br e gera gráfico + CSV.

Feito na noite do 1º turno de 2026, quando o TSE ainda não tinha publicado os
boletins de urna. Ele só publica o retrato atual dos totais, mas publica, para
cada seção, a data e a hora em que o boletim de urna dela foi recebido (arquivo
de configuração das seções, "-cs.json", um por UF). Com isso:

  * boletins recebidos ao longo do tempo  -> valor EXATO (horário de cada seção);
  * votos ao longo do tempo               -> ESTIMATIVA: cada seção recebe a média
    por seção do seu município (o TSE não divulga resultado abaixo do município
    no arquivo de resultados).

Uso:  uv run eleicoes historico     (pode rodar de novo durante a apuração;
                                     só baixa de novo o que mudou)
A eleição acompanhada vem de [ao_vivo] em config/eleicoes.toml. Saídas em
dados/processado/ao_vivo/<ciclo>-<eleicao>/historico_estimado.{csv,png}.
O painel ao vivo (servidor.py) importa este módulo.
"""
import collections
import concurrent.futures as cf
import csv
import datetime as dt
import gzip
import json
import time
import urllib.error
import urllib.request

from eleicoes import config
from eleicoes.formato_tse import candidatos, nomes, num

AV = config.ao_vivo()
CICLO, PLEITO, ELEICAO, CARGO = AV.ciclo, AV.pleito, AV.eleicao, AV.cargo
INICIO_DIVULGACAO = AV.inicio  # horário de Brasília
BASE = "https://resultados.tse.jus.br/oficial"
URL_BR = f"{BASE}/{CICLO}/{ELEICAO}/dados/br/br-c{CARGO}-e{ELEICAO.zfill(6)}-u.json"
CACHE = AV.cache
SAIDA_CSV = AV.processado / "historico_estimado.csv"
SAIDA_PNG = AV.processado / "historico_estimado.png"
PARALELO = 8

REGIOES = {r: [uf.lower() for uf in ufs] for r, ufs in config.REGIOES.items()}  # o site do TSE usa minúsculas
REGIAO_DA_UF = {uf: r for r, ufs in REGIOES.items() for uf in ufs}
UFS = list(REGIAO_DA_UF)


# ---- Rede -----------------------------------------------------------------
def baixar(url, etag=None, tentativas=4):
    """(json, etag). Com etag, devolve (None, etag) se o arquivo não mudou."""
    cab = {"User-Agent": "historico-apuracao-local/1.0", "Accept-Encoding": "gzip"}
    if etag:
        cab["If-None-Match"] = etag
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=30) as r:
                corpo = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    corpo = gzip.decompress(corpo)
                return json.loads(corpo.decode("utf-8")), r.headers.get("ETag")
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return None, etag
            if e.code == 404:  # o TSE bloqueia IPs que acumulam 404: não insiste
                raise
            erro = e
        except Exception as e:  # timeout, conexão caiu etc.
            erro = e
        time.sleep(2 * (i + 1))
    raise erro


# ---- Leitura dos arquivos do TSE -------------------------------------------
_cs = {}       # uf -> (etag, seções já processadas)
_horas = {}    # "dd/mm/aaaa hh:mm" -> datetime (evita milhares de strptime iguais)


def secoes_da_uf(uf):
    """{municipio: [total de seções, Counter(minuto -> boletins recebidos)]}.

    Seções agregadas (campo "nsp") ficam de fora: votam na urna da seção
    principal e não têm boletim próprio, como no total "ts" do TSE.
    """
    url = f"{BASE}/{CICLO}/arquivo-urna/{PLEITO}/config/{uf}/{uf}-p{PLEITO.zfill(6)}-cs.json"
    etag, antigo = _cs.get(uf, (None, None))
    d, etag = baixar(url, etag if antigo else None)
    if d is None:
        return antigo
    out = {}
    for abr in d["abr"]:
        for mu in abr["mu"]:
            item = out.setdefault(mu["cd"], [0, collections.Counter()])
            for zona in mu["zon"]:
                for s in zona["sec"]:
                    if "nsp" in s:
                        continue
                    item[0] += 1
                    if s.get("da") and s.get("ha"):
                        chave = f'{s["da"]} {s["ha"][:5]}'
                        h = _horas.get(chave)
                        if h is None:
                            h = _horas[chave] = dt.datetime.strptime(chave, "%d/%m/%Y %H:%M")
                        item[1][h] += 1
    _cs[uf] = (etag, out)
    return out


def resumo_resultado(d):
    s = d.get("s", {})
    return {"st": int(num(s.get("st"))), "ts": int(num(s.get("ts"))), "and": d.get("and", ""),
            "vv": num(d.get("v", {}).get("vv")), "cand": candidatos(d)}


# ---- Coleta -----------------------------------------------------------------
_mun = None  # (uf, municipio) -> resumo do resultado municipal (espelho de cache_tse/mun)
_lido = {}   # (uf, municipio) -> momento da última leitura nesta execução


def _resultado_municipio(uf, mu):
    antigo = _mun.get((uf, mu))
    d, etag = baixar(f"{BASE}/{CICLO}/{ELEICAO}/dados/{uf}/{uf}{mu}-c{CARGO}-e{ELEICAO.zfill(6)}-u.json",
                     antigo and antigo.get("etag"))
    _lido[(uf, mu)] = time.time()
    if d is None:  # o TSE ainda não publicou versão nova deste município
        return antigo
    r = resumo_resultado(d)
    r["etag"] = etag
    (CACHE / "mun" / f"{uf}{mu}.json").write_text(json.dumps(r), "utf-8")
    return r


def coletar(limite=None, folga=0.0, revisita=0, log=print):
    """Baixa horários das seções, resultados municipais que ficaram para trás e o arquivo nacional.

    limite:   máximo de municípios baixados nesta rodada (None = todos os pendentes).
    folga:    só baixa de novo um município se ele recebeu pelo menos essa fração
              a mais de seções desde a última leitura (0 = qualquer seção nova).
    revisita: segundos mínimos entre duas leituras do mesmo município (o TSE
              publica os resultados em rajadas, bem depois de os boletins chegarem).
    """
    global _mun
    (CACHE / "mun").mkdir(parents=True, exist_ok=True)
    if _mun is None:
        _mun = {(a.stem[:2], a.stem[2:]): json.loads(a.read_text("utf-8"))
                for a in (CACHE / "mun").glob("*.json")}

    with cf.ThreadPoolExecutor(PARALELO) as ex:
        secoes = dict(zip(UFS, ex.map(secoes_da_uf, UFS)))

    pendentes, atrasados, agora = [], 0, time.time()
    for uf, municipios in secoes.items():
        for mu, (total, chegadas) in municipios.items():
            recebidas = sum(chegadas.values())
            if not recebidas:
                continue
            r = _mun.get((uf, mu))
            if r is None:
                pendentes.append((float("inf"), uf, mu))
            elif r["and"] != "f" and recebidas > r["st"]:
                atrasados += 1
                falta = recebidas - r["st"]
                if (falta >= folga * r["st"] or recebidas == total) and agora - _lido.get((uf, mu), 0) >= revisita:
                    pendentes.append((falta / max(r["st"], 1), uf, mu))
    pendentes.sort(reverse=True)
    lote = pendentes[:limite] if limite else pendentes

    falhas = 0
    if lote:
        log(f"     baixando {len(lote)} resultados municipais…")
    with cf.ThreadPoolExecutor(PARALELO) as ex:
        futs = {ex.submit(_resultado_municipio, uf, mu): (uf, mu) for _, uf, mu in lote}
        for f in cf.as_completed(futs):
            try:
                _mun[futs[f]] = f.result()
            except Exception:
                falhas += 1

    br, _ = baixar(URL_BR)
    return {"secoes": secoes, "mun": _mun, "br": br, "baixados": len(lote) - falhas,
            "falhas": falhas, "atrasados": atrasados}


# ---- Reconstrução -----------------------------------------------------------
def reconstruir(c, max_cand=None):
    """Série minuto a minuto desde o início da divulgação (boletins anteriores entram no 1º ponto)."""
    secoes, mun, br = c["secoes"], c["mun"], c["br"]
    oficial = resumo_resultado(br)
    nome = nomes(br)
    numeros = sorted(oficial["cand"], key=lambda n: -oficial["cand"][n])[:max_cand]

    media = {k: ({n: v / r["st"] for n, v in r["cand"].items()}, r["vv"] / r["st"])
             for k, r in mun.items() if r["st"]}
    eventos = collections.defaultdict(list)
    tot_reg = dict.fromkeys(REGIOES, 0)
    ufs = []
    for uf, municipios in secoes.items():
        rec_uf = tot_uf = 0
        for mu, (total, chegadas) in municipios.items():
            tot_uf += total
            for minuto, q in chegadas.items():
                eventos[max(minuto, INICIO_DIVULGACAO)].append((uf, mu, q))
                rec_uf += q
        tot_reg[REGIAO_DA_UF[uf]] += tot_uf
        ufs.append({"uf": uf.upper(), "reg": REGIAO_DA_UF[uf], "rec": rec_uf, "tot": tot_uf})
    total = sum(tot_reg.values())

    acum_reg = dict.fromkeys(REGIOES, 0)
    acum_votos = dict.fromkeys(numeros, 0.0)
    acum_vv = 0.0
    serie = {"t": [], "recebidas": [], "secoes": {r: [] for r in ["Brasil", *REGIOES]},
             "cand": [{"n": n, "nome": nome.get(n, n), "pct": [], "votos": []} for n in numeros]}
    minuto, fim = INICIO_DIVULGACAO, max(eventos, default=INICIO_DIVULGACAO)
    while minuto <= fim:
        for uf, mu, q in eventos.get(minuto, ()):
            acum_reg[REGIAO_DA_UF[uf]] += q
            m = media.get((uf, mu))
            if m:
                for n in numeros:
                    acum_votos[n] += q * m[0].get(n, 0.0)
                acum_vv += q * m[1]
        rec = sum(acum_reg.values())
        serie["t"].append(minuto)
        serie["recebidas"].append(rec)
        serie["secoes"]["Brasil"].append(round(100 * rec / total, 3) if total else 0)
        for r in REGIOES:
            serie["secoes"][r].append(round(100 * acum_reg[r] / tot_reg[r], 3) if tot_reg[r] else 0)
        # com menos de 1% das seções a estimativa oscila demais para significar algo
        firme = total and rec / total >= 0.01 and acum_vv
        for cand in serie["cand"]:
            v = acum_votos[cand["n"]]
            cand["votos"].append(round(v))
            cand["pct"].append(round(100 * v / acum_vv, 3) if firme else None)
        minuto += dt.timedelta(minutes=1)

    serie["ufs"] = ufs
    serie["total_secoes"] = total
    serie["oficial"] = {
        "dt": br.get("dt"), "ht": br.get("ht"), "and": br.get("and", ""), "dv": br.get("dv", ""),
        "pst": num(br.get("s", {}).get("pstn") or br.get("s", {}).get("pst")),
        "st": oficial["st"], "ts": oficial["ts"], "vv": oficial["vv"],
        "cand": [{"n": n, "nome": nome.get(n, n), "v": oficial["cand"][n],
                  "p": round(100 * oficial["cand"][n] / oficial["vv"], 3) if oficial["vv"] else None}
                 for n in numeros],
    }
    return serie


def horario_oficial(br):
    return dt.datetime.strptime(f"{br['dt']} {br['ht']}", "%d/%m/%Y %H:%M:%S")


# ---- Linha de comando: CSV + PNG ---------------------------------------------
def main():
    print("1/3  Horários das seções e resultados municipais (27 UFs + exterior)…")
    c = coletar()
    print("2/3  Reconstruindo a série minuto a minuto…")
    s = reconstruir(c)
    print(f"     {s['total_secoes']:,} seções, {s['recebidas'][-1]:,} com boletim recebido "
          f"(arquivo nacional do TSE: {s['oficial']['ts']:,} seções)".replace(",", "."))

    SAIDA_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(SAIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["horario", "boletins_recebidos", *[f"pct_recebidos_{r}" for r in s["secoes"]],
                    *[x for cand in s["cand"] for x in (f"votos_estimados_{cand['n']}_{cand['nome']}",
                                                         f"pct_validos_estimado_{cand['n']}_{cand['nome']}")]])
        br_num = lambda v: "" if v is None else f"{v:.3f}".replace(".", ",")
        for i, t in enumerate(s["t"]):
            w.writerow([t.strftime("%d/%m/%Y %H:%M"), s["recebidas"][i],
                        *[br_num(s["secoes"][r][i]) for r in s["secoes"]],
                        *[x for cand in s["cand"] for x in (cand["votos"][i], br_num(cand["pct"][i]))]])

    # conferência: a reconstrução no horário do arquivo nacional contra o total oficial dele
    of = s["oficial"]
    h_of = horario_oficial(c["br"])
    i = max(0, min(len(s["t"]) - 1, int((h_of - INICIO_DIVULGACAO).total_seconds() // 60)))
    print(f"3/3  Conferência com o arquivo nacional do TSE de {of['dt']} {of['ht']} "
          f"({of['pst']:.2f}% das seções totalizadas):")
    for cand, o in list(zip(s["cand"], of["cand"]))[:4]:
        print(f"     {cand['nome']:<22} reconstruído {cand['pct'][i] or 0:6.2f}%   oficial {o['p'] or 0:6.2f}%")

    plotar(s, h_of)
    print(f"\nPronto: {SAIDA_PNG.relative_to(config.RAIZ)} e {SAIDA_CSV.relative_to(config.RAIZ)}")


def plotar(s, h_of):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    INK, INK2, INK3, GRID, SURF = "#1b1d21", "#545962", "#868b93", "#eeebe6", "#fcfcfb"
    COR_CAND = {"13": "#d0343f", "22": "#2b67b8"}  # cores da identidade de cada candidato
    COR_REG = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # ordem categórica fixa
    nan = float("nan")

    plt.rcParams.update({"font.family": "Segoe UI", "font.size": 10, "text.color": INK,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 9), sharex=True, facecolor=SURF,
                                 gridspec_kw={"height_ratios": [1.15, 1], "hspace": 0.28})
    x = s["t"]
    for ax in (a1, a2):
        ax.set_facecolor(SURF)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for lado in ("top", "right", "left"):
            ax.spines[lado].set_visible(False)
        ax.spines["bottom"].set_color("#e3e0da")
        ax.tick_params(length=0)

    # Painel 1: % dos votos válidos (estimado) dos dois primeiros colocados
    rotulos = []
    for cand, o in list(zip(s["cand"], s["oficial"]["cand"]))[:2]:
        cor = COR_CAND.get(cand["n"], INK2)
        y = [nan if v is None else v for v in cand["pct"]]
        a1.plot(x, y, color=cor, lw=2, label=cand["nome"])
        rotulos.append((y[-1], f"{cand['nome']}  {y[-1]:.2f}%".replace(".", ","), cor))
        a1.plot([h_of], [o["p"]], marker="o", ms=8, mfc=cor, mec=SURF, mew=2, zorder=5)
    rotulos.sort()
    if len(rotulos) == 2 and rotulos[1][0] - rotulos[0][0] < 1.2:
        rotulos[0] = (rotulos[1][0] - 1.2,) + rotulos[0][1:]
    for y, txt, _ in rotulos:
        a1.annotate(txt, (x[-1], y), xytext=(10, 0), textcoords="offset points", va="center",
                    fontsize=10, color=INK, fontweight="semibold", annotation_clip=False)
    a1.axhline(50, color=INK3, lw=0.8, ls=(0, (4, 3)))
    a1.set_ylabel("% dos votos válidos (estimado)")
    a1.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    a1.set_title(f"Votos válidos ao longo da apuração — Presidente, {AV.turno}º turno {AV.ano}",
                 loc="left", fontsize=13, fontweight="semibold", pad=26)
    a1.text(0, 1.02, "Linha: reconstrução pelo horário de cada seção e a média por seção do município. "
            f"Ponto: total oficial do arquivo nacional do TSE ({h_of:%H:%M}).",
            transform=a1.transAxes, fontsize=9, color=INK2)
    a1.legend(loc="upper left", frameon=False, ncol=2)

    # Painel 2: % de seções com boletim recebido, Brasil e regiões (exato)
    fins = []
    for cor, r in zip(COR_REG, [r for r in REGIOES if r != "Exterior"]):
        y = s["secoes"][r]
        a2.plot(x, y, color=cor, lw=2, label=r)
        fins.append([y[-1], f"{r}  {y[-1]:.0f}%"])
    y = s["secoes"]["Brasil"]
    a2.plot(x, y, color=INK, lw=2.6, label="Brasil")
    fins.append([y[-1], f"Brasil  {y[-1]:.0f}%"])
    fins.sort()
    for i in range(1, len(fins)):  # afasta rótulos que se encostam
        fins[i][0] = max(fins[i][0], fins[i - 1][0] + 4.5)
    for yv, txt in fins:
        a2.annotate(txt, (x[-1], yv), xytext=(10, 0), textcoords="offset points", va="center",
                    fontsize=9.5, color=INK, annotation_clip=False)
    a2.set_ylim(0, 100)
    a2.set_ylabel("% das seções com boletim recebido")
    a2.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    a2.set_title("Boletins de urna recebidos por região (horário exato informado pelo TSE)",
                 loc="left", fontsize=13, fontweight="semibold", pad=10)
    a2.legend(loc="upper left", frameon=False, ncol=3)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    a2.set_xlabel("Horário de Brasília")

    fig.text(0.01, 0.005, f"Fonte: resultados.tse.jus.br · eleição {ELEICAO} · arquivo nacional de "
             f"{h_of:%d/%m/%Y %H:%M:%S} · {s['total_secoes']:,} seções".replace(",", "."),
             fontsize=8, color=INK3)
    fig.subplots_adjust(left=0.08, right=0.82, top=0.93, bottom=0.08)
    fig.savefig(SAIDA_PNG, dpi=150, facecolor=SURF)
