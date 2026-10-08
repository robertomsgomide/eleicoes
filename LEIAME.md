# Ramo `dados`

Os dados que a atualização automática do site usa e que não ficam no `main`: vêm dos arquivos do TSE (gigabytes) e
não mudam até o 2º turno. A rodada do GitHub Actions (`.github/workflows/site.yml`, no `main`) copia a pasta
`dados/` deste ramo por cima da do `main` antes de rodar `uv run eleicoes atualizar`.

| Arquivo | O que é | Gerado por |
|---|---|---|
| `dados/processado/tse/secoes/<ano>_t<turno>.parquet` | uma linha por seção, com os votos de cada campo: 2018 e 2022 nos dois turnos, 2026 no 1º | `uv run eleicoes processar` |
| `dados/processado/tse/totais_oficiais/<ano>.parquet` | votos oficiais de Presidente por município, zona e candidato | `uv run eleicoes processar` |
| `dados/processado/pesquisas/pesquisas_<ano>.parquet` | as pesquisas de 2018 e 2022, uma por turno | `uv run eleicoes pesquisas` |
| `dados/bruto/wikipedia/pesquisas_presidente_<ano>.json` | a revisão da Wikipedia de onde vêm as pesquisas de 2018 e 2022 | `uv run eleicoes pesquisas` |
| `dados/bruto/tse/pesquisas/2026/pesquisa_eleitoral_2026.zip` | o registro de pesquisas do TSE de 07/10/2026, para quando o download falhar | `uv run eleicoes pesquisas` |

Fontes: TSE (dados abertos) e Wikipedia em português. A base de pesquisas deriva das tabelas da Wikipedia e segue
a licença dela, CC BY-SA 4.0. As colunas estão descritas em `docs/dados.md`, no `main`.

O ramo tem um commit só e é refeito por inteiro quando os dados mudam (depois do 2º turno, por exemplo).
