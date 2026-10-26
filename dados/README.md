# dados/

Quase nada aqui vai para o git: tudo é gerado ou baixado pelos comandos do projeto. A exceção é
`bruto/ao_vivo/`, gravado durante as apurações, que o TSE não deixa baixar de novo depois (ele
reescreve os horários das seções quando a apuração termina). Essa pasta é versionada.

| Pasta | O que guarda | Regra |
|---|---|---|
| `bruto/` | O que veio de fora, exatamente como veio: arquivos do TSE, IBGE e pesquisas, e as leituras gravadas ao vivo durante a apuração | Nunca editar. Cada download tem a origem e o hash registrados. As leituras ao vivo não podem ser baixadas de novo depois, então guarde cópia |
| `processado/` | Tabelas limpas (Parquet) geradas a partir de `bruto/` | Pode ser apagado e regenerado |
| `cache/` | Cópias temporárias para acelerar a coleta | Pode ser apagado a qualquer momento |

Organização dentro de cada pasta: `<fonte ou uso>/<ano ou eleição>/...`, por exemplo
`bruto/ao_vivo/ele2026-6257/leituras_oficiais.json` (eleição 6257 = 1º turno de 2026).

`atualizar.log` guarda o que cada rodada de `uv run eleicoes atualizar` fez. `cache/atualizar.json` lembra a
última revisão da Wikipedia conferida e a última recusada, para não baixar a mesma revisão de novo a cada rodada.

## Na nuvem: o ramo `dados`

A rodada de cada hora no GitHub Actions (`.github/workflows/site.yml`) não tem os gigabytes daqui. O que ela
precisa e não muda até o 2º turno fica no ramo `dados` do repositório, com um commit só, e é copiado por cima
desta pasta antes da rodada:

- `processado/tse/secoes/` e `processado/tse/totais_oficiais/` dos turnos já apurados;
- `processado/pesquisas/pesquisas_2018.parquet` e `_2022`, com as revisões da Wikipedia delas
  (`bruto/wikipedia/pesquisas_presidente_<ano>.json`);
- o registro de pesquisas do TSE de 2026 (`bruto/tse/pesquisas/2026/`), para quando o download falhar.

O que muda de uma rodada para outra (a revisão de 2026 guardada, o registro do TSE atual, as pesquisas
processadas de 2026 e `cache/atualizar.json`) passa pelo cache do Actions. Se o cache sumir, o comando refaz a
revisão que está no site. Quando estes dados mudarem (depois do 2º turno, por exemplo), o ramo é refeito por
inteiro, também com um commit só.

## Na nuvem: a noite do 2º turno (ramos `ao-vivo-a`, `-b` e `-c`)

Durante a apuração de 25/10, cada um dos três coletores (`.github/workflows/apuracao.yml`) grava no seu ramo, em
pedaços que só se acrescentam (formato em `src/eleicoes/ao_vivo/coletor.py`), e mantém lá o que a página de 2026 lê
(`src/eleicoes/ao_vivo/painel.py`): `dados.json` (a apuração com as leituras oficiais do país e das UFs, o forecast do
resultado final e o histórico dele na noite) e `mapa.json` (o apurado e o swing estimado de cada município). Para o
forecast, o job copia do ramo `dados` as seções do 1º turno (`processado/tse/secoes/2026_t1.parquet`). No fim,
`uv run eleicoes juntar` junta os três em `bruto/ao_vivo/ele2026-6258/`, com um commit no `main`:

- `leituras_oficiais.json`: cada atualização do total do país (o mesmo formato do 1º turno, com mais totais);
- `leituras_ufs.json`: idem, de cada UF e do exterior;
- `municipios.jsonl.gz`: cada atualização do resultado de cada município;
- `secoes.csv.gz`: o horário de chegada de cada seção como o TSE mostrava na primeira vez que um coletor a viu (o TSE
  reescreve esses horários depois da apuração);
- `final/` e `historico_estimado.*`, como no 1º turno, e `coleta.json`, com os jobs de cada coletor;
- `previsoes.json`: o forecast que os coletores mostraram na noite, um por atualização do total do país (o feito com
  mais seções lidas, quando mais de um coletor o fez), e `mapa.json`, o `mapa.json` do fim da noite. Os dois foram
  acrescentados em 26/10/2026, de uma cópia dos três ramos, com `uv run eleicoes juntar <ramos>` (a gravação já estava
  juntada; o comando só acrescenta o que falta).

O site lê só o que foi juntado aqui (`uv run eleicoes site`; `src/eleicoes/analises/noite.py`): os ramos `ao-vivo-*`
já podem ser apagados. O ensaio (push no ramo `ensaio-apuracao`) grava nos ramos `ensaio-a`, `-b`, `-c` e junta no
`ensaio-juntado`, que também podem ser apagados.
