// Mapa dos votos por local de votação.
//
// Pontos: cada ponto é um grupo de votos de um local de votação, na cor do campo (vermelho = petismo, azul =
// bolsonarismo, cinza = outros candidatos). Os pontos de cada local se espalham num disco em volta dele, com área
// proporcional aos votos (quem vota ali mora em volta, não em cima da escola). Quanto mais perto, menos votos por
// ponto, até 1 ponto = 1 voto; os pontos de uma escala continuam na seguinte, que só acrescenta pontos.
// Hexágonos: a cor é a vantagem de um campo sobre o outro na área; o tamanho, os votos válidos da área.
//
// Desenho: pontos em WebGL; terra, hexágonos, fronteiras e rótulos em canvas 2D. Projeção cônica de áreas iguais
// (paralelos-padrão de 2°S e 22°S, como a Albers do IBGE): a densidade de pontos vale o mesmo no país todo.
// Sem biblioteca de mapas nem fundo de terceiros: d3 (projeção, zoom, quadtree) e a malha do IBGE.

import * as d3 from "npm:d3";
import {html} from "npm:htl";
import {num, pct} from "./formato.js";

const MUNDO = 1000; // a projeção põe o Brasil num quadrado de 1000 × 1000 unidades
const ESCADA = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]; // votos por ponto
const ORCAMENTO = 320000; // pontos desenhados no máximo
const M2_POR_VOTO = 30; // área do disco de cada local: votos × 30 m²
const RAIO_M = [35, 300]; // limites do raio do disco (locais com posição exata)
const RAIO_HEX = 9; // px
const LIMIARES = [-40, -20, -10, -5, 0, 5, 10, 20, 40]; // vantagem do bolsonarismo, em p.p. dos válidos
const CATEGORIAS = ["petismo", "bolsonarismo", "outros"];
const PRECISAO = [
  null,
  "posição do mesmo local em outra eleição",
  "posição aproximada pelo bairro",
  "posição aproximada pela zona eleitoral ou pelo município"
];

// ---- Pequenas ferramentas -------------------------------------------------------------------

function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function semente(i, c, ano) {
  let h = Math.imul(i + 1, 0x9e3779b1) ^ Math.imul(c + 7, 0x85ebca77) ^ Math.imul(ano, 0xc2b2ae3d);
  h ^= h >>> 16;
  return Math.imul(h, 0x27d4eb2f) ^ (h >>> 15);
}

const somar = (deltas, Tipo = Float64Array) => {
  const out = new Tipo(deltas.length);
  let acc = 0;
  for (let i = 0; i < deltas.length; i++) out[i] = acc += deltas[i];
  return out;
};

// TopoJSON -> anéis/linhas em lon/lat, sem dependências (arcos com quantização e diferenças)
function decodificarArcos(topo) {
  const [sx, sy] = topo.transform.scale;
  const [tx, ty] = topo.transform.translate;
  return topo.arcs.map((arco) => {
    let x = 0, y = 0;
    return arco.map(([dx, dy]) => [(x += dx) * sx + tx, (y += dy) * sy + ty]);
  });
}

function anel(arcos, indices) {
  const pts = [];
  for (const i of indices) {
    const a = i < 0 ? arcos[~i].slice().reverse() : arcos[i];
    for (let k = pts.length ? 1 : 0; k < a.length; k++) pts.push(a[k]);
  }
  return pts;
}

function poligonosDe(geometria) {
  if (geometria.type === "Polygon") return [geometria.arcs];
  if (geometria.type === "MultiPolygon") return geometria.arcs;
  return [];
}

// Cor CSS qualquer (variável, color-mix...) -> d3.rgb. O navegador resolve a cor num elemento; como o resultado
// pode vir num formato que o d3 não lê (ex.: "color(srgb ...)"), ela é pintada num pixel e lida de volta.
let pixel = null;
function resolverCor(elemento, css) {
  const s = document.createElement("span");
  s.style.color = css;
  s.style.display = "none";
  elemento.appendChild(s);
  const valor = getComputedStyle(s).color;
  s.remove();
  if (!pixel) {
    const c = document.createElement("canvas");
    c.width = c.height = 1;
    pixel = c.getContext("2d", {willReadFrequently: true});
  }
  pixel.clearRect(0, 0, 1, 1);
  pixel.fillStyle = "#808080";
  pixel.fillStyle = valor;
  pixel.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = pixel.getImageData(0, 0, 1, 1).data;
  return d3.rgb(r, g, b, a / 255);
}

// ---- WebGL -----------------------------------------------------------------------------------

const VERTICE = `
attribute vec2 a_pos;
attribute float a_cat;
uniform vec2 u_escala;
uniform vec2 u_desloc;
uniform mediump float u_tam; // mesma precisão do fragmento (o WebGL exige)
varying float v_cat;
void main() {
  gl_Position = vec4(a_pos * u_escala + u_desloc, 0.0, 1.0);
  gl_PointSize = u_tam;
  v_cat = a_cat;
}`;

const FRAGMENTO = `
precision mediump float;
uniform vec4 u_cores[3];
uniform float u_tam;
varying float v_cat;
void main() {
  vec4 cor = v_cat < 0.5 ? u_cores[0] : (v_cat < 1.5 ? u_cores[1] : u_cores[2]);
  float a = cor.a;
  if (u_tam > 2.5) {
    float d = length(gl_PointCoord - 0.5) * u_tam;
    a *= clamp(0.5 * u_tam - d + 0.5, 0.0, 1.0);
    if (a <= 0.0) discard;
  }
  gl_FragColor = vec4(cor.rgb * a, a);
}`;

function criarGL(canvas) {
  const gl = canvas.getContext("webgl", {alpha: true, premultipliedAlpha: true, antialias: false});
  if (!gl) return null;
  const sombreador = (tipo, fonte) => {
    const s = gl.createShader(tipo);
    gl.shaderSource(s, fonte);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  };
  const prog = gl.createProgram();
  gl.attachShader(prog, sombreador(gl.VERTEX_SHADER, VERTICE));
  gl.attachShader(prog, sombreador(gl.FRAGMENT_SHADER, FRAGMENTO));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
  return {
    gl,
    prog,
    bufPos: gl.createBuffer(),
    bufCat: gl.createBuffer(),
    aPos: gl.getAttribLocation(prog, "a_pos"),
    aCat: gl.getAttribLocation(prog, "a_cat"),
    uEscala: gl.getUniformLocation(prog, "u_escala"),
    uDesloc: gl.getUniformLocation(prog, "u_desloc"),
    uTam: gl.getUniformLocation(prog, "u_tam"),
    uCores: gl.getUniformLocation(prog, "u_cores"),
    n: 0
  };
}

// ---- Ícones ------------------------------------------------------------------------------------

const icone = (d) =>
  html`<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d=${d} fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ICONES = {
  mais: "M8 3v10M3 8h10",
  menos: "M3 8h10",
  brasil: "M2.5 7.5 8 3l5.5 4.5M4 6.5V13h8V6.5",
  tela: "M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10"
};

// ---- O mapa --------------------------------------------------------------------------------------

/**
 * Mapa dos votos de um ano. Os arquivos (FileAttachment) só são carregados quando o mapa chega perto da tela.
 * Devolve o elemento, com .mostrar(turno) para trocar o turno sem perder o zoom.
 */
export function mapaDeVotos({locais, nomes, malha, municipios, nomesCampos, turno = 2}) {
  const id = "mapa-" + Math.random().toString(36).slice(2, 9);
  const raiz = html`<figure class="mapa" role="group" aria-label="Mapa interativo dos votos por local de votação">
    <canvas class="mapa-camada"></canvas>
    <canvas class="mapa-camada"></canvas>
    <canvas class="mapa-camada mapa-interacao" role="img" aria-label="Mapa de pontos: cada ponto é um grupo de votos num local de votação"></canvas>
    <div class="mapa-barra">
      <div class="mapa-modo" role="group" aria-label="Mostrar como">
        <button type="button" data-modo="pontos" aria-pressed="true">Pontos</button>
        <button type="button" data-modo="hex" aria-pressed="false">Hexágonos</button>
      </div>
      <input class="mapa-busca" type="search" placeholder="Ir para um município…" list=${id} aria-label="Ir para um município" autocomplete="off" spellcheck="false">
      <datalist id=${id}></datalist>
    </div>
    <div class="mapa-zoom">
      <button type="button" data-acao="mais" title="Aproximar" aria-label="Aproximar">${icone(ICONES.mais)}</button>
      <button type="button" data-acao="menos" title="Afastar" aria-label="Afastar">${icone(ICONES.menos)}</button>
      <button type="button" data-acao="brasil" title="Brasil inteiro" aria-label="Brasil inteiro">${icone(ICONES.brasil)}</button>
      <button type="button" data-acao="tela" title="Tela cheia" aria-label="Tela cheia">${icone(ICONES.tela)}</button>
    </div>
    <div class="mapa-legenda"></div>
    <div class="mapa-dica" hidden></div>
    <div class="mapa-info" hidden></div>
    <div class="mapa-aviso">Carregando o mapa…</div>
  </figure>`;
  const [cBase, cPontos, cTopo] = raiz.querySelectorAll("canvas");
  const el = (sel) => raiz.querySelector(sel);
  const legenda = el(".mapa-legenda"), dica = el(".mapa-dica"), info = el(".mapa-info"), aviso = el(".mapa-aviso");
  const busca = el(".mapa-busca"), lista = el("datalist");
  const ctxBase = cBase.getContext("2d");
  const ctxTopo = cTopo.getContext("2d");
  let webgl = null;
  try {
    webgl = criarGL(cPontos);
  } catch (e) {
    console.warn("Mapa: WebGL indisponível", e);
  }

  const estado = {turno, modo: webgl ? "pontos" : "hex", t: d3.zoomIdentity, W: 0, H: 0, dpr: 1, k0: 1, pronto: false};
  let D = null; // dados preparados
  let cores = null;
  let pedido = 0;
  let nomesLocais = null, pedidoNomes = null;
  let destaque = null; // {tipo: "local"|"hex", ...} sob o cursor ou tocado
  let municipioDestacado = null; // Path2D do município buscado
  let geracao = null; // {N, x0, x1, y0, y1, turno}
  let hexCache = null;
  let timerPontos = 0;

  // ---- Dados -----------------------------------------------------------------------------------

  function preparar(L, M, T) {
    const n = L.n;
    const esc = L.escala;
    const lon = somar(L.lon), lat = somar(L.lat);
    const mun = somar(L.municipio, Int32Array);
    const arcos = decodificarArcos(T);
    const geoms = T.objects.municipios.geometries;

    // A projeção põe todos os vértices da malha (o Brasil inteiro) no quadrado do mundo
    const todos = {type: "MultiPoint", coordinates: arcos.flat()};
    const proj = d3.geoConicEqualArea().parallels([-2, -22]).rotate([54, 0]).fitExtent([[0, 0], [MUNDO, MUNDO]], todos);
    const a = proj([-54, -12]), b = proj([-54, -12.009]);
    const porMetro = Math.hypot(b[0] - a[0], b[1] - a[1]) / 1000.8;

    const wx = new Float32Array(n), wy = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const p = proj([lon[i] / esc, lat[i] / esc]);
      wx[i] = p[0];
      wy[i] = p[1];
    }

    // Votos de cada turno
    const votos = {};
    for (const t of L.turnos) {
      const v = L.votos[String(t)];
      const pt = Int32Array.from(v.petismo), bo = Int32Array.from(v.bolsonarismo);
      const ou = v.outros ? Int32Array.from(v.outros) : new Int32Array(n);
      const total = new Int32Array(n);
      for (let i = 0; i < n; i++) total[i] = pt[i] + bo[i] + ou[i];
      votos[t] = {cat: [pt, bo, ou], total};
    }

    // Raio do disco de cada local (unidades do mundo): pela maior votação entre os turnos
    const precisao = new Uint8Array(n);
    for (let i = 0; i < n; i++) precisao[i] = L.precisao.charCodeAt(i) - 48;
    const raio = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let v = 0;
      for (const t of L.turnos) v = Math.max(v, votos[t].total[i]);
      raio[i] = Math.min(RAIO_M[1], Math.max(RAIO_M[0], Math.sqrt((v * M2_POR_VOTO) / Math.PI)));
    }
    for (const [i, r] of Object.entries(L.raio)) raio[+i] = Math.max(raio[+i], r);
    for (let i = 0; i < n; i++) raio[i] *= porMetro;

    // Caminhos (em coordenadas do mundo) da terra, das fronteiras e dos municípios, por UF
    const P = (pts, caminho) => {
      for (let k = 0; k < pts.length; k++) {
        const p = proj(pts[k]);
        if (k) caminho.lineTo(p[0], p[1]);
        else caminho.moveTo(p[0], p[1]);
      }
    };
    const terra = new Path2D();
    const usos = new Map(); // arco -> geometrias que o usam
    geoms.forEach((g, gi) => {
      for (const poli of poligonosDe(g)) {
        for (const r of poli) {
          P(anel(arcos, r), terra);
          terra.closePath();
          for (const i of r) {
            const k = i < 0 ? ~i : i;
            if (!usos.has(k)) usos.set(k, []);
            usos.get(k).push(gi);
          }
        }
      }
    });
    const uf = (gi) => geoms[gi].id.slice(0, 2);
    const contorno = new Path2D(), ufs = new Path2D();
    const porUF = new Map(); // UF -> {caminho, caixa}
    for (const [k, gs] of usos) {
      const pts = arcos[k];
      if (gs.length === 1) P(pts, contorno);
      else if (uf(gs[0]) !== uf(gs[1])) P(pts, ufs);
      else {
        const u = uf(gs[0]);
        if (!porUF.has(u)) porUF.set(u, {caminho: new Path2D(), caixa: [Infinity, Infinity, -Infinity, -Infinity]});
        const c = porUF.get(u);
        P(pts, c.caminho);
        for (const q of pts) {
          const p = proj(q);
          c.caixa[0] = Math.min(c.caixa[0], p[0]);
          c.caixa[1] = Math.min(c.caixa[1], p[1]);
          c.caixa[2] = Math.max(c.caixa[2], p[0]);
          c.caixa[3] = Math.max(c.caixa[3], p[1]);
        }
      }
    }

    // Municípios: rótulos (do maior eleitorado para o menor) e busca
    const nm = M.codigo.length;
    const rotulos = [];
    for (let j = 0; j < nm; j++) {
      const p = proj([M.lon[j] / esc, M.lat[j] / esc]);
      rotulos.push({j, x: p[0], y: p[1], nome: M.nome[j], eleitores: M.eleitores[j]});
    }
    rotulos.sort((a, b) => b.eleitores - a.eleitores);
    const geomPorCodigo = new Map(geoms.map((g) => [+g.id, g]));

    D = {
      n, ano: L.ano, turnos: L.turnos, wx, wy, mun, votos, raio, precisao, proj, arcos, geomPorCodigo,
      M, terra, contorno, ufs, porUF: [...porUF.values()], rotulos, raioMax: Math.min(d3.max(raio), 2000 * porMetro),
      quadtree: d3.quadtree(d3.range(n), (i) => wx[i], (i) => wy[i])
    };
    if (!D.turnos.includes(estado.turno)) estado.turno = D.turnos.at(-1);

    // Lista da busca
    const opcoes = d3.range(nm).sort((a, b) => d3.ascending(M.nome[a], M.nome[b]));
    lista.replaceChildren(...opcoes.map((j) => html`<option value=${`${M.nome[j]} (${M.uf[j]})`}>`));
  }

  // ---- Cores do tema ---------------------------------------------------------------------------

  function lerCores() {
    const fundo = resolverCor(raiz, "var(--theme-background-alt, var(--theme-background))");
    const tinta = resolverCor(raiz, "var(--theme-foreground)");
    const mistura = (f) => d3.interpolateLab(fundo, tinta)(f);
    const campo = Object.fromEntries(CATEGORIAS.map((c) => [c, resolverCor(raiz, `var(--${c})`)]));
    const neutro = d3.color(mistura(0.12));
    const rampa = (c) => [0.2, 0.42, 0.62, 0.82, 1].map((f) => d3.interpolateLab(neutro, campo[c])(f));
    const pt = rampa("petismo"), bo = rampa("bolsonarismo");
    cores = {
      fundo: fundo.formatRgb(),
      terra: d3.color(mistura(0.045)).formatRgb(),
      contorno: d3.color(mistura(0.42)).formatRgb(),
      ufs: d3.color(mistura(0.36)).formatRgb(),
      municipios: d3.color(mistura(0.2)).formatRgb(),
      rotulo: tinta.formatRgb(),
      fonte: getComputedStyle(raiz).fontFamily || "system-ui, sans-serif",
      campo,
      // classes de LIMIARES: da maior vantagem do petismo à maior do bolsonarismo
      classes: [...pt.slice().reverse(), ...bo]
    };
  }

  const classe = (vantagem) => d3.bisectRight(LIMIARES, vantagem); // 0..9

  // ---- Tamanho e zoom ------------------------------------------------------------------------------

  function medir() {
    const W = raiz.clientWidth;
    if (document.fullscreenElement === raiz) return {W, H: window.innerHeight};
    const H = Math.min(760, window.innerHeight * 0.8, W * (W < 640 ? 1.45 : 0.78));
    return {W, H: Math.round(Math.max(380, H))};
  }

  // O Brasil inteiro no espaço livre: abaixo da barra de controles e à esquerda dos botões de zoom
  function brasilInteiro() {
    const {W, H} = estado;
    const barra = raiz.querySelector(".mapa-barra");
    const topo = Math.min(H * 0.25, barra.offsetTop + barra.offsetHeight + 6);
    const direita = W < 640 ? 48 : 0;
    const k = (Math.min(W - direita, H - topo - 8) / MUNDO) * 0.96;
    return d3.zoomIdentity.translate((W - direita - MUNDO * k) / 2, topo + (H - topo - 8 - MUNDO * k) / 2).scale(k);
  }

  function redimensionar() {
    const {W, H} = medir();
    if (!W || (W === estado.W && H === estado.H)) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const antes = estado.W ? {W: estado.W, H: estado.H, t: estado.t, k0: estado.k0} : null;
    Object.assign(estado, {W, H, dpr});
    raiz.style.height = document.fullscreenElement === raiz ? "" : `${H}px`;
    for (const c of [cBase, cPontos, cTopo]) {
      c.width = Math.round(W * dpr);
      c.height = Math.round(H * dpr);
      c.style.width = `${W}px`;
      c.style.height = `${H}px`;
    }
    const inicial = brasilInteiro();
    estado.k0 = inicial.k;
    zoom.scaleExtent([estado.k0 * 0.8, estado.k0 * 6000]).translateExtent([[-MUNDO * 0.3, -MUNDO * 0.3], [MUNDO * 1.3, MUNDO * 1.3]]);
    if (!antes) {
      d3.select(cTopo).call(zoom.transform, inicial);
    } else {
      // mantém o centro e o quanto estava aproximado
      const cx = (antes.W / 2 - antes.t.x) / antes.t.k, cy = (antes.H / 2 - antes.t.y) / antes.t.k;
      const k = (antes.t.k / antes.k0) * estado.k0;
      d3.select(cTopo).call(zoom.transform, d3.zoomIdentity.translate(W / 2 - cx * k, H / 2 - cy * k).scale(k));
    }
    agendarPontos(0);
  }

  const zoom = d3
    .zoom()
    .filter((e) => {
      if (e.type === "wheel") {
        if (e.ctrlKey || e.metaKey || document.fullscreenElement === raiz) return true;
        mostrarDica("Para aproximar, use Ctrl + rolagem (⌘ no Mac), os botões + e − ou dois cliques");
        return false;
      }
      return !e.button;
    })
    .wheelDelta((e) => -e.deltaY * (e.deltaMode === 1 ? 0.05 : e.deltaMode ? 1 : 0.002) * (e.ctrlKey && Math.abs(e.deltaY) < 40 ? 8 : 1.5))
    .on("zoom", (e) => {
      estado.t = e.transform;
      if (e.sourceEvent) esconderInfo();
      agendar();
    })
    .on("end", () => agendarPontos());
  d3.select(cTopo).call(zoom);

  let timerDica = 0;
  function mostrarDica(texto) {
    dica.textContent = texto;
    dica.hidden = false;
    clearTimeout(timerDica);
    timerDica = setTimeout(() => (dica.hidden = true), 1600);
  }

  // ---- Desenho ---------------------------------------------------------------------------------------

  function agendar() {
    if (!pedido) pedido = requestAnimationFrame(desenhar);
  }

  function visivel(margem = 0) {
    const {t, W, H} = estado;
    const mx = (W * margem) / t.k, my = (H * margem) / t.k;
    return [-t.x / t.k - mx, -t.y / t.k - my, (W - t.x) / t.k + mx, (H - t.y) / t.k + my];
  }

  function desenhar() {
    pedido = 0;
    if (!D || !estado.W) return;
    const {W, H, dpr, t} = estado;
    const zoomRel = t.k / estado.k0;

    // Terra e hexágonos
    ctxBase.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctxBase.clearRect(0, 0, W, H);
    ctxBase.setTransform(dpr * t.k, 0, 0, dpr * t.k, dpr * t.x, dpr * t.y);
    ctxBase.fillStyle = cores.terra;
    ctxBase.fill(D.terra);
    if (estado.modo === "hex") desenharHexagonos();

    // Pontos
    if (webgl) {
      const {gl} = webgl;
      gl.viewport(0, 0, cPontos.width, cPontos.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      if (estado.modo === "pontos" && webgl.n) desenharPontos(zoomRel);
    }

    // Fronteiras, rótulos e destaque
    const c = ctxTopo;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    c.setTransform(dpr * t.k, 0, 0, dpr * t.k, dpr * t.x, dpr * t.y);
    c.lineJoin = "round";
    const fMun = Math.max(0, Math.min(1, (Math.log2(zoomRel) - 2.2) / 1.2));
    if (fMun > 0) {
      const [x0, y0, x1, y1] = visivel();
      c.globalAlpha = fMun;
      c.strokeStyle = cores.municipios;
      c.lineWidth = 0.6 / t.k;
      for (const u of D.porUF) {
        const [a, b, cc, d] = u.caixa;
        if (cc < x0 || a > x1 || d < y0 || b > y1) continue;
        c.stroke(u.caminho);
      }
      c.globalAlpha = 1;
    }
    c.strokeStyle = cores.ufs;
    c.lineWidth = (zoomRel > 4 ? 1.3 : 0.9) / t.k;
    c.stroke(D.ufs);
    c.strokeStyle = cores.contorno;
    c.lineWidth = 1 / t.k;
    c.stroke(D.contorno);
    if (municipioDestacado) {
      c.strokeStyle = cores.rotulo;
      c.lineWidth = 2 / t.k;
      c.stroke(municipioDestacado);
    }
    if (destaque?.tipo === "local") {
      const i = destaque.i;
      c.beginPath();
      c.arc(D.wx[i], D.wy[i], Math.max(D.raio[i], 6 / t.k), 0, 2 * Math.PI);
      c.strokeStyle = cores.rotulo;
      c.lineWidth = 1.5 / t.k;
      c.stroke();
    }
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (destaque?.tipo === "hex") contornoHex(c, destaque.bin);
    desenharRotulos(c, zoomRel);
  }

  function desenharPontos(zoomRel) {
    const {gl, prog} = webgl;
    const {W, H, t, dpr} = estado;
    gl.useProgram(prog);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.uniform2f(webgl.uEscala, (2 * t.k) / W, (-2 * t.k) / H);
    gl.uniform2f(webgl.uDesloc, (2 * t.x) / W - 1, 1 - (2 * t.y) / H);
    const tam = Math.min(3.6, Math.max(1.3, 1.3 + 0.2 * Math.log2(Math.max(1, zoomRel)))) * dpr;
    gl.uniform1f(webgl.uTam, tam);
    const alfa = zoomRel < 3 ? 0.82 : 0.9;
    const rgba = CATEGORIAS.flatMap((c) => {
      const cor = cores.campo[c];
      return [cor.r / 255, cor.g / 255, cor.b / 255, alfa];
    });
    gl.uniform4fv(webgl.uCores, rgba);
    gl.bindBuffer(gl.ARRAY_BUFFER, webgl.bufPos);
    gl.enableVertexAttribArray(webgl.aPos);
    gl.vertexAttribPointer(webgl.aPos, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, webgl.bufCat);
    gl.enableVertexAttribArray(webgl.aCat);
    gl.vertexAttribPointer(webgl.aCat, 1, gl.UNSIGNED_BYTE, false, 0, 0);
    gl.drawArrays(gl.POINTS, 0, webgl.n);
  }

  // Gera os pontos dos locais à vista (com folga), com a escala que cabe no orçamento
  function gerarPontos() {
    if (!D || !webgl || estado.modo !== "pontos") return;
    const v = D.votos[estado.turno];
    const [x0, y0, x1, y1] = visivel(0.35);
    const idx = [];
    let total = 0;
    for (let i = 0; i < D.n; i++) {
      const x = D.wx[i], y = D.wy[i];
      if (x < x0 || x > x1 || y < y0 || y > y1) continue;
      idx.push(i);
      total += v.total[i];
    }
    const N = ESCADA.find((e) => total / e <= ORCAMENTO) ?? ESCADA.at(-1);
    const g = geracao;
    if (g && g.N === N && g.turno === estado.turno && x0 >= g.x0 && y0 >= g.y0 && x1 <= g.x1 && y1 <= g.y1) return;

    // Fração de cada local e campo: a mesma em todas as escalas (os pontos de uma escala estão na seguinte)
    const frac = (i, c) => (semente(i, c + 3, D.ano) >>> 0) / 4294967296;
    let cont = 0;
    for (const i of idx) for (let c = 0; c < 3; c++) cont += Math.floor(v.cat[c][i] / N + frac(i, c));
    const pos = new Float32Array(cont * 2), cat = new Uint8Array(cont), chave = new Float64Array(cont);
    let j = 0;
    for (const i of idx) {
      const R = D.raio[i], cx = D.wx[i], cy = D.wy[i];
      for (let c = 0; c < 3; c++) {
        const m = Math.floor(v.cat[c][i] / N + frac(i, c));
        if (!m) continue;
        const rng = mulberry32(semente(i, c, D.ano));
        for (let s = 0; s < m; s++) {
          const a = 2 * Math.PI * rng(), r = R * Math.sqrt(rng());
          pos[2 * j] = cx + r * Math.cos(a);
          pos[2 * j + 1] = cy + r * Math.sin(a);
          cat[j] = c;
          chave[j] = Math.floor(rng() * 4294967296) * 1048576 + j; // ordem de desenho aleatória e estável
          j++;
        }
      }
    }
    chave.sort();
    const pos2 = new Float32Array(cont * 2), cat2 = new Uint8Array(cont);
    for (let k = 0; k < cont; k++) {
      const o = chave[k] % 1048576;
      pos2[2 * k] = pos[2 * o];
      pos2[2 * k + 1] = pos[2 * o + 1];
      cat2[k] = cat[o];
    }
    const {gl} = webgl;
    gl.bindBuffer(gl.ARRAY_BUFFER, webgl.bufPos);
    gl.bufferData(gl.ARRAY_BUFFER, pos2, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, webgl.bufCat);
    gl.bufferData(gl.ARRAY_BUFFER, cat2, gl.STATIC_DRAW);
    webgl.n = cont;
    geracao = {N, turno: estado.turno, x0, y0, x1, y1};
    atualizarLegenda();
    agendar();
  }

  function agendarPontos(espera = 120) {
    clearTimeout(timerPontos);
    timerPontos = setTimeout(gerarPontos, espera);
  }

  // Hexágonos numa grade presa ao mapa (não à tela), em degraus de meia oitava de zoom
  function hexagonos() {
    const nivel = Math.round(Math.log2(estado.t.k) * 2) / 2;
    if (hexCache && hexCache.nivel === nivel && hexCache.turno === estado.turno) return hexCache;
    const r = RAIO_HEX / 2 ** nivel;
    const v = D.votos[estado.turno];
    const bins = new Map();
    const membro = new Float64Array(D.n);
    for (let i = 0; i < D.n; i++) {
      const {q, rr, chave} = hexDe(D.wx[i], D.wy[i], r);
      let b = bins.get(chave);
      if (!b) bins.set(chave, (b = {x: r * Math.sqrt(3) * (q + rr / 2), y: r * 1.5 * rr, pt: 0, bo: 0, ou: 0, locais: 0, chave}));
      b.pt += v.cat[0][i];
      b.bo += v.cat[1][i];
      b.ou += v.cat[2][i];
      b.locais++;
      membro[i] = chave;
    }
    const lista = [...bins.values()].filter((b) => b.pt + b.bo + b.ou > 0);
    const ref = d3.quantile(lista, 0.85, (b) => b.pt + b.bo + b.ou) || 1;
    hexCache = {nivel, turno: estado.turno, r, lista, ref, membro, bins};
    return hexCache;
  }

  // Hexágono (topo pontudo) que contém o ponto (x, y) do mundo, numa grade de raio r
  function hexDe(x, y, r) {
    const qf = ((Math.sqrt(3) / 3) * x - y / 3) / r, rf = ((2 / 3) * y) / r, sf = -qf - rf;
    let q = Math.round(qf), rr = Math.round(rf);
    const s = Math.round(sf);
    const dq = Math.abs(q - qf), dr = Math.abs(rr - rf), ds = Math.abs(s - sf);
    if (dq > dr && dq > ds) q = -rr - s;
    else if (dr > ds) rr = -q - s;
    return {q, rr, chave: q * 2097152 + rr};
  }

  function caminhoHex(c, x, y, r) {
    for (let k = 0; k < 6; k++) {
      const a = (Math.PI / 3) * k + Math.PI / 6;
      const px = x + r * Math.cos(a), py = y + r * Math.sin(a);
      if (k) c.lineTo(px, py);
      else c.moveTo(px, py);
    }
    c.closePath();
  }

  function desenharHexagonos() {
    const h = hexagonos();
    const {t, W, H, dpr} = estado;
    const c = ctxBase;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    const rTela = h.r * t.k;
    const caminhos = cores.classes.map(() => new Path2D());
    for (const b of h.lista) {
      const x = b.x * t.k + t.x, y = b.y * t.k + t.y;
      if (x < -rTela || x > W + rTela || y < -rTela || y > H + rTela) continue;
      const total = b.pt + b.bo + b.ou;
      const f = Math.max(0.28, Math.min(1, Math.sqrt(total / h.ref)));
      caminhoHex(caminhos[classe((100 * (b.bo - b.pt)) / total)], x, y, rTela * 0.94 * f);
    }
    caminhos.forEach((p, k) => {
      c.fillStyle = cores.classes[k];
      c.fill(p);
    });
  }

  function contornoHex(c, b) {
    const {t} = estado;
    const h = hexCache;
    if (!h) return;
    c.beginPath();
    caminhoHex(c, b.x * t.k + t.x, b.y * t.k + t.y, h.r * t.k * 0.98);
    c.strokeStyle = cores.rotulo;
    c.lineWidth = 1.5;
    c.stroke();
  }

  // Rótulos das cidades, das maiores para as menores: um ponto e o nome à direita, à esquerda, acima ou abaixo,
  // na primeira posição que não cobre outro rótulo
  const larguras = new Map();
  function desenharRotulos(c, zoomRel) {
    const {t, W, H} = estado;
    const minimo = 1.4e6 / Math.pow(zoomRel, 1.55);
    c.font = `600 12px ${cores.fonte}`;
    c.textBaseline = "middle";
    c.lineJoin = "round";
    const postos = [];
    const livre = (b) => postos.every((p) => b[2] < p[0] || b[0] > p[2] || b[3] < p[1] || b[1] > p[3]);
    const candidatos = [];
    for (const r of D.rotulos) {
      if (r.eleitores < minimo || candidatos.length >= 90) break;
      const x = r.x * t.k + t.x, y = r.y * t.k + t.y;
      if (x > -60 && x < W + 60 && y > -20 && y < H + 20) candidatos.push([r, x, y]);
    }
    // Entre as posições livres, a que menos cobre o ponto de cidades que ainda vão receber rótulo
    const cobre = (b, de) => {
      let n = 0;
      for (let k = de; k < candidatos.length; k++) {
        const [, x, y] = candidatos[k];
        if (x > b[0] - 6 && x < b[2] + 6 && y > b[1] - 6 && y < b[3] + 6) n++;
      }
      return n;
    };
    for (let k = 0; k < candidatos.length; k++) {
      const [r, x, y] = candidatos[k];
      let w = larguras.get(r.j);
      if (w == null) larguras.set(r.j, (w = c.measureText(r.nome).width));
      const opcoes = [
        [x + 6, y, "left", [x - 3, y - 8, x + w + 9, y + 8]],
        [x - 6, y, "right", [x - w - 9, y - 8, x + 3, y + 8]],
        [x, y - 12, "center", [x - w / 2 - 2, y - 20, x + w / 2 + 2, y + 3]],
        [x, y + 12, "center", [x - w / 2 - 2, y - 3, x + w / 2 + 2, y + 20]]
      ].filter((o) => livre(o[3]));
      if (!opcoes.length) continue;
      const o = d3.least(opcoes, (o) => cobre(o[3], k + 1));
      postos.push(o[3]);
      c.beginPath();
      c.arc(x, y, 2.6, 0, 2 * Math.PI);
      c.fillStyle = cores.rotulo;
      c.strokeStyle = cores.fundo;
      c.lineWidth = 1.5;
      c.fill();
      c.stroke();
      c.textAlign = o[2];
      c.lineWidth = 3.5;
      c.strokeText(r.nome, o[0], o[1]);
      c.fillText(r.nome, o[0], o[1]);
    }
  }

  // ---- Legenda e informações ------------------------------------------------------------------------

  function atualizarLegenda() {
    if (!D) return;
    const nomes = {...nomesCampos, outros: "Outros candidatos"};
    const cats = estado.turno === 1 ? ["petismo", "bolsonarismo", "outros"] : ["petismo", "bolsonarismo"];
    if (estado.modo === "pontos") {
      const N = geracao?.N;
      legenda.replaceChildren(
        html`<div class="mapa-legenda-itens">${cats.map((c) => html`<span><i style="background:var(--${c})"></i>${nomes[c]}</span>`)}</div>`,
        html`<div class="mapa-escala">${N ? `1 ponto = ${N === 1 ? "1 voto" : `${num(N)} votos`}` : ""}</div>`
      );
    } else {
      legenda.replaceChildren(
        html`<div class="mapa-rampa-titulo">Vantagem na área, em pontos percentuais dos votos válidos</div>`,
        html`<div class="mapa-rampa">${cores.classes.map((cor) => html`<i style="background:${cor}"></i>`)}</div>`,
        html`<div class="mapa-rampa-marcas">${LIMIARES.map((v, k) => html`<span style="left:${(k + 1) * 10}%">${Math.abs(v)}</span>`)}</div>`,
        html`<div class="mapa-rampa-lados"><span>← ${nomesCampos.petismo}</span><span>${nomesCampos.bolsonarismo} →</span></div>`,
        html`<div class="mapa-escala">Tamanho do hexágono: votos válidos da área</div>`
      );
    }
  }

  function carregarNomes() {
    if (!pedidoNomes) {
      pedidoNomes = nomes.json().then((n) => {
        nomesLocais = n;
        if (destaque) mostrarInfo(destaque);
      });
    }
  }

  function linhaCampos(v) {
    const total = v[0] + v[1] + v[2];
    const nomesC = [nomesCampos.petismo, nomesCampos.bolsonarismo, "Outros"];
    const ordem = estado.turno === 1 ? [0, 1, 2] : [0, 1];
    return html`<table>${ordem.map(
      (c) => html`<tr><td><i style="background:var(--${CATEGORIAS[c]})"></i>${nomesC[c]}</td><td>${pct((100 * v[c]) / (total || 1), 1)}</td><td>${num(v[c])}</td></tr>`
    )}</table>`;
  }

  function mostrarInfo(d) {
    destaque = d;
    const V = D.votos[estado.turno];
    if (d.tipo === "local") {
      const i = d.i;
      const m = D.mun[i];
      const v = [V.cat[0][i], V.cat[1][i], V.cat[2][i]];
      const nome = nomesLocais ? nomesLocais[i] || "Local de votação" : "…";
      const p = D.precisao[i];
      info.replaceChildren(
        html`<strong>${nome}</strong>`,
        html`<div class="mapa-info-sub">${D.M.nome[m]} (${D.M.uf[m]}) · ${num(v[0] + v[1] + v[2])} votos válidos</div>`,
        linhaCampos(v),
        ...(PRECISAO[p] ? [html`<div class="mapa-info-nota">${PRECISAO[p]}</div>`] : [])
      );
    } else {
      const b = d.bin;
      const h = hexCache;
      const conta = new Map();
      for (let i = 0; i < D.n; i++) if (h.membro[i] === b.chave) conta.set(D.mun[i], (conta.get(D.mun[i]) ?? 0) + V.total[i]);
      const principais = [...conta].sort((a, c) => c[1] - a[1]).slice(0, 2).map(([m]) => `${D.M.nome[m]} (${D.M.uf[m]})`);
      info.replaceChildren(
        html`<strong>${principais.join(", ")}${conta.size > 2 ? ` e mais ${conta.size - 2}` : ""}</strong>`,
        html`<div class="mapa-info-sub">${num(b.locais)} ${b.locais === 1 ? "local" : "locais"} de votação · ${num(b.pt + b.bo + b.ou)} votos válidos</div>`,
        linhaCampos([b.pt, b.bo, b.ou])
      );
    }
    info.hidden = false;
    posicionarInfo();
    agendar();
  }

  let ultimoPonteiro = [0, 0];
  function posicionarInfo() {
    const [x, y] = ultimoPonteiro;
    const {W, H} = estado;
    const w = info.offsetWidth, h = info.offsetHeight;
    const left = x + 16 + w > W - 8 ? Math.max(8, x - 16 - w) : x + 16;
    const top = Math.min(H - h - 8, Math.max(8, y - h / 2));
    info.style.transform = `translate(${left}px, ${top}px)`;
  }

  function esconderInfo() {
    if (!destaque && info.hidden) return;
    destaque = null;
    info.hidden = true;
    agendar();
  }

  function procurar(px, py, raioPx) {
    const {t} = estado;
    const x = (px - t.x) / t.k, y = (py - t.y) / t.k;
    if (estado.modo === "hex") {
      const h = hexagonos();
      const b = h.bins.get(hexDe(x, y, h.r).chave);
      return b && b.pt + b.bo + b.ou > 0 ? {tipo: "hex", bin: b} : null;
    }
    // o local mais próximo, se o cursor está no disco dele (ou a poucos pixels do centro)
    const i = D.quadtree.find(x, y, Math.max(raioPx / t.k, D.raioMax));
    if (i == null || Math.hypot(D.wx[i] - x, D.wy[i] - y) > Math.max(raioPx / t.k, D.raio[i])) return null;
    const V = D.votos[estado.turno];
    return V.total[i] > 0 ? {tipo: "local", i} : null;
  }

  cTopo.addEventListener("pointermove", (e) => {
    if (!D || e.pointerType !== "mouse" || e.buttons) return;
    ultimoPonteiro = [e.offsetX, e.offsetY];
    const d = procurar(e.offsetX, e.offsetY, 12);
    if (!d) return esconderInfo();
    carregarNomes();
    if (d.tipo === destaque?.tipo && (d.i === destaque.i && d.tipo === "local" || d.bin === destaque.bin)) return posicionarInfo();
    mostrarInfo(d);
  });
  cTopo.addEventListener("pointerleave", (e) => e.pointerType === "mouse" && esconderInfo());
  cTopo.addEventListener("click", (e) => {
    if (!D) return;
    ultimoPonteiro = [e.offsetX, e.offsetY];
    const d = procurar(e.offsetX, e.offsetY, 22);
    if (!d) return esconderInfo();
    carregarNomes();
    mostrarInfo(d);
  });

  // ---- Controles --------------------------------------------------------------------------------------

  for (const b of raiz.querySelectorAll(".mapa-modo button")) {
    b.disabled = b.dataset.modo === "pontos" && !webgl;
    b.addEventListener("click", () => {
      estado.modo = b.dataset.modo;
      for (const o of raiz.querySelectorAll(".mapa-modo button")) o.setAttribute("aria-pressed", String(o === b));
      esconderInfo();
      atualizarLegenda();
      if (estado.modo === "pontos") {
        geracao = null;
        gerarPontos();
      }
      agendar();
    });
  }
  if (!webgl) for (const o of raiz.querySelectorAll(".mapa-modo button")) o.setAttribute("aria-pressed", String(o.dataset.modo === "hex"));

  const sel = d3.select(cTopo);
  raiz.querySelector('[data-acao="mais"]').addEventListener("click", () => sel.transition().duration(300).call(zoom.scaleBy, 2));
  raiz.querySelector('[data-acao="menos"]').addEventListener("click", () => sel.transition().duration(300).call(zoom.scaleBy, 0.5));
  raiz.querySelector('[data-acao="brasil"]').addEventListener("click", () => {
    municipioDestacado = null;
    busca.value = "";
    sel.transition().duration(600).call(zoom.transform, brasilInteiro());
  });
  raiz.querySelector('[data-acao="tela"]').addEventListener("click", () => {
    if (document.fullscreenElement === raiz) document.exitFullscreen();
    else raiz.requestFullscreen?.();
  });
  document.addEventListener("fullscreenchange", () => {
    raiz.classList.toggle("tela-cheia", document.fullscreenElement === raiz);
    requestAnimationFrame(redimensionar);
  });

  busca.addEventListener("change", () => {
    if (!D) return;
    const alvo = busca.value.trim().toLowerCase();
    const j = D.M.codigo.findIndex((_, k) => `${D.M.nome[k]} (${D.M.uf[k]})`.toLowerCase() === alvo);
    if (j < 0) return;
    irPara(j);
  });

  function irPara(j) {
    const g = D.geomPorCodigo.get(D.M.codigo[j]);
    let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity];
    const caminho = new Path2D();
    if (g) {
      for (const poli of poligonosDe(g)) {
        for (const r of poli) {
          anel(D.arcos, r).forEach((q, k) => {
            const p = D.proj(q);
            if (k) caminho.lineTo(p[0], p[1]);
            else caminho.moveTo(p[0], p[1]);
            x0 = Math.min(x0, p[0]);
            y0 = Math.min(y0, p[1]);
            x1 = Math.max(x1, p[0]);
            y1 = Math.max(y1, p[1]);
          });
          caminho.closePath();
        }
      }
      municipioDestacado = caminho;
    } else {
      const p = D.proj([D.M.lon[j] / 1e4, D.M.lat[j] / 1e4]);
      [x0, y0, x1, y1] = [p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2];
      municipioDestacado = null;
    }
    const {W, H} = estado;
    const k = Math.min(estado.k0 * 4000, 0.82 * Math.min(W / (x1 - x0), H / (y1 - y0)));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    sel.transition().duration(900).call(zoom.transform, d3.zoomIdentity.translate(W / 2 - cx * k, H / 2 - cy * k).scale(k));
  }

  // ---- Ciclo de vida --------------------------------------------------------------------------------------

  async function carregar() {
    try {
      const [L, M, T] = await Promise.all([locais.json(), municipios.json(), malha.json()]);
      preparar(L, M, T);
      lerCores();
      estado.pronto = true;
      aviso.remove();
      redimensionar();
      atualizarLegenda();
      gerarPontos();
      agendar();
    } catch (e) {
      console.error(e);
      aviso.textContent = "Não foi possível carregar o mapa.";
    }
  }

  const observador = new IntersectionObserver(
    (entradas) => {
      if (entradas.some((e) => e.isIntersecting)) {
        observador.disconnect();
        carregar();
      }
    },
    {rootMargin: "400px"}
  );
  observador.observe(raiz);
  new ResizeObserver(() => estado.pronto && redimensionar()).observe(raiz);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!D) return;
    lerCores();
    atualizarLegenda();
    agendar();
  });

  raiz.mostrar = (t) => {
    if (t === estado.turno && (D == null || D.turnos.includes(t))) return;
    estado.turno = D && !D.turnos.includes(t) ? D.turnos.at(-1) : t;
    hexCache = null;
    geracao = null;
    esconderInfo();
    if (D) {
      atualizarLegenda();
      gerarPontos();
      agendar();
    }
  };
  return raiz;
}
