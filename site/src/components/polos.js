// Os pontos dos cartões da página inicial: o eleitorado do ano em 200 pontos, cada um 0,5% dos eleitores, somando os
// turnos já apurados. Os dois campos se juntam cada um num polo, vermelho à esquerda e azul à direita; os outros
// candidatos (violeta) vagam entre os dois; brancos, nulos e abstenções (cinza) ficam espalhados em volta de tudo.
//
// Cada ponto tem dois lugares: o polarizado e o de uma mistura, uma elipse com todo mundo junto. Na abertura, eles saem
// da mistura e vão para o lugar polarizado. O cursor (ou o dedo) empurra e gira os pontos por onde passa e manda cada
// ponto que toca para o seu lugar na mistura; enquanto ele está no desenho, eles ficam misturados, e quando sai,
// voltam para o seu lado. É uma física simples (molas, atrito e colisões), um passo a cada 1/60 s. Com "reduzir
// movimento" no sistema, os pontos ficam parados no lugar polarizado. As cores ficam em index.md.
import {svg} from "npm:htl";

const W = 260; // tamanho do desenho, em unidades do viewBox
const H = 104;
const N = 200; // pontos: cada um, 0,5% do eleitorado
const RAIO = 2.5;
const PASSO = 3.5; // distância entre os pontos de um disco: o de n pontos tem raio ≈ PASSO·√n
const OURO = Math.PI * (3 - Math.sqrt(5)); // ângulo de ouro: os pontos do disco em espiral, como num girassol
const GRUPOS = ["petismo", "outros", "bolsonarismo", "nenhum"]; // nenhum: brancos, nulos e abstenções

// Física, por passo de 1/60 s; distâncias em unidades do viewBox
const MOLA = 0.035; // puxão de cada ponto para o seu alvo
const ATRITO = 0.86; // parte da velocidade que sobra a cada passo
const VELOCIDADE = 2.6; // máxima, por passo
const VOLTA = 0.03; // quanto do caminho entre a mistura e o lugar polarizado o alvo de cada ponto anda por passo
const ALCANCE = 34; // raio da perturbação em volta do cursor
const MISTURA = 0.15; // quanto um ponto bem embaixo do cursor vai para a mistura, por passo
const EMPURRAO = 0.4; // para fora do cursor
const GIRO = 0.35; // em volta do cursor, como uma colher mexendo
const ARRASTO = 0.3; // parte do movimento do cursor que os pontos perto dele acompanham
const AGITO = 0.45; // tremor dos pontos perto do cursor
const DISTANCIA = 2 * RAIO + 0.3; // a menor entre dois pontos (colisão)

function girassol(n, cx, cy, {passo = PASSO, achatar = 1} = {}) {
  return Array.from({length: n}, (_, k) => {
    const r = passo * Math.sqrt(k + 0.5);
    return [cx + r * Math.cos(k * OURO) * achatar, cy + (r * Math.sin(k * OURO)) / achatar];
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

// Pontos de cada grupo, somando os turnos (maiores restos)
function contar(turnos) {
  const soma = (k) => turnos.reduce((s, d) => s + d[k], 0);
  const aptos = soma("aptos");
  const partes = [soma("petismo"), soma("outros"), soma("bolsonarismo"), aptos - soma("validos")].map((v) => (N * v) / aptos);
  const n = partes.map(Math.floor);
  const ordem = partes.map((p, i) => [p - n[i], i]).sort((a, b) => b[0] - a[0]);
  const faltam = N - n.reduce((s, v) => s + v, 0);
  for (let k = 0; k < faltam; k++) n[ordem[k][1]]++;
  return Object.fromEntries(GRUPOS.map((g, i) => [g, n[i]]));
}

// Os cinza: espalhados pela elipse do desenho, cada um o mais longe possível dos que já têm lugar (melhor candidato)
function espalhar(n, ocupados, sorteio) {
  const a = W / 2 - RAIO - 3;
  const b = H / 2 - RAIO - 3;
  const lugares = [];
  const todos = [...ocupados];
  for (let i = 0; i < n; i++) {
    let melhor = null;
    let folga = -1;
    for (let k = 0; k < 40; k++) {
      const r = Math.sqrt(sorteio());
      const ang = 2 * Math.PI * sorteio();
      const x = W / 2 + a * r * Math.cos(ang);
      const y = H / 2 + b * r * Math.sin(ang);
      const d = Math.min(...todos.map(([px, py]) => Math.hypot(px - x, py - y)));
      if (d > folga) [melhor, folga] = [[x, y], d];
    }
    lugares.push(melhor);
    todos.push(melhor);
  }
  return lugares;
}

// turnos: o Brasil de cada turno já apurado em data/resultados.json; atraso: quando a separação começa, em segundos.
export function polos(turnos, {semente = 1, atraso = 0} = {}) {
  const sorteio = sorteador(semente);
  const n = contar(turnos);
  const lugares = {
    petismo: girassol(n.petismo, W / 4, H / 2),
    outros: girassol(n.outros, W / 2, H / 2),
    bolsonarismo: girassol(n.bolsonarismo, (3 * W) / 4, H / 2)
  };
  lugares.nenhum = espalhar(n.nenhum, [...lugares.petismo, ...lugares.outros, ...lugares.bolsonarismo], sorteio);
  const mistura = girassol(N, W / 2, H / 2, {passo: 4.6, achatar: 1.35});
  for (let i = mistura.length - 1; i > 0; i--) {
    const j = Math.floor(sorteio() * (i + 1));
    [mistura[i], mistura[j]] = [mistura[j], mistura[i]];
  }
  // o vão entre os dois discos, onde os outros candidatos vagam
  const borda = (g) => PASSO * Math.sqrt(n[g]) + RAIO;
  const vao = Math.max(4, Math.min(W / 2 - W / 4 - borda("petismo"), W / 4 - borda("bolsonarismo")) - RAIO);
  let k = 0;
  const pontos = GRUPOS.flatMap((g) =>
    lugares[g].map(([x, y]) => {
      const [x0, y0] = mistura[k++];
      // m: quanto o alvo do ponto está na mistura (1) ou no seu lado (0); solta: quando ele começa a voltar
      const p = {i: k, grupo: g, casa: [x, y], mistura: [x0, y0], m: 1, x: x0, y: y0, vx: 0, vy: 0,
        rigidez: 0.7 + 0.6 * sorteio(), solta: atraso + 0.2 + 0.7 * sorteio()};
      if (g === "outros") {
        // vai e volta no vão, em ritmos diferentes
        p.vaga = {ax: Math.max(2, (vao - Math.abs(x - W / 2)) * (0.6 + 0.4 * sorteio())), ay: 2 + 5 * sorteio(),
          wx: (2 * Math.PI) / (3.5 + 3 * sorteio()), wy: (2 * Math.PI) / (2.5 + 2 * sorteio()), fx: 6.3 * sorteio(), fy: 6.3 * sorteio()};
      }
      return p;
    })
  );
  const circulos = pontos.map((p) => svg`<circle class=${p.grupo} r=${RAIO} cx=${p.x.toFixed(2)} cy=${p.y.toFixed(2)}></circle>`);
  const desenho = svg`<svg class="polos" viewBox="0 0 ${W} ${H}" aria-hidden="true">${circulos}</svg>`;
  animar(desenho, pontos, circulos);
  return desenho;
}

function animar(desenho, pontos, circulos) {
  const parado = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (parado) {
    pontos.forEach((p, i) => desenhar(circulos[i], p, ...p.casa));
    return;
  }
  const cursor = {dentro: false, x: 0, y: 0, vx: 0, vy: 0, t: 0};
  // colisões numa grade de células do tamanho da distância mínima: cada ponto só olha as 9 células em volta
  const colunas = Math.ceil(W / DISTANCIA);
  const linhas = Math.ceil(H / DISTANCIA);
  const grade = Array.from({length: colunas * linhas}, () => []);
  const coluna = (x) => Math.min(colunas - 1, Math.max(0, Math.floor(x / DISTANCIA)));
  const linha = (y) => Math.min(linhas - 1, Math.max(0, Math.floor(y / DISTANCIA)));
  let t = 0; // segundos de simulação, contados a partir da primeira vez que o desenho aparece na tela
  let pedido = null;
  let anterior = null;
  let sobra = 0;
  let visivel = false;
  let montado = false;
  let repouso = false; // sem cursor e com todos já do seu lado: só os violeta andam (e os cinza em que esbarram)
  let quadros = 0;

  function passo() {
    t += 1 / 60;
    repouso = !cursor.dentro;
    for (const p of pontos) {
      if (p.m > 0) repouso = false;
      // parado no seu lugar: nada a fazer (os violeta nunca param)
      p.quieto = !cursor.dentro && p.m === 0 && !p.vaga && Math.abs(p.vx) + Math.abs(p.vy) < 0.002 &&
        Math.abs(p.x - p.casa[0]) + Math.abs(p.y - p.casa[1]) < 0.02;
      if (p.quieto) continue;
      let ax = 0;
      let ay = 0;
      if (cursor.dentro) {
        const dx = p.x - cursor.x;
        const dy = p.y - cursor.y;
        const d = Math.hypot(dx, dy) || 1e-6;
        if (d < ALCANCE) {
          const f = 1 - d / ALCANCE;
          p.m = Math.min(1, p.m + MISTURA * f);
          p.mexido = true;
          ax += ((dx * EMPURRAO * f - dy * GIRO) * f) / d + cursor.vx * ARRASTO * f + (Math.random() - 0.5) * AGITO * f;
          ay += ((dy * EMPURRAO * f + dx * GIRO) * f) / d + cursor.vy * ARRASTO * f + (Math.random() - 0.5) * AGITO * f;
        }
      }
      // volta para o seu lado: na abertura e quando o cursor sai; com ele no desenho, só quem ele não tocou
      if (t >= p.solta && !(cursor.dentro && p.mexido)) p.m = Math.max(0, p.m - VOLTA * p.rigidez);
      let [cx, cy] = p.casa;
      if (p.vaga) {
        cx += p.vaga.ax * Math.sin(t * p.vaga.wx + p.vaga.fx);
        cy += p.vaga.ay * Math.sin(t * p.vaga.wy + p.vaga.fy);
      }
      // o alvo anda em linha reta entre o lugar polarizado e o da mistura
      cx += (p.mistura[0] - cx) * p.m;
      cy += (p.mistura[1] - cy) * p.m;
      ax += MOLA * p.rigidez * (cx - p.x);
      ay += MOLA * p.rigidez * (cy - p.y);
      p.vx = (p.vx + ax) * ATRITO;
      p.vy = (p.vy + ay) * ATRITO;
      const v = Math.hypot(p.vx, p.vy);
      if (v > VELOCIDADE) {
        p.vx *= VELOCIDADE / v;
        p.vy *= VELOCIDADE / v;
      }
      p.x += p.vx;
      p.y += p.vy;
    }
    // colisões: dois pontos colados se afastam, cada um metade. Só a partir dos que se mexem: dois parados no seu
    // lugar nunca estão colados
    for (const p of pontos) {
      p.celula = coluna(p.x) + linha(p.y) * colunas;
      grade[p.celula].push(p);
    }
    for (const a of pontos) {
      if (a.quieto) continue;
      const gx = coluna(a.x);
      const gy = linha(a.y);
      for (let y = Math.max(0, gy - 1); y <= Math.min(linhas - 1, gy + 1); y++) {
        for (let x = Math.max(0, gx - 1); x <= Math.min(colunas - 1, gx + 1); x++) {
          for (const b of grade[x + y * colunas]) {
            if (b === a || (!b.quieto && b.i < a.i)) continue; // cada par uma vez só
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const d = Math.hypot(dx, dy);
            if (d >= DISTANCIA) continue;
            const s = d > 1e-6 ? (0.5 * (DISTANCIA - d)) / d : 0;
            a.x -= dx * s;
            a.y -= dy * s;
            b.x += dx * s;
            b.y += dy * s;
          }
        }
      }
    }
    for (const p of pontos) grade[p.celula].length = 0;
    for (const p of pontos) {
      if (p.x < RAIO || p.x > W - RAIO) [p.x, p.vx] = [Math.min(W - RAIO, Math.max(RAIO, p.x)), -0.3 * p.vx];
      if (p.y < RAIO || p.y > H - RAIO) [p.y, p.vy] = [Math.min(H - RAIO, Math.max(RAIO, p.y)), -0.3 * p.vy];
    }
    cursor.vx *= 0.8;
    cursor.vy *= 0.8;
  }

  function quadro(agora) {
    pedido = null;
    if (!desenho.isConnected) {
      if (montado) observador.disconnect();
      else pedido = requestAnimationFrame(quadro); // ainda não entrou na página
      return;
    }
    montado = true;
    if (!visivel) return;
    sobra += anterior == null ? 1 / 60 : Math.min(0.1, (agora - anterior) / 1000);
    anterior = agora;
    for (; sobra >= 1 / 60; sobra -= 1 / 60) passo();
    // em repouso, só os violeta andam, e devagar: basta desenhar a metade dos quadros
    if (!repouso || quadros++ % 2 === 0) pontos.forEach((p, i) => desenhar(circulos[i], p, p.x, p.y));
    pedido = requestAnimationFrame(quadro);
  }

  function continuar() {
    if (pedido == null && visivel) {
      anterior = null;
      pedido = requestAnimationFrame(quadro);
    }
  }

  // Só anima com o desenho na tela
  const observador = new IntersectionObserver((entradas) => {
    visivel = entradas.at(-1).isIntersecting;
    if (visivel) continuar();
  });
  observador.observe(desenho);
  pedido = requestAnimationFrame(quadro);

  // Cursor e dedo. No celular, arrastar o dedo para os lados mexe nos pontos; para cima e para baixo, rola a página.
  const onde = (e) => {
    const r = desenho.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H];
  };
  const entrar = (e) => {
    [cursor.x, cursor.y] = onde(e);
    [cursor.vx, cursor.vy, cursor.t] = [0, 0, e.timeStamp];
    cursor.dentro = true;
    continuar();
  };
  const mover = (e) => {
    if (!cursor.dentro) return entrar(e);
    const [x, y] = onde(e);
    const passos = Math.max(0.5, (e.timeStamp - cursor.t) / (1000 / 60));
    cursor.vx = 0.5 * cursor.vx + (0.5 * (x - cursor.x)) / passos;
    cursor.vy = 0.5 * cursor.vy + (0.5 * (y - cursor.y)) / passos;
    [cursor.x, cursor.y, cursor.t] = [x, y, e.timeStamp];
  };
  const sair = () => {
    if (!cursor.dentro) return;
    cursor.dentro = false;
    // cada ponto volta num instante um pouco diferente, como na abertura
    for (const p of pontos) [p.mexido, p.solta] = [false, t + 0.35 * Math.random()];
  };
  desenho.addEventListener("pointerenter", entrar);
  desenho.addEventListener("pointerdown", entrar);
  desenho.addEventListener("pointermove", mover);
  desenho.addEventListener("pointerleave", sair);
  desenho.addEventListener("pointercancel", sair);
  desenho.addEventListener("pointerup", (e) => e.pointerType !== "mouse" && sair());
}

// Só mexe no SVG quando o ponto andou
function desenhar(circulo, p, x, y) {
  if (p.desenho && Math.abs(x - p.desenho[0]) < 0.01 && Math.abs(y - p.desenho[1]) < 0.01) return;
  p.desenho = [x, y];
  circulo.setAttribute("cx", x.toFixed(2));
  circulo.setAttribute("cy", y.toFixed(2));
}
