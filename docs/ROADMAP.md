# Roteiro

Estudo Lulismo/Petismo × Bolsonarismo, só Presidente, 2018 · 2022 · 2026. Primeiro em
localhost; depois, publicação para o público geral sem depender de um PC ligado.

## Decisões (05/10/2026)

- Etapas em ordem natural, uma por vez, com conferência ao fim de cada uma.
- A última etapa é o **forecast dinâmico na noite do 2º turno (25/10/2026)**, ensaiado antes com 2022.
- Dados dentro do projeto, em `dados/` (bruto / processado / cache), fora do git.
- Site com Observable Framework: páginas em Markdown, dados gerados por Python, saída estática,
  bibliotecas embutidas (sem CDN, sem fontes externas). Os JSON do site (`site/src/data`) vão para o git,
  para o site ser montado sem os gigabytes de dados brutos.
- Extras no escopo: projeção do 2º turno a partir do 1º turno e das pesquisas; cruzamento com o Censo 2022.
- Fora do escopo por ora: 2014 como linha de base; validar o método de estimativa usado na noite do 1º turno.

## Etapas

| # | Etapa | Entrega | Pronta quando |
|---|---|---|---|
| 0 | Fundação ✅ | git, estrutura, ambiente uv, `config/eleicoes.toml`, painel ao vivo na estrutura nova | `uv run eleicoes ao-vivo` funciona e os testes passam |
| 1 | Base de dados ✅ 2018 e 2022 (05/10); 1º turno de 2026 (07/10): boletins de urna conferidos com o total oficial zona a zona e com a votação por seção seção a seção. 2º turno de 2026 depois do dia 25 | Boletins de urna, votos por seção, locais com coordenadas, malhas IBGE, códigos TSE↔IBGE, convertidos em Parquet só com Presidente ([dados.md](dados.md)) | Testes batem com os totais oficiais do TSE em cada ano e turno ([qualidade_dados.md](qualidade_dados.md)) |
| 2 | Site + apuração no tempo ✅ (05/10; 2026 exato desde 07/10) | Abas Início, 2018, 2022, 2026, Comparações e Metodologia; resultado por região; apuração em % dos válidos, votos e vantagem, Brasil e regiões; eixo por horário e por % apurado; viradas anotadas | 2022 e 2026 exatos, 2018 estimado e validado (também com 2026) (`uv run eleicoes site`) |
| 3 | Pesquisas ✅ (05/10) | Base de pesquisas dos três anos (Wikipedia em português, revisão guardada, conferida com o registro do TSE); tendência × resultado; erro por instituto; erro das médias em Comparações (`uv run eleicoes pesquisas`) | 100% ligadas ao registro em 2018 e no 1º turno de 2022; ~95% no 2º turno de 2022; ~88% em 2026 (a Futura não aparece no registro nacional de 2026). Lista em [qualidade_pesquisas.md](qualidade_pesquisas.md) |
| 4 | Mapa de pontos ✅ (05/10; 2º turno de 2026 depois do dia 25) | Seção "Mapa" em cada ano: pontos (WebGL; 1 ponto = 500 votos no país até 1 voto na rua), hexágonos de vantagem, busca de município, nome e votos de cada local ao passar o mouse; gráfico do voto por local e comparação entre os anos. Coordenadas completadas com 2016–2026 e validadas (`docs/qualidade_dados.md`) | 2018 e 2022 nos dois turnos, 2026 no 1º |
| 5 | Projeção do 2º turno 2026 ✅ (07/10; refeita sozinha a cada pesquisa nova até 25/10) | Total do país: ponto de partida (1º turno das urnas + divisão dos outros candidatos nas pesquisas que perguntaram os dois turnos) combinado com a tendência das pesquisas feitas depois do 1º turno, com incerteza e chance de vitória; distribuição seção a seção para regiões e UFs. Seção "Projeção do 2º turno" em 2026 e na Metodologia; tendência das pesquisas de 2º turno recomeça depois do 1º turno (`uv run eleicoes projecao`). Pesquisas e projeção atualizadas a cada 2 horas, com conferência antes de publicar (`uv run eleicoes atualizar`, no GitHub Actions) | Refeita dia a dia em 2018 e 2022: erro médio de 1,0 e 1,6 p.p., na véspera −0,05 e +0,8 p.p., urnas na faixa de 80% em todos os dias ([validacao_projecao.md](validacao_projecao.md)) |
| 6 | Forecast dinâmico da apuração | Painel ao vivo novo: grava cada atualização oficial (Brasil e UFs) e prevê a evolução da curva a partir do estado atual. Base: `modelos.projecao.distribuir` dá o resultado esperado de cada seção para qualquer total do país | Ensaio completo com a noite de 2022; no ar em 25/10 às 17h |
| 7 | Depois de 25/10 | 2º turno de 2026 com os boletins do TSE; aba de comparações; Censo 2022 | — |
| 8 | Publicação ✅ (08/10; a parte ao vivo fica com a Etapa 6) | Site no GitHub Pages ([robertomsgomide.github.io/eleicoes](https://robertomsgomide.github.io/eleicoes/)), publicado a cada envio para o `main`; `atualizar` a cada 2 horas no GitHub Actions, com os dados que ele usa no ramo `dados` (`.github/workflows/site.yml`) | Site no ar e a rodada automática conferida no GitHub |

Sugestão de folga para 25/10: etapas 1–3 até ~15/10, mapa até ~19/10, projeção até ~21/10,
ensaio do forecast até ~23/10. Se apertar, o mapa pode ir para depois do dia 25 sem prejuízo. (Em 08/10, as
etapas 0 a 5 e a publicação, a 8, estão prontas.)

## Projeção do 2º turno: decisões (07/10/2026)

- **Ponto de partida pelas pesquisas pareadas**, não pelas pesquisas de 2º turno diretamente: tomadas diretamente, as
  de 2º turno da semana do 1º turno erraram o PT em +4,0 (2018) e +5,5 p.p. (2022); aplicar às urnas a divisão dos
  outros candidatos que elas mostravam errou +0,4 e +2,3.
- **Só pesquisas com o campo inteiro depois do 1º turno** entram na média; a tendência da página de pesquisas também
  recomeça ali.
- **Distribuição**: quem votou nos dois campos continua com eles; os outros se dividem pela inclinação da seção
  (testados também o deslocamento uniforme em logit e a média dos dois: o escolhido foi o mais estável entre 2018 e
  2022, com erro por UF de 2,1 e 0,7 p.p. dado o total verdadeiro).
- **Incerteza**: desvios redondos e conservadores, com a sensibilidade de cada um no relatório; normal, sem caudas
  mais pesadas. Em 07/10 ainda não há pesquisa de 2º turno feita depois do 1º turno na Wikipedia: a projeção é só o
  ponto de partida (Lula 48,2%, chance de 24%).
- **Atualização automática** (07/10; no GitHub Actions desde 08/10): `uv run eleicoes atualizar` roda a cada 2 horas
  até as 17h de 25/10. Uma revisão nova da Wikipedia só é publicada depois de comparada com a guardada. Ela é
  segurada, e a rodada falha (o GitHub avisa por e-mail), se mais de 2 pesquisas somem ou mudam de uma vez, se um número já publicado muda mais
  de 3 pontos, ou se uma pesquisa nova tem datas ou percentuais impossíveis ou, no 2º turno, fica a mais de 8
  pontos da projeção (`src/eleicoes/atualizacao.py`). Testado numa cópia do projeto: as 20 pesquisas que entraram
  entre 03/10 e 07/10 passaram; a tabela do 2º turno apagada e Lula +5 / Flávio −5 numa pesquisa já publicada
  foram segurados.

## Publicação: decisões (08/10/2026)

- **GitHub Pages**, não Cloudflare Pages: a atualização a cada 2 horas precisa rodar no GitHub Actions de qualquer
  jeito, e assim código, atualização e site ficam numa conta só. O custo é o repositório público.
- **Histórico**: o repositório público começa num commit só ("Início"), com o estado de 08/10; o histórico do
  desenvolvimento fica só no computador local, no ramo `historico-local`.
- **Dados da nuvem** no ramo `dados` (um commit, ~47 MB: seções e totais oficiais dos turnos apurados, pesquisas de
  2018 e 2022, registro do TSE de 2026), fora do `main`; o estado entre rodadas, no cache do Actions.
- **A noite de 25/10** não depende da hospedagem: o TSE deixa o navegador ler o placar direto (CORS liberado,
  conferido em 07/10). A curva e o forecast precisam de quem grave cada atualização: um job longo do GitHub Actions
  (até 6 horas) ou, se ele se mostrar frágil no ensaio com 2022, um Worker do Cloudflare (Etapa 6).

## O que os dados permitem (verificado em 05/10/2026; 2026 atualizado em 07/10)

| | 2018 | 2022 | 2026 |
|---|---|---|---|
| Votos por seção (Presidente) | ✅ | ✅ | ✅ 1º turno: boletins de urna (publicados em 06/10) e votação por seção (05/10), idênticos em todas as seções |
| Hora de chegada de cada boletim (`DT_BU_RECEBIDO`) | ❌ só abertura/encerramento da urna | ✅ | ✅ 1º turno: 61% das seções até 19h, como na noite (o `-cs.json` reescrito dava 12%) |
| Coordenadas dos locais de votação | 82% do eleitorado (resto completado) | 94% (idem) | 99% (idem) |
| Total oficial por município e zona | ✅ | ✅ | ✅ 1º turno: saiu sem Presidente em 05/10 e foi republicado com ele em 07/10 |
| Números das pesquisas | Wikipedia | Wikipedia | Wikipedia |

- Boletins de urna: `dadosabertos.tse.jus.br`, conjuntos `resultados-<ano>-boletim-de-urna`, um zip por
  UF e turno, com `.sha512`. 1º turno ≈ 1,5 GB compactado em 2018 e 2022 (todos os cargos) e 4,8 GB em 2026;
  2º turno ≈ 70 MB. Em 2026, o formato mudou: datas em aaaa-mm-dd e duas colunas renomeadas
  (`src/eleicoes/tratamento/boletins.py`).
- O TSE guarda só o registro das pesquisas (empresa, amostra, datas), não os números.
- Códigos de município TSE → IBGE: campo `cdi` em `/oficial/ele2026/6257/config/mun-e006257-cm.json`.
- 2018: o arquivo da internet guardou só a interface do site de resultados, não os dados da apuração.
- **O TSE reescreve os horários do `-cs.json` depois da apuração.** Na noite de 04/10 eles eram a chegada
  dos boletins (62% das seções até 19h, batendo com o oficial); em 05/10 às 00h54 o mesmo arquivo dava 12%
  até 19h e o Sul inteiro depois das 21h. Consequências: a curva exata de 2026 vem do boletim de urna
  (`DT_BU_RECEBIDO`), que guarda a chegada real (conferido em 07/10 com o que a noite gravou); no 2º
  turno, o painel precisa gravar o **primeiro horário visto** de cada seção durante a noite (Etapa 6).

## Exato × estimado

Tudo o que for estimativa aparece rotulado como tal no site (selo e linha tracejada). Hoje:
- **2022 e 2026: exatas.** Cada seção entra no minuto em que o boletim chegou ao TSE.
- **2018: estimada.** Chegada = encerramento da urna + atraso mediano da mesma zona no mesmo turno de 2022
  (`src/eleicoes/analises/apuracao.py`). Testado em 2022 com os atrasos do outro turno: erro médio de
  0,25–0,50 p.p. na participação de cada candidato por % apurado (máximo 1,5), mas de 13–21 pontos no
  % apurado por horário. Testado em 2026 com os atrasos do 1º turno de 2022 (mesmo turno, outra eleição, o
  caso mais parecido com o de 2018): 0,40 p.p. (máximo 1,9) e 12 pontos (máximo 37). Por isso o eixo padrão
  de 2018 é o % apurado.
- **A noite de 2026 gravada ao vivo** saiu do site quando a curva exata entrou (decisão de 07/10: a noite foi
  improvisada e não acrescenta ao dado exato). Os arquivos brutos ficam, porque não dá para baixá-los de novo:
  - `dados/bruto/ao_vivo/ele2026-6257/leituras_oficiais.json`: 112 leituras oficiais do arquivo nacional do
    TSE gravadas durante a noite do 1º turno (19h06 → 00h45).
  - `dados/bruto/ao_vivo/ele2026-6257/historico_estimado.*`: votos até 19h17 estimados pela média municipal
    com os horários da noite.
  - `dados/bruto/ao_vivo/ele2026-6257/final/`: resultado final por UF do site de resultados.
  - Medido em 07/10 contra os boletins, para a Etapa 6: a totalização oficial veio 2 minutos (mediana) depois da
    chegada dos boletins, até 14 minutos; a estimativa pela média municipal ficou a 0,4 ponto da curva exata
    (máximo 0,7).
