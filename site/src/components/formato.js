// Números e horas no padrão brasileiro.

const formatos = new Map();
function nf(casas) {
  if (!formatos.has(casas)) {
    formatos.set(casas, new Intl.NumberFormat("pt-BR", {minimumFractionDigits: casas, maximumFractionDigits: casas}));
  }
  return formatos.get(casas);
}

export const pct = (v, casas = 2) => (v == null || Number.isNaN(v) ? "–" : nf(casas).format(v) + "%");
export const num = (v) => nf(0).format(Math.round(v));
export const decimal = (v, casas = 1) => nf(casas).format(v);

// 12,3 mi · 845 mil · 912
export function mi(v) {
  const a = Math.abs(v);
  if (a >= 1e6) return nf(a >= 1e7 ? 1 : 2).format(v / 1e6) + " mi";
  if (a >= 1e3) return nf(0).format(v / 1e3) + " mil";
  return nf(0).format(v);
}

// Para eixos: sem casas decimais quando o valor é redondo (6 mi, 2,5 mi, 800 mil)
export function miEixo(v) {
  const a = Math.abs(v);
  if (a >= 1e6) return nf(Number.isInteger(v / 1e6) ? 0 : 1).format(v / 1e6) + " mi";
  if (a >= 1e3) return nf(0).format(v / 1e3) + " mil";
  return nf(0).format(v);
}

// Pontos percentuais com sinal: +1,8 p.p.
export const pp = (v, casas = 1) => (v > 0 ? "+" : v < 0 ? "−" : "") + nf(casas).format(Math.abs(v)) + " p.p.";
export const comSinal = (v, f = num) => (v > 0 ? "+" : v < 0 ? "−" : "") + f(Math.abs(v));

// As horas são guardadas como datas UTC com o relógio de Brasília; por isso tudo é lido em UTC.
export const relogio = (inicio, minutos) => new Date(Date.parse(inicio + ":00Z") + minutos * 60000);
export const hora = (d) => `${d.getUTCHours()}h${String(d.getUTCMinutes()).padStart(2, "0")}`;
export const horaEixo = (d) => `${d.getUTCHours()}h` + (d.getUTCMinutes() ? String(d.getUTCMinutes()).padStart(2, "0") : "");
export const data = (iso) => new Date(iso + "T12:00:00Z").toLocaleDateString("pt-BR", {day: "numeric", month: "long", year: "numeric", timeZone: "UTC"});

// Datas (YYYY-MM-DD) como meio-dia UTC, para não mudarem de dia com o fuso de quem vê
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
export const dia = (iso) => new Date(iso + "T12:00:00Z");
export const diaCurto = (d) => `${d.getUTCDate()} ${MESES[d.getUTCMonth()]}`;
export const mesEixo = (d) => (d.getUTCDate() <= 1 ? MESES[d.getUTCMonth()] : `${d.getUTCDate()}/${d.getUTCMonth() + 1}`);
export const periodoCampo = (inicio, fim) => (inicio === fim ? diaCurto(dia(fim)) : `${diaCurto(dia(inicio))}–${diaCurto(dia(fim))}`);
