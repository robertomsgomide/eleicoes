# Validação do forecast da apuração

> Gerado por `uv run eleicoes forecast` em 14/10/2026 00:32. Não editar à mão.

Método em `src/eleicoes/modelos/forecast.py` e na Metodologia do site. Cada noite de 2º turno já apurada (2018 e 2022) é refeita seção a seção, só com o que se sabia em cada momento: o resultado de cada município como o coletor o teria lido (no máximo 400 por minuto, os mais atrasados primeiro, cada um com as seções totalizadas até 2 min antes), o total oficial de cada UF a cada minuto e a hora de chegada de cada seção. O ponto de partida é o 1º turno de cada seção, distribuído como na projeção do 2º turno da véspera daquele ano.

Em 2018, sem a hora de chegada de cada boletim, ela é estimada como no site, e a divulgação só começou às 19h, com quase todas as seções já apuradas: a ordem real de 2018 quase não testa o forecast, e valem as ordens inventadas.

Ordens de chegada: a real; em 2022, a do 1º turno (as mesmas seções); cada região por último; as UFs em ordem sorteada (cada uma começa com um atraso sorteado de até 90 min; 10 sorteios); e as seções embaralhadas.

## Erro do forecast a cada % apurado

Erro = forecast − urnas, na parte do petismo nos votos válidos, em pontos percentuais, em todas as ordens de chegada. Faixa: a metade do intervalo de 80% (média). Contagem: o erro médio de quem lesse só o que já foi apurado.

### 2018 (17 ordens de chegada)

Resultado dentro da faixa de 80%: 97% das vezes no país e 92% nas UFs ainda não apuradas por inteiro (de 1% apurado em diante).

| Apurado | Erro médio | Erro máximo | Faixa de 80% | Na faixa | Contagem: erro médio |
|--:|--:|--:|--:|--:|--:|
| 0,5% | 0,27 | 0,69 | ±1,36 | 100% | 24,52 |
| 1% | 0,31 | 0,69 | ±1,33 | 100% | 20,22 |
| 2% | 0,30 | 0,69 | ±1,31 | 100% | 16,18 |
| 3% | 0,33 | 0,76 | ±1,29 | 100% | 15,80 |
| 5% | 0,38 | 0,86 | ±1,24 | 100% | 13,24 |
| 7,5% | 0,36 | 0,91 | ±1,18 | 100% | 11,58 |
| 10% | 0,41 | 1,04 | ±1,14 | 100% | 9,68 |
| 15% | 0,45 | 1,00 | ±1,06 | 100% | 8,13 |
| 20% | 0,49 | 1,33 | ±0,96 | 100% | 6,20 |
| 30% | 0,40 | 1,08 | ±0,88 | 100% | 5,66 |
| 40% | 0,31 | 0,88 | ±0,76 | 94% | 4,95 |
| 50% | 0,32 | 0,75 | ±0,66 | 94% | 4,49 |
| 60% | 0,27 | 0,69 | ±0,53 | 94% | 4,71 |
| 70% | 0,20 | 0,91 | ±0,38 | 88% | 4,88 |
| 80% | 0,08 | 0,25 | ±0,26 | 94% | 3,71 |
| 90% | 0,04 | 0,19 | ±0,11 | 94% | 1,86 |
| 95% | 0,01 | 0,03 | ±0,05 | 94% | 1,11 |
| 98% | 0,01 | 0,03 | ±0,02 | 94% | 0,28 |

### 2022 (18 ordens de chegada)

Resultado dentro da faixa de 80%: 100% das vezes no país e 95% nas UFs ainda não apuradas por inteiro (de 1% apurado em diante).

| Apurado | Erro médio | Erro máximo | Faixa de 80% | Na faixa | Contagem: erro médio |
|--:|--:|--:|--:|--:|--:|
| 0,5% | 0,16 | 0,48 | ±0,63 | 100% | 5,82 |
| 1% | 0,16 | 0,44 | ±0,57 | 100% | 6,48 |
| 2% | 0,15 | 0,42 | ±0,52 | 100% | 5,72 |
| 3% | 0,13 | 0,36 | ±0,49 | 100% | 5,02 |
| 5% | 0,12 | 0,34 | ±0,47 | 100% | 4,30 |
| 7,5% | 0,09 | 0,25 | ±0,44 | 100% | 3,91 |
| 10% | 0,09 | 0,26 | ±0,42 | 100% | 3,61 |
| 15% | 0,11 | 0,26 | ±0,38 | 100% | 3,42 |
| 20% | 0,10 | 0,26 | ±0,36 | 100% | 3,21 |
| 30% | 0,10 | 0,25 | ±0,31 | 100% | 2,81 |
| 40% | 0,09 | 0,23 | ±0,28 | 100% | 2,55 |
| 50% | 0,08 | 0,20 | ±0,24 | 100% | 2,28 |
| 60% | 0,06 | 0,18 | ±0,19 | 100% | 2,11 |
| 70% | 0,05 | 0,17 | ±0,15 | 100% | 1,78 |
| 80% | 0,03 | 0,16 | ±0,09 | 100% | 1,32 |
| 90% | 0,01 | 0,02 | ±0,05 | 100% | 0,79 |
| 95% | 0,00 | 0,01 | ±0,02 | 100% | 0,47 |
| 98% | 0,00 | 0,00 | ±0,01 | 100% | 0,23 |

## Swing por atributos

Variante testada: além do swing de cada lugar, o swing de cada seção acompanha três atributos do 1º turno (a parte dos outros candidatos, a inclinação entre os dois e o comparecimento), com coeficientes aprendidos a cada momento nos municípios já apurados. Erro médio no país e a parte das vezes com o resultado na faixa de 80%:

| Apurado | 2018: simples | 2018: atributos | 2022: simples | 2022: atributos |
|--:|--:|--:|--:|--:|
| 0,5% | 0,27 | 0,31 | 0,16 | 0,31 |
| 1% | 0,31 | 0,36 | 0,16 | 0,23 |
| 2% | 0,30 | 0,33 | 0,15 | 0,22 |
| 3% | 0,33 | 0,37 | 0,13 | 0,18 |
| 5% | 0,38 | 0,43 | 0,12 | 0,15 |
| 7,5% | 0,36 | 0,44 | 0,09 | 0,11 |
| 10% | 0,41 | 0,48 | 0,09 | 0,10 |
| 15% | 0,45 | 0,40 | 0,11 | 0,11 |
| 20% | 0,49 | 0,50 | 0,10 | 0,10 |
| 30% | 0,40 | 0,46 | 0,10 | 0,08 |
| 40% | 0,31 | 0,35 | 0,09 | 0,08 |
| 50% | 0,32 | 0,34 | 0,08 | 0,06 |
| 60% | 0,27 | 0,31 | 0,06 | 0,06 |
| 70% | 0,20 | 0,21 | 0,05 | 0,05 |
| 80% | 0,08 | 0,09 | 0,03 | 0,02 |
| 90% | 0,04 | 0,04 | 0,01 | 0,01 |
| 95% | 0,01 | 0,01 | 0,00 | 0,00 |
| 98% | 0,01 | 0,01 | 0,00 | 0,00 |
| na faixa | 97% | 94% | 100% | 100% |

A variante teve erro médio menor em 13 dos 36 pontos acima. Só entraria no forecast se ganhasse do modelo simples nas duas eleições.

## Desvios do modelo

Em logit: da parte do petismo entre os dois (swing) e do log da razão entre os votos dos dois no 2º turno e os válidos do 1º (comparecimento). Medido: o desvio de cada nível em torno do nível de cima, com o resultado verdadeiro (município e seção ponderados pelos votos). Usado: proporcional à parte dos outros candidatos no 1º turno do país, com um mínimo.

| Desvio | Medido em 2018 | Medido em 2022 | Usado em 2018 | Usado em 2022 | Usado em 2026 |
|---|--:|--:|--:|--:|--:|
| swing: região | 0,063 | 0,018 | 0,074 | 0,025 | 0,023 |
| swing: UF | 0,092 | 0,022 | 0,099 | 0,033 | 0,031 |
| swing: município | 0,089 | 0,028 | 0,099 | 0,033 | 0,031 |
| swing: seção | 0,179 | 0,101 | 0,200 | 0,116 | 0,114 |
| o que falta: país | – | – | 0,037 | 0,013 | 0,012 |
| o que falta: UF | – | – | 0,062 | 0,021 | 0,020 |
| o que falta: município | – | – | 0,062 | 0,021 | 0,020 |
| comparecimento: país | −0,021 | 0,003 | 0,030 | 0,030 | 0,030 |
| comparecimento: região | 0,025 | 0,016 | 0,030 | 0,030 | 0,030 |
| comparecimento: UF | 0,021 | 0,021 | 0,030 | 0,030 | 0,030 |
| comparecimento: município | 0,020 | 0,014 | 0,040 | 0,040 | 0,040 |
| comparecimento: seção | 0,039 | 0,030 | 0,060 | 0,060 | 0,060 |

Parte dos outros candidatos nos válidos do 1º turno: 24,7% em 2018, 8,4% em 2022, 7,8% em 2026.

## A noite de 2022, minuto a minuto

| Hora | Apurado | Forecast | Faixa de 80% | Chance de Lula |
|---|--:|--:|---|--:|
| 17h10 | 0,3% | 50,89% | 50,26% a 51,51% | 96,6% |
| 17h20 | 2,0% | 50,92% | 50,50% a 51,35% | 99,7% |
| 17h30 | 6,9% | 50,99% | 50,60% a 51,37% | mais de 99,9% |
| 17h40 | 13,1% | 51,01% | 50,65% a 51,36% | mais de 99,9% |
| 17h50 | 19,9% | 51,02% | 50,69% a 51,35% | mais de 99,9% |
| 18h00 | 27,3% | 51,02% | 50,71% a 51,32% | mais de 99,9% |
| 18h10 | 34,5% | 51,01% | 50,73% a 51,28% | mais de 99,9% |
| 18h20 | 42,5% | 50,99% | 50,75% a 51,23% | mais de 99,9% |
| 18h30 | 51,8% | 50,97% | 50,76% a 51,17% | mais de 99,9% |
| 18h40 | 62,2% | 50,95% | 50,79% a 51,11% | mais de 99,9% |
| 18h50 | 72,2% | 50,93% | 50,81% a 51,05% | mais de 99,9% |
| 19h00 | 82,1% | 50,92% | 50,84% a 51,00% | mais de 99,9% |
| 19h10 | 89,5% | 50,91% | 50,87% a 50,96% | mais de 99,9% |
| 19h20 | 93,5% | 50,91% | 50,88% a 50,94% | mais de 99,9% |
| 19h30 | 96,7% | 50,91% | 50,89% a 50,92% | mais de 99,9% |
| 19h40 | 97,7% | 50,90% | 50,89% a 50,91% | mais de 99,9% |
| 19h50 | 98,4% | 50,90% | 50,90% a 50,91% | mais de 99,9% |
| 20h00 | 98,9% | 50,90% | 50,90% a 50,91% | mais de 99,9% |
| 20h10 | 99,3% | 50,90% | 50,90% a 50,91% | mais de 99,9% |
| 20h20 | 99,5% | 50,90% | 50,90% a 50,91% | mais de 99,9% |

Urnas: 50,90%. Projeção da véspera: 51,73%.
