// A noite do 2º turno de 2026 ao vivo. Duas fontes, lidas a cada minuto:
//  - o TSE, direto (resultados.tse.jus.br deixa o navegador ler): o arquivo do país e o de cada UF, o mais novo que há;
//  - os três coletores na nuvem (ramos ao-vivo-a, -b e -c; src/eleicoes/ao_vivo/painel.py): a apuração minuto a minuto
//    desde as 17h, o forecast do resultado final e o histórico dele, e os dados do mapa. Vale o coletor mais recente;
//    o cache do GitHub atrasa esses arquivos em até 5 min, e o TSE completa o que falta da apuração.
// Se uma das fontes falhar, a outra segura a página. Em localhost, ?ao-vivo=<base>&tse=<base> troca as fontes (o
// simulador da noite: uv run eleicoes simular); no site publicado, as fontes são fixas.

const RAMOS = "https://raw.githubusercontent.com/robertomsgomide/eleicoes/ao-vivo-{c}/";
const TSE = "https://resultados.tse.jus.br/oficial/ele2026/6258/";
const COLETORES = ["a", "b", "c"];
export const UFS = ["ac", "am", "ap", "pa", "ro", "rr", "to", "al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se",
  "df", "go", "ms", "mt", "es", "mg", "rj", "sp", "pr", "rs", "sc", "zz"];
export const REGIAO_DA_UF = Object.fromEntries([
  ...["ac", "am", "ap", "pa", "ro", "rr", "to"].map((u) => [u, "Norte"]),
  ...["al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se"].map((u) => [u, "Nordeste"]),
  ...["df", "go", "ms", "mt"].map((u) => [u, "Centro-Oeste"]),
  ...["es", "mg", "rj", "sp"].map((u) => [u, "Sudeste"]),
  ...["pr", "rs", "sc"].map((u) => [u, "Sul"]),
  ["zz", "Exterior"]
]);
const REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Exterior"];
const INTERVALO = 60e3;
const MAPA_A_CADA = 3; // o mapa.json muda a cada envio dos coletores (3 min)

// Quando a página começa a ler: 30 min antes das 17h de 25/10 (horário de Brasília). Até lá, nada é pedido.
const JANELA = Date.UTC(2026, 9, 25, 19, 30);

export function fontes(loc = typeof location === "undefined" ? null : location) {
  const local = loc && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(loc.hostname);
  const q = local ? new URLSearchParams(loc.search) : new URLSearchParams();
  return {
    ramos: COLETORES.map((c) => (q.get("ao-vivo") ?? RAMOS).replace("{c}", c)),
    tse: q.get("tse") ?? TSE,
    ensaio: q.has("ao-vivo") || q.has("tse")
  };
}

// ---- Leitura do formato do TSE (como src/eleicoes/formato_tse.py e coletor.leitura) ----------------------------------

const num = (x) => {
  if (x == null || x === "") return 0;
  const s = String(x);
  return Number(s.includes(",") ? s.replaceAll(".", "").replace(",", ".") : s);
};

function candidatos(d) {
  const out = {};
  const andar = (o) => {
    if (Array.isArray(o)) return o.forEach(andar);
    if (o && typeof o === "object") {
      if ("vap" in o && "n" in o && ("nmu" in o || "nm" in o)) out[String(o.n)] = num(o.vap);
      for (const [k, v] of Object.entries(o)) if (k !== "vs" && k !== "subs" && v && typeof v === "object") andar(v);
    }
  };
  andar(d.carg ?? []);
  return out;
}

// Um arquivo de resultado do TSE (país ou UF) no formato das leituras dos coletores; null antes de haver votos.
export function leituraTSE(d, numeros) {
  const v = d.v ?? {}, s = d.s ?? {}, e = d.e ?? {};
  if (!(d.dt && d.ht) || !num(v.vv) || d.dv === "n") return null;
  const [dia, mes, ano] = d.dt.split("/");
  const c = candidatos(d);
  return {
    h: `${ano}-${mes}-${dia}T${d.ht}`,
    pst: num(s.pstn ?? s.pst),
    st: num(s.st),
    ts: num(s.ts),
    vv: num(v.vv),
    c: num(e.c),
    a: num(e.a),
    and: d.and ?? "",
    tf: d.tf ?? "",
    petismo: c[numeros.petismo] ?? 0,
    bolsonarismo: c[numeros.bolsonarismo] ?? 0
  };
}

// ---- Rede -----------------------------------------------------------------------------------------------------------

async function pegar(url, {cache = "no-cache", segundos = 20} = {}) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), segundos * 1000);
  try {
    const r = await fetch(url, {cache, signal: ctl.signal});
    if (!r.ok) throw new Error(`${r.status} em ${url}`);
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

// o cache do GitHub guarda cada endereço por até 5 min: um parâmetro que muda a cada minuto pede o arquivo novo
const comMinuto = (url) => `${url}${url.includes("?") ? "&" : "?"}m=${Math.floor(Date.now() / 60e3)}`;

async function lerTSE(base, numeros) {
  const arq = (abr) => `${base}dados/${abr}/${abr}-c0001-e006258-u.json`;
  const [br, ...ufs] = await Promise.allSettled([arq("br"), ...UFS.map(arq)].map((u) => pegar(u)));
  const l = (r) => (r.status === "fulfilled" ? leituraTSE(r.value, numeros) : null);
  return {br: l(br), ufs: Object.fromEntries(UFS.map((u, i) => [u, l(ufs[i])]).filter(([, x]) => x))};
}

async function lerRamos(ramos) {
  const lidos = await Promise.allSettled(ramos.map((r) => pegar(comMinuto(`${r}dados.json`))));
  const bons = lidos.map((r, i) => (r.status === "fulfilled" ? {...r.value, _ramo: ramos[i]} : null)).filter((d) => d?.versao >= 2);
  // o mais recente: a última leitura do TSE e, de duas iguais, o envio mais novo
  bons.sort((x, y) => (y.tse?.h ?? "").localeCompare(x.tse?.h ?? "") || (y.atualizado ?? "").localeCompare(x.atualizado ?? ""));
  return bons[0] ?? null;
}

// ---- Juntar as fontes -------------------------------------------------------------------------------------------------

const minuto = (h, inicio) => Math.floor((Date.parse(h + "Z") - Date.parse(inicio + ":00Z")) / 60e3);

// Os últimos totais de cada UF e do país: os do coletor, trocados pelos do TSE quando estes são mais novos.
function juntarUltimos(ramo, direto) {
  const ufs = {};
  for (const [u, x] of Object.entries(ramo?.ufs ?? {})) ufs[u.toLowerCase()] = x;
  for (const [u, x] of Object.entries(direto?.ufs ?? {})) if (!ufs[u] || x.h > ufs[u].h) ufs[u] = x;
  let br = ramo?.tse ?? null;
  if (direto?.br && (!br || direto.br.h > br.h)) br = direto.br;
  return {br, ufs};
}

// O resultado no formato de data/resultados.json (Brasil, regiões, UFs), com o que já foi apurado.
function resultadoAoVivo({br, ufs}) {
  const vazio = () => ({petismo: 0, bolsonarismo: 0, outros: 0, validos: 0, comparecimento: 0, aptos: 0, secoes: 0, total: 0});
  const soma = (a, x) => {
    a.petismo += x.petismo;
    a.bolsonarismo += x.bolsonarismo;
    a.validos += x.vv;
    a.outros += Math.max(0, x.vv - x.petismo - x.bolsonarismo);
    a.comparecimento += x.c;
    a.aptos += x.c + x.a;
    a.secoes += x.st;
    a.total += x.ts;
    return a;
  };
  const regioes = Object.fromEntries(REGIOES.map((r) => [r, vazio()]));
  const porUf = {};
  for (const [u, x] of Object.entries(ufs)) {
    soma(regioes[REGIAO_DA_UF[u]], x);
    porUf[u.toUpperCase()] = soma(vazio(), x);
  }
  return {fonte: "TSE, ao vivo", Brasil: br ? soma(vazio(), br) : null, regioes, ufs: porUf, candidatos: [13, 22]};
}

// A apuração do coletor (formato de data/apuracao_*.json) com os totais mais novos do TSE no fim.
function apuracaoAoVivo(ramo, ultimos, inicio) {
  const base = ramo?.apuracao;
  const ap = base
    ? structuredClone(base)
    : {tipo: "ao vivo", inicio, t: [], viradas: [], t999: 0, regioes: Object.fromEntries(["Brasil", ...REGIOES].map((r) => [r, {secoes: [], validos: [], petismo: [], bolsonarismo: []}])), totais: {}};
  const {br, ufs} = ultimos;
  if (br) {
    const m = Math.max(0, minuto(br.h, inicio));
    const ultimo = ap.t.at(-1);
    if (ultimo == null || m >= ultimo) {
      const regs = resultadoAoVivo(ultimos).regioes;
      const valores = {Brasil: [br.st, br.vv, br.petismo, br.bolsonarismo]};
      for (const r of REGIOES) valores[r] = [regs[r].secoes, regs[r].validos, regs[r].petismo, regs[r].bolsonarismo];
      const novo = m !== ultimo;
      if (novo) ap.t.push(m);
      for (const [r, v] of Object.entries(valores)) {
        ["secoes", "validos", "petismo", "bolsonarismo"].forEach((k, j) => {
          const s = ap.regioes[r][k];
          if (novo) s.push(v[j]);
          else s[s.length - 1] = v[j];
        });
      }
      const totalUf = (r) => Object.entries(ufs).filter(([u]) => REGIAO_DA_UF[u] === r).reduce((a, [, x]) => a + x.ts, 0);
      ap.totais = Object.fromEntries(["Brasil", ...REGIOES].map((r) => [r, {secoes: r === "Brasil" ? br.ts : totalUf(r) || ap.totais?.[r]?.secoes || 0}]));
    }
  }
  // viradas e o minuto de 99,9% com a série completa (como src/eleicoes/analises/apuracao.py)
  const b = ap.regioes.Brasil, total = ap.totais.Brasil?.secoes || 0;
  ap.viradas = [];
  let lider = null;
  ap.t.forEach((t, i) => {
    if (!total || b.secoes[i] < 0.01 * total) return;
    const atual = b.petismo[i] > b.bolsonarismo[i] ? "petismo" : b.petismo[i] < b.bolsonarismo[i] ? "bolsonarismo" : lider;
    if (lider != null && atual !== lider) ap.viradas.push({t, pct_secoes: (100 * b.secoes[i]) / total, lider: atual});
    lider = atual;
  });
  const i999 = b.secoes.findIndex((n) => total && n >= 0.999 * total);
  ap.t999 = i999 >= 0 ? ap.t[i999] : ap.t.at(-1) ?? 0;
  return ap;
}

// O histórico do forecast, no formato que graficoCampos usa (minuto desde o início e % apurado)
function serieForecast(ramo, inicio) {
  return (ramo?.previsoes ?? []).map((p) => ({...p, minuto: minuto(p.h, inicio), apurado: p.pst ?? p.apurado}));
}

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * O estado da noite, de minuto em minuto (gerador assíncrono para o Observable Framework).
 * {modo: "antes" | "ao vivo" | "encerrada" | "sem dados", res, ap, previsao, serie, mapa, tse, coletor, atualizado}
 */
export async function* acompanhar({numeros = {petismo: "13", bolsonarismo: "22"}, inicio = "2026-10-25T17:00"} = {}) {
  const f = fontes();
  if (!f.ensaio && Date.now() < JANELA) {
    yield {modo: "antes"};
    while (Date.now() < JANELA) await dormir(Math.min(JANELA - Date.now(), 10 * 60e3));
  }
  // um primeiro valor na hora: o resto da página não espera a rede
  yield {modo: "carregando"};
  let ciclo = 0, mapa = null, ultimoRamo = null;
  while (true) {
    const [direto, ramo] = await Promise.all([lerTSE(f.tse, numeros).catch(() => null), lerRamos(f.ramos).catch(() => null)]);
    if (ramo) ultimoRamo = ramo;
    const fonte = ramo ?? ultimoRamo;
    if (fonte && (ciclo % MAPA_A_CADA === 0 || !mapa)) {
      try {
        mapa = await pegar(comMinuto(`${fonte._ramo}mapa.json`));
      } catch {
        // fica o anterior
      }
    }
    const ultimos = juntarUltimos(fonte, direto);
    const encerrada = ultimos.br && (ultimos.br.and === "f" || ultimos.br.tf === "s");
    yield {
      modo: !ultimos.br ? "sem dados" : encerrada ? "encerrada" : "ao vivo",
      tse: ultimos.br,
      res: resultadoAoVivo(ultimos),
      ap: apuracaoAoVivo(fonte, ultimos, inicio),
      previsao: fonte?.previsao ?? null,
      serie: serieForecast(fonte, inicio),
      mapa,
      coletor: fonte ? {nome: fonte.coletor, atualizado: fonte.atualizado} : null,
      atualizado: new Date()
    };
    if (encerrada && ciclo > 0 && (fonte?.previsao?.apurado ?? 0) >= 99.9) return; // nada mais vai mudar
    ciclo++;
    await dormir(INTERVALO);
  }
}
