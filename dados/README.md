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

A rodada a cada 2 horas no GitHub Actions (`.github/workflows/site.yml`) não tem os gigabytes daqui. O que ela
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
