"""Comandos do projeto:  uv run eleicoes <comando>  (uv run eleicoes -h lista todos)."""
import argparse
import sys

ANOS_COM_DADOS = [2018, 2022, 2026]  # de 2026, o que o TSE já publicou (ver `baixar`)
# Eleições municipais, das quais só se usam os locais de votação: completam as coordenadas que faltam (Etapa 4)
ANOS_SO_LOCAIS = [2016, 2020, 2024]


def main(argv=None):
    if sys.stdout is not None:  # a tarefa agendada roda pelo pythonw, sem terminal
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # também quando a saída vai para um arquivo
    p = argparse.ArgumentParser(prog="eleicoes", description="Estudo Lulismo/Petismo × Bolsonarismo (Presidente).")
    sub = p.add_subparsers(dest="comando", required=True, metavar="comando")

    b = sub.add_parser("baixar", help="baixa os dados do TSE e do IBGE para dados/bruto (retoma se interrompido)")
    b.add_argument("--anos", type=int, nargs="+", default=ANOS_COM_DADOS)

    pr = sub.add_parser("processar", help="gera as tabelas de dados/processado a partir de dados/bruto")
    pr.add_argument("--anos", type=int, nargs="+", default=ANOS_COM_DADOS)

    pq = sub.add_parser("pesquisas", help="baixa (se faltar) e processa as pesquisas: Wikipedia + registro do TSE")
    pq.add_argument("--anos", type=int, nargs="+", default=[2018, 2022, 2026])
    pq.add_argument("--atualizar", action="store_true", help="baixa a revisão atual da Wikipedia e o registro do TSE")

    sub.add_parser("projecao", help="projeção do 2º turno (1º turno + pesquisas) e a validação em 2018 e 2022")

    at = sub.add_parser("atualizar", help="pesquisa nova na Wikipedia? confere e refaz as pesquisas e a projeção do site")
    at.add_argument("--forcar", action="store_true", help="publica a revisão atual mesmo se a conferência achar problemas")
    at.add_argument("--avisar", action="store_true", help="avisos do Windows quando entra pesquisa nova ou algo dá errado")

    ag = sub.add_parser("agendar", help="tarefa do Windows que roda `atualizar` sozinha até o 2º turno")
    ag.add_argument("--horas", type=int, default=2, help="intervalo entre as rodadas (padrão: 2)")
    ag.add_argument("--remover", action="store_true", help="apaga a tarefa agendada")

    sub.add_parser("site", help="gera os dados do site (site/src/data) a partir de dados/processado")

    co = sub.add_parser("coletar", help="coleta da apuração na nuvem (GitHub Actions): um dos três coletores")
    co.add_argument("coletor", nargs="?", choices=list("abc"))
    co.add_argument("--plano", action="store_true", help="só diz o que a rodada do workflow faz agora (chave=valor)")
    co.add_argument("--pasta", help="pasta do ramo onde o coletor grava (padrão: dados/cache/ao_vivo/<eleição>/ramo-<coletor>)")
    co.add_argument("--ramo", help="ramo do git para onde enviar; sem ele, só grava na pasta")
    co.add_argument("--job", help="nome do job: a pasta das gravações dele dentro do ramo")
    co.add_argument("--epoca", help="uma troca de job do coletor a (ISO; padrão: 40 min antes da divulgação)")
    co.add_argument("--periodo", type=int, help="minutos entre duas trocas de job de um coletor")
    co.add_argument("--fim", help="até quando coletar, no máximo (ISO)")
    co.add_argument("--ensaio", action="store_true", help="ensaio curto: trocas de job a cada 12 min, por 30 min")
    co.add_argument("--juntar", action="store_true", help="com --plano: só juntar o que já foi gravado")

    ju = sub.add_parser("juntar", help="junta o que os coletores gravaram em dados/bruto/ao_vivo/<eleição>")
    ju.add_argument("pastas", nargs="+", help="pastas dos ramos dos coletores")
    ju.add_argument("--destino", help="outra pasta de saída (o ensaio não grava em dados/bruto)")
    ju.add_argument("--forcar", action="store_true", help="junta antes do fim da apuração ou refaz uma junção")
    ju.add_argument("--ensaio", action="store_true", help="ensaio: junta sem esperar o fim e exige --destino")

    a = p.parse_args(argv)
    try:
        if a.comando == "baixar":
            baixar(a.anos)
        elif a.comando == "processar":
            from eleicoes import tratamento
            tratamento.processar(a.anos)
        elif a.comando == "pesquisas":
            pesquisas(a.anos, a.atualizar)
        elif a.comando == "projecao":
            from eleicoes.modelos import projecao
            projecao.rodar()
        elif a.comando == "atualizar":
            from eleicoes import atualizacao
            raise SystemExit(atualizacao.rodar(forcar=a.forcar, avisos=a.avisar))
        elif a.comando == "agendar":
            from eleicoes import atualizacao
            atualizacao.remover() if a.remover else atualizacao.agendar(a.horas)
        elif a.comando == "site":
            from eleicoes.analises import site
            print("Gerando os dados do site em site/src/data")
            site.gerar()
            print("Para ver o site:  cd site  e  npm run dev")
        elif a.comando == "coletar":
            from eleicoes.ao_vivo import coletor
            if a.plano:
                coletor.imprimir_plano(ensaio=a.ensaio, juntar=a.juntar)
            elif a.coletor is None:
                p.error("coletar: diga qual coletor (a, b ou c), ou --plano")
            else:
                pasta = a.pasta or coletor.AV.cache / f"ramo-{a.coletor}"
                raise SystemExit(coletor.main(a.coletor, pasta, a.ramo, a.job, a.epoca, a.periodo, a.fim, a.ensaio))
        elif a.comando == "juntar":
            from eleicoes.ao_vivo import juntar
            if a.ensaio and not a.destino:
                p.error("juntar --ensaio: diga onde gravar com --destino")
            raise SystemExit(juntar.juntar(a.pastas, a.destino, forcar=a.forcar, ensaio=a.ensaio))
    except KeyboardInterrupt:
        raise SystemExit(1)


def pesquisas(anos, atualizar=False):
    from eleicoes.coleta import manifesto, tse, wikipedia
    from eleicoes.tratamento import pesquisas as tratamento
    for ano in anos:
        print(f"\n{ano} · pesquisas")
        wikipedia.baixar(ano, atualizar=atualizar)
        arq = tse.pasta("pesquisas", ano) / f"pesquisa_eleitoral_{ano}.zip"
        if atualizar and arq.exists() and manifesto.registro(arq):
            arq.unlink()  # o registro do TSE cresce durante a campanha: baixa de novo
        tse.pesquisas(ano)
        tratamento.processar(ano)
    from eleicoes import config
    tratamento.relatorio(config.anos())  # todos os anos já processados, não só os desta rodada
    print("\nRelatório → docs/qualidade_pesquisas.md")


def baixar(anos):
    from eleicoes.coleta import ibge, tse
    print("Baixando para dados/bruto (≈8 GB na primeira vez). Pode interromper: rodar de novo retoma.")
    for ano in anos:
        print(f"\n{ano} · totais oficiais por município e zona")
        tse.totais_oficiais(ano)
        print(f"{ano} · locais de votação")
        tse.locais(ano)
        if tse.boletins_publicados(ano):
            print(f"{ano} · boletins de urna (1º e 2º turno, por UF)")
            tse.boletins(ano)
        else:
            print(f"{ano} · boletins de urna ainda não publicados: votos por seção do arquivo de votação por seção")
            tse.votacao_secao(ano)
    print("\nLocais de votação das eleições municipais (para completar coordenadas)")
    for ano in ANOS_SO_LOCAIS:
        tse.locais(ano)
    print("\nCódigos de município TSE → IBGE")
    tse.municipios()
    print("IBGE · malhas e lista de municípios")
    ibge.baixar()
    print("\nPronto. Origem e SHA-512 de cada arquivo em dados/bruto/manifesto.csv")
