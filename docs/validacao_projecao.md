# Validação da projeção do 2º turno

> Gerado por `uv run eleicoes projecao` (ou `atualizar`) em 10/10/2026 14:51. Não editar à mão.

Método em `src/eleicoes/modelos/projecao.py` e na Metodologia do site. Cada ano é refeito dia a dia, só com o que se sabia em cada dia (o 1º turno das urnas e as pesquisas concluídas até ali).

## Projeção de cada ano

| Ano | Último dia | Pesquisas depois do 1º turno | Ponto de partida | Projeção do petismo | Intervalo de 80% | Chance do petismo | 2º turno das urnas |
|---|---|--:|--:|--:|---|--:|--:|
| 2018 | 27/10 | 25 | 45,27% | 44,82% | 42,9% a 46,7% | 0% | 44,87% |
| 2022 | 29/10 | 50 | 53,24% | 51,73% | 49,9% a 53,6% | 89% | 50,90% |
| 2026 | 10/10 | 4 | 48,20% | 48,21% | 45,6% a 50,8% | 19% | – |

## Erros em 2018 e 2022

Erro = projeção − urnas, em pontos percentuais da parte do petismo nos votos válidos.

| Ano | Pesquisas de 2º turno da véspera do 1º | Ponto de partida | Projeção: erro médio · máximo · na véspera | Dias com o resultado no intervalo de 80% | Véspera, UFs: erro típico · no intervalo de 80% |
|---|--:|--:|---|--:|---|
| 2018 | +3,95 | +0,40 | 1,01 · 2,00 · −0,05 | 100% | 2,14 · 93% |
| 2022 | +5,51 | +2,34 | 1,63 · 2,66 · +0,83 | 100% | 1,08 · 89% |

### Distribuição pelo país, com o total nacional verdadeiro

Quanto o modelo de distribuição erra só na geografia: o total do país é o das urnas e o modelo reparte esse total pelas seções a partir do 1º turno. Desvio típico em p.p. (municípios ponderados pelos votos) e a parte dos lugares cujo resultado caiu no intervalo de 80% do modelo.

| Ano | Regiões | UFs | Municípios | Regiões no intervalo | UFs no intervalo |
|---|--:|--:|--:|--:|--:|
| 2018 | 1,58 | 2,13 | 2,62 | 67% | 86% |
| 2022 | 0,46 | 0,66 | 0,93 | 83% | 75% |

## Sensibilidade aos desvios do total do país

Cada desvio 40% menor e 40% maior, com os outros como no modelo. Nos anos já decididos: erro médio da projeção (p.p.) e parte dos dias com as urnas na faixa de 80%; nos outros, a chance do petismo no último dia.

| Desvio | Valor | 2018 | 2022 | 2026 |
|---|--:|--:|--:|--:|
| **como no modelo** |  | 1,01 · 100% | 1,63 · 100% | 19% |
| ponto de partida | 1,50 | 0,39 · 100% | 1,96 · 29% | 10% |
| ponto de partida | 3,50 | 1,52 · 86% | 1,41 · 100% | 23% |
| uma pesquisa | 1,20 | 1,09 · 100% | 1,61 · 96% | 18% |
| uma pesquisa | 2,80 | 0,92 · 100% | 1,66 · 100% | 19% |
| erro comum na véspera | 0,90 | 1,16 · 86% | 1,54 · 96% | 18% |
| erro comum na véspera | 2,10 | 0,84 · 100% | 1,74 · 100% | 19% |
| mudança por raiz de dia | 0,42 | 1,36 · 76% | 1,48 · 96% | 16% |
| mudança por raiz de dia | 0,98 | 0,71 · 100% | 1,77 · 100% | 20% |

## Parâmetros

| Parâmetro | Valor |
|---|--:|
| `inclinacao` | 0,5 |
| `erro_uf` | 0,09 |
| `erro_regiao` | 0,06 |
| `desvio_partida` | 2,5 |
| `desvio_pesquisa` | 2,0 |
| `desvio_vespera` | 1,5 |
| `desvio_deriva` | 0,7 |
| `semana_pareadas` | 7 |
| `intervalo` | 0,8 |
| `janela_dias` | 7 |
