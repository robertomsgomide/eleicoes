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
pedaços que só se acrescentam (formato em `src/eleicoes/ao_vivo/coletor.py`), e mantém lá um `dados.json` igual ao do
painel local. No fim, `uv run eleicoes juntar` junta os três em `bruto/ao_vivo/ele2026-6258/`, com um commit no `main`:

- `leituras_oficiais.json`: cada atualização do total do país (o mesmo formato do 1º turno, com mais totais);
- `leituras_ufs.json`: idem, de cada UF e do exterior;
- `municipios.jsonl.gz`: cada atualização do resultado de cada município;
- `secoes.csv.gz`: o horário de chegada de cada seção como o TSE mostrava na primeira vez que um coletor a viu (o TSE
  reescreve esses horários depois da apuração);
- `final/` e `historico_estimado.*`, como no 1º turno, e `coleta.json`, com os jobs de cada coletor.

Depois de juntados, os ramos `ao-vivo-*` podem ser apagados. O ensaio (push no ramo `ensaio-apuracao`) grava nos
ramos `ensaio-a`, `-b`, `-c` e junta no `ensaio-juntado`, que também podem ser apagados.
