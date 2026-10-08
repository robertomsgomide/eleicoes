// Site do estudo (Observable Framework). Dados gerados por `uv run eleicoes site` em src/data.
export default {
  title: "Lulismo × Bolsonarismo",
  root: "src",
  pages: [
    {name: "2018 · Bolsonaro × Haddad", path: "/2018"},
    {name: "2022 · Lula × Bolsonaro", path: "/2022"},
    {name: "2026 · Lula × Flávio Bolsonaro", path: "/2026"},
    {name: "Comparações", path: "/comparacoes"},
    {name: "Metodologia", path: "/metodologia"}
  ],
  style: "style.css",
  // Sem folhas de estilo externas: o padrão do Framework carrega uma fonte do Google Fonts.
  globalStylesheets: [],
  head: `<script>document.documentElement.lang = "pt-BR";</script>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M8 1a7 7 0 0 0 0 14z' fill='%23d0343f'/%3E%3Cpath d='M8 1a7 7 0 0 1 0 14z' fill='%232b67b8'/%3E%3C/svg%3E">`,
  footer: `Estudo independente, com dados públicos do TSE e do IBGE e pesquisas compiladas da Wikipedia
    (<a href="https://creativecommons.org/licenses/by-sa/4.0/deed.pt-br">CC BY-SA 4.0</a>).
    Sem vínculo com partidos, candidatos, institutos de pesquisa ou com o TSE.`,
  toc: {label: "Nesta página"},
  pager: true,
  search: false,
  cleanUrls: true
};
