---
title: Comparações
toc: true
---

```js
import {graficoComparacao, graficoPolarizacaoAnos, legenda, serieComparacao} from "./components/graficos.js";
import {decimal, num, pct, pp} from "./components/formato.js";
```

```js
const ap18a = FileAttachment("data/apuracao_2018_t1.json").json();
const ap18b = FileAttachment("data/apuracao_2018_t2.json").json();
const ap22a = FileAttachment("data/apuracao_2022_t1.json").json();
const ap22b = FileAttachment("data/apuracao_2022_t2.json").json();
const ap26a = FileAttachment("data/apuracao_2026_t1.json").json();
const pesquisas = [
  await FileAttachment("data/pesquisas_2018.json").json(),
  await FileAttachment("data/pesquisas_2022.json").json(),
  await FileAttachment("data/pesquisas_2026.json").json()
];
const eleicoes = FileAttachment("data/eleicoes.json").json();
const resumoMapa = FileAttachment("data/mapa/resumo.json").json();
```

```js
const series = [
  ...serieComparacao(ap18a), ...serieComparacao(ap18b),
  ...serieComparacao(ap22a), ...serieComparacao(ap22b),
  ...serieComparacao(ap26a)
];
// Vantagem do petismo quando a apuração atingiu cada marco (vazio se a curva ainda não existia)
const marcos = [25, 50, 75, 90];
const grupos = d3.groups(series, (s) => `${s.ano}|${s.turno}`).map(([chave, partes]) => {
  const pontos = partes.flatMap((p) => p.pontos).sort((a, b) => a.apurado - b.apurado);
  const em = (m) => (pontos[0].apurado > m + 0.5 ? null : pontos.find((d) => d.apurado >= m)?.vantagem ?? null);
  const [ano, turno] = chave.split("|");
  const trechos = new Set(partes.map((p) => p.trecho));
  const selo = trechos.has("estimado") ? (trechos.has("exato") ? "provisória" : "estimada") : null;
  return {ano, turno: +turno, selo, valores: marcos.map(em), final: pontos.at(-1).vantagem};
});
const desde25 = grupos.filter((g) => g.valores[0] != null);
```

# Comparações entre eleições

<p class="lead">Como a disputa entre os dois campos se moveu durante cada apuração. O eixo horizontal é o % de seções apuradas, o que permite pôr 2018, 2022 e 2026 lado a lado mesmo com horários de divulgação diferentes.</p>

```js
const modo = view(Inputs.radio(new Map([["Vantagem do petismo", "vantagem"], ["Quanto ainda faltava mudar", "deslocamento"]]), {value: "vantagem", label: "Mostrar"}));
```

<div class="card">
  <h2>${modo === "vantagem" ? "Vantagem do candidato do PT sobre o bolsonarista ao longo da apuração" : "Diferença entre a vantagem naquele momento e a vantagem final"}</h2>
  <h3>Pontos percentuais dos votos válidos. ${modo === "vantagem" ? "Acima de zero, o petismo à frente; abaixo, o bolsonarismo." : "Abaixo de zero, o petismo ainda ia ganhar terreno até o fim."}</h3>
  ${legenda([{nome: "2018", cor: "var(--ano-2018)"}, {nome: "2022", cor: "var(--ano-2022)"}, {nome: "2026", cor: "var(--ano-2026)"}, {nome: "trecho estimado", cor: "var(--theme-foreground-muted)", estilo: "tracejado"}])}
  ${resize((width) => graficoComparacao(series, {modo, width}))}
</div>

<p class="nota">2018: curva estimada (o TSE não publicou a chegada dos boletins) e que só começa às 19h, quando a divulgação começou e boa parte das seções já estava apurada. 2022 e 2026: exatas, pela hora em que cada boletim de urna chegou ao TSE.</p>

## A vantagem em cada momento da apuração

<div class="card" style="max-width: 760px;">
  <table>
    <thead><tr><th>Eleição</th>${marcos.map((m) => html`<th style="text-align:right">com ${m}%</th>`)}<th style="text-align:right">final</th></tr></thead>
    <tbody>${grupos.map((g) => html`<tr>
      <td>${g.ano}, ${g.turno}º turno${g.selo ? html` <span class="selo estimado">${g.selo}</span>` : ""}</td>
      ${g.valores.map((v) => html`<td style="text-align:right;font-variant-numeric:tabular-nums">${v == null ? "–" : pp(v, 1)}</td>`)}
      <td style="text-align:right;font-variant-numeric:tabular-nums;font-weight:600">${pp(g.final, 1)}</td>
    </tr>`)}</tbody>
  </table>
</div>

<p class="nota">Vantagem do candidato do PT sobre o bolsonarista, em pontos percentuais dos votos válidos, quando o Brasil atingiu cada % de seções apuradas. “–”: a curva ainda não existia nesse ponto (em 2018, a divulgação começou com parte das seções já apurada).</p>

<p>Do momento em que um quarto das seções estava apurado até o resultado final, a vantagem do petismo ${desde25.every((g) => g.final > g.valores[0]) ? "cresceu em todas as apurações em que dá para medir" : "mudou assim"}: ${desde25.map((g) => `${pp(g.final - g.valores[0], 1)} em ${g.ano} (${g.turno}º turno)`).join(", ")}. ${desde25.every((g) => g.valores[0] < 0 && g.final > g.valores[0]) ? "Em todas elas, o candidato bolsonarista liderava com um quarto das seções apuradas: as seções que chegam primeiro são, em média, mais favoráveis a ele do que as que chegam por último." : ""}</p>

## O erro das pesquisas

```js
// Média das pesquisas da semana final de cada turno já decidido × resultado das urnas
const erros = pesquisas.flatMap((d) => Object.entries(d.turnos)
  .filter(([, t]) => t.resultado && t.media_semana_final)
  .map(([turno, t]) => {
    const e = eleicoes.eleicoes[String(d.ano)];
    const m = t.media_semana_final, r = t.resultado;
    return {ano: d.ano, turno: +turno, n: t.pesquisas_semana_final, pt: e.petismo.nome, bo: e.bolsonarismo.nome,
            media: m, resultado: r, erro_pt: m.petismo - r.petismo, erro_bo: m.bolsonarismo - r.bolsonarismo};
  }));
const primeiros = erros.filter((e) => e.turno === 1);
const pontos = (v) => `${decimal(Math.abs(v), 1)} ${Math.abs(v) < 2 ? "ponto" : "pontos"}`;
```

<div class="card" style="max-width: 860px;">
  <table>
    <thead><tr><th>Eleição</th><th style="text-align:right">Pesquisas</th><th>Candidato</th>
      <th style="text-align:right">Média da semana final</th><th style="text-align:right">Urnas</th><th style="text-align:right">Erro</th></tr></thead>
    <tbody>${erros.flatMap((e) => [
      html`<tr><td rowspan="2">${e.ano}, ${e.turno}º turno</td><td rowspan="2" style="text-align:right">${e.n}</td>
        <td>${e.bo}</td><td style="text-align:right">${pct(e.media.bolsonarismo, 1)}</td><td style="text-align:right">${pct(e.resultado.bolsonarismo, 1)}</td>
        <td style="text-align:right;font-weight:600">${pp(e.erro_bo, 1)}</td></tr>`,
      html`<tr><td>${e.pt}</td><td style="text-align:right">${pct(e.media.petismo, 1)}</td><td style="text-align:right">${pct(e.resultado.petismo, 1)}</td>
        <td style="text-align:right;font-weight:600">${pp(e.erro_pt, 1)}</td></tr>`
    ])}</tbody>
  </table>
</div>

<p class="nota">Média simples das pesquisas com fim do campo na semana anterior a cada turno, em % dos votos válidos. Erro: média menos resultado; negativo quer dizer que as pesquisas deram menos do que as urnas.</p>

<p>${primeiros.length && primeiros.every((e) => e.erro_bo < 0)
  ? `Em todos os primeiros turnos estudados, a média das pesquisas da semana final ficou abaixo do resultado do candidato bolsonarista: ${primeiros.map((e) => `${pontos(e.erro_bo)} em ${e.ano}`).join(", ")}.`
  : ""} ${erros.filter((e) => e.turno === 2).map((e) => `No 2º turno de ${e.ano}, com dois candidatos, a média ${e.erro_bo > 0 ? "superestimou" : "subestimou"} ${e.bo} em ${pontos(e.erro_bo)}.`).join(" ")}</p>

## O voto em cada local de votação

```js
const turnoLocais = view(Inputs.radio(new Map([["1º turno", "1"], ["2º turno", "2"]]), {value: "2", label: "Turno"}));
```

```js
const anosLocais = Object.keys(resumoMapa.anos).filter((a) => resumoMapa.anos[a].turnos[turnoLocais]);
const linhasLocais = Object.entries(resumoMapa.anos).flatMap(([ano, a]) => Object.entries(a.turnos).map(([turno, t]) => {
  const e = eleicoes.eleicoes[ano];
  return {ano, turno, pt: e.petismo.nome, bo: e.bolsonarismo.nome, ...t};
}));
```

<div class="card">
  <h2>Quanto os locais de votação pendem para um lado</h2>
  <h3>${turnoLocais}º turno · parte dos votos dos dois campos dada em locais com cada % do candidato bolsonarista</h3>
  ${legenda(anosLocais.map((a) => ({nome: a, cor: `var(--ano-${a})`})))}
  ${resize((width) => graficoPolarizacaoAnos(resumoMapa, {turno: turnoLocais, width}))}
</div>

<div class="card" style="max-width: 860px;">
  <table>
    <thead><tr><th>Eleição</th><th style="text-align:right">Votos em locais com 60% ou mais para um campo</th><th style="text-align:right">Com 70% ou mais</th><th style="text-align:right">Locais vencidos pelo petismo</th><th style="text-align:right">Pelo bolsonarismo</th></tr></thead>
    <tbody>${linhasLocais.map((l) => html`<tr><td style="white-space:nowrap">${l.ano}, ${l.turno}º turno</td>
      <td style="text-align:right">${pct(100 * l.acima_60, 0)}</td><td style="text-align:right">${pct(100 * l.acima_70, 0)}</td>
      <td style="text-align:right">${num(l.locais_petismo)}</td><td style="text-align:right">${num(l.locais_bolsonarismo)}</td></tr>`)}</tbody>
  </table>
</div>

<p class="nota">Locais de votação no Brasil (o exterior fica de fora). A % de cada local considera só os votos dos dois campos estudados; no 1º turno, os outros candidatos não entram na conta. Um local "vencido" teve mais votos de um campo do que do outro. Os mapas de cada ano estão nas páginas <a href="./2018#mapa">2018</a>, <a href="./2022#mapa">2022</a> e <a href="./2026#mapa">2026</a>.</p>
