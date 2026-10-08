# Lulismo/Petismo × Bolsonarismo nas eleições presidenciais

Estudo de ciência de dados, com finalidade informativa, sobre as eleições para Presidente de
**2018** (Bolsonaro × Haddad), **2022** (Lula × Bolsonaro) e **2026** (Lula × Flávio Bolsonaro):
apuração ao longo do tempo, resultados por região, pesquisas × resultado, mapa de pontos e,
no 2º turno de 2026, projeção e forecast da apuração.

**O site: [robertomsgomide.github.io/eleicoes](https://robertomsgomide.github.io/eleicoes/)**, atualizado sozinho a
cada pesquisa nova até o 2º turno.

Fontes: TSE (resultados, boletins de urna, locais de votação, registro de pesquisas), IBGE
(malhas e Censo 2022) e tabelas de pesquisas da Wikipedia (CC BY-SA). Roteiro em
[docs/ROADMAP.md](docs/ROADMAP.md); dados e tabelas em [docs/dados.md](docs/dados.md); conferência
contra os totais oficiais em [docs/qualidade_dados.md](docs/qualidade_dados.md); a projeção do 2º turno
refeita em 2018 e 2022 em [docs/validacao_projecao.md](docs/validacao_projecao.md).

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
uv run eleicoes ao-vivo          # painel da apuração ao vivo em http://localhost:8765
uv run eleicoes ao-vivo --publico   # idem, com link https temporário (precisa do cloudflared)
uv run eleicoes historico        # reconstrução estimada da apuração ao vivo -> CSV + PNG
uv run pytest                    # testes
```

A eleição acompanhada pelo painel ao vivo é escolhida em `[ao_vivo]` no
[config/eleicoes.toml](config/eleicoes.toml).

Até o 2º turno de 2026, as pesquisas novas entram sozinhas no site. A cada hora, até as 17h de 25/10, o GitHub
Actions ([.github/workflows/site.yml](.github/workflows/site.yml)) roda `uv run eleicoes atualizar`, faz o commit
dos dados refeitos e publica o site de novo. Cada rodada:

- pergunta à Wikipedia se a página de pesquisas de 2026 mudou (as revisões de 2018 e 2022 ficam fixas);
- se mudou, confere as pesquisas antes de gravar e refaz `site/src/data/pesquisas_2026.json` e `projecao.json`.
  Sem nada novo, a projeção só passa a valer até hoje (um commit por dia);
- segura a revisão quando pesquisas já publicadas somem ou mudam de número, ou quando uma pesquisa nova é
  impossível ou fica longe demais da projeção: pode ser vandalismo ou uma tabela lida errado. O site fica como
  estava, a rodada falha e o GitHub avisa por e-mail. Depois de conferir a página: na aba Actions, "Run workflow"
  com "forcar" marcado.

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
.github/workflows/     publicação do site no GitHub Pages e atualização a cada hora (GitHub Actions)
config/eleicoes.toml   anos, turnos, códigos do TSE, candidatos e cores de cada campo
src/eleicoes/          o código (pacote Python)
  ao_vivo/             painel da apuração em tempo real
  coleta/              downloads (TSE, IBGE, pesquisas)            [Etapa 1]
  tratamento/          dados brutos -> tabelas limpas              [Etapa 1]
  analises/            o que alimenta o site (apuração no tempo, resultados, pesquisas, mapa)
  modelos/             projeção do 2º turno [Etapa 5]; forecast da apuração [Etapa 6]
  atualizacao.py       pesquisas novas e projeção atualizadas sozinhas até o 2º turno (atualizar, agendar)
site/                  o site com as abas (Observable Framework)
  src/*.md             as páginas: Início, 2018, 2022, 2026, Comparações, Metodologia
  src/components/      gráficos (Observable Plot), o mapa (WebGL + canvas) e formatação em pt-BR
  src/data/            JSON gerados por `uv run eleicoes site`
tests/                 testes (inclusive contra os totais oficiais)
docs/                  roteiro, metodologia, dicionário de dados
dados/                 bruto, processado e cache (fora do git; ver dados/README.md)
```
