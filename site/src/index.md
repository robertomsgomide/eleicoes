---
title: Início
toc: false
---

```js
import {polos} from "./components/polos.js";
const eleicoes = FileAttachment("data/eleicoes.json").json();
const resultados = FileAttachment("data/resultados.json").json();
```

```js
// Cada cartão leva à página do ano e mostra o eleitorado em pontos (components/polos.js), somando os turnos já
// apurados: em 2026, até a eleição, só o 1º.
const ANOS = ["2018", "2022", "2026"];
const antesDo2 = ANOS.filter((ano) => !resultados[ano]["2"]);
function cartao(ano, i) {
  const e = eleicoes.eleicoes[ano];
  const turnos = Object.values(resultados[ano]).map((t) => t.Brasil);
  const [, mes, dia] = e.turno2.data.split("-");
  return html`<a class="card cartao" href="./${ano}" aria-label=${`${ano}: ${e.petismo.nome} × ${e.bolsonarismo.nome}`}>
    <div class="cartao-topo">
      <span class="cartao-ano">${ano}</span>
      ${turnos.length < 2 ? html`<span class="selo">2º turno em ${+dia}/${+mes}</span>` : ""}
      <span class="cartao-seta" aria-hidden="true">→</span>
    </div>
    ${polos(turnos, {semente: +ano, atraso: 0.15 * i})}
    <div class="cartao-nomes"><span>${e.petismo.nome}</span><span>${e.bolsonarismo.nome}</span></div>
  </a>`;
}
```

# Lulismo/Petismo × Bolsonarismo

<p class="lead">Um estudo de dados sobre as eleições para Presidente de 2018, 2022 e 2026, a partir dos arquivos públicos do TSE: como cada apuração se desenrolou minuto a minuto, onde cada campo venceu, local de votação por local de votação, e o que as pesquisas previam.</p>

<div class="grid grid-cols-3">
  ${cartao("2018", 0)}
  ${cartao("2022", 1)}
  ${cartao("2026", 2)}
</div>

<p class="nota">Cada ponto é 0,5% do eleitorado, somando o 1º e o 2º turno: vermelho para o lulismo/petismo, azul para o bolsonarismo, violeta para os outros candidatos e cinza para brancos, nulos e abstenções.${antesDo2.length ? ` Em ${antesDo2.join(" e ")}, até o 2º turno, só o 1º.` : ""}</p>

## O que há aqui

- **2018, 2022 e 2026**: o resultado no país e em cada região; o mapa dos votos, com cada local de votação do país; a apuração ao longo da noite, em % dos votos válidos, em votos e na vantagem de um sobre o outro, inclusive o momento exato das viradas; e as pesquisas eleitorais do ano comparadas com as urnas, instituto por instituto.
- **2º turno de 2026**: a <a href="./2026#projecao-do-2-turno">projeção do resultado</a>, a partir do 1º turno seção por seção e das pesquisas, com a chance de cada candidato, no país, em cada região e em cada estado. Atualizada a cada nova pesquisa.
- **Comparações**: as três apurações lado a lado, o erro das pesquisas em cada turno e quanto os locais de votação pendem para um lado em cada eleição.
- **Metodologia**: de onde vêm os números, como foram conferidos com o resultado oficial e com o registro de pesquisas do TSE, como cada local de votação ganhou sua posição no mapa, como a projeção é feita e como teria se saído em 2018 e 2022, e o que é exato ou estimado.

## Em construção

- 2º turno de 2026: acompanhamento ao vivo da apuração, com a previsão de como a curva vai evoluir a partir do que já foi apurado.

<style>
/* O cartão inteiro é um link: o texto fica na cor normal (a cor de link é azul, que aqui é a do bolsonarismo) */
a.card.cartao { display: grid; gap: 10px; color: var(--theme-foreground); text-decoration: none; transition: border-color 0.3s, transform 0.3s; }
a.card.cartao:hover { border-color: var(--theme-foreground-faint); transform: translateY(-2px); }
a.card.cartao:focus-visible { outline: 2px solid var(--theme-foreground-focus); outline-offset: 2px; }
.cartao-topo { display: flex; align-items: center; gap: 10px; }
.cartao-ano { font: 600 1.6rem/1 var(--sans-serif); letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.cartao-seta { margin-left: auto; color: var(--theme-foreground-muted); transition: transform 0.3s, color 0.3s; }
a.card.cartao:hover .cartao-seta { transform: translateX(4px); color: var(--theme-foreground); }
/* cada nome embaixo do disco do seu campo: os discos ficam a 1/4 e a 3/4 da largura */
.cartao-nomes { display: grid; grid-template-columns: 1fr 1fr; text-align: center; font: 600 14px/1.3 var(--sans-serif); color: var(--theme-foreground-alt); }

/* Os pontos (components/polos.js). No celular, arrastar o dedo para os lados mexe nos pontos; para cima e para baixo,
   rola a página. O violeta dos outros candidatos é mais escuro que o vermelho e o azul nos dois temas: assim ele se
   distingue do azul também para quem não enxerga bem o vermelho (protanopia e deuteranopia). O cinza de brancos, nulos
   e abstenções é o neutro dos gráficos do site. */
.polos { display: block; width: 100%; height: auto; overflow: visible; touch-action: pan-y; --violeta: #622c91; }
.polos .petismo { fill: var(--petismo); }
.polos .bolsonarismo { fill: var(--bolsonarismo); }
.polos .outros { fill: var(--violeta); }
.polos .nenhum { fill: var(--outros); }
@media (prefers-color-scheme: dark) {
  .polos { --violeta: #7f4bb1; }
}
@media (prefers-reduced-motion: reduce) {
  a.card.cartao, .cartao-seta { transition: none; }
}
</style>
