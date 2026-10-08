"""Arquivos de dados/bruto -> tabelas limpas em dados/processado (só Presidente), com validação contra os totais oficiais.

Tabelas geradas (Parquet), descritas em docs/dados.md:
  referencia/municipios.parquet          códigos de município TSE -> IBGE, nome, UF, região
  tse/totais_oficiais/<ano>.parquet      votos oficiais por município, zona e candidato (o gabarito)
  tse/locais_votacao/<ano>.parquet       local de votação e coordenadas de cada seção
  tse/votos_secao/<ano>_t<turno>.parquet votos de cada seção por candidato, branco e nulo
  tse/secoes/<ano>_t<turno>.parquet      uma linha por seção: comparecimento, votos por campo, horários
  tse/votacao_secao/<ano>_t<turno>.parquet  a mesma linha por seção, sem horários: antes dos boletins e conferência deles
  mapa/locais_<ano>.parquet              cada local de votação com coordenadas completadas e votos de cada turno
"""
import duckdb

from eleicoes import config

TMP = config.CACHE / "tmp"


def conexao():
    TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET temp_directory = '{TMP.as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    return con


def ler_csv(caminho, colunas, aspas_soltas=False):
    """Trecho SQL que lê um CSV do TSE (';', aspas, latin-1) com tudo como texto e nomes de coluna normalizados.

    aspas_soltas: o arquivo tem aspas dentro de campos sem o escape do padrão CSV (ex.: o boletim de urna de
    2018 traz `"PASTOR JOÃO CARLOS "O JUCÁ""`). Aí o arquivo é lido separando só por ';' e as aspas das pontas
    de cada campo são retiradas depois; um ';' dentro de um campo faria a leitura falhar, nunca errar calada.
    """
    nomes = ", ".join(f"'{c}'" for c in colunas)
    comum = f"delim=';', header=true, encoding='latin-1', all_varchar=true, names=[{nomes}]"
    if aspas_soltas:
        return f"(SELECT trim(COLUMNS(*), '\"') FROM read_csv('{caminho.as_posix()}', quote='', escape='', {comum}))"
    return f"read_csv('{caminho.as_posix()}', quote='\"', escape='\"', {comum})"


def cabecalho(caminho):
    with open(caminho, encoding="latin-1") as f:
        return [c.strip().strip('"').replace(" ", "") for c in f.readline().split(";")]  # 2018 tem "SG_ UF"


def processar(anos, log=print):
    """Gera as tabelas dos anos pedidos com o que estiver em dados/bruto, completa as coordenadas dos locais de
    votação (Etapa 4) e refaz o relatório de qualidade de todos os anos."""
    from eleicoes.tratamento import boletins, coordenadas, locais, municipios, oficial, qualidade, votacao_secao
    log("Códigos de município TSE → IBGE")
    municipios.processar(log)
    for ano in anos:
        log(f"\n{ano}")
        if oficial.origem(ano).exists():
            log(f"{ano} · totais oficiais")
            oficial.processar(ano, log)
        else:
            log(f"{ano} · totais oficiais ainda não publicados")
        log(f"{ano} · locais de votação")
        locais.processar(ano, log)
        for turno in (1, 2):
            if boletins.zips(ano, turno):
                log(f"{ano} · boletins de urna, {turno}º turno")
                boletins.processar(ano, turno, log)
        if votacao_secao.origem(ano).exists():
            log(f"{ano} · votação por seção")
            votacao_secao.processar(ano, log)
    # Locais de votação de outras eleições: só servem de referência para as coordenadas; refeitos se mudaram
    for ano in coordenadas.ANOS_LOCAIS:
        bruto, tabela = locais.origem(ano), locais.saida(ano)
        if ano not in anos and bruto.exists() and (not tabela.exists() or tabela.stat().st_mtime < bruto.stat().st_mtime):
            log(f"\n{ano} · locais de votação (referência para as coordenadas)")
            locais.processar(ano, log)
    com_mapa = [ano for ano in config.anos() if any(votacao_secao.fonte_secoes(ano, t) for t in (1, 2))]
    for ano in com_mapa:
        log(f"\n{ano} · coordenadas dos locais de votação")
        coordenadas.processar(ano, log)
    log("\nErro de cada método de coordenadas (escondendo a coordenada de quem a tem)")
    coordenadas.validar(com_mapa, log)
    log("\nRelatório de qualidade → docs/qualidade_dados.md")
    qualidade.gerar(log)
