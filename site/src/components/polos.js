// Os pontos dos cartões da página inicial: um ponto para cada 1% dos votos válidos. Eles saem misturados do centro e
// se separam nos dois campos, vermelho à esquerda e azul à direita, num disco do tamanho da votação de cada um. Os
// dos outros candidatos (num 1º turno) ficam no meio, indo de um lado para o outro. O movimento é só CSS (o estilo
// fica em index.md) e para com "reduzir movimento" no sistema.
import {svg} from "npm:htl";

const W = 260; // largura e altura do desenho, em unidades do viewBox
const H = 104;
const RAIO = 3.3; // de cada ponto
const PASSO = 4.7; // distância entre os pontos: o disco de n pontos tem raio ≈ PASSO·√n
const OURO = Math.PI * (3 - Math.sqrt(5)); // ângulo de ouro: os pontos do disco em espiral, como num girassol
const CAMPOS = ["petismo", "outros", "bolsonarismo"];
const CENTRO = {petismo: W / 4, outros: W / 2, bolsonarismo: (3 * W) / 4};

function girassol(n, cx, cy) {
  return Array.from({length: n}, (_, k) => {
    const r = PASSO * Math.sqrt(k + 0.5);
    return [cx + r * Math.cos(k * OURO), cy + r * Math.sin(k * OURO)];
  });
}

// Sorteio com semente (mulberry32): o mesmo desenho a cada visita
function sorteador(semente) {
  let a = semente >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), a | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Pontos de cada campo, somando 100 (maiores restos)
function contar(d) {
  const partes = CAMPOS.map((c) => (100 * d[c]) / d.validos);
  const n = partes.map(Math.floor);
  const ordem = partes.map((p, i) => [p - n[i], i]).sort((a, b) => b[0] - a[0]);
  const faltam = 100 - n.reduce((s, v) => s + v, 0);
  for (let k = 0; k < faltam; k++) n[ordem[k][1]]++;
  return Object.fromEntries(CAMPOS.map((c, i) => [c, n[i]]));
}

// d: o Brasil de um turno em data/resultados.json; atraso: quando a separação começa, em segundos.
export function polos(d, {semente = 1, atraso = 0} = {}) {
  const sorteio = sorteador(semente);
  const n = contar(d);
  const misturados = girassol(100, W / 2, H / 2);
  for (let i = misturados.length - 1; i > 0; i--) {
    const j = Math.floor(sorteio() * (i + 1));
    [misturados[i], misturados[j]] = [misturados[j], misturados[i]];
  }
  // os outros vagam no vão entre os dois discos, sem encostar neles
  const borda = (c) => PASSO * Math.sqrt(n[c]) + RAIO;
  const folga = Math.min(W / 2 - CENTRO.petismo - borda("petismo"), CENTRO.bolsonarismo - W / 2 - borda("bolsonarismo"));
  let usados = 0;
  const grupos = CAMPOS.filter((c) => n[c] > 0).map((c) => {
    // da esquerda para a direita, cada ponto da mistura vai para o lugar correspondente do seu disco
    const de = misturados.slice(usados, (usados += n[c])).sort((a, b) => a[0] - b[0]);
    const para = girassol(n[c], CENTRO[c], H / 2).sort((a, b) => a[0] - b[0]);
    const pontos = para.map(([x, y], k) => {
      const estilo = `--dx:${(de[k][0] - x).toFixed(1)}px;--dy:${(de[k][1] - y).toFixed(1)}px;--atraso:${(atraso + 0.25 + 0.6 * sorteio()).toFixed(2)}s`;
      const ponto = svg`<circle cx=${x.toFixed(1)} cy=${y.toFixed(1)} r=${RAIO} style=${estilo}></circle>`;
      if (c !== "outros") return ponto;
      const ax = Math.max(2, (folga - Math.abs(x - W / 2) - RAIO - 1.5) * (0.55 + 0.45 * sorteio()));
      const vaga = (a, t) => `--a:${a.toFixed(1)}px;--t:${t.toFixed(2)}s;--fase:${(-t * sorteio()).toFixed(2)}s`;
      return svg`<g class="vaga-x" style=${vaga(ax, 3.5 + 3 * sorteio())}><g class="vaga-y" style=${vaga(2 + 4 * sorteio(), 2.5 + 2 * sorteio())}>${ponto}</g></g>`;
    });
    return svg`<g class=${`polo ${c}`}>${pontos}</g>`;
  });
  return svg`<svg class="polos" viewBox="0 0 ${W} ${H}" aria-hidden="true">${grupos}</svg>`;
}
