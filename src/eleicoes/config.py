"""Caminhos do projeto e parâmetros das eleições (lidos de config/eleicoes.toml)."""
import dataclasses
import datetime as dt
import functools
import pathlib
import tomllib

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ARQ_CONFIG = RAIZ / "config" / "eleicoes.toml"

# dados/bruto: o que veio de fora, como veio (nunca editado; tudo se regenera a partir daqui)
# dados/processado: tabelas limpas geradas pelo código
# dados/cache: pode ser apagado a qualquer momento
DADOS = RAIZ / "dados"
BRUTO = DADOS / "bruto"
PROCESSADO = DADOS / "processado"
CACHE = DADOS / "cache"

# Regiões do IBGE; "ZZ" é a sigla do TSE para o voto no exterior
REGIOES = {
    "Norte": ("AC", "AM", "AP", "PA", "RO", "RR", "TO"),
    "Nordeste": ("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"),
    "Centro-Oeste": ("DF", "GO", "MS", "MT"),
    "Sudeste": ("ES", "MG", "RJ", "SP"),
    "Sul": ("PR", "RS", "SC"),
    "Exterior": ("ZZ",),
}
REGIAO_DA_UF = {uf: r for r, ufs in REGIOES.items() for uf in ufs}


@functools.cache
def carregar():
    with open(ARQ_CONFIG, "rb") as f:
        return tomllib.load(f)


def anos():
    return sorted(int(a) for a in carregar()["eleicoes"])


def candidatos(ano):
    """{numero: campo} dos dois campos estudados naquele ano, ex. {13: "petismo", 22: "bolsonarismo"}."""
    e = carregar()["eleicoes"][str(ano)]
    return {e[campo]["numero"]: campo for campo in carregar()["campos"]}


def nomes(ano):
    """{campo: nome do candidato} naquele ano, ex. {"petismo": "Lula", "bolsonarismo": "Flávio Bolsonaro"}."""
    e = carregar()["eleicoes"][str(ano)]
    return {campo: e[campo]["nome"] for campo in carregar()["campos"]}


def turno(ano, numero):
    """Dados de um turno: data, divulgacao (hora de Brasília) e, quando conhecidos, códigos do TSE."""
    return carregar()["eleicoes"][str(ano)][f"turno{numero}"]


def nulos_tecnicos(ano, numero):
    """Números dos candidatos cujos votos o TSE anulou naquele turno (contam como nulos, não como válidos)."""
    return list(turno(ano, numero).get("nulos_tecnicos", []))


def inicio_divulgacao(ano, numero):
    """Data e hora (Brasília) em que o TSE começou a divulgar os resultados daquele turno."""
    t = turno(ano, numero)
    hora, minuto = map(int, t["divulgacao"].split(":"))
    return dt.datetime.fromisoformat(t["data"]).replace(hour=hora, minute=minuto)


@dataclasses.dataclass(frozen=True)
class AoVivo:
    """A eleição que o painel ao vivo acompanha em resultados.tse.jus.br."""
    ano: int
    turno: int
    ciclo: str
    pleito: str
    eleicao: str
    cargo: str
    inicio: dt.datetime
    porta: int

    @property
    def chave(self):
        return f"{self.ciclo}-{self.eleicao}"

    @property
    def bruto(self):  # leituras gravadas durante a apuração: não dá para baixar de novo depois
        return BRUTO / "ao_vivo" / self.chave

    @property
    def processado(self):
        return PROCESSADO / "ao_vivo" / self.chave

    @property
    def cache(self):
        return CACHE / "ao_vivo" / self.chave


def ao_vivo():
    c = carregar()
    a = c["ao_vivo"]
    t = c["eleicoes"][str(a["ano"])][f"turno{a['turno']}"]
    faltam = [k for k in ("pleito", "eleicao") if not t.get(k)]
    if faltam:
        raise SystemExit(f"Preencha {', '.join(faltam)} de eleicoes.{a['ano']}.turno{a['turno']} "
                         f"em {ARQ_CONFIG.relative_to(RAIZ)} antes de abrir o painel ao vivo.")
    return AoVivo(ano=a["ano"], turno=a["turno"], ciclo=f"ele{a['ano']}", pleito=t["pleito"],
                  eleicao=t["eleicao"], cargo=a["cargo"], inicio=inicio_divulgacao(a["ano"], a["turno"]),
                  porta=a["porta"])
