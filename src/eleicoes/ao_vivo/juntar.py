"""Junta o que os coletores da nuvem gravaram (coletor.py, nos ramos ao-vivo-a, -b e -c) em
dados/bruto/ao_vivo/<ciclo>-<eleicao>: `uv run eleicoes juntar <pasta de cada ramo>`.

Uma leitura vista por mais de um coletor entra uma vez; de cada seção fica a primeira vez que algum coletor a viu.
  leituras_oficiais.json   cada atualização do total do país, no formato do 1º turno (noite.py lê h, pst e cand), com
                           os totais do arquivo (seções, comparecimento, abstenção, brancos, nulos)
  leituras_ufs.json        idem, de cada UF e do exterior: {"ac": [...], ..., "zz": [...]}
  municipios.jsonl.gz      cada atualização do resultado de cada município
  secoes.csv.gz            uf,municipio,zona,secao,recebido,visto: o horário de chegada de cada seção como o TSE
                           mostrava na primeira vez que um coletor a viu (o TSE reescreve esses horários depois)
  final/                   os arquivos de resultado do país e de cada UF no fim, como vieram do TSE
  historico_estimado.*     a apuração minuto a minuto, pelos horários gravados e a média por seção do município
  coleta.json              os jobs de cada coletor (rodadas, falhas) e o que foi juntado
Só junta depois de a coleta acabar (ou com --forcar) e não refaz uma gravação já juntada sem --forcar.
"""
import collections
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import pathlib

from eleicoes.ao_vivo import coletor as C
from eleicoes.ao_vivo import historico as H
from eleicoes.coleta import rede

NAO_ACABOU = 3  # código de saída: a apuração ainda não acabou (a próxima rodada do workflow retoma a coleta)
RECUSADO = 1


def primeiros(registros, chave):
    """Um registro por chave: o que algum coletor viu primeiro."""
    out = {}
    for r in registros:
        k = chave(r)
        if k not in out or r["visto"] < out[k]["visto"]:
            out[k] = r
    return out


def secoes(pastas):
    """{(uf, municipio, zona, secao): (uf, municipio, zona, secao, recebido, visto)}, da primeira vez que foi vista."""
    out = {}
    for s in C.registros(pastas, "secoes"):
        k = s[:4]
        if k not in out or s[5] < out[k][5]:
            out[k] = s
    return out


def _json(arq, dados, **opcoes):
    arq.write_text(json.dumps(dados, ensure_ascii=False, **opcoes), "utf-8")


def _gzip(arq, linhas):
    """Gzip sem data no cabeçalho: juntar de novo os mesmos registros dá o mesmo arquivo."""
    with open(arq, "wb") as f, gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as gz:
        gz.write("".join(linhas).encode("utf-8"))


def _finais(destino, log):
    """Os arquivos de resultado do país e das UFs agora, como vêm do TSE, em destino/final; devolve o do país."""
    pasta = destino / "final"
    pasta.mkdir(exist_ok=True)
    br = None
    for abr in ["br", *H.UFS]:
        try:
            texto = rede.texto(H.url_resultado(abr))
        except OSError as e:
            log(f"   final/{abr}.json não saiu: {e}")
            continue
        (pasta / f"{abr}.json").write_text(texto, "utf-8")
        if abr == "br":
            br = json.loads(texto)
    return br


def _historico(destino, br, vistas, municipios):
    """historico_estimado.csv e .png: cada seção no minuto em que chegou (como gravado durante a apuração), com a
    média por seção do município no último resultado gravado."""
    with cf.ThreadPoolExecutor(H.PARALELO) as ex:  # só o total de seções de cada município: os horários já mudaram
        totais = dict(zip(H.UFS, ex.map(H.secoes_da_uf, H.UFS)))
    contagem = {uf: {mu: [t, collections.Counter()] for mu, (t, _) in m.items()} for uf, m in totais.items()}
    for uf, mu, _, _, recebido, _ in vistas.values():
        item = contagem.get(uf, {}).get(mu)
        if item:
            item[1][dt.datetime.strptime(recebido[:16], "%d/%m/%Y %H:%M")] += 1
    ultimos = {(r["uf"], r["mu"]): C.resumo_do_registro(r) for r in municipios}  # em ordem de horário: fica o último
    s = H.reconstruir({"secoes": contagem, "mun": ultimos, "br": br})
    H.gravar_csv(s, destino / "historico_estimado.csv")
    H.plotar(s, H.horario_oficial(br), destino / "historico_estimado.png")


def juntar(pastas, destino=None, forcar=False, ensaio=False, log=print):
    """Devolve 0 (juntado), NAO_ACABOU ou RECUSADO (já havia uma gravação juntada no destino)."""
    pastas = [pathlib.Path(p) for p in pastas if pathlib.Path(p).is_dir()]
    destino = pathlib.Path(destino) if destino else H.AV.bruto
    agora = dt.datetime.now()
    br = sorted(primeiros(C.registros(pastas, "leituras_br"), lambda l: l["h"]).values(), key=lambda l: l["h"])
    if not (forcar or ensaio or C.acabou(br, agora)):
        fechou = C.fim_da_apuracao(br)
        log("A coleta ainda não acabou: " + (f"o TSE fechou a totalização às {fechou:%H:%M} e a coleta segue até 1 h "
                                            "depois." if fechou else "o TSE ainda não fechou a totalização."))
        return NAO_ACABOU
    if (destino / "leituras_oficiais.json").exists() and not forcar:
        log(f"{destino} já tem uma gravação juntada; para refazer, --forcar.")
        return RECUSADO
    destino.mkdir(parents=True, exist_ok=True)
    log(f"Juntando {len(pastas)} ramos em {destino}")

    ufs = collections.defaultdict(list)
    for l in sorted(primeiros(C.registros(pastas, "leituras_uf"), lambda l: (l["abr"], l["h"])).values(),
                    key=lambda l: (l["abr"], l["h"])):
        ufs[l["abr"]].append(l)
    municipios = sorted(primeiros(C.registros(pastas, "municipios"), lambda r: (r["uf"], r["mu"], r["h"])).values(),
                        key=lambda r: (r["h"], r["uf"], r["mu"]))
    vistas = secoes(pastas)

    _json(destino / "leituras_oficiais.json", br)
    _json(destino / "leituras_ufs.json", dict(sorted(ufs.items())))
    _gzip(destino / "municipios.jsonl.gz",
          (json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in municipios))
    _gzip(destino / "secoes.csv.gz",
          ["uf,municipio,zona,secao,recebido,visto\n", *(",".join(s) + "\n" for _, s in sorted(vistas.items()))])
    log(f"   {len(br)} leituras do país, {sum(map(len, ufs.values()))} das UFs, {len(municipios):,} de municípios e "
        f"{len(vistas):,} seções".replace(",", "."))

    final = _finais(destino, log)
    if final and C.leitura(final, agora):
        try:
            _historico(destino, final, vistas, municipios)
        except Exception as e:  # derivado: não segura o resto
            log(f"   historico_estimado não saiu: {e!r}")

    jobs = [json.loads(j.read_text("utf-8")) for p in pastas for j in sorted(p.glob("*/job.json"))]
    _json(destino / "coleta.json", {
        "eleicao": H.AV.eleicao, "pleito": H.AV.pleito, "juntado_em": C.iso(agora), "ensaio": ensaio,
        "primeira_leitura": br[0]["h"] if br else None, "ultima_leitura": br[-1]["h"] if br else None,
        "fim_da_totalizacao": C.iso(f) if (f := C.fim_da_apuracao(br)) else None,
        "leituras_br": len(br), "leituras_uf": sum(map(len, ufs.values())), "municipios": len(municipios),
        "secoes": len(vistas), "jobs": jobs}, indent=1)
    log("Pronto.")
    return 0
