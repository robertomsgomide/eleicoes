# Lulismo/Petismo × Bolsonarismo nas eleições presidenciais

Estudo de ciência de dados, com finalidade informativa, sobre as eleições para Presidente de
**2018** (Bolsonaro × Haddad), **2022** (Lula × Bolsonaro) e **2026** (Lula × Flávio Bolsonaro):
apuração ao longo do tempo, resultados por região, pesquisas × resultado, mapa de pontos e,
no 2º turno de 2026, projeção e forecast da apuração.

**O site: [robertomsgomide.github.io/eleicoes](https://robertomsgomide.github.io/eleicoes/)**. No 2º turno de 2026
(25/10), Lula venceu Flávio Bolsonaro por 51,79% a 48,21% dos votos válidos. Até a véspera, o site se atualizou sozinho
a cada pesquisa nova; na noite da apuração, acompanhou a contagem ao vivo, com o forecast; agora mostra o resultado
final. O mapa e a curva da apuração do 2º turno ficam exatos quando o TSE publicar os boletins de urna (Etapa 7).

Fontes: TSE (resultados, boletins de urna, locais de votação, registro de pesquisas), IBGE
(malhas e Censo 2022) e tabelas de pesquisas da Wikipedia (CC BY-SA). Roteiro em
[docs/ROADMAP.md](docs/ROADMAP.md); dados e tabelas em [docs/dados.md](docs/dados.md); conferência
contra os totais oficiais em [docs/qualidade_dados.md](docs/qualidade_dados.md); a projeção do 2º turno
refeita em 2018 e 2022, e comparada com as urnas em 2026, em [docs/validacao_projecao.md](docs/validacao_projecao.md); o
forecast da apuração, com as noites de 2018 e 2022 refeitas, em [docs/validacao_forecast.md](docs/validacao_forecast.md),
e a noite de 2026, como ele apareceu ao vivo, na Metodologia do site.

## Como rodar

Requisito: [uv](https://docs.astral.sh/uv/). Ele cria o ambiente do projeto (`.venv`) sem mexer no Python do sistema.

```bash
uv sync                          # instala as dependências fixadas em uv.lock
uv run eleicoes -h               # lista os comandos
uv run eleicoes baixar           # dados do TSE e do IBGE -> dados/bruto (≈8 GB; retoma se interrompido)
uv run eleicoes processar        # tabelas limpas e coordenadas do mapa -> dados/processado + docs/qualidade_dados.md
uv run eleicoes pesquisas        # pesquisas: Wikipedia + registro do TSE (--atualizar para a revisão atual)
uv run eleicoes projecao         # projeção do 2º turno e a validação em 2018 e 2022 -> site/src/data + docs
uv run eleicoes atualizar        # pesquisa nova na Wikipedia? confere e refaz as pesquisas e a projeção do site
uv run eleicoes agendar          # o mesmo pelo Agendador de Tarefas do Windows, no próprio computador (--remover apaga)
uv run eleicoes site             # dados do site -> site/src/data (JSON, versionados no git)
uv run eleicoes forecast         # forecast da apuração: as noites de 2018 e 2022 refeitas -> site/src/data + docs
uv run eleicoes coletar a        # um dos três coletores da apuração na nuvem (quem roda é o GitHub Actions; ver abaixo)
uv run eleicoes juntar <ramos>   # junta o que os coletores gravaram em dados/bruto/ao_vivo/<eleição>
uv run pytest                    # testes
```

A eleição acompanhada ao vivo pelos coletores é escolhida em `[ao_vivo]` no
[config/eleicoes.toml](config/eleicoes.toml).

### A noite do 2º turno, gravada na nuvem

Em 25/10, a apuração foi gravada pelo GitHub Actions ([.github/workflows/apuracao.yml](.github/workflows/apuracao.yml)),
sem depender de nenhum computador ligado:

- três coletores (a, b, c) leem o TSE a cada 60 s, defasados de 20 s entre si. Cada um grava no seu ramo
  (`ao-vivo-a`, `-b`, `-c`) e envia a cada 3 min o que o TSE não deixa baixar depois: cada atualização do país, de cada
  UF e de cada município, e o horário de chegada de cada seção como aparecia durante a apuração;
- um job do Actions dura no máximo 6 h, então cada coletor troca de job a cada 5h40, e as trocas dos três ficam
  defasadas de 1h53: enquanto um troca, os outros dois seguem lendo;
- o GitHub pula muitas rodadas agendadas, então há uma a cada 10 min no dia 25, a partir das 10h; a primeira espera
  até as 15h30 e libera os coletores, e as seguintes só entram se ela cair antes do fim;
- a cada envio, cada coletor refaz também o que o site lê na noite: `dados.json` (a apuração com as leituras oficiais do
  país e das UFs, o forecast do resultado final e o histórico dele) e `mapa.json` (o apurado e o swing estimado de cada
  município) — [src/eleicoes/ao_vivo/painel.py](src/eleicoes/ao_vivo/painel.py). O forecast parte do 1º turno de cada
  seção, que o job copia do ramo `dados`;
- 1 h depois de o TSE fechar a totalização (ou às 6h de 26/10, no máximo), o job "Junta as gravações" junta os três
  ramos em `dados/bruto/ao_vivo/ele2026-6258` e faz o commit no `main`.

Na noite, a página de 2026 lia, a cada minuto, o placar direto do TSE (país e UFs) e o `dados.json` e o `mapa.json`
do coletor mais recente (ramos `ao-vivo-*`). Desde 26/10, ela só lê os arquivos do site, que `uv run eleicoes site` gera
da gravação juntada ([src/eleicoes/analises/noite.py](src/eleicoes/analises/noite.py)): `apuracao_2026_t2.json`, a
apuração pelas leituras oficiais gravadas, até os boletins de urna; e `noite_2026_t2.json`, o forecast como apareceu na
noite e, até o TSE publicar os votos de cada seção, o mapa do fim (o resultado de cada município, que a página reparte
entre os locais pelo 1º turno). O histórico do forecast e o mapa do fim só existiam no `dados.json` e no `mapa.json` de
cada ramo: `uv run eleicoes juntar <ramos>` os acrescentou à gravação já juntada (`previsoes.json` e `mapa.json`). Com
isso, os ramos `ao-vivo-*` (e os do ensaio) podem ser apagados. Como o forecast funciona, como foi testado e como se
saiu: Metodologia do site e [src/eleicoes/modelos/forecast.py](src/eleicoes/modelos/forecast.py).

Para ver a coleta funcionando antes: um push no ramo `ensaio-apuracao` (ou "Run workflow" com "ensaio") roda o mesmo
esquema por 30 min contra os arquivos do 1º turno, com trocas de job a cada 12 min. "Run workflow" sem "ensaio" liga a
coleta de verdade, se faltar menos de 24 h para as 15h30 de 25/10 (antes disso, não faz nada). Para parar tudo: na aba
Actions, "Apuração ao vivo" → "Disable workflow" e cancelar a rodada em curso. Como funciona por dentro:
[src/eleicoes/ao_vivo/coletor.py](src/eleicoes/ao_vivo/coletor.py).

Até o 2º turno de 2026, as pesquisas novas entraram sozinhas no site. A cada hora, aos 17 minutos, até as 17h de
25/10, o workflow Site ([.github/workflows/site.yml](.github/workflows/site.yml)) roda `uv run eleicoes atualizar`,
faz o commit dos dados refeitos e publica o site de novo. Cada rodada:

- pergunta à Wikipedia se a página de pesquisas de 2026 mudou (as revisões de 2018 e 2022 ficam fixas);
- se mudou, confere as pesquisas antes de gravar e refaz `site/src/data/pesquisas_2026.json` e `projecao.json`.
  Sem nada novo, a projeção só passa a valer até hoje (um commit por dia);
- segura a revisão quando pesquisas já publicadas somem ou mudam de número, ou quando uma pesquisa nova é
  impossível ou fica longe demais da projeção: pode ser vandalismo ou uma tabela lida errado. O site fica como
  estava, a rodada falha e abre uma issue no repositório, que menciona você. Depois de conferir a página: na aba
  Actions, "Run workflow" no Site, com "forcar" marcado;
- publica o site quando os dados mudaram, ou quando o site no ar não foi montado do último commit do `main` (a
  publicação anterior falhou). Uma publicação que falha também abre a issue, e a rodada seguinte publica de novo
  sozinha.

Quem dispara o Site a cada hora é o relógio das pesquisas ([.github/workflows/relogio.yml](.github/workflows/relogio.yml),
[src/eleicoes/relogio.py](src/eleicoes/relogio.py)), não o agendamento do GitHub: o cron é "melhor esforço" e, de
08 a 14/10, o de hora em hora rodou em só 18% das horas. O relógio é uma corrente de rodadas: cada uma fica acordada
até 5h40, dispara o Site a cada hora e, ao começar, já deixa a seguinte na fila, que assume quando ela acabar. Para
ligar: "Relógio das pesquisas" → "Run workflow", uma vez. Para parar: "Disable workflow" e cancelar a rodada em curso
e a da fila. "Run workflow" com "ensaio" mostra a corrente funcionando em 12 min, sem disparar o Site a cada tique.
Um disparo que falha também vira uma issue.

O resumo de cada rodada fica na página dela, na aba Actions. Como o robô faz commits no `main`, rode `git pull`
antes de enviar mudanças suas. Os dados que a rodada usa e que não ficam no `main` estão no ramo `dados`
([dados/README.md](dados/README.md)). Cada envio seu para o `main` (`git push`) também monta e publica o site.

### O site

Feito com [Observable Framework](https://observablehq.com/framework/) (Node 18+). Os dados já vêm em
`site/src/data`, então não é preciso baixar nada do TSE para vê-lo:

```bash
cd site
npm install        # uma vez
npm run dev        # http://localhost:3000, recarrega a cada mudança
npm run build      # site estático em site/dist, sem nenhuma dependência externa
```

## Organização

```
.github/workflows/     publicação do site no GitHub Pages, atualização a cada hora e a coleta da apuração (GitHub Actions)
config/eleicoes.toml   anos, turnos, códigos do TSE, candidatos e cores de cada campo
src/eleicoes/          o código (pacote Python)
  ao_vivo/             a coleta da apuração na nuvem (coletor.py, juntar.py; leitura do TSE em historico.py) e o que o
                       site lia na noite (painel.py)
  coleta/              downloads (TSE, IBGE, pesquisas)            [Etapa 1]
  tratamento/          dados brutos -> tabelas limpas              [Etapa 1]
  analises/            o que alimenta o site (apuração no tempo, resultados, pesquisas, mapa)
  modelos/             projeção do 2º turno [Etapa 5]; forecast da apuração e a validação dele [Etapa 6]
  atualizacao.py       pesquisas novas e projeção atualizadas sozinhas até o 2º turno de 2026 (atualizar, agendar)
site/                  o site com as abas (Observable Framework)
  src/*.md             as páginas: Início, 2018, 2022, 2026, Comparações, Metodologia
  src/components/      gráficos (Observable Plot), o mapa (WebGL + canvas), os pontos da página inicial e formatação em pt-BR
  src/data/            JSON gerados por `uv run eleicoes site`
tests/                 testes (inclusive contra os totais oficiais)
docs/                  roteiro, metodologia, dicionário de dados
dados/                 bruto, processado e cache (fora do git; ver dados/README.md)
```
