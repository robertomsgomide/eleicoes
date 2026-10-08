"""Leitura do formato JSON do site de resultados do TSE (resultados.tse.jus.br, arquivos "-u.json")."""


def num(x):
    """Números do TSE vêm como texto: inteiros "123456"; percentuais "45,67" ou "45.670000000"."""
    if x in (None, ""):
        return 0.0
    s = str(x)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def _percorrer(o, f):
    if isinstance(o, list):
        for x in o:
            _percorrer(x, f)
    elif isinstance(o, dict):
        if "vap" in o and "n" in o and ("nmu" in o or "nm" in o):
            f(o)
        for k, v in o.items():
            if k not in ("vs", "subs") and isinstance(v, (dict, list)):  # vs/subs: vices e suplentes
                _percorrer(v, f)


def candidatos(d):
    """{numero: votos} de todos os candidatos do arquivo de resultado."""
    out = {}
    _percorrer(d.get("carg", []), lambda c: out.__setitem__(str(c["n"]), num(c["vap"])))
    return out


def nomes(d):
    """{numero: nome na urna}."""
    out = {}
    _percorrer(d.get("carg", []), lambda c: out.__setitem__(str(c["n"]), (c.get("nmu") or c["nm"]).title()))
    return out
