---
title: Início
toc: false
---

```js
import {COR, chances} from "./components/graficos.js";
import {data, num, pct} from "./components/formato.js";
const eleicoes = FileAttachment("data/eleicoes.json").json();
const resultados = FileAttachment("data/resultados.json").json();
const projecao = FileAttachment("data/projecao.json").json();
```

```js
const parte = (d, c) => (100 * d[c]) / d.validos;
const e26 = eleicoes.eleicoes["2026"];
const ch26 = chances(projecao.anos["2026"].atual);
const fav26 = ch26.petismo >= 50 ? "petismo" : "bolsonarismo";
function cartao(ano, turno, rodape) {
  const e = eleicoes.eleicoes[ano];
  const d = resultados[ano][turno].Brasil;
  const ordem = ["petismo", "bolsonarismo"].sort((a, b) => d[b] - d[a]);
  return html`<a class="card cartao" href="./${ano}">
    <h2>${ano}</h2>
    <h3>${turno}º turno · ${data(e[`turno${turno}`].data)}</h3>
    ${ordem.map((c) => html`<div class="placar"><div class="quem"><span class="amostra" style="background:${COR[c]}"></span>${e[c].nome}</div>
      <div class="grande">${pct(parte(d, c))}</div><div class="detalhe">${num(d[c])} votos</div></div>`)}
    ${rodape ? html`<p class="nota">${rodape}</p>` : ""}
  </a>`;
}
```

# Lulismo/Petismo × Bolsonarismo

<p class="lead">Um estudo de dados sobre as eleições para Presidente de 2018, 2022 e 2026, a partir dos arquivos públicos do TSE: como cada apuração se desenrolou minuto a minuto, onde cada campo venceu, local de votação por local de votação, e o que as pesquisas previam.</p>

<div class="grid grid-cols-3">
  ${cartao("2018", "2")}
  ${cartao("2022", "2")}
  ${cartao("2026", "1", `2º turno em ${data(e26.turno2.data)}. Na projeção, ${e26[fav26].nome} tem ${pct(ch26[fav26], 0)} de chance de vencer.`)}
</div>

## O que há aqui

- **2018, 2022 e 2026**: o resultado no país e em cada região; o mapa dos votos, com cada local de votação do país; a apuração ao longo da noite, em % dos votos válidos, em votos e na vantagem de um sobre o outro, inclusive o momento exato das viradas; e as pesquisas eleitorais do ano comparadas com as urnas, instituto por instituto.
- **2º turno de 2026**: a <a href="./2026#projecao-do-2-turno">projeção do resultado</a>, a partir do 1º turno seção por seção e das pesquisas, com a chance de cada candidato, no país, em cada região e em cada estado. Atualizada a cada nova pesquisa.
- **Comparações**: as três apurações lado a lado, o erro das pesquisas em cada turno e quanto os locais de votação pendem para um lado em cada eleição.
- **Metodologia**: de onde vêm os números, como foram conferidos com o resultado oficial e com o registro de pesquisas do TSE, como cada local de votação ganhou sua posição no mapa, como a projeção é feita e como teria se saído em 2018 e 2022, e o que é exato ou estimado.

## Em construção

- 2º turno de 2026: acompanhamento ao vivo da apuração, com a previsão de como a curva vai evoluir a partir do que já foi apurado.

<style>
/* O cartão inteiro é um link: o texto fica na cor normal (a cor de link é azul, que aqui é a do bolsonarismo) */
a.card.cartao { display: grid; gap: 14px; color: var(--theme-foreground); text-decoration: none; }
a.card.cartao:hover { border-color: var(--theme-foreground-faint); }
a.card.cartao h2, a.card.cartao h3 { margin: 0; }
</style>
