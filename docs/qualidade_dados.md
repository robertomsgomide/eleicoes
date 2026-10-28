# Qualidade dos dados

> Gerado por `uv run eleicoes processar` em 28/10/2026 15:19. Não editar à mão.

## 1. Boletins de urna × totais oficiais do TSE

Soma dos votos dos boletins de cada seção comparada com o total oficial do TSE (votação nominal por município e zona), candidato a candidato, no Brasil, em cada UF e em cada zona.

| Ano | Turno | Seções | Aptos | Comparecimento | Votos válidos | Petismo | Bolsonarismo | Diferença do oficial |
|---|---|--:|--:|--:|--:|--:|--:|---|
| 2018 | 1º | 454.490 | 147.306.295 | 117.364.560 | 107.050.673 | 29,28% | 46,03% | -76 votos em 1 zona(s), já conhecida ✅ |
| 2018 | 2º | 454.490 | 147.306.294 | 115.933.451 | 104.838.753 | 44,87% | 55,13% | nenhuma ✅ |
| 2022 | 1º | 472.028 | 156.453.354 | 123.682.372 | 118.229.719 | 48,43% | 43,20% | nenhuma ✅ |
| 2022 | 2º | 472.028 | 156.453.354 | 124.252.796 | 118.552.353 | 50,90% | 49,10% | nenhuma ✅ |
| 2026 | 1º | 499.206 | 158.745.007 | 125.275.835 | 119.300.788 | 45,16% | 47,03% | nenhuma ✅ |
| 2026 | 2º | 499.205 | 158.744.977 | 128.236.074 | 124.082.273 | 51,79% | 48,21% | nenhuma ✅ |

Divergências conhecidas, conferidas uma a uma (`DIVERGENCIAS_CONHECIDAS` em `src/eleicoes/tratamento/oficial.py`):

- 2018, 1º turno, MA, município 08591, zona 17: boletins − oficial = 13: -46, 17: -20, 12: -5, 15: -2, 30: -1, 45: -1, 18: -1.

Votos anulados de candidatos com candidatura indeferida (`nulos_tecnicos` em `config/eleicoes.toml`) são nominais nos boletins, mas o total oficial não os traz: contam como nulos, fora da conferência.

### Boletins de urna × votação por seção

O TSE publica os votos de cada seção em dois arquivos: a votação por seção, um dia depois da eleição, e os boletins de urna, dias depois. Comparados seção a seção, nos votos de cada campo, dos outros candidatos, brancos e nulos.

| Ano | Turno | Seções | Seções com alguma diferença |
|---|---|--:|---|
| 2026 | 1º | 499.206 | nenhuma ✅ |
| 2026 | 2º | 499.205 | nenhuma ✅ |

## 2. Horários

A chegada do boletim ao TSE está no horário de Brasília; abertura, encerramento e emissão do boletim estão no horário local da seção. O TSE só publica a chegada a partir de 2022.

| Ano | Turno | Seções com chegada do boletim | Primeira chegada | Última chegada | Seções com encerramento da urna |
|---|---|--:|---|---|--:|
| 2018 | 1º | 0,00% | – | – | 99,96% |
| 2018 | 2º | 0,00% | – | – | 99,97% |
| 2022 | 1º | 100,00% | 2022-10-02 02:09:48 | 2022-10-03 19:28:51 | 99,97% |
| 2022 | 2º | 100,00% | 2022-10-30 01:20:48 | 2022-10-31 00:17:31 | 99,99% |
| 2026 | 1º | 100,00% | 2026-10-04 17:08:44 | 2026-10-05 02:58:30 | 99,99% |
| 2026 | 2º | 100,00% | 2026-10-25 17:05:10 | 2026-10-25 23:21:40 | 99,99% |

## 3. Tipos de urna

| Ano | Turno | Tipo | Seções | Boletins por seção |
|---|---|---|--:|--:|
| 2018 | 1º | Apurada | 454.446 | 1 |
| 2018 | 1º | Não instalada | 40 | 1 |
| 2018 | 1º | Anulada | 2 | 1 |
| 2018 | 1º | Anulada e apurada em separado | 2 | 1 |
| 2018 | 2º | Apurada | 454.447 | 1 |
| 2018 | 2º | Não instalada | 40 | 1 |
| 2018 | 2º | Não apurada | 2 | 1 |
| 2018 | 2º | Anulada | 1 | 1 |
| 2022 | 1º | APURADA | 472.024 | 1 |
| 2022 | 1º | ANULADA | 4 | 1 |
| 2022 | 2º | APURADA | 472.027 | 1 |
| 2022 | 2º | ANULADA | 1 | 1 |
| 2026 | 1º | Apurada | 499.206 | 1 |
| 2026 | 2º | Apurada | 499.205 | 1 |

## 4. Locais de votação

Cada seção com votos procurada no arquivo de locais de votação do mesmo ano e turno. Coordenada válida: informada pelo TSE, a até 2 km do município (malha do IBGE) e não repetida em 3 ou mais locais de nomes diferentes do município.

| Ano | Turno | Seções com votos | Achadas no arquivo de locais | Votos válidos em seções com coordenada válida do TSE |
|---|---|--:|--:|--:|
| 2018 | 1º | 453.706 | 100,00% | 82,21% |
| 2018 | 2º | 453.706 | 100,00% | 82,38% |
| 2022 | 1º | 471.010 | 100,00% | 94,43% |
| 2022 | 2º | 471.010 | 100,00% | 94,42% |
| 2026 | 1º | 497.897 | 100,00% | 99,42% |
| 2026 | 2º | 497.897 | 100,00% | 99,41% |

## 5. Coordenadas completadas para o mapa

Como cada local de votação recebeu a posição (`src/eleicoes/tratamento/coordenadas.py`), em % do eleitorado dos locais (fora o exterior). Métodos em ordem de preferência.

| Método | 2018 | 2022 | 2026 |
|---|--:|--:|--:|
| 0. coordenada do TSE para o próprio local | 81,78% (73.949 locais) | 94,38% (84.618 locais) | 99,43% (92.746 locais) |
| 1. mesmo local em outra eleição | 16,52% (15.557 locais) | 4,60% (5.573 locais) | 0,09% (125 locais) |
| 2. mesmo nome no município | 0,14% (217 locais) | 0,13% (175 locais) | 0,03% (33 locais) |
| 3. mesmo endereço no município | 0,04% (124 locais) | 0,02% (26 locais) | 0,00% (7 locais) |
| 4. aproximada pelo bairro | 0,70% (1.191 locais) | 0,39% (491 locais) | 0,15% (217 locais) |
| 5. aproximada pela zona eleitoral | 0,83% (2.292 locais) | 0,49% (1.291 locais) | 0,30% (998 locais) |
| 6. aproximada pelo município | 0,00% (4 locais) | – | – |
| 7. ponto dentro do município | 0,01% (6 locais) | 0,00% (5 locais) | 0,00% (5 locais) |

Erro de cada método, medido nos locais que têm coordenada do TSE: a coordenada é escondida e o método tenta encontrá-la. Distância entre a posição dada pelo método e a do TSE; n = locais em que o método se aplica.

| Método | 2018: mediana · 90% até · acima de 1 km | 2022: mediana · 90% até · acima de 1 km | 2026: mediana · 90% até · acima de 1 km |
|---|---|---|---|
| 1. mesmo local em outra eleição | 0,00 km · 0,00 km · 0,40% (n = 73.423) | 0,00 km · 0,00 km · 0,10% (n = 84.116) | 0,00 km · 0,03 km · 1,60% (n = 83.403) |
| 2. mesmo nome no município | 0,00 km · 0,11 km · 6,70% (n = 9.173) | 0,00 km · 0,31 km · 7,40% (n = 8.403) | 0,01 km · 0,66 km · 9,00% (n = 7.247) |
| 3. mesmo endereço no município | 0,00 km · 0,05 km · 2,30% (n = 4.567) | 0,00 km · 0,07 km · 2,60% (n = 4.326) | 0,00 km · 0,08 km · 2,60% (n = 4.036) |
| 4. aproximada pelo bairro | 0,45 km · 1,14 km · 13,60% (n = 25.321) | 0,45 km · 1,12 km · 13,30% (n = 28.221) | 0,45 km · 1,13 km · 13,40% (n = 30.375) |
| 5. aproximada pela zona eleitoral | 3,37 km · 21,44 km · 80,30% (n = 73.817) | 3,20 km · 21,07 km · 79,60% (n = 84.457) | 3,29 km · 21,75 km · 80,10% (n = 92.574) |
| 6. aproximada pelo município | 5,14 km · 22,77 km · 83,80% (n = 73.837) | 4,89 km · 22,28 km · 83,00% (n = 84.477) | 4,96 km · 22,84 km · 83,40% (n = 92.594) |

## 6. Municípios

- Tabela de códigos TSE → IBGE: 5.757 municípios, 186 deles no exterior.
- Municípios brasileiros sem código IBGE: 0 na tabela; 0 nas tabelas de seções.
