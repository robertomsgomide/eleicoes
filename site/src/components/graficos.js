// Gráficos do estudo (Observable Plot). Cores vêm de variáveis CSS (style.css), com versões clara e escura.
import * as Plot from "npm:@observablehq/plot";
import {html} from "npm:htl";
import {comSinal, dia, diaCurto, hora, horaEixo, mesEixo, mi, miEixo, num, pct, periodoCampo, pp, relogio} from "./formato.js";

export const CAMPOS = ["petismo", "bolsonarismo"];
export const COR = {petismo: "var(--petismo)", bolsonarismo: "var(--bolsonarismo)", outros: "var(--outros)"};
export const REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Exterior"];
export const COR_REGIAO = {
  Norte: "var(--regiao-norte)",
  Nordeste: "var(--regiao-nordeste)",
  "Centro-Oeste": "var(--regiao-centro-oeste)",
  Sudeste: "var(--regiao-sudeste)",
  Sul: "var(--regiao-sul)",
  Exterior: "var(--regiao-exterior)"
};
const TINTA = "var(--theme-foreground)";
const TINTA_SUAVE = "var(--theme-foreground-muted)";
const TINTA_FRACA = "var(--theme-foreground-faint)";
const FUNDO = "var(--theme-background)";

// O Plot não mede, não quebra nem encolhe texto, e o que passa da borda do gráfico some (no celular, sobretudo). A
// largura de um texto é estimada pela linha mais longa: 0,55 do corpo por letra, com folga sobre as fontes do sistema.
const largura = (texto, corpo = 10) => Math.max(...String(texto).split("\n").map((l) => l.length)) * corpo * 0.55;

// Das versões de um texto, da mais completa à mais curta, a primeira que cabe no espaço (em px)
const caber = (espaco, versoes, corpo = 10) => versoes.find((t) => largura(t, corpo) <= espaco) ?? versoes.at(-1);

// Se duas caixas [x0, y0, x1, y1] (em px) se cobrem em mais de 1 px nas duas direções
const cruzam = (a, b) => a[0] < b[2] - 1 && b[0] < a[2] - 1 && a[1] < b[3] - 1 && b[1] < a[3] - 1;

// ---- Peças de HTML ------------------------------------------------------------------

export function legenda(itens) {
  return html`<div class="legenda">${itens.map(
    (i) => html`<span style="color:${i.cor}"><i class=${i.estilo ?? ""}></i><span style="color:var(--theme-foreground-alt)">${i.nome}</span></span>`
  )}</div>`;
}

// Sem valor (um resultado que ainda não saiu), o placar diz "Não divulgado". previsao: uma linha a mais, embaixo
// (o forecast, durante a apuração).
export function placar({nome, cor, valor, votos, detalhe, casas = 2, previsao}) {
  return html`<div class="placar">
    <div class="quem">${cor ? html`<span class="amostra" style="background:${cor}"></span>` : ""}${nome}</div>
    <div class=${valor == null ? "grande pendente" : "grande"}>${valor == null ? "Não divulgado" : pct(valor, casas)}</div>
    <div class="detalhe">${votos != null ? `${num(votos)} votos` : ""}${detalhe ? (votos != null ? " · " : "") + detalhe : ""}</div>
    ${previsao ? html`<div class="previsao">${previsao}</div>` : ""}
  </div>`;
}

// O forecast de um campo (f: um lugar do forecast, com a parte do petismo), em "previsto: 50,8% (50,6–51,1%)".
export function textoPrevisto(f, campo) {
  const l = lados(f)[campo];
  return `previsto: ${pct(l.valor, 1)} (${pct(l.inf, 1).replace("%", "")}–${pct(l.sup, 1)})`;
}

// No lugar de um gráfico ou do mapa, enquanto o turno não tem dados (o 2º turno de 2026 até a eleição).
export function naoDivulgado(texto, {altura = 240, titulo = "Não divulgado"} = {}) {
  return html`<div class="nao-divulgado" style="min-height:${altura}px"><strong>${titulo}</strong><span>${texto}</span></div>`;
}

// Os cartões do resultado de um turno (b: o Brasil em data/resultados.json): os dois campos, quem teve mais votos
// primeiro; no 1º turno, os outros candidatos; e o comparecimento. Sem resultado (o 2º turno de 2026 até a eleição),
// os placares dizem "Não divulgado", com `pendente` embaixo, e a ordem dos dois vem em `ordem`. Espaço fixo entre o
// número e a palavra: em cartões estreitos, a linha não quebra entre os dois.
// Durante a apuração (aoVivo), os números são o que já foi apurado, e `previsao` (o forecast do Brasil) entra embaixo
// de cada campo.
export function placaresResultado(b, {turno, nomes, ordem, pendente = "", previsao = null, aoVivo = false}) {
  const parte = (c) => b && (100 * b[c]) / b.validos;
  const cartoes = [
    ...(ordem ?? [...CAMPOS].sort((x, y) => b[y] - b[x])).map((c) => ({nome: nomes[c], cor: COR[c], valor: parte(c), votos: b?.[c], detalhe: b ? "" : pendente, previsao: previsao ? textoPrevisto(previsao, c) : null})),
    ...(turno === 1 ? [{nome: "Outros candidatos", cor: COR.outros, valor: parte("outros"), votos: b?.outros, detalhe: b ? `${b.candidatos.length - 2}\u00a0candidatos` : pendente}] : []),
    {nome: "Comparecimento", valor: b && (100 * b.comparecimento) / b.aptos, detalhe: b ? `${num(b.comparecimento)} de ${num(b.aptos)}\u00a0eleitores${aoVivo ? " das seções apuradas" : ""}` : pendente}
  ];
  return html`<div class="grid grid-cols-${cartoes.length} placares">${cartoes.map((c) => html`<div class="card">${placar(c)}</div>`)}</div>`;
}

// A faixa embaixo dos placares durante a apuração: quanto já foi apurado, a chance de vitória pelo forecast e a hora
// da última atualização do TSE. vivo: o estado de components/aovivo.js.
export function faixaAoVivo(vivo, {nomes}) {
  const t = vivo.tse;
  const p = vivo.previsao?.brasil;
  const quando = t ? hora(new Date(Date.parse(t.h + "Z"))) : "";
  const favorito = p ? (p.chance >= 0.5 ? "petismo" : "bolsonarismo") : null;
  const chance = p ? 100 * (favorito === "petismo" ? p.chance : 1 - p.chance) : null;
  const apurado = t?.pst ?? 0;
  const encerrada = vivo.modo === "encerrada";
  return html`<div class="faixa-ao-vivo" role="status">
    <span class=${encerrada ? "selo" : "selo ao-vivo"}>${encerrada ? "apuração encerrada" : "ao vivo"}</span>
    <span class="faixa-apurado"><span class="faixa-barra" aria-hidden="true"><i style=${`width:${Math.min(100, apurado)}%`}></i></span><b>${pct(apurado, 1)}</b> das seções apuradas</span>
    ${p && !encerrada ? html`<span>Chance de vitória pelo forecast: <b style=${`color:${COR[favorito]}`}>${nomes[favorito]}, ${chance >= 99.95 ? "mais de 99,9%" : pct(chance, chance >= 99 ? 1 : 0)}</b></span>` : ""}
    ${t ? html`<span class="faixa-hora">TSE, ${quando}</span>` : ""}
  </div>`;
}

// Nota sob o resultado: de onde vêm os números do turno (o campo `fonte` de data/resultados.json).
export function fonteResultado(res) {
  return res.fonte === "boletins de urna e total oficial do TSE"
    ? "Fonte: votos dos candidatos, total oficial do TSE; eleitorado, comparecimento, brancos e nulos, boletins de urna."
    : `Fonte: ${res.fonte}.`;
}

// ---- Dados ----------------------------------------------------------------------------

// Uma linha por minuto da série acumulada (formato de data/apuracao_<ano>_t<turno>.json).
export function pontos(ap, regiao = "Brasil") {
  const r = ap.regioes[regiao];
  const total = ap.totais[regiao].secoes;
  return ap.t.map((m, i) => ({
    minuto: m,
    hora: relogio(ap.inicio, m),
    apurado: (100 * r.secoes[i]) / total,
    validos: r.validos[i],
    petismo: r.petismo[i],
    bolsonarismo: r.bolsonarismo[i]
  }));
}

// O Brasil atinge `alvo`% das seções apuradas: quanto cada região tinha nesse momento.
export function momento(ap, alvo) {
  const b = pontos(ap);
  const i = b.findIndex((d) => d.apurado >= alvo);
  return {
    hora: b[i].hora,
    regioes: Object.fromEntries(REGIOES.map((r) => [r, (100 * ap.regioes[r].secoes[i]) / ap.totais[r].secoes]))
  };
}

// Frase que explica por que a curva se move: quais regiões já tinham chegado quando o Brasil estava na metade.
export function explicarRitmo(ap, res, nomes) {
  const inicial = (100 * ap.regioes.Brasil.secoes[0]) / ap.totais.Brasil.secoes;
  const meio = momento(ap, Math.max(50, inicial));
  const ordem = REGIOES.filter((r) => r !== "Exterior").sort((a, b) => meio.regioes[b] - meio.regioes[a]);
  const [r1, r2] = ordem;
  const ultima = ordem.at(-1);
  const lider = (r) => {
    const d = res.regioes[r];
    const c = d.petismo >= d.bolsonarismo ? "petismo" : "bolsonarismo";
    return `${nomes[c]} teve ${pct((100 * d[c]) / d.validos, 0)}`;
  };
  const p = (r) => pct(meio.regioes[r], 0);
  const quando = `${ap.tipo === "estimada" ? "por volta das " : "às "}${hora(meio.hora)}`;
  const abertura =
    inicial > 50
      ? `Quando a divulgação começou (${quando}), com ${pct(inicial, 0)} das seções do Brasil já apuradas`
      : `Quando o Brasil chegou a 50% das seções apuradas (${quando})`;
  return (
    `${abertura}, o ${r1} já tinha ${p(r1)} e o ${r2}, ${p(r2)} ` +
    `(no ${r1}, ${lider(r1)} dos válidos; no ${r2}, ${lider(r2)}), enquanto o ${ultima} estava em ${p(ultima)} ` +
    `(lá, ${lider(ultima)}).`
  );
}

const MEDIDAS = {
  pct: {rotulo: "% dos votos válidos", valor: (d, c) => (100 * d[c]) / d.validos, fmt: (v) => pct(v), eixo: (v) => v + "%"},
  votos: {rotulo: "Votos apurados", valor: (d, c) => d[c], fmt: mi, eixo: miEixo}
};

// x0: onde começa o eixo de % apurado (a curva de 2018 só começa com parte das seções já apuradas)
function escalaX(porHora, x0 = 0, rotulo = "Seções apuradas") {
  return porHora
    ? {type: "utc", label: "Horário de Brasília", labelArrow: "none", tickFormat: horaEixo}
    : {domain: [x0, 100], label: rotulo, labelArrow: "none", tickFormat: (v) => v + "%"};
}

const piso = (valores) => Math.floor(Math.min(...valores) / 10) * 10;

function dica(d, nomes, {estimada = false, previsto = null} = {}) {
  const p = (100 * d.petismo) / d.validos;
  const b = (100 * d.bolsonarismo) / d.validos;
  const f = previsto?.(d);
  return [
    `${estimada ? "~" : ""}${hora(d.hora)} · ${pct(d.apurado, 1)} das seções`,
    `${nomes.petismo}: ${pct(p)} · ${num(d.petismo)} votos`,
    `${nomes.bolsonarismo}: ${pct(b)} · ${num(d.bolsonarismo)} votos`,
    `Diferença: ${pp(p - b, 2)} · ${comSinal(d.petismo - d.bolsonarismo)} votos`,
    ...(f ? [`Forecast para o fim: ${nomes.petismo} ${pct(f.petismo, 1)} (80%: ${pct(f.inf, 1)} a ${pct(f.sup, 1)})`] : [])
  ].join("\n");
}

// ---- O forecast sobre a curva da apuração --------------------------------------------------------------------------
// previsao.serie: o resultado final que o forecast previa a cada momento ({minuto, apurado, petismo, inf, sup,
// chance, vantagem, vinf, vsup, votos_petismo, votos_bolsonarismo}), ao vivo ou refeito com uma noite passada.

function pontosPrevisao(ap, serie, porHora) {
  return serie
    .map((f) => ({...f, hora: relogio(ap.inicio, f.minuto)}))
    .filter((f) => (porHora ? f.minuto <= ap.t999 : f.apurado >= 1));
}

// O forecast do momento de cada ponto da curva (o último feito até ali), para a dica.
function forecastNoMomento(pontos, porHora) {
  const xs = pontos.map((f) => (porHora ? f.minuto : f.apurado));
  return (d) => {
    const i = quantosAte(xs, porHora ? d.minuto : d.apurado) - 1;
    return i >= 0 ? pontos[i] : null;
  };
}

// Quantos valores de xs (em ordem) são <= x
function quantosAte(xs, x) {
  let lo = 0, hi = xs.length;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (xs[m] <= x) lo = m + 1;
    else hi = m;
  }
  return lo;
}

function marcasPrevisao(pontos, {x, medida}) {
  const curve = "step-after";
  if (medida === "vantagem") {
    return [
      Plot.areaY(pontos, {x, y1: "vinf", y2: "vsup", fill: TINTA_SUAVE, fillOpacity: 0.1, curve}),
      Plot.line(pontos, {x, y: "vantagem", stroke: TINTA, strokeWidth: 1.5, strokeDasharray: "5,4", curve})
    ];
  }
  if (medida === "votos") {
    const longas = pontos.flatMap((f) => CAMPOS.map((c) => ({...f, campo: c, valor: f[`votos_${c}`]})));
    return [Plot.line(longas, {x, y: "valor", z: "campo", stroke: "campo", strokeWidth: 1.5, strokeDasharray: "5,4", curve})];
  }
  const longas = pontos.flatMap((f) => [
    {...f, campo: "petismo", valor: f.petismo, baixo: f.inf, alto: f.sup},
    {...f, campo: "bolsonarismo", valor: 100 - f.petismo, baixo: 100 - f.sup, alto: 100 - f.inf}
  ]);
  return [
    Plot.areaY(longas, {x, y1: "baixo", y2: "alto", z: "campo", fill: "campo", fillOpacity: 0.13, curve}),
    Plot.line(longas, {x, y: "valor", z: "campo", stroke: "campo", strokeWidth: 1.5, strokeDasharray: "5,4", curve})
  ];
}

// No eixo de % apurado, enquanto falta apurar: onde o forecast prevê que cada curva termine (100%), com a faixa de 80%.
// Na vantagem, já com o texto; nos dois campos, o texto de cada ponto (em `fins`) vem de textoDestino, que acha onde
// ele cabe sem cobrir as curvas e os rótulos do fim delas.
function marcasDestino(pontos, {medida, apurado}) {
  const f = pontos.at(-1);
  if (!f || apurado >= 99) return {marcas: [], fins: []};
  if (medida === "vantagem") {
    const d = [{x: 100, valor: f.vantagem, inf: f.vinf, sup: f.vsup}];
    return {
      marcas: [
        Plot.ruleX(d, {x: "x", y1: "inf", y2: "sup", stroke: TINTA_SUAVE, strokeWidth: 3, strokeOpacity: 0.6}),
        Plot.dot(d, {x: "x", y: "valor", r: 4, fill: TINTA, stroke: FUNDO, strokeWidth: 1.5}),
        Plot.text(d, {x: "x", y: "valor", dx: -8, textAnchor: "end", text: (x) => `previsto: ${comSinal(x.valor, mi)}`, fill: TINTA, fontSize: 11})
      ],
      fins: []
    };
  }
  const d = medida === "votos"
    ? CAMPOS.map((c) => ({campo: c, x: 100, valor: f[`votos_${c}`]}))
    : [{campo: "petismo", x: 100, valor: f.petismo, inf: f.inf, sup: f.sup}, {campo: "bolsonarismo", x: 100, valor: 100 - f.petismo, inf: 100 - f.sup, sup: 100 - f.inf}];
  return {
    marcas: [
      ...(medida === "votos" ? [] : [Plot.ruleX(d, {x: "x", y1: "inf", y2: "sup", stroke: "campo", strokeWidth: 3, strokeOpacity: 0.5})]),
      Plot.dot(d, {x: "x", y: "valor", r: 4, fill: "campo", stroke: FUNDO, strokeWidth: 1.5})
    ],
    fins: afastar(d)
  };
}

// O texto do destino de cada curva: à esquerda do ponto, com o nome; senão só o número, à direita, na margem; senão
// nenhum (o ponto fica, e a dica e os placares trazem o forecast). Vale o primeiro que fica no gráfico, à direita do fim
// das curvas e fora das caixas `ocupadas` (os rótulos do fim delas). Os lugares, em px, vêm das escalas (sx, sy) de
// um primeiro desenho do gráfico. Perto do fim da apuração, curva e forecast se aproximam e os textos se encontrariam.
function textoDestino(fins, {medida, nomes, sx, sy, width, marginLeft, fimCurvas, ocupadas}) {
  const fmt = medida === "votos" ? mi : (v) => pct(v, 1);
  const versoes = [
    {dx: -8, textAnchor: "end", texto: (d) => `${nomes[d.campo]} previsto: ${fmt(d.valor)}`},
    {dx: 8, textAnchor: "start", texto: (d) => fmt(d.valor)}
  ];
  const caixa = (d, v) => {
    const w = largura(v.texto(d), 11);
    const x = sx.apply(100) + v.dx;
    const y = sy.apply(d.valor) + d.dy;
    return v.dx < 0 ? [x - w, y - 6, x, y + 6] : [x, y - 6, x + w, y + 6];
  };
  const cabe = (c) => c[0] >= Math.max(marginLeft, fimCurvas + 4) && c[2] <= width && !ocupadas.some((o) => cruzam(c, o));
  const v = versoes.find((v) => fins.every((d) => cabe(caixa(d, v))));
  return v ? fins.map((d) => Plot.text([d], {x: "x", y: "valor", dy: d.dy, dx: v.dx, textAnchor: v.textAnchor, text: v.texto, fill: TINTA, fontSize: 11})) : [];
}

// Uma noite refeita (data/forecast.json, noites[ano]: colunas) no formato de previsao.serie (uma linha por momento).
export function serieDaNoite(n) {
  const campos = ["apurado", "petismo", "inf", "sup", "chance", "vantagem", "vinf", "vsup", "votos_petismo", "votos_bolsonarismo"];
  return n.t.map((t, i) => ({minuto: t, ...Object.fromEntries(campos.map((k) => [k, n[k][i]]))}));
}

// Durante a apuração: se o forecast dá a vitória, com 80% de chance ou mais, a quem está atrás na contagem.
export function viradaPrevista(ap, serie) {
  const f = serie?.at(-1);
  const b = ap?.regioes.Brasil;
  if (!f || !b?.petismo.length) return null;
  const lider = b.petismo.at(-1) >= b.bolsonarismo.at(-1) ? "petismo" : "bolsonarismo";
  const vencedor = f.chance >= 0.5 ? "petismo" : "bolsonarismo";
  const chance = vencedor === "petismo" ? f.chance : 1 - f.chance;
  return vencedor !== lider && chance >= 0.8 ? {vencedor, chance} : null;
}

// O aviso da virada prevista, no canto direito do quadro (largura `quadro`), encurtado até caber, em até duas linhas: no
// alto, abaixo das `linhasAcima` linhas de texto que já houver ali; nos votos, embaixo, longe dos votos previstos para o
// fim, que ficam no alto. Devolve as marcas e quantas linhas o aviso ocupa.
function marcaViradaPrevista(v, nomes, {quadro, embaixo = false, linhasAcima = 0}) {
  if (!v) return {marcas: [], linhas: 0};
  const ch = 100 * v.chance;
  const chance = ch >= 99.95 ? "mais de 99,9%" : pct(ch, ch >= 99 ? 1 : 0);
  const nome = nomes[v.vencedor];
  const texto = caber(quadro - 8, [`Virada prevista: ${nome} deve terminar à frente (chance de ${chance})`, `Virada prevista: ${nome} (chance de ${chance})`, `Virada prevista: ${nome}`, `Virada prevista:\n${nome}`], 12);
  const lugar = embaixo ? {frameAnchor: "bottom-right", dy: -4, lineAnchor: "bottom"} : {frameAnchor: "top-right", dy: 2 + 15 * linhasAcima, lineAnchor: "top"};
  return {marcas: [Plot.text([texto], {...lugar, dx: -4, textAnchor: "end", fill: COR[v.vencedor], fontWeight: 600, fontSize: 12})], linhas: texto.split("\n").length};
}

// Afasta dois rótulos finais quando os valores ficam colados.
// escala: o tamanho do eixo, quando ele vai bem além dos dois valores (os votos previstos para o fim, por exemplo).
function afastar(fins, campo = "valor", escala = 0) {
  if (fins.length !== 2) return fins.map((d) => ({...d, dy: 0}));
  const [a, b] = fins;
  const perto = Math.abs(a[campo] - b[campo]) < 0.06 * Math.max(Math.abs(a[campo]), Math.abs(b[campo]), escala, 1e-9);
  const sobe = a[campo] >= b[campo] ? a : b;
  return fins.map((d) => ({...d, dy: perto ? (d === sobe ? -9 : 9) : 0}));
}

// Rótulo no fim de cada linha (o deslocamento vertical do Plot é fixo por marca: uma marca por rótulo).
function rotulosFinais(fins, x, texto, dx = 8) {
  return fins.map((d) => Plot.text([d], {x, y: "valor", dy: d.dy, dx, text: texto, textAnchor: "start", fill: TINTA, fontWeight: 600}));
}

// Linha tracejada vertical, ponto e texto no momento em que muda o líder. O texto fica centrado na linha, mas dentro do
// quadro (largura `quadro`; noQuadro: onde um x cai nele, em px), e encurta quando não cabe.
function marcaVirada(ap, linhas, x, valor, nomes, {quadro, noQuadro}) {
  const v = ap.viradas.at(-1);
  if (!v) return [];
  const d = linhas.find((l) => l.minuto >= v.t);
  if (!d) return [];
  const ponto = {...d, valor: valor(d, v.lider)};
  const quando = `${ap.tipo === "estimada" ? "~" : ""}${hora(d.hora)}`;
  const texto = caber(quadro, [`${nomes[v.lider]} passa à frente · ${quando} · ${pct(d.apurado, 1)} apurado`, `${nomes[v.lider]} passa à frente · ${quando}`, `Virada · ${quando}`], 12);
  const meia = largura(texto, 12) / 2;
  const centro = noQuadro(d[x]);
  const dx = Math.max(meia, Math.min(quadro - meia, centro)) - centro;
  // um contorno da cor do cartão separa o texto da linha da virada e das curvas que passam por ele
  return [
    Plot.ruleX([ponto], {x, stroke: TINTA_SUAVE, strokeDasharray: "2,3"}),
    Plot.dot([ponto], {x, y: "valor", r: 5, fill: COR[v.lider], stroke: FUNDO, strokeWidth: 2}),
    Plot.text([ponto], {x, text: () => texto, frameAnchor: "top", dy: 2, dx, lineAnchor: "top", textAnchor: "middle", fill: TINTA, fontSize: 12, stroke: "var(--theme-background-alt)", strokeWidth: 4, paintOrder: "stroke"})
  ];
}

// ---- Gráficos -------------------------------------------------------------------------

// Os dois campos ao longo da apuração: % dos válidos, votos acumulados ou vantagem em votos. previsao: {serie} do
// forecast (tracejado, com a faixa de 80%); aoVivo: durante a apuração, avisa a virada que o forecast prevê.
export function graficoCampos(ap, {eixo = "hora", medida = "pct", width = 640, nomes, previsao = null, aoVivo = false}) {
  const porHora = eixo === "hora";
  let linhas = pontos(ap);
  if (porHora) linhas = linhas.filter((d) => d.minuto <= ap.t999);
  if (medida !== "votos") linhas = linhas.filter((d) => d.apurado >= 1); // o começo é muito ruidoso
  const x = porHora ? "hora" : "apurado";
  const curve = "step-after";
  const tracejado = ap.tipo === "estimada" ? "6,3" : undefined;
  const estimada = ap.tipo === "estimada";
  const regua = Plot.ruleX(linhas, Plot.pointerX({x, stroke: TINTA_FRACA}));
  const x0 = piso(linhas.map((d) => d.apurado));
  if (!linhas.length) return naoDivulgado("A curva começa quando 1% das seções estiver apurado.", {altura: 380, titulo: "Daqui a pouco"});
  const prev = previsao?.serie?.length ? pontosPrevisao(ap, previsao.serie, porHora) : [];
  const previsto = prev.length ? forecastNoMomento(prev, porHora) : null;
  const apuradoAgora = (100 * ap.regioes.Brasil.secoes.at(-1)) / (ap.totais.Brasil.secoes || 1);
  const estreito = width < 560;
  // As margens e, entre elas, o quadro, onde os textos soltos precisam caber. noQuadro: onde um x cai no quadro, em px
  // (por hora, o eixo vai do primeiro ao último ponto da curva e do forecast).
  const margens = medida === "vantagem" ? {marginLeft: 64, marginRight: 20} : {marginLeft: 52, marginRight: estreito ? 64 : 172};
  const quadro = width - margens.marginLeft - margens.marginRight;
  const horas = porHora ? [...linhas, ...prev].map((d) => +d.hora) : [];
  const [xi, xf] = porHora ? [Math.min(...horas), Math.max(...horas)] : [x0, 100];
  const noQuadro = (v) => (quadro * (+v - xi)) / (xf - xi || 1);
  const destino = porHora ? {marcas: [], fins: []} : marcasDestino(prev, {medida, apurado: apuradoAgora});
  const previstas = marcasPrevisao(prev, {x, medida});
  const prevista = aoVivo ? viradaPrevista(ap, previsao?.serie) : null;

  if (medida === "vantagem") {
    const vant = (d) => d.petismo - d.bolsonarismo;
    const virada = marcaVirada(ap, linhas, x, (d) => vant(d), nomes, {quadro, noQuadro});
    const aviso = marcaViradaPrevista(prevista, nomes, {quadro, linhasAcima: virada.length ? 1 : 0});
    // "↑ … à frente" desce o quanto os textos do alto ocupam; ele e "↓ … à frente" perdem o "à frente" se não cabem
    const noAlto = (virada.length ? 1 : 0) + aviso.linhas;
    const lado = (seta, c) => caber(quadro - 8, [`${seta} ${nomes[c]} à frente`, `${seta} ${nomes[c]}`], 12);
    return Plot.plot({
      width,
      height: 380,
      ...margens,
      marginTop: 28,
      x: escalaX(porHora, x0),
      y: {label: "Vantagem em votos", labelArrow: "none", grid: true, tickFormat: (v) => comSinal(v, miEixo)},
      marks: [
        Plot.areaY(linhas, {x, y: (d) => Math.max(0, vant(d)), fill: COR.petismo, fillOpacity: 0.2, curve}),
        Plot.areaY(linhas, {x, y: (d) => Math.min(0, vant(d)), fill: COR.bolsonarismo, fillOpacity: 0.2, curve}),
        Plot.ruleY([0], {stroke: TINTA_SUAVE}),
        ...previstas,
        ...destino.marcas,
        Plot.line(linhas, {x, y: vant, stroke: TINTA, strokeWidth: 2, curve, strokeDasharray: tracejado}),
        Plot.text([lado("↑", "petismo")], {frameAnchor: "top-left", dx: 8, dy: 4 + 15 * noAlto, textAnchor: "start", fill: TINTA_SUAVE, fontSize: 12}),
        Plot.text([lado("↓", "bolsonarismo")], {frameAnchor: "bottom-left", dx: 8, dy: -4, textAnchor: "start", fill: TINTA_SUAVE, fontSize: 12}),
        ...virada,
        ...aviso.marcas,
        regua,
        Plot.tip(linhas, Plot.pointerX({x, y: vant, title: (d) => dica(d, nomes, {estimada, previsto})}))
      ]
    });
  }

  const m = MEDIDAS[medida];
  const longas = linhas.flatMap((d) => CAMPOS.map((c) => ({...d, campo: c, valor: m.valor(d, c)})));
  const maiorPrevisto = medida === "votos" ? Math.max(0, ...prev.flatMap((f) => CAMPOS.map((c) => f[`votos_${c}`]))) : 0;
  const fins = afastar(CAMPOS.map((c) => longas.findLast((d) => d.campo === c)), "valor", maiorPrevisto);
  const virada = marcaVirada(ap, linhas, x, m.valor, nomes, {quadro, noQuadro});
  const aviso = marcaViradaPrevista(prevista, nomes, {quadro, embaixo: medida === "votos", linhasAcima: virada.length ? 1 : 0});
  const rotuloFim = (d) => (estreito ? "" : `${nomes[d.campo]}  `) + m.fmt(d.valor);
  // destinos: as marcas do destino do forecast e o texto delas
  const desenhar = (destinos) =>
    Plot.plot({
      width,
      height: 380,
      ...margens,
      marginTop: 28,
      x: escalaX(porHora, x0),
      y: {label: m.rotulo, labelArrow: "none", grid: true, nice: true, tickFormat: m.eixo},
      color: {domain: CAMPOS, range: [COR.petismo, COR.bolsonarismo]},
      marks: [
        medida === "pct" ? Plot.ruleY([50], {stroke: TINTA_FRACA, strokeDasharray: "3,3"}) : null,
        ...previstas,
        ...destinos,
        Plot.line(longas, {x, y: "valor", z: "campo", stroke: "campo", strokeWidth: 2, curve, strokeDasharray: tracejado}),
        ...rotulosFinais(fins, x, rotuloFim),
        ...virada,
        ...aviso.marcas,
        regua,
        Plot.tip(linhas, Plot.pointerX({x, y: (d) => Math.max(m.valor(d, "petismo"), m.valor(d, "bolsonarismo")), title: (d) => dica(d, nomes, {estimada, previsto})}))
      ]
    });
  // Com o destino do forecast, o texto dele só entra depois de um primeiro desenho, que dá onde fica cada coisa
  const rascunho = desenhar(destino.marcas);
  if (!destino.fins.length) return rascunho;
  const [sx, sy] = [rascunho.scale("x"), rascunho.scale("y")];
  const ocupadas = fins.map((d) => {
    const x1 = sx.apply(d[x]) + 8;
    const y = sy.apply(d.valor) + d.dy;
    return [x1, y - 6, x1 + largura(rotuloFim(d)), y + 6];
  });
  // Perto do fim, os rótulos do fim das curvas chegam aos pontos do forecast, que então saem, como a partir de 99%: o
  // forecast já coincide com a contagem
  const pontosDestino = destino.fins.map((d) => [sx.apply(100) - 5, sy.apply(d.valor) - 5, sx.apply(100) + 5, sy.apply(d.valor) + 5]);
  if (pontosDestino.some((p) => ocupadas.some((o) => cruzam(p, o)))) return desenhar([]);
  const fimCurvas = sx.apply(apuradoAgora);
  return desenhar([...destino.marcas, ...textoDestino(destino.fins, {medida, nomes, sx, sy, width, marginLeft: margens.marginLeft, fimCurvas, ocupadas})]);
}

// Regiões: ritmo da apuração (% das seções de cada região) ou votos válidos apurados em cada uma.
export function graficoRegioes(ap, {eixo = "hora", modo = "ritmo", width = 640}) {
  const porHora = eixo === "hora";
  const brasil = pontos(ap);
  const indices = brasil.map((_, i) => i).filter((i) => !porHora || brasil[i].minuto <= ap.t999);
  const regioes = modo === "ritmo" ? REGIOES.filter((r) => r !== "Exterior") : REGIOES;
  const x = porHora ? "hora" : "apuradoBrasil";
  const linhas = indices.flatMap((i) =>
    regioes.map((r) => ({
      hora: brasil[i].hora,
      apuradoBrasil: brasil[i].apurado,
      regiao: r,
      apurado: (100 * ap.regioes[r].secoes[i]) / ap.totais[r].secoes,
      validos: ap.regioes[r].validos[i]
    }))
  );
  const largas = indices.map((i) => ({hora: brasil[i].hora, apuradoBrasil: brasil[i].apurado, i}));
  const estimada = ap.tipo === "estimada";
  const titulo = (d) =>
    [
      `${estimada ? "~" : ""}${hora(d.hora)} · Brasil ${pct(d.apuradoBrasil, 1)} apurado`,
      ...regioes.map((r) =>
        modo === "ritmo"
          ? `${r}: ${pct((100 * ap.regioes[r].secoes[d.i]) / ap.totais[r].secoes, 1)}`
          : `${r}: ${mi(ap.regioes[r].validos[d.i])} votos`
      )
    ].join("\n");
  const curve = "step-after";
  const x0 = piso([brasil[0].apurado]);
  const y0 = piso(linhas.map((d) => d.apurado));
  const comum = {
    width,
    height: 340,
    marginLeft: 52,
    x: escalaX(porHora, x0, "Seções apuradas no Brasil"),
    color: {domain: REGIOES, range: REGIOES.map((r) => COR_REGIAO[r])}
  };
  const regua = Plot.ruleX(largas, Plot.pointerX({x, stroke: TINTA_FRACA}));
  if (modo === "ritmo") {
    return Plot.plot({
      ...comum,
      y: {domain: [y0, 100], label: "Seções apuradas na região", labelArrow: "none", grid: true, tickFormat: (v) => v + "%"},
      marks: [
        Plot.line(linhas, {x, y: "apurado", z: "regiao", stroke: "regiao", strokeWidth: 2, curve, strokeDasharray: estimada ? "6,3" : undefined}),
        porHora
          ? Plot.line(brasil.filter((d) => d.minuto <= ap.t999), {x: "hora", y: "apurado", stroke: TINTA, strokeWidth: 2.5, curve})
          : Plot.line([{x: Math.max(x0, y0), y: Math.max(x0, y0)}, {x: 100, y: 100}], {x: "x", y: "y", stroke: TINTA, strokeWidth: 1, strokeDasharray: "2,3"}),
        regua,
        Plot.tip(largas, Plot.pointerX({x, y: () => 50, title: titulo}))
      ]
    });
  }
  return Plot.plot({
    ...comum,
    y: {label: "Votos válidos apurados", labelArrow: "none", grid: true, tickFormat: miEixo},
    marks: [
      Plot.areaY(linhas, {x, y: "validos", fill: "regiao", order: REGIOES, curve, insetTop: 1}),
      regua,
      Plot.tip(largas, Plot.pointerX({x, y: (d) => ap.regioes.Brasil.validos[d.i] / 2, title: titulo}))
    ]
  });
}

// Resultado final por região: barras de 100% com petismo | outros | bolsonarismo. Durante a apuração, as barras são o
// que já foi apurado; `apurado` ({região: %}) vai ao lado do nome e `previsao` ({região: lugar do forecast}) marca,
// em cada barra, onde o petismo deve terminar (traço) e o intervalo de 80% (linha).
export function graficoResultadoRegioes(res, {width = 640, nomes, apurado = null, previsao = null}) {
  const ordem = ["Brasil", ...REGIOES].filter((n) => (n === "Brasil" ? res.Brasil : res.regioes[n])?.validos > 0);
  const dados = (n) => (n === "Brasil" ? res.Brasil : res.regioes[n]);
  const partes = ["petismo", "outros", "bolsonarismo"];
  const rotulo = {...nomes, outros: "Outros candidatos"};
  const linhas = ordem.flatMap((n) => {
    const d = dados(n);
    return partes.map((c) => ({regiao: n, campo: c, v: (100 * d[c]) / d.validos, votos: d[c]}));
  });
  const prev = previsao ? ordem.filter((n) => previsao[n]).map((n) => ({regiao: n, ...previsao[n]})) : [];
  const estreito = width < 480;
  const nome = (n) => (apurado?.[n] != null ? `${n} · ${pct(apurado[n], 0)}` : n);
  const pilha = (opcoes) => Plot.stackX({x: "v", y: "regiao", z: "campo", order: partes, ...opcoes});
  const dicaPrevisao = (n) => (previsao?.[n] ? `\nPrevisto para o fim: ${nomes.petismo} ${pct(previsao[n].petismo, 1)} (80%: ${pct(previsao[n].inf, 1)} a ${pct(previsao[n].sup, 1)})` : "");
  return Plot.plot({
    width,
    height: 34 * ordem.length + 44,
    marginLeft: apurado ? (estreito ? 120 : 140) : 104,
    x: {domain: [0, 100], label: apurado ? "% dos votos válidos já apurados" : "% dos votos válidos", labelArrow: "none", tickFormat: (v) => v + "%"},
    y: {domain: ordem, label: null, tickSize: 0, tickFormat: nome},
    color: {domain: partes, range: partes.map((c) => COR[c])},
    marks: [
      Plot.barX(linhas, pilha({fill: "campo", insetTop: 5, insetBottom: 5, insetLeft: 1, insetRight: 1})),
      Plot.text(linhas, pilha({text: (d) => (d.campo !== "outros" && d.v >= 9 ? pct(d.v, 1) : ""), fill: "white", fontWeight: 600})),
      Plot.ruleX([50], {stroke: TINTA, strokeOpacity: 0.5, strokeDasharray: "2,2"}),
      Plot.ruleY(prev, {y: "regiao", x1: "inf", x2: "sup", stroke: FUNDO, strokeWidth: 5, strokeOpacity: 0.85}),
      Plot.ruleY(prev, {y: "regiao", x1: "inf", x2: "sup", stroke: TINTA, strokeWidth: 1.5}),
      Plot.tickX(prev, {y: "regiao", x: "petismo", stroke: FUNDO, strokeWidth: 5, insetTop: 3, insetBottom: 3}),
      Plot.tickX(prev, {y: "regiao", x: "petismo", stroke: TINTA, strokeWidth: 2.5, insetTop: 4, insetBottom: 4}),
      Plot.tip(linhas, Plot.pointer(pilha({title: (d) => `${nome(d.regiao)}${apurado ? " apurado" : ""}\n${rotulo[d.campo]}: ${pct(d.v)} · ${num(d.votos)} votos${dicaPrevisao(d.regiao)}`})))
    ]
  });
}

// A noite gravada ao vivo (data/noite_<ano>_t<turno>.json): estimativa até a 1ª leitura oficial gravada, depois o oficial.
export function graficoNoite(n, {eixo = "hora", width = 640, nomes}) {
  const porHora = eixo === "hora";
  const x = porHora ? "hora" : "apurado";
  const of = n.oficial;
  const es = n.estimada;
  const corte = of.t[0];
  const oficiais = of.t.map((t, i) => ({
    t,
    hora: relogio(n.inicio, t),
    apurado: of.pct_secoes[i],
    petismo: of.petismo[i],
    bolsonarismo: of.bolsonarismo[i],
    vp: of.votos_petismo[i],
    vb: of.votos_bolsonarismo[i]
  }));
  const estimadas = es.t
    .map((t, i) => ({t, hora: relogio(n.inicio, t), apurado: es.pct_secoes[i], petismo: es.petismo[i], bolsonarismo: es.bolsonarismo[i]}))
    .filter((d) => d.petismo != null && d.t <= corte);
  const longas = (linhas) => linhas.flatMap((d) => CAMPOS.map((c) => ({...d, campo: c, valor: d[c]})));
  const fins = afastar(CAMPOS.map((c) => ({...oficiais.at(-1), campo: c, valor: oficiais.at(-1)[c]})));
  const estreito = width < 560;
  return Plot.plot({
    width,
    height: 380,
    marginLeft: 52,
    marginRight: estreito ? 64 : 172,
    x: escalaX(porHora),
    y: {label: "% dos votos válidos", labelArrow: "none", grid: true, nice: true, tickFormat: (v) => v + "%"},
    color: {domain: CAMPOS, range: [COR.petismo, COR.bolsonarismo]},
    marks: [
      Plot.ruleY([50], {stroke: TINTA_FRACA, strokeDasharray: "3,3"}),
      Plot.line(longas(estimadas), {x, y: "valor", z: "campo", stroke: "campo", strokeWidth: 2, strokeDasharray: "6,3"}),
      Plot.line(longas(oficiais), {x, y: "valor", z: "campo", stroke: "campo", strokeWidth: 2}),
      Plot.dot(longas(oficiais), {x, y: "valor", fill: "campo", r: 2.2}),
      ...rotulosFinais(fins, x, (d) => (estreito ? "" : `${nomes[d.campo]}  `) + pct(d.valor)),
      Plot.ruleX(oficiais, Plot.pointerX({x, stroke: TINTA_FRACA})),
      Plot.tip(
        oficiais,
        Plot.pointerX({
          x,
          y: (d) => Math.max(d.petismo, d.bolsonarismo),
          title: (d) =>
            [
              `${hora(d.hora)} · ${pct(d.apurado, 1)} das seções (oficial)`,
              `${nomes.petismo}: ${pct(d.petismo)} · ${num(d.vp)} votos`,
              `${nomes.bolsonarismo}: ${pct(d.bolsonarismo)} · ${num(d.vb)} votos`,
              `Diferença: ${pp(d.petismo - d.bolsonarismo, 2)} · ${comSinal(d.vp - d.vb)} votos`
            ].join("\n")
        })
      )
    ]
  });
}

// ---- Comparações entre eleições -------------------------------------------------------

// Vantagem do petismo (p.p. dos válidos) a cada ponto da apuração, a partir de 1% das seções.
export function serieComparacao(ap) {
  return [
    {
      ano: String(ap.ano),
      turno: ap.turno,
      trecho: ap.tipo === "exata" ? "exato" : "estimado",
      pontos: pontos(ap)
        .filter((d) => d.apurado >= 1)
        .map((d) => ({apurado: d.apurado, vantagem: (100 * (d.petismo - d.bolsonarismo)) / d.validos}))
    }
  ];
}

// A noite gravada: trecho estimado (até a 1ª leitura oficial) + leituras oficiais.
export function serieComparacaoNoite(n) {
  const corte = n.oficial.t[0];
  const est = n.estimada.t
    .map((t, i) => ({t, apurado: n.estimada.pct_secoes[i], p: n.estimada.petismo[i], b: n.estimada.bolsonarismo[i]}))
    .filter((d) => d.p != null && d.t <= corte && d.apurado >= 1);
  const of = n.oficial.t.map((t, i) => ({apurado: n.oficial.pct_secoes[i], p: n.oficial.petismo[i], b: n.oficial.bolsonarismo[i]}));
  const pt = (d) => ({apurado: d.apurado, vantagem: d.p - d.b});
  return [
    {ano: String(n.ano), turno: n.turno, trecho: "estimado", pontos: est.map(pt)},
    {ano: String(n.ano), turno: n.turno, trecho: "exato", pontos: of.map(pt)}
  ];
}

export function graficoComparacao(series, {modo = "vantagem", width = 640}) {
  const anos = [...new Set(series.map((s) => s.ano))].sort();
  // vantagem final de cada eleição/turno = último ponto do último trecho
  const final = new Map();
  for (const s of series) final.set(`${s.ano}-${s.turno}`, s.pontos.at(-1).vantagem);
  const linhas = series.flatMap((s) =>
    s.pontos.map((d) => ({
      ano: s.ano,
      turno: `${s.turno}º turno`,
      trecho: s.trecho,
      chave: `${s.ano}-${s.turno}-${s.trecho}`,
      apurado: d.apurado,
      y: modo === "vantagem" ? d.vantagem : d.vantagem - final.get(`${s.ano}-${s.turno}`)
    }))
  );
  // O ano no fim de cada curva; em "quanto ainda faltava mudar", todas terminam no zero, e o ano vai para o começo dela
  const chaves = [...new Set(linhas.map((d) => `${d.ano}|${d.turno}`))];
  const ponta = (k) => (modo === "vantagem" ? linhas.findLast((d) => `${d.ano}|${d.turno}` === k) : linhas.find((d) => `${d.ano}|${d.turno}` === k));
  const rotulos = chaves.map(ponta);
  const empilhar = width < 640;
  const faceta = empilhar ? {fy: "turno"} : {fx: "turno"};
  const turnos = [...new Set(linhas.map((d) => d.turno))].sort().map((turno) => ({turno}));
  return Plot.plot({
    width,
    height: empilhar ? 620 : 380,
    marginLeft: 56,
    marginRight: 44,
    marginTop: 28,
    x: {domain: [0, 100], label: "Seções apuradas", labelArrow: "none", tickFormat: (v) => v + "%"},
    y: {label: null, grid: true, tickFormat: (v) => comSinal(v, (a) => a.toLocaleString("pt-BR"))}, // a unidade está no subtítulo do cartão
    fx: {label: null, axis: null},
    fy: {label: null, axis: null},
    color: {domain: anos, range: anos.map((a) => `var(--ano-${a})`)},
    marks: [
      Plot.text(turnos, {text: "turno", frameAnchor: "top-left", dy: -20, fontWeight: 600, fontSize: 13, fill: TINTA, ...faceta}),
      Plot.ruleY([0], {stroke: TINTA_SUAVE}),
      Plot.line(linhas.filter((d) => d.trecho === "exato"), {x: "apurado", y: "y", z: "chave", stroke: "ano", strokeWidth: 2, ...faceta}),
      Plot.line(linhas.filter((d) => d.trecho === "estimado"), {x: "apurado", y: "y", z: "chave", stroke: "ano", strokeWidth: 2, strokeDasharray: "6,3", ...faceta}),
      // no começo, o ano pode cruzar outra curva: um contorno da cor do cartão o separa dela
      Plot.text(rotulos, {x: "apurado", y: "y", text: "ano", ...(modo === "vantagem" ? {dx: 6} : {dx: 2, dy: -10, stroke: "var(--theme-background-alt)", strokeWidth: 3, paintOrder: "stroke"}), textAnchor: "start", fill: TINTA, fontWeight: 600, ...faceta}),
      Plot.tip(
        linhas,
        Plot.pointer({
          x: "apurado",
          y: "y",
          ...faceta,
          title: (d) => `${d.ano}, ${d.turno}${d.trecho === "estimado" ? " (estimado)" : ""}\n${pct(d.apurado, 1)} apurado: ${pp(d.y, 2)}`
        })
      )
    ]
  });
}

// ---- Pesquisas (data/pesquisas_<ano>.json) -------------------------------------------

// Institutos do turno, do que mais publicou ao que menos.
export function institutos(dados, turno) {
  const n = new Map();
  for (const p of dados.turnos[String(turno)].pesquisas) n.set(p.instituto, (n.get(p.instituto) ?? 0) + 1);
  return [...n].sort((a, b) => b[1] - a[1]).map(([i]) => i);
}

function dicaPesquisa(p, nomes) {
  return [
    `${p.instituto}${p.contratante ? ` (${p.contratante})` : ""} · ${periodoCampo(p.inicio, p.fim)}`,
    `${p.amostra ? `${num(p.amostra)} entrevistas · ` : ""}${p.registro ? `registro ${p.registro}` : "sem registro no TSE encontrado"}`,
    `${nomes.petismo}: ${pct(p.petismo_validos, 1)} dos válidos (${pct(p.petismo, 1)} do total)`,
    `${nomes.bolsonarismo}: ${pct(p.bolsonarismo_validos, 1)} dos válidos (${pct(p.bolsonarismo, 1)} do total)`
  ].join("\n");
}

// O 1º turno das urnas na base das pesquisas de 2º turno: a parte de cada um só entre os dois (t = turno 2).
function primeiroTurnoEntreOsDois(t) {
  const r = t.resultado_primeiro_turno;
  return r ? Object.fromEntries(CAMPOS.map((c) => [c, (100 * r[c]) / (r.petismo + r.bolsonarismo)])) : null;
}

function dicaPrimeiroTurno(t, nomes) {
  const dois = primeiroTurnoEntreOsDois(t);
  return [
    `1º turno das urnas · ${diaCurto(dia(t.primeiro_turno))}`,
    ...CAMPOS.map((c) => `${nomes[c]}: ${pct(dois[c], 1)} entre os dois (${pct(t.resultado_primeiro_turno[c], 2)} dos válidos, com os outros)`)
  ].join("\n");
}

// Frase para a nota do gráfico de 2º turno: o que são as pesquisas de antes do 1º turno e o losango vazado.
export function notaPrimeiroTurno(t, nomes) {
  const dois = primeiroTurnoEntreOsDois(t);
  if (!dois) return "";
  const r = t.resultado_primeiro_turno;
  return `Antes do 1º turno, as pesquisas já testavam o confronto direto entre os dois; depois dele, medem a disputa de fato, e a linha de tendência recomeça. O losango vazado é o 1º turno das urnas contado só entre os dois, a mesma base das pesquisas de 2º turno: ${nomes.petismo} ${pct(dois.petismo, 1)} × ${nomes.bolsonarismo} ${pct(dois.bolsonarismo, 1)} (com os outros candidatos, ${pct(r.petismo, 1)} e ${pct(r.bolsonarismo, 1)} dos válidos).`;
}

// Frase para a nota das pesquisas, a mesma nas três eleições: como a linha de tendência é feita.
export const NOTA_TENDENCIA =
  "Tendência: em cada data, uma reta ajustada às pesquisas das semanas em volta, antes e depois dela, com mais peso para as mais próximas e as de amostra maior; no fim da linha, só entram as anteriores.";

// Cada pesquisa (pontos), a tendência (linhas) e o resultado das urnas (losangos), em % dos votos válidos.
// No 2º turno, a tendência recomeça depois do 1º turno (campo `segmento`), marcado por uma linha vertical e pelo
// resultado das urnas no 1º turno, contado só entre os dois (losangos vazados).
export function graficoPesquisas(dados, {turno, width = 640, nomes, destaque = null, periodo = "campanha"}) {
  const t = dados.turnos[String(turno)];
  const eleicao = dia(t.eleicao);
  const inicio = periodo === "campanha" ? new Date(Date.UTC(dados.ano, 7, 16, 12)) : new Date(Date.UTC(dados.ano, 0, 1, 12));
  const longas = t.pesquisas
    .filter((p) => dia(p.fim) >= inicio)
    .flatMap((p) => CAMPOS.map((c) => ({p, campo: c, data: dia(p.fim), valor: p[`${c}_validos`]})));
  const tendencia = t.tendencia
    ? t.tendencia.datas
        .flatMap((d, i) => CAMPOS.map((c) => ({data: dia(d), campo: c, valor: t.tendencia[c][i], trecho: `${c}-${t.tendencia.segmento?.[i] ?? 0}`})))
        .filter((d) => d.data >= inicio)
    : [];
  const primeiro = t.primeiro_turno ? [dia(t.primeiro_turno)] : [];
  const dois = primeiroTurnoEntreOsDois(t);
  const urnas1 = dois && primeiro[0] >= inicio ? CAMPOS.map((c) => ({data: primeiro[0], campo: c, valor: dois[c]})) : [];
  const resultado = t.resultado ? CAMPOS.map((c) => ({data: eleicao, campo: c, valor: t.resultado[c]})) : [];
  const fins = afastar(resultado.length ? resultado : CAMPOS.map((c) => tendencia.findLast((d) => d.campo === c)).filter(Boolean));
  // Sem pesquisas depois do 1º turno, a tendência termina antes dele: os rótulos vão para depois dos losangos vazados
  const aposLosangos = urnas1.length > 0 && !resultado.length && fins.every((d) => d.data < primeiro[0]);
  const rotulos = aposLosangos ? fins.map((d) => ({...d, data: primeiro[0]})) : fins;
  const destacadas = destaque ? longas.filter((d) => d.p.instituto === destaque) : longas;
  const apagadas = destaque ? longas.filter((d) => d.p.instituto !== destaque) : [];
  const estreito = width < 560;
  const marginRight = estreito ? 56 : 150;
  const fim = new Date(eleicao.getTime() + 2 * 864e5);
  // Antes do resultado, o rótulo diz que o número é o da tendência, se couber até a borda: na margem e no trecho do eixo
  // depois do fim da tendência (curto no período do ano eleitoral)
  const dx = aposLosangos ? 12 : 8;
  const espaco = (d) => marginRight - dx + ((fim - d.data) / (fim - inicio)) * (width - 48 - marginRight);
  const rotulo = (d, sufixo) => (estreito ? "" : `${nomes[d.campo]}  `) + pct(d.valor, 1) + sufixo;
  const sufixo = !resultado.length && rotulos.every((d) => largura(rotulo(d, " (tendência)")) <= espaco(d)) ? " (tendência)" : "";
  return Plot.plot({
    width,
    height: 380,
    marginLeft: 48,
    marginRight,
    x: {type: "utc", domain: [inicio, fim], label: null, tickFormat: mesEixo},
    y: {label: "% dos votos válidos", labelArrow: "none", grid: true, nice: true, tickFormat: (v) => v + "%"},
    color: {domain: CAMPOS, range: [COR.petismo, COR.bolsonarismo]},
    marks: [
      Plot.ruleY([50], {stroke: TINTA_FRACA, strokeDasharray: "3,3"}),
      Plot.ruleX([eleicao, ...primeiro], {stroke: TINTA_SUAVE, strokeDasharray: "2,3"}),
      Plot.text([eleicao], {x: (d) => d, text: () => `${turno}º turno`, frameAnchor: "top", dy: 2, dx: -4, textAnchor: "end", fill: TINTA_SUAVE, fontSize: 11}),
      Plot.text(primeiro.filter((d) => d >= inicio), {x: (d) => d, text: () => "1º turno", frameAnchor: "bottom", dy: -4, dx: -4, textAnchor: "end", fill: TINTA_SUAVE, fontSize: 11}),
      Plot.dot(apagadas, {x: "data", y: "valor", fill: "campo", r: 2, fillOpacity: 0.15}),
      Plot.dot(destacadas, {x: "data", y: "valor", fill: "campo", r: destaque ? 4 : 2.5, fillOpacity: destaque ? 1 : 0.45}),
      destaque
        ? Plot.line(destacadas, {x: "data", y: "valor", z: "campo", stroke: "campo", strokeWidth: 1.5})
        : Plot.line(tendencia, {x: "data", y: "valor", z: "trecho", stroke: "campo", strokeWidth: 2.5}),
      Plot.dot(urnas1, {x: "data", y: "valor", symbol: "diamond", r: 6, fill: FUNDO, stroke: "campo", strokeWidth: 2}),
      Plot.dot(resultado, {x: "data", y: "valor", symbol: "diamond", r: 7, fill: "campo", stroke: FUNDO, strokeWidth: 1.5}),
      ...rotulosFinais(rotulos, "data", (d) => rotulo(d, sufixo), dx),
      Plot.tip([...longas, ...urnas1], Plot.pointer({x: "data", y: "valor", title: (d) => (d.p ? dicaPesquisa(d.p, nomes) : dicaPrimeiroTurno(t, nomes))}))
    ]
  });
}

// Legenda do gráfico de pesquisas. primeiroTurno: o gráfico de 2º turno traz o 1º turno das urnas (losango vazado).
export function legendaPesquisas(nomes, {comResultado = true, primeiroTurno = false} = {}) {
  const neutro = "var(--theme-foreground-muted)";
  return legenda([
    {nome: nomes.petismo, cor: COR.petismo},
    {nome: nomes.bolsonarismo, cor: COR.bolsonarismo},
    {nome: "cada pesquisa", cor: neutro, estilo: "ponto"},
    {nome: "tendência", cor: neutro},
    ...(primeiroTurno ? [{nome: "1º turno das urnas, só entre os dois", cor: neutro, estilo: "losango vazado"}] : []),
    ...(comResultado ? [{nome: "resultado das urnas", cor: neutro, estilo: "losango"}] : [])
  ]);
}

// Frase que compara a média da semana final com as urnas.
export function resumoErro(t, nomes) {
  const m = t.media_semana_final;
  const r = t.resultado;
  if (!m || !r) return "";
  const lado = (c) => {
    const d = Math.abs(m[c] - r[c]);
    const valor = pct(d, 1).replace("%", "");
    return `${m[c] < r[c] ? "subestimou" : "superestimou"} ${nomes[c]} em ${valor} ${d < 2 ? "ponto" : "pontos"}`;
  };
  return `Na média das ${t.pesquisas_semana_final} pesquisas da semana final, ${nomes.petismo} tinha ${pct(m.petismo, 1)} e ${nomes.bolsonarismo}, ${pct(m.bolsonarismo, 1)} dos válidos; as urnas deram ${pct(r.petismo, 1)} e ${pct(r.bolsonarismo, 1)}. A média ${lado("bolsonarismo")} e ${lado("petismo")}.`;
}

// A última pesquisa de cada instituto. Com o resultado, a da semana final, que a tabela compara com as urnas
// (t.ultimas). Antes dele (o 2º turno de 2026, até a eleição), a mais recente de cada instituto entre as de campo
// inteiro depois do 1º turno, as mesmas da tendência e da projeção: muda a cada pesquisa nova.
export function ultimasPesquisas(t) {
  if (t.resultado || !t.primeiro_turno) return t.ultimas;
  const ultimas = new Map();
  for (const p of t.pesquisas) {
    if (p.inicio > t.primeiro_turno && !(ultimas.get(p.instituto)?.fim >= p.fim)) ultimas.set(p.instituto, p);
  }
  return [...ultimas.values()]
    .sort((a, b) => b.fim.localeCompare(a.fim) || a.instituto.localeCompare(b.instituto, "pt-BR"))
    .map((p) => ({instituto: p.instituto, fim: p.fim, registro: p.registro, petismo: p.petismo_validos, bolsonarismo: p.bolsonarismo_validos}));
}

// A última pesquisa de cada instituto (linhas: ultimasPesquisas) e, com o resultado, o erro de cada uma.
export function tabelaUltimas(t, nomes, linhas = t.ultimas) {
  const erro = (v) => (v == null ? "–" : pp(v, 1));
  const media = t.media_semana_final;
  return html`<div class="tabela"><table>
    <thead><tr><th>Instituto</th><th>Fim do campo</th>
      <th style="text-align:right">${nomes.petismo}</th><th style="text-align:right">${nomes.bolsonarismo}</th>
      ${t.resultado ? html`<th style="text-align:right">Erro na vantagem</th>` : ""}</tr></thead>
    <tbody>
      ${linhas.map((u) => html`<tr><td>${u.instituto}${u.registro ? "" : html` <span class="selo estimado">sem registro</span>`}</td>
        <td>${periodoCampo(u.fim, u.fim)}</td>
        <td style="text-align:right">${pct(u.petismo, 1)}</td><td style="text-align:right">${pct(u.bolsonarismo, 1)}</td>
        ${t.resultado ? html`<td style="text-align:right">${erro(u.erro_vantagem)}</td>` : ""}</tr>`)}
      ${media ? html`<tr style="font-weight:600"><td>Média da semana final (${t.pesquisas_semana_final} pesquisas)</td><td></td>
        <td style="text-align:right">${pct(media.petismo, 1)}</td><td style="text-align:right">${pct(media.bolsonarismo, 1)}</td>
        ${t.resultado ? html`<td style="text-align:right">${erro(media.petismo - t.resultado.petismo - (media.bolsonarismo - t.resultado.bolsonarismo))}</td>` : ""}</tr>` : ""}
      ${t.resultado ? html`<tr style="font-weight:600"><td>Resultado das urnas</td><td></td>
        <td style="text-align:right">${pct(t.resultado.petismo, 1)}</td><td style="text-align:right">${pct(t.resultado.bolsonarismo, 1)}</td><td></td></tr>` : ""}
    </tbody>
  </table></div>`;
}

// ---- Projeção do 2º turno (data/projecao.json) ----------------------------------------------
// A projeção guarda a parte do petismo nos válidos; a do bolsonarismo é o complemento.

export function lados(d) {
  return {
    petismo: {valor: d.petismo, inf: d.inf, sup: d.sup},
    bolsonarismo: {valor: 100 - d.petismo, inf: 100 - d.sup, sup: 100 - d.inf}
  };
}

export const chances = (d) => ({petismo: 100 * d.chance, bolsonarismo: 100 * (1 - d.chance)});

function dicaProjecao(d, nomes) {
  const l = lados(d);
  const ch = chances(d);
  return [
    `${diaCurto(dia(d.data))} · faltavam ${d.dias} dias · ${d.pesquisas ? `${d.pesquisas} ${d.pesquisas === 1 ? "pesquisa" : "pesquisas"} depois do 1º turno` : "nenhuma pesquisa depois do 1º turno"}`,
    ...CAMPOS.map((c) => `${nomes[c]}: ${pct(l[c].valor, 1)} (80%: ${pct(l[c].inf, 1)} a ${pct(l[c].sup, 1)}) · chance ${pct(ch[c], 0)}`)
  ].join("\n");
}

// A projeção para o dia da eleição, refeita a cada dia com o que se sabia até ali: linha e faixa de 80% de cada
// campo, as pesquisas de 2º turno feitas depois do 1º turno (pontos) e, se a eleição já houve, as urnas (losangos).
export function graficoProjecao(proj, {width = 640, nomes, pesquisas = null, height = 360}) {
  const eleicao = dia(proj.eleicao);
  const primeiro = dia(proj.primeiro_turno.data);
  const serie = proj.serie.map((d) => ({...d, dia: dia(d.data)}));
  const linhas = serie.flatMap((d) => CAMPOS.map((c) => ({dia: d.dia, campo: c, ...lados(d)[c]})));
  const pontos = pesquisas
    ? pesquisas.turnos["2"].pesquisas
        .filter((p) => dia(p.inicio) > primeiro)
        .flatMap((p) => CAMPOS.map((c) => ({p, campo: c, dia: dia(p.fim), valor: p[`${c}_validos`]})))
    : [];
  const urnas = proj.resultado ? CAMPOS.map((c) => ({campo: c, dia: eleicao, valor: c === "petismo" ? proj.resultado.petismo : 100 - proj.resultado.petismo})) : [];
  const ultimo = serie.at(-1);
  const fins = afastar(urnas.length ? urnas : CAMPOS.map((c) => ({campo: c, dia: ultimo.dia, valor: lados(ultimo)[c].valor})));
  const estreito = width < 560;
  const rotulo = (d) => (estreito ? "" : `${nomes[d.campo]}  `) + pct(d.valor, 1) + (urnas.length ? " (urnas)" : "");
  // a margem da direita cresce para caber o rótulo do fim, mais longo com "(urnas)", depois da eleição
  const marginRight = Math.max(estreito ? 56 : 150, ...fins.map((d) => largura(rotulo(d)) + 12));
  const [x0, x1] = [new Date(+primeiro - 864e5), new Date(+eleicao + 864e5)];
  // no eixo, uma data por semana; se elas não cabem, só a do 1º e a do 2º turno
  const semana = ((7 * 864e5) / (x1 - x0)) * (width - 48 - marginRight);
  return Plot.plot({
    width,
    height,
    marginLeft: 48,
    marginRight,
    x: {type: "utc", domain: [x0, x1], label: null, tickFormat: mesEixo, ticks: semana < 34 ? [primeiro, eleicao] : estreito ? 4 : 7},
    y: {label: "% dos votos válidos", labelArrow: "none", grid: true, nice: true, tickFormat: (v) => v + "%"},
    color: {domain: CAMPOS, range: [COR.petismo, COR.bolsonarismo]},
    marks: [
      Plot.ruleY([50], {stroke: TINTA_FRACA, strokeDasharray: "3,3"}),
      Plot.ruleX([eleicao], {stroke: TINTA_SUAVE, strokeDasharray: "2,3"}),
      Plot.text([eleicao], {x: (d) => d, text: () => "2º turno", frameAnchor: "top", dy: 2, dx: -4, textAnchor: "end", fill: TINTA_SUAVE, fontSize: 11}),
      Plot.areaY(linhas, {x: "dia", y1: "inf", y2: "sup", z: "campo", fill: "campo", fillOpacity: 0.16, curve: "step-after"}),
      Plot.dot(pontos, {x: "dia", y: "valor", fill: "campo", r: 2.5, fillOpacity: 0.45}),
      Plot.line(linhas, {x: "dia", y: "valor", z: "campo", stroke: "campo", strokeWidth: 2.5, curve: "step-after"}),
      Plot.dot(urnas, {x: "dia", y: "valor", symbol: "diamond", r: 7, fill: "campo", stroke: FUNDO, strokeWidth: 1.5}),
      ...rotulosFinais(fins, "dia", rotulo),
      Plot.ruleX(serie, Plot.pointerX({x: "dia", stroke: TINTA_FRACA})),
      Plot.tip(serie, Plot.pointerX({x: "dia", y: (d) => Math.max(d.petismo, 100 - d.petismo), title: (d) => dicaProjecao(d, nomes)}))
    ]
  });
}

// Os resultados possíveis segundo a projeção: a distribuição (normal) da diferença entre os dois, pintada com a
// cor de quem vence em cada lado do empate.
export function graficoCenarios(d, {width = 640, nomes}) {
  const media = 2 * d.petismo - 100;
  const desvio = 2 * d.desvio;
  const densidade = (x) => Math.exp(-0.5 * ((x - media) / desvio) ** 2);
  const passo = desvio / 50;
  const xs = Array.from({length: 401}, (_, i) => media - 4 * desvio + i * passo);
  const lado = (c) => [...(c === "petismo" ? [0] : []), ...xs.filter((x) => (c === "petismo" ? x > 0 : x < 0)), ...(c === "petismo" ? [] : [0])];
  const area = CAMPOS.flatMap((c) => lado(c).map((x) => ({x, y: densidade(x), campo: c})));
  const ch = chances(d);
  const limite = Math.max(Math.abs(media) + 4 * desvio, 10);
  const texto = (c) => (c === "petismo" ? `${nomes.petismo} vence: ${pct(ch.petismo, 0)} →` : `← ${nomes.bolsonarismo} vence: ${pct(ch.bolsonarismo, 0)}`);
  const estreito = width < 480; // os dois rótulos não cabem lado a lado: um em cada linha
  return Plot.plot({
    width,
    height: estreito ? 236 : 220,
    marginTop: estreito ? 44 : 28,
    x: {domain: [-limite, limite], label: caber(width - 10, ["Diferença entre os dois, em pontos dos votos válidos", "Diferença, em pontos dos votos válidos"]), labelArrow: "none", tickFormat: (v) => (v === 0 ? "empate" : `+${Math.abs(v)}`)},
    y: {axis: null},
    color: {domain: CAMPOS, range: [COR.petismo, COR.bolsonarismo]},
    marks: [
      Plot.areaY(area, {x: "x", y: "y", z: "campo", fill: "campo", fillOpacity: 0.8, curve: "linear"}),
      Plot.ruleX([0], {stroke: TINTA, strokeDasharray: "2,2"}),
      Plot.ruleY([0], {stroke: TINTA_FRACA}),
      Plot.text([texto("bolsonarismo")], {frameAnchor: "top-left", dy: estreito ? -36 : -20, textAnchor: "start", fill: COR.bolsonarismo, fontWeight: 600, fontSize: 13}),
      Plot.text([texto("petismo")], {frameAnchor: "top-right", dy: estreito ? -16 : -20, textAnchor: "end", fill: COR.petismo, fontWeight: 600, fontSize: 13})
    ]
  });
}

// Região ou UF: a projeção do petismo (ponto) e o intervalo de 80% (barra), na cor de quem fica à frente;
// com o resultado das urnas (losango), se a eleição já houve.
export function graficoLugares(proj, {nivel = "ufs", width = 640, nomes}) {
  const dados = Object.entries(proj[nivel])
    .filter(([k]) => k !== "ZZ")
    .map(([lugar, v]) => ({lugar, ...v, lider: v.petismo >= 50 ? "petismo" : "bolsonarismo", urnas: proj.resultado?.[nivel]?.[lugar]}))
    .sort((a, b) => b.petismo - a.petismo);
  const p = (v) => pct(v, 1);
  const dica = (d) =>
    [
      `${d.lugar} · projeção: ${nomes.petismo} ${p(d.petismo)}, ${nomes.bolsonarismo} ${p(100 - d.petismo)}`,
      `${nomes.petismo} entre ${p(d.inf)} e ${p(d.sup)} (80%) · chance de ${nomes.petismo}: ${pct(100 * d.chance, 0)}`,
      `1º turno: ${nomes.petismo} ${p(d.primeiro_turno.petismo)}, ${nomes.bolsonarismo} ${p(d.primeiro_turno.bolsonarismo)}, outros ${p(d.primeiro_turno.outros)}`,
      ...(d.urnas != null ? [`Urnas: ${nomes.petismo} ${p(d.urnas)}`] : [])
    ].join("\n");
  const min = Math.min(...dados.map((d) => Math.min(d.inf, d.urnas ?? 100)));
  const max = Math.max(...dados.map((d) => Math.max(d.sup, d.urnas ?? 0)));
  return Plot.plot({
    width,
    height: (nivel === "ufs" ? 18 : 28) * dados.length + 48,
    marginLeft: nivel === "ufs" ? 36 : 96,
    x: {domain: [Math.floor(min / 10) * 10, Math.ceil(max / 10) * 10], label: caber(width - 10, [`% de ${nomes.petismo} nos votos válidos (${nomes.bolsonarismo} fica com o restante)`, `% de ${nomes.petismo} nos votos válidos`]), labelArrow: "none", tickFormat: (v) => v + "%", grid: true},
    y: {domain: dados.map((d) => d.lugar), label: null, tickSize: 0},
    color: {domain: CAMPOS, range: [COR.petismo, COR.bolsonarismo]},
    marks: [
      Plot.ruleX([50], {stroke: TINTA, strokeOpacity: 0.5, strokeDasharray: "2,2"}),
      Plot.ruleY(dados, {y: "lugar", x1: "inf", x2: "sup", stroke: "lider", strokeWidth: nivel === "ufs" ? 5 : 8, strokeOpacity: 0.3}),
      Plot.dot(dados, {y: "lugar", x: "petismo", fill: "lider", r: nivel === "ufs" ? 3.5 : 5}),
      Plot.dot(dados.filter((d) => d.urnas != null), {y: "lugar", x: "urnas", symbol: "diamond", r: 4, fill: TINTA, stroke: FUNDO, strokeWidth: 1}),
      Plot.tip(dados, Plot.pointerY({y: "lugar", x: "petismo", title: dica}))
    ]
  });
}

// ---- Mapa: posição dos locais e o voto por local ----------------------------------------------

// Frase sob o mapa: quanto do eleitorado tem a posição exata do local de votação e o que fica de fora (exterior)
export function notaMapa(resumo, ano, res) {
  const p = resumo.anos[ano].precisao;
  const el = (k) => p[k]?.eleitores ?? 0;
  const total = el("0") + el("1") + el("2") + el("3");
  const exatos = (100 * (el("0") + el("1"))) / total;
  const doTSE = (100 * el("0")) / total;
  const aprox = (100 * (el("2") + el("3"))) / total;
  const exterior = res.regioes.Exterior.validos;
  return html`<p class="nota">Cada local de votação está na posição informada pelo TSE para ${pct(doTSE, 0)} do eleitorado${
    doTSE < 99.5 ? `; outros ${pct(exatos - doTSE, 1)} estão na posição do mesmo local numa outra eleição (de 2016 a 2026), e ${pct(aprox, 1)} têm a posição aproximada pelo bairro, pela zona eleitoral ou pelo município — esses votos se espalham num círculo maior` : ""
  }. Os ${num(exterior)} votos válidos do exterior não aparecem no mapa. Como as posições foram completadas e conferidas: <a href="./metodologia#mapa">Metodologia</a>.</p>`;
}

// Votos dos dois campos agrupados pela % do bolsonarismo no local onde foram dados
export function graficoPolarizacao(resumo, {ano, turno, width = 640, nomes}) {
  const r = resumo.anos[ano].turnos[turno];
  const f = resumo.faixa;
  const linhas = r.histograma.flatMap((b) =>
    ["petismo", "bolsonarismo"].map((c) => ({campo: c, x1: b.inicio, x2: b.inicio + f, votos: b[c], locais: b.locais}))
  );
  return Plot.plot({
    width,
    height: 260,
    marginLeft: 48,
    x: {domain: [0, 100], label: caber(width - 10, [`% de ${nomes.bolsonarismo} entre os dois, no local de votação`, `% de ${nomes.bolsonarismo} no local de votação`]), labelArrow: "none", tickFormat: (v) => v + "%", ticks: [0, 25, 50, 75, 100]},
    y: {label: "Votos", labelArrow: "none", tickFormat: miEixo, grid: true},
    color: {domain: ["petismo", "bolsonarismo"], range: [COR.petismo, COR.bolsonarismo]},
    marks: [
      Plot.rectY(linhas, Plot.stackY({x1: "x1", x2: "x2", y: "votos", fill: "campo", order: ["petismo", "bolsonarismo"], insetLeft: 1, insetRight: 1})),
      Plot.ruleX([50], {stroke: TINTA, strokeOpacity: 0.5, strokeDasharray: "2,2"}),
      Plot.ruleY([0], {stroke: TINTA_FRACA}),
      Plot.tip(linhas, Plot.pointerX(Plot.stackY({
        x1: "x1", x2: "x2", y: "votos", z: "campo", order: ["petismo", "bolsonarismo"],
        title: (d) => `Locais com ${d.x1}% a ${d.x2}% de ${nomes.bolsonarismo}: ${num(d.locais)}\n${nomes[d.campo]}: ${num(d.votos)} votos`
      })))
    ]
  });
}

export function frasePolarizacao(resumo, {ano, turno, nomes}) {
  const r = resumo.anos[ano].turnos[turno];
  const total = r.locais_petismo + r.locais_bolsonarismo;
  return `${pct(100 * r.acima_60, 0)} dos votos dos dois campos foram dados em locais onde um deles teve 60% ou mais, e ${pct(100 * r.acima_70, 0)} em locais com 70% ou mais. ${nomes.petismo} venceu em ${num(r.locais_petismo)} locais de votação (${pct((100 * r.locais_petismo) / total, 0)}) e ${nomes.bolsonarismo}, em ${num(r.locais_bolsonarismo)}.`;
}

// O voto por local nos três anos: % dos votos dos dois campos dados em locais com cada % de bolsonarismo
export function graficoPolarizacaoAnos(resumo, {turno, width = 640}) {
  const f = resumo.faixa;
  const linhas = Object.entries(resumo.anos)
    .filter(([, a]) => a.turnos[turno])
    .flatMap(([ano, a]) => {
      const h = a.turnos[turno].histograma;
      const total = h.reduce((s, b) => s + b.petismo + b.bolsonarismo, 0);
      return h.map((b) => ({ano, x: b.inicio + f / 2, parte: (100 * (b.petismo + b.bolsonarismo)) / total}));
    });
  const anos = [...new Set(linhas.map((d) => d.ano))];
  return Plot.plot({
    width,
    height: 280,
    marginLeft: 44,
    x: {domain: [0, 100], label: caber(width - 10, ["% do candidato bolsonarista entre os dois, no local de votação", "% do candidato bolsonarista no local de votação", "% do bolsonarista no local"]), labelArrow: "none", tickFormat: (v) => v + "%", ticks: [0, 25, 50, 75, 100]},
    y: {label: "% dos votos dos dois campos", labelArrow: "none", tickFormat: (v) => v + "%", grid: true},
    color: {domain: anos, range: anos.map((a) => `var(--ano-${a})`)},
    marks: [
      Plot.ruleX([50], {stroke: TINTA, strokeOpacity: 0.5, strokeDasharray: "2,2"}),
      Plot.ruleY([0], {stroke: TINTA_FRACA}),
      Plot.lineY(linhas, {x: "x", y: "parte", stroke: "ano", strokeWidth: 2, curve: "monotone-x"}),
      Plot.dot(linhas, {x: "x", y: "parte", fill: "ano", r: 2.5}),
      Plot.tip(linhas, Plot.pointer({x: "x", y: "parte", title: (d) => `${d.ano}: ${pct(d.parte, 1)} dos votos em locais com ${d.x - f / 2}% a ${d.x + f / 2}%`}))
    ]
  });
}
