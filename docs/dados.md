# Dados

Como os dados chegam e o que cada tabela contém. Os números de conferência ficam em
[qualidade_dados.md](qualidade_dados.md), gerado a cada `uv run eleicoes processar`.

```bash
uv run eleicoes baixar      # dados/bruto (≈8 GB para 2018, 2022 e 2026; retoma se interrompido)
uv run eleicoes processar   # dados/processado + docs/qualidade_dados.md
uv run pytest               # inclui a conferência contra os totais oficiais
```

## Fontes (`dados/bruto`)

Origem, tamanho e SHA-512 de cada arquivo ficam em `dados/bruto/manifesto.csv` (versionado no git).

| Fonte | Pasta | Origem | Conferência |
|---|---|---|---|
| Boletins de urna (bweb), 1º e 2º turno, um zip por UF + exterior | `tse/boletins_urna/<ano>/` | dadosabertos.tse.jus.br, conjunto `resultados-<ano>-boletim-de-urna` | SHA-512 publicado pelo TSE |
| Votação por seção, só Presidente (antes dos boletins de urna; depois, conferência deles: 2026) | `tse/votacao_secao/<ano>/` | `cdn.tse.jus.br/.../votacao_secao/votacao_secao_<ano>_BR.zip` | tamanho |
| Locais de votação, com coordenadas (também 2016, 2020 e 2024, só para completar coordenadas) | `tse/locais_votacao/<ano>/` | `cdn.tse.jus.br/.../eleitorado_local_votacao_<ano>.zip` | tamanho |
| Totais oficiais de Presidente por município e zona | `tse/totais_oficiais/<ano>/` | só o arquivo `_BR.csv` de dentro de `votacao_candidato_munzona_<ano>.zip`, lido por partes sem baixar o zip | CRC do zip |
| Códigos de município TSE → IBGE | `tse/municipios/` | `resultados.tse.jus.br/.../mun-e006257-cm.json` (o de 2026; os de anos anteriores saíram do ar, e os códigos do TSE não mudam) | JSON válido |
| Malhas de municípios, UFs e regiões (qualidade intermediária); a de municípios também em TopoJSON, para o mapa do site | `ibge/malhas/` | `servicodados.ibge.gov.br/api/v3/malhas` | JSON válido |
| Lista de municípios do IBGE | `ibge/municipios.json` | `servicodados.ibge.gov.br/api/v1/localidades/municipios` | JSON válido |

Os zips do TSE trazem o dicionário oficial de cada arquivo (`leiame.pdf`).

## Tabelas (`dados/processado`, Parquet)

Os dois campos estudados vêm de `config/eleicoes.toml`: **petismo** = 13 (Haddad em 2018, Lula em 2022 e 2026);
**bolsonarismo** = 17 em 2018 (Jair Bolsonaro, PSL) e 22 em 2022 e 2026 (PL).

### `tse/secoes/<ano>_t<turno>.parquet` — uma linha por seção

| Coluna | Descrição |
|---|---|
| `ano`, `turno` | |
| `sg_uf`, `regiao` | UF (ZZ = exterior) e região do IBGE |
| `cd_municipio`, `cd_ibge`, `nm_municipio` | código do TSE (5 dígitos), código do IBGE (7; vazio no exterior), nome |
| `nr_zona`, `nr_secao` | identificam a seção junto com o município |
| `nr_local_votacao` | liga com `locais_votacao` |
| `qt_aptos`, `qt_comparecimento`, `qt_abstencoes` | eleitorado da seção e quem votou |
| `votos_petismo`, `votos_bolsonarismo`, `votos_outros` | votos nominais; somam `votos_validos` |
| `votos_brancos`, `votos_nulos` | |
| `qt_boletins`, `tipo_urna` | quantos boletins a seção teve e de que tipo (APURADA, ANULADA…) |
| `secoes_agregadas` | seções que votaram nesta urna (os votos delas estão aqui) |
| `qt_eleitores_biometria_nh` | eleitores liberados sem reconhecimento biométrico |
| `dt_abertura`, `dt_encerramento`, `dt_emissao_bu` | **horário local da seção** |
| `dt_bu_recebido` | chegada do boletim ao TSE, **horário de Brasília**; só existe a partir de 2022 |

### `tse/votacao_secao/<ano>_t<turno>.parquet` — uma linha por seção, da votação por seção

A fonte dos votos por seção dos turnos ainda sem boletins de urna e, depois deles, uma conferência (no 1º turno de
2026, as duas tabelas dão os mesmos votos em todas as seções). As mesmas colunas de votos de `secoes` (`votos_petismo`,
`votos_bolsonarismo`, `votos_outros`, `votos_validos`, `votos_brancos`, `votos_nulos`), com `ano`, `turno`,
`sg_uf`, `regiao`, `cd_municipio`, `cd_ibge`, `nm_municipio`, `nr_zona`, `nr_secao` e `nr_local_votacao`; sem
horários, eleitorado e comparecimento. Votos de candidatos com candidatura indeferida (`nulos_tecnicos` em
`config/eleicoes.toml`) contam como nulos, como no resultado oficial. Quando há boletins, as análises usam `secoes`.

### `tse/votos_secao/<ano>_t<turno>.parquet` — uma linha por seção e votável

`ano`, `turno`, `sg_uf`, `cd_municipio`, `nr_zona`, `nr_secao`, `nr_votavel` (número do candidato; 95 = branco;
96 = nulo), `nm_votavel`, `cd_tipo_votavel` (1 nominal, 2 branco, 3 nulo), `qt_votos`.

### `tse/locais_votacao/<ano>.parquet` — uma linha por seção e turno

`ano`, `turno`, chave da seção, `tipo_secao` (Principal/Agregada), `nr_secao_principal`, `nr_local_votacao`,
`nm_local_votacao`, `tipo_local`, `endereco`, `bairro`, `cep`, `lat`, `lon`, `coord_ok`, `qt_eleitores`,
`situacao_secao`. Coordenadas inválidas (ausentes, −1, 0/0, ou fora do território para seções no Brasil)
ficam vazias e com `coord_ok = false`.

### `mapa/locais_<ano>.parquet` — um local de votação por linha, com coordenadas completadas

Os locais com seções no ano (fora o exterior), ligados às seções pelo arquivo de locais de votação do mesmo ano.
`ano`, `sg_uf`, `regiao`, `cd_municipio`, `cd_ibge`, `nm_municipio`, `nr_zona`, `nr_local_votacao`, `nm_local`,
`endereco`, `bairro`, `eleitores`; `lat`, `lon` (a posição final), `nivel` e `metodo` (como a posição foi obtida:
0 `tse`, 1 `outra_eleicao`, 2 `mesmo_nome`, 3 `mesmo_endereco`, 4 `bairro`, 5 `zona`, 6 `municipio`, 7 `poligono`),
`precisao` (0 do TSE, 1 posição do próprio local, 2 bairro, 3 zona ou município), `raio_km` (incerteza das
posições aproximadas), `ano_coordenada` (de que eleição veio a coordenada, nos métodos 1 a 3); e, para cada turno,
`t<turno>_secoes`, `t<turno>_validos`, `t<turno>_petismo`, `t<turno>_bolsonarismo`, `t<turno>_outros`.

Os métodos estão em `src/eleicoes/tratamento/coordenadas.py`. O erro de cada um, medido escondendo a coordenada
dos locais que a têm, fica em `mapa/validacao_coordenadas.json` e em [qualidade_dados.md](qualidade_dados.md).

### `tse/totais_oficiais/<ano>.parquet` — o gabarito

Votos nominais oficiais de Presidente por município, zona e candidato: `ano`, `turno`, `sg_uf`, `cd_municipio`,
`nr_zona`, `nr_candidato`, `nm_urna_candidato`, `qt_votos`, `st_voto_em_transito` (2022), `ds_sit_tot_turno`.

### `referencia/municipios.parquet`

`cd_municipio` (TSE), `cd_ibge`, `nm_municipio` (nome oficial do IBGE; no exterior, o do TSE), `nm_municipio_tse`,
`sg_uf`, `regiao`.

## Pesquisas eleitorais

```bash
uv run eleicoes pesquisas              # baixa o que faltar e processa 2018, 2022 e 2026
uv run eleicoes pesquisas --atualizar  # pega a revisão atual da Wikipedia e o registro atual do TSE
uv run eleicoes atualizar              # só 2026: revisão nova? confere antes de guardar e refaz o site
```

Até o 2º turno de 2026, `atualizar` roda sozinho a cada 2 horas, no GitHub Actions (`.github/workflows/site.yml`;
os dados que ele usa estão descritos em [dados/README.md](../dados/README.md)). A revisão nova só é
guardada depois de comparada com a anterior (`src/eleicoes/atualizacao.py`): mais de 2 pesquisas sumindo ou
mudando de uma vez, um número já publicado mudando mais de 3 pontos ou uma pesquisa nova impossível (ou, no 2º
turno, a mais de 8 pontos da projeção) seguram a revisão até alguém conferir. Sem pesquisa nova, a revisão
guardada fica e o `.json` dela ganha `consultado_em`, a última vez em que ela ainda batia com a página: a projeção
vai até esse dia.

| Fonte | Pasta | Origem |
|---|---|---|
| Tabelas de pesquisas (HTML da página, com a revisão em `.json` ao lado) | `wikipedia/` | Wikipedia em português, "Pesquisas de opinião para a eleição presidencial no Brasil em <ano>", via API |
| Registro de pesquisas (PesqEle): número, empresa, datas, amostra, metodologia | `tse/pesquisas/<ano>/` | `cdn.tse.jus.br/.../pesquisa_eleitoral/pesquisa_eleitoral_<ano>.zip` |

Tabelas em `dados/processado/pesquisas/`:

- `linhas_<ano>.parquet`: cada linha lida das tabelas (cada cenário de cada pesquisa), com a seção da página
  e a posição de origem, para auditoria.
- `pesquisas_<ano>.parquet`: uma linha por pesquisa e turno: `instituto`, `contratante`, `inicio`, `fim`,
  `amostra`, `margem`, `petismo` e `bolsonarismo` (% do total), `petismo_validos` e `bolsonarismo_validos`
  (% dos válidos), `nao_validos`, `registro` (protocolo no TSE), `ligacao` (como foi feita), `empresa_tse`,
  `amostra_tse`, `metodologia`.

Critérios, ligação com o registro e conversão para votos válidos: ver a Metodologia do site. Cobertura e
pesquisas sem registro: [qualidade_pesquisas.md](qualidade_pesquisas.md).

**Licença.** A base de pesquisas deriva das tabelas da Wikipedia e por isso segue a licença dela,
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/): pode ser reutilizada citando a fonte e
mantendo a mesma licença.

## Dados do site (`site/src/data`, JSON)

Gerados por `uv run eleicoes site` a partir das tabelas acima e de `dados/bruto/ao_vivo`; vão para o git.

| Arquivo | Conteúdo |
|---|---|
| `eleicoes.json` | campos, eleições (datas, horário de divulgação, candidatos) e regiões, de `config/eleicoes.toml` |
| `resultados.json` | resultado final de cada turno no Brasil, por região e por UF. Votos dos candidatos: total oficial; eleitorado, comparecimento, brancos e nulos: boletins. Turnos ainda sem boletins ou total oficial: arquivos finais do site de resultados |
| `apuracao_<ano>_t<turno>.json` | a apuração minuto a minuto: `t` (minutos desde o início da divulgação) e, para o Brasil e cada região, seções, válidos, petismo e bolsonarismo acumulados; `tipo` (exata/estimada), `viradas`, `t999` (minuto em que 99,9% das seções tinham chegado) |
| `noite_<ano>_t<turno>.json` | a noite de um turno como foi gravada ao vivo (leituras oficiais e estimativa da noite), só enquanto o TSE não publica os boletins de urna daquele turno; com eles, entra `apuracao_<ano>_t<turno>.json` |
| `pesquisas_<ano>.json` | por turno: as pesquisas (em % do total e dos válidos), a tendência diária, a média da semana final, o resultado e a última pesquisa de cada instituto com o erro. No 2º turno, a tendência tem dois trechos, antes e depois do 1º turno (`segmento` 0 e 1; data do 1º turno em `primeiro_turno`). CC BY-SA 4.0 |
| `projecao.json` | a projeção do 2º turno (`src/eleicoes/modelos/projecao.py`) de cada ano com 1º turno e pesquisas de 2º turno: o 1º turno, o ponto de partida (com cada pesquisa pareada), a projeção de cada dia entre os turnos (parte do petismo nos válidos, desvio, faixa de 80%, chance, peso das pesquisas), regiões e UFs no último dia, as urnas (2018 e 2022), a validação e os parâmetros. Em 2018 e 2022, é a projeção refeita só com o que se sabia em cada dia |
| `validacao_estimativa.json` | o teste do método de estimativa de 2018 aplicado a 2022 (com os atrasos do outro turno) e a 2026 (com os do 1º turno de 2022) |
| `mapa/malha.json` | municípios do IBGE em TopoJSON simplificado (fronteiras compartilhadas; `id` = código IBGE) |
| `mapa/municipios.json` | nome, UF, eleitorado e posição do rótulo (centro dos locais de votação) de cada município |
| `mapa/locais_<ano>.json` | cada ponto de votação (locais do mesmo prédio juntos): posição em graus × 10⁴, município e coordenadas em diferenças para o anterior, precisão da posição, raio das posições aproximadas e votos de cada campo por turno |
| `mapa/nomes_<ano>.json` | nome de cada ponto, na mesma ordem (o site só carrega quando alguém passa o mouse no mapa) |
| `mapa/resumo.json` | por ano e turno, a distribuição dos votos pela % do bolsonarismo no local; a posição dos locais por método e o erro de cada método |

## Cuidados

- **Fusos.** A chegada do boletim está no horário de Brasília; abertura, encerramento e emissão, no horário local
  da seção. Evidência (2º turno de 2022): o menor intervalo entre emissão e chegada é de ~0–7 min nas UFs no
  horário de Brasília, ~60 min nas que estão 1h atrás (MT, MS, RO, RR, AM) e ~126 min no Acre (2h atrás). No exterior,
  os horários locais variam por país. A conversão para um único fuso fica para a Etapa 2.
- **Horário de votação.** Em 2022 o país todo votou das 8h às 17h de Brasília; em 2018, das 8h às 17h no horário local.
- **2018 não tem a chegada dos boletins.** A linha do tempo da apuração de 2018 será aproximada e rotulada (Etapa 2).
- **Seções agregadas** votam na urna da seção principal; os votos estão no boletim da principal.
- **Exterior (ZZ):** os "municípios" são cidades fora do Brasil, sem código IBGE.
- **Seções sem votação.** Em 2018, 40 seções no exterior não foram instaladas (nos dois turnos) e 2 seções
  (ES e PR) não foram apuradas no 2º turno, todas sem comparecimento. Estão em `secoes` com zero votos e não
  aparecem em `votos_secao`.
- **Votos anulados.** Seções de tipo "Anulada" ou "Anulada e apurada em separado" (2 na BA no 1º turno de 2018,
  com 746 votos sob o votável 97) não somam votos a nenhum candidato nem aos válidos, como no total oficial.
- **Uma divergência conhecida com o oficial:** no 1º turno de 2018, em Pastos Bons (MA), zona 17, o total oficial
  tem 76 votos a mais que os boletins publicados (Haddad +46, Bolsonaro +20, outros +10). Todas as seções principais
  da zona estão nos boletins e batem internamente; a origem dos 76 votos não aparece nos arquivos. Está registrada em
  `DIVERGENCIAS_CONHECIDAS` (`src/eleicoes/tratamento/oficial.py`); qualquer outra diferença faz os testes falharem.
- **Coordenadas.** O TSE dá coordenada válida para 82% do eleitorado de 2018 (quase nada em MG e ES), 94% de
  2022 e 99% de 2026. As que faltam são completadas (`mapa/locais_<ano>.parquet`): primeiro com a posição do mesmo
  local em outra eleição, de 2016 a 2026, e só no fim com aproximações pelo bairro, pela zona ou pelo município.
  Coordenadas fora do município ou repetidas em vários locais diferentes (a posição padrão do centro da cidade)
  também são descartadas; há casos de municípios homônimos, como Tapiraí (MG), geocodificado em Tapira (MG).
- **Número do local de votação.** Em cerca de 1% das seções, o número do local no arquivo de votos difere do arquivo
  de locais (que o TSE regera anos depois). O local de cada seção vem do arquivo de locais, pela seção, que bate
  em 100% dos casos.
- **2026.** O total oficial por município e zona saiu em 05/10/2026 sem os votos de Presidente e foi republicado
  com eles em 07/10. Os boletins do 1º turno (publicados em 06/10) batem com ele em todas as zonas e com a votação
  por seção em todas as seções. Os votos de Leonardo Alves de Araújo (28), com candidatura indeferida, são nulos
  (nulos técnicos): nominais nos boletins e na votação por seção, ausentes do total oficial. O eleitorado do
  exterior nos boletins (916.039) é 495 menor que no resultado final do site de resultados (916.534); votos,
  comparecimento, brancos e nulos são iguais.
- **Formato dos boletins de 2026.** Datas em `aaaa-mm-dd hh:mm:ss` (antes, `dd/mm/aaaa`) e duas colunas com outro
  nome: `DS_SECOES_AGREGADAS` (antes `DS_AGREGADAS`) e `QT_ELEI_BIOM_SEM_HABILITACAO` (antes
  `QT_ELEITORES_BIOMETRIA_NH`). O processamento lê os dois formatos.
- **Arquivo de 2018 com aspas fora do padrão** (ex.: `"PASTOR JOÃO CARLOS "O JUCÁ""`): os boletins são lidos
  separando só por `;` e tirando as aspas das pontas de cada campo.
