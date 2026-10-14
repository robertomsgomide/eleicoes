---
title: Metodologia
toc: true
---

```js
import {COR, graficoCampos, graficoLugares, graficoProjecao, legenda, serieDaNoite} from "./components/graficos.js";
import {decimal, hora, num, pct, pp} from "./components/formato.js";
const validacao = FileAttachment("data/validacao_estimativa.json").json();
const eleicoes = FileAttachment("data/eleicoes.json").json();
const resumoMapa = FileAttachment("data/mapa/resumo.json").json();
const projecao = FileAttachment("data/projecao.json").json();
```

# Metodologia

<p class="lead">De onde vêm os números, como foram conferidos e o que é exato ou estimado. Todo o processamento é feito por código aberto, a partir dos arquivos públicos do TSE e do IBGE.</p>

## Os dois campos

Em cada eleição, o **petismo** é o candidato do PT e o **bolsonarismo**, o candidato da família Bolsonaro:

```js
const linhas = Object.entries(eleicoes.eleicoes).map(([ano, e]) => html`<tr><td>${ano}</td><td>${e.petismo.nome} (${e.petismo.partido}, ${e.petismo.numero})</td><td>${e.bolsonarismo.nome} (${e.bolsonarismo.partido}, ${e.bolsonarismo.numero})</td></tr>`);
display(html`<div class="tabela"><table><thead><tr><th>Ano</th><th>Petismo</th><th>Bolsonarismo</th></tr></thead><tbody>${linhas}</tbody></table></div>`);
```

Os demais candidatos aparecem como "outros". Como nos resultados do TSE, os percentuais são calculados sobre os **votos válidos**, sem brancos e nulos.

## Fontes

- **Boletins de urna** (TSE, dados abertos): os votos de cada uma das cerca de 450 a 500 mil seções, com a abertura e o encerramento da urna e, a partir de 2022, a hora em que o boletim chegou ao TSE. Cada arquivo é conferido pelo código SHA-512 que o TSE publica junto.
- **Totais oficiais por município e zona** (TSE): o resultado oficial, usado como gabarito.
- **Votação por seção** (TSE): os mesmos votos de cada seção, sem os horários. Sai um dia depois da eleição, dias antes dos boletins de urna: é a fonte dos votos por seção enquanto os boletins não saem e, depois, mais uma conferência deles.
- **Locais de votação** (TSE): endereço e coordenadas de cada seção, de 2016 a 2026 (as eleições municipais entram só para completar coordenadas; veja [Mapa](#mapa)).
- **Site de resultados do TSE**: as leituras do total oficial gravadas por este projeto durante a noite da apuração e o resultado final de cada turno, usado na conferência enquanto o total oficial por município e zona não sai.
- **IBGE**: códigos e fronteiras de municípios, estados e regiões.

## Conferência com o resultado oficial

A soma dos votos de todos os boletins de urna é comparada, candidato a candidato, com o total oficial do TSE no Brasil, em cada estado e em cada zona eleitoral, nos dois turnos de 2018 e de 2022 e no 1º turno de 2026. Tudo bate exatamente, com uma única exceção: no 1º turno de 2018, em Pastos Bons (MA), zona 17, o total oficial tem 76 votos a mais do que os boletins publicados (Haddad +46, Bolsonaro +20, outros +10). Os boletins dessa zona estão completos e consistentes, e os arquivos públicos não mostram de onde vêm esses votos. A diferença fica registrada no código, e qualquer outra divergência interrompe o processamento.

Em 2026, o total oficial por município e zona saiu primeiro sem os votos de Presidente e foi republicado com eles em 7 de outubro; até lá, a conferência foi com o resultado final da totalização em cada estado. Os boletins do 1º turno, publicados em 6 de outubro, batem com o total oficial em todas as zonas e, seção por seção, com a votação por seção, em todas as 499.206 seções. Os 5.246 votos de Leonardo Alves de Araújo (28), cuja candidatura foi indeferida, contam como nulos, como no resultado oficial, que não os traz.

## Apuração no tempo

**Exata (2022 em diante).** Cada seção entra na curva no minuto em que o boletim dela chegou ao TSE, com os votos que tinha. Boletins que chegaram antes do início da divulgação (do exterior, sobretudo) entram no primeiro minuto. Nas medidas em %, o primeiro 1% das seções fica de fora, por ser muito ruidoso. A chegada do boletim antecede em alguns minutos a publicação oficial, que o TSE faz em lotes.

**Estimada (2018).** O TSE não publicou a hora de chegada dos boletins de 2018. Cada seção entra então na hora estimada: o encerramento da urna (que o TSE publica) mais o atraso típico (mediana) entre encerramento e chegada na mesma zona eleitoral, no mesmo turno de 2022. Sem a zona, usa-se o município; sem ele, a UF. Como nas duas eleições o encerramento está no horário local, a diferença de fuso já vem embutida no atraso.

Para saber quanto o método erra, ele foi aplicado onde a chegada real é conhecida: a cada turno de 2022, com os atrasos do **outro** turno, e ao 1º turno de 2026, com os atrasos do 1º turno de 2022 (o mesmo turno, em outra eleição, como no caso de 2018):

```js
const teste26 = validacao.find((v) => v.alvo.startsWith("2026"));
const erroCampo = (v, k) => Math.max(v.erro_pct_validos.petismo[k], v.erro_pct_validos.bolsonarismo[k]);
```

```js
display(html`<div class="tabela"><table>
  <thead><tr><th>Curva estimada</th><th>Atrasos usados</th><th style="text-align:right">Participação de cada candidato: erro médio · máximo</th><th style="text-align:right">% apurado em cada horário: erro médio · máximo</th></tr></thead>
  <tbody>${validacao.map((v) => {
    const media = Math.max(v.erro_pct_validos.petismo.media, v.erro_pct_validos.bolsonarismo.media);
    const max = Math.max(v.erro_pct_validos.petismo.max, v.erro_pct_validos.bolsonarismo.max);
    return html`<tr><td>${v.alvo}</td><td>${v.referencia}</td>
      <td style="text-align:right;white-space:nowrap">${decimal(media, 2)} · ${decimal(max, 2)} p.p.</td>
      <td style="text-align:right;white-space:nowrap">${decimal(v.erro_pct_apurado.media, 1)} · ${decimal(v.erro_pct_apurado.max, 1)} pontos</td></tr>`;
  })}</tbody>
</table></div>`);
```

A participação de cada candidato ao longo do % apurado é bem reproduzida: a **ordem** em que as seções chegam se repete de uma eleição para outra. O **relógio** não: o 2º turno transmite os boletins muito mais rápido que o 1º, então o % apurado em cada horário erra bastante entre turnos. ${teste26 ? `De uma eleição para a outra, no mesmo turno, o quadro se repete: no 1º turno de 2026, a participação de cada candidato erra em média ${decimal(erroCampo(teste26, "media"), 1)} ponto (no máximo ${decimal(erroCampo(teste26, "max"), 1)}), e o % apurado em cada horário, ${decimal(teste26.erro_pct_apurado.media, 0)} pontos em média (no máximo ${decimal(teste26.erro_pct_apurado.max, 0)}). Por isso, em 2018, o eixo padrão é o % apurado.` : ""}

**Antes dos boletins.** Nos dias entre a eleição e a publicação dos boletins de urna, a noite de um turno aparece como este projeto a gravou ao vivo (as leituras do total oficial do TSE), rotulada como provisória. A curva exata a substitui quando os boletins saem.

## Mapa

**Cada ponto.** Os votos de cada local de votação (em geral, uma escola) viram pontos na cor de cada campo. Cada ponto vale um número fixo de votos, que diminui quando o mapa é aproximado: de 500 votos por ponto no país inteiro até 1 voto por ponto numa rua, para que nunca haja mais de 320 mil pontos na tela. A fração de ponto de cada local é resolvida por um número sorteado, fixo para aquele local e campo. Assim, na média, os pontos correspondem exatamente aos votos, e os pontos de uma escala continuam na seguinte: aproximar só acrescenta pontos. Os pontos se espalham num círculo em volta do local, com área proporcional aos votos (30 m² por voto, de 35 a 300 metros de raio). O círculo é uma convenção para mostrar quantos votos há ali; ele não indica onde os eleitores moram. A ordem em que os pontos são desenhados também é sorteada, para nenhum campo ficar sempre por cima.

**Hexágonos.** O país é dividido numa grade de hexágonos presa ao mapa, que fica mais fina a cada aproximação. A cor mostra a vantagem de um campo sobre o outro nos votos válidos da área, em pontos percentuais. O tamanho cresce com a raiz quadrada dos votos da área; ficam inteiros os hexágonos com mais votos que 85% dos que estão à vista.

**Projeção.** Cônica de áreas iguais (Albers, com paralelos-padrão em 2°S e 22°S, como a do IBGE): o mesmo número de pontos ocupa a mesma área em qualquer parte do país. O fundo do mapa é feito só com a malha de municípios do IBGE, sem serviços de mapas de terceiros.

**Locais e posições.** Cada seção é ligada ao seu local de votação pelo arquivo de locais do TSE do mesmo ano. Locais no mesmo prédio (mesmo nome e coordenada, em zonas diferentes) viram um ponto só. O TSE informa as coordenadas da maior parte dos locais, mas não de todos: em 2018, faltam quase todas as de Minas Gerais e do Espírito Santo. Também são descartadas as coordenadas a mais de 2 km do município, pela malha do IBGE, e as repetidas em 3 ou mais locais de nomes diferentes do mesmo município (é o centro da cidade usado como posição padrão). As posições que faltam são completadas na ordem da tabela abaixo; cada local usa o primeiro método que se aplica a ele. Os locais de votação das eleições municipais de 2016, 2020 e 2024 entram só como referência.

```js
const anosMapa = Object.keys(resumoMapa.anos);
const parteEleitorado = (a, n) => {
  const m = resumoMapa.anos[a].metodos;
  const total = Object.values(m).reduce((s, v) => s + v.eleitores, 0);
  const v = m[n]?.eleitores ?? 0;
  if (!v) return "–";
  return v / total < 0.0001 ? "<\u00a00,01%" : pct((100 * v) / total, v / total < 0.001 ? 2 : 1);
};
display(html`<div class="tabela"><table>
  <thead><tr><th>Posição do local de votação</th>${anosMapa.map((a) => html`<th style="text-align:right">${a}</th>`)}</tr></thead>
  <tbody>${Object.entries(resumoMapa.metodos).map(([n, m]) => html`<tr><td>${n}.&nbsp;${m.descricao}</td>${anosMapa.map((a) => html`<td style="text-align:right">${parteEleitorado(a, n)}</td>`)}</tr>`)}</tbody>
</table></div>`);
```

<p class="nota">Em % do eleitorado dos locais de votação no Brasil. Os métodos 1 a 3 procuram, nesta ordem: o mesmo local (mesmo município, zona e número) em outra eleição, com nome parecido ou o mesmo endereço; outro local do município com o mesmo nome, sem as palavras genéricas como "escola estadual"; outro local com o mesmo endereço, desde que tenha número. Nos dois últimos, todos os locais com aquele nome ou endereço precisam estar no mesmo lugar. Os métodos 4 a 6 usam a mediana das posições dos outros locais do bairro, da zona eleitoral ou do município; no bairro, só se ele tem nome específico (não "zona rural") e é compacto. O método 7 vale para os poucos municípios sem nenhum local com coordenada válida: um ponto dentro do polígono do município.</p>

**Quanto cada método erra.** Para medir, cada método foi aplicado aos locais que têm coordenada do TSE, como se ela faltasse, e a posição encontrada foi comparada com a do TSE:

```js
const v22 = resumoMapa.validacao["2022"];
const km = (x) => `${decimal(x, x < 1 ? 2 : 1)}\u00a0km`;
display(html`<div class="tabela"><table>
  <thead><tr><th>Método</th><th style="text-align:right">Locais testados</th><th style="text-align:right">Erro mediano</th><th style="text-align:right">90% dos locais até</th><th style="text-align:right">Acima de 1 km</th></tr></thead>
  <tbody>${Object.entries(v22).map(([n, r]) => html`<tr><td>${n}.&nbsp;${resumoMapa.metodos[n].descricao}</td>
    <td style="text-align:right">${num(r.n)}</td><td style="text-align:right">${km(r.mediana_km)}</td>
    <td style="text-align:right">${km(r.p90_km)}</td><td style="text-align:right">${pct(100 * r.acima_1km, 1)}</td></tr>`)}</tbody>
</table></div>`);
```

<p class="nota">Locais de 2022. Em 2018 e em 2026 os números são praticamente os mesmos; os três anos estão no relatório de qualidade dos dados do projeto (<code>docs/qualidade_dados.md</code>).</p>

Os três primeiros métodos acham a posição do próprio local, quase sempre com erro nulo: o TSE repete a coordenada de um local de uma eleição para a outra. Os demais são aproximações: pelo bairro, o erro típico é de meio quilômetro; pela zona eleitoral ou pelo município, de vários quilômetros, sobretudo nos locais rurais. Por isso, os votos dos locais com posição aproximada se espalham num círculo maior, do tamanho da dispersão dos locais do bairro, da zona ou do município (de 300 metros a 10 km).

**Fora do mapa.** O voto no exterior, que não tem posição no Brasil.

## Pesquisas eleitorais

**De onde vêm.** O TSE guarda o registro de cada pesquisa (empresa, datas, tamanho da amostra, metodologia), mas não os resultados. Os números vêm das tabelas da Wikipedia em português ("Pesquisas de opinião para a eleição presidencial no Brasil"), que transcrevem as pesquisas divulgadas. Cada página é guardada na revisão usada, e a base derivada dela segue a licença da Wikipedia (CC BY-SA 4.0).

**Atualização.** Em 2026, a página é conferida a cada hora até a véspera do 2º turno. Como qualquer pessoa pode editar a Wikipedia, uma revisão nova só entra no site depois de uma conferência automática. Ela fica de fora até alguém olhar a página se mais de duas pesquisas já publicadas sumirem ou mudarem de uma vez, se um número já publicado mudar mais de 3 pontos, ou se uma pesquisa nova tiver datas ou percentuais impossíveis ou, no 2º turno, ficar a mais de 8 pontos da projeção.

**Quais entram.** Pesquisas nacionais com fim do campo entre 1º de janeiro do ano da eleição e a véspera de cada turno, quando o registro no TSE é obrigatório. No 1º turno, entra o cenário estimulado mais completo de cada pesquisa que traga os dois candidatos estudados; linhas que listam só os dois primeiros colocados, sem os demais, ficam de fora, porque não permitem calcular votos válidos. No 2º turno, entra o confronto direto entre os dois. Em 2018, só os cenários com Fernando Haddad (até 11 de setembro as pesquisas também testavam Lula).

**Ligação com o registro do TSE.** Pelo número de registro citado na Wikipedia (quase todas as de 2018 e do 1º turno de 2022). Sem número, pela mesma empresa com amostra a até 3% da registrada e fim do campo a até 3 dias: o registro traz o que foi planejado e a pesquisa publicada, o que foi feito. Amostra e datas sozinhas não bastam, porque amostras de 2.000 entrevistas são comuns a vários institutos. Pesquisas que não aparecem no registro nacional continuam no estudo, marcadas como "sem registro".

**Votos válidos.** As pesquisas medem a intenção de voto sobre o total de entrevistados; o resultado oficial é calculado sobre os votos válidos. Para comparar, cada candidato é dividido pela soma dos candidatos (e de "outros", no 1º turno), excluindo brancos, nulos e indecisos.

**Tendência e erro.** A linha de tendência é, em cada data, uma reta ajustada às pesquisas próximas (regressão linear local), com peso que cai com a distância no tempo (núcleo gaussiano de 7 dias) e cresce com a amostra (raiz quadrada, limitada a 5.000 entrevistas). Uma média móvel simples fica para trás no fim da série, onde só há pesquisas de um lado: na véspera da eleição, ela ainda mostraria a semana anterior. A reta corrige esse atraso: nos cinco turnos já decididos, deixou o fim da tendência mais perto das urnas (erro médio de 2,4 pontos no candidato bolsonarista e 0,9 no petista, contra 3,3 e 1,3 da média móvel). O erro de cada instituto compara a última pesquisa dele na semana anterior à eleição com o resultado das urnas.

**Percentuais "<1%".** Algumas tabelas trazem um limite em vez do percentual dos candidatos pequenos ("<0,9%"). Cada um conta como metade do limite, desde que a soma desses valores não passe do que falta para 100%. A regra importa nas pesquisas que já publicam votos válidos, como as da AtlasIntel: lá, oito "<0,9%" contados pela metade somariam 3,6 pontos além do total.

**2º turno.** A tendência das pesquisas de 2º turno recomeça no dia seguinte ao 1º turno. Antes dele, as pesquisas mediam um confronto hipotético; o resultado das urnas muda a disputa de um dia para o outro (em 2022, a tendência caiu de 57% para 53% de Lula entre a véspera do 1º turno e as primeiras pesquisas depois dele), e uma linha contínua espalharia essa mudança pelas semanas em volta.

## Projeção do 2º turno

```js
const par = projecao.parametros;
const anosValidados = Object.keys(projecao.validacao);
const nomesDe = (ano) => ({petismo: eleicoes.eleicoes[ano].petismo.nome, bolsonarismo: eleicoes.eleicoes[ano].bolsonarismo.nome});
```

A projeção estima o resultado do 2º turno de 2026, em % dos votos válidos, com a incerteza de cada número. Ela tem duas partes: quanto cada candidato terá no país e como esse total se distribui pelos estados e regiões. O mesmo método, refeito dia a dia com os dados de 2018 e de 2022, mostra quanto ele teria errado naquelas eleições.

**O ponto de partida.** Na noite do 1º turno, ainda sem pesquisas novas, a projeção parte do resultado das urnas e da divisão dos eleitores dos outros candidatos que as pesquisas da última semana mostravam. Muitas pesquisas perguntam o 1º e o 2º turno às mesmas pessoas: a diferença entre o petismo no 2º turno e no 1º, dividida pelo que os outros candidatos tinham no 1º, diz que parte dos eleitores dos outros iria para o petismo. A média dessa parte nas pesquisas da semana (${par.semana_pareadas} dias) é aplicada aos votos que os outros candidatos tiveram nas urnas. Comparar os dois turnos dentro da mesma pesquisa tira o viés que ela tenha igual nos dois. Em 2018, 2022 e 2026, as pesquisas do 1º turno ficaram abaixo do candidato bolsonarista; tomadas diretamente, as de 2º turno da mesma semana erraram a parte do PT em ${anosValidados.map((a) => `${pp(projecao.validacao[a].segundo_turno_nas_pesquisas, 1)} (${a})`).join(" e ")}, e o ponto de partida, em ${anosValidados.map((a) => `${pp(projecao.validacao[a].partida, 1)} (${a})`).join(" e ")}.

**As pesquisas depois do 1º turno.** A cada dia, entra a tendência das pesquisas de 2º turno com o campo inteiro depois do 1º turno, a mesma reta local da seção de pesquisas (núcleo de ${par.janela_dias} dias), no dia da última pesquisa. As duas estimativas se juntam pela precisão de cada uma. Os desvios usados (em pontos percentuais da parte de cada candidato nos votos válidos):

```js
display(html`<div class="tabela"><table>
  <thead><tr><th>Parte da incerteza</th><th style="text-align:right">Desvio</th><th>De onde vem</th></tr></thead>
  <tbody>
    <tr><td>Ponto de partida</td><td style="text-align:right">${decimal(par.desvio_partida, 1)}</td><td>errou ${anosValidados.map((a) => `${pp(projecao.validacao[a].partida, 1)} em ${a}`).join(" e ")}; com duas eleições, um valor maior que esses erros</td></tr>
    <tr><td>Uma pesquisa em torno da média</td><td style="text-align:right">${decimal(par.desvio_pesquisa, 1)}</td><td>amostra e estilo de cada instituto; pesa menos quanto mais pesquisas houver</td></tr>
    <tr><td>Erro comum a todas as pesquisas</td><td style="text-align:right">${decimal(par.desvio_vespera, 1)}</td><td>o que a média das pesquisas ainda erra na véspera; não diminui com mais pesquisas</td></tr>
    <tr><td>Mudança até a eleição</td><td style="text-align:right">${decimal(par.desvio_deriva, 1)} por raiz de dia</td><td>quanto a opinião ainda pode mudar entre a última pesquisa e a eleição: ${decimal(par.desvio_deriva * Math.sqrt(7), 1)} pontos em uma semana</td></tr>
  </tbody>
</table></div>`);
```

<p class="nota">Logo depois do 1º turno, com poucas pesquisas, o ponto de partida pesa mais; perto da eleição, com dezenas de pesquisas e pouco tempo para a opinião mudar, as pesquisas pesam quase tudo. A chance de vitória é a probabilidade de passar de 50% numa distribuição normal com a média e o desvio combinados. Com só duas eleições para comparar, os desvios são números redondos, escolhidos para que as faixas de 80% contenham o resultado com folga em 2018 e 2022, e não um ajuste fino.</p>

**Estados e regiões.** O total do país é distribuído seção por seção, a partir do 1º turno. Quem votou no candidato do PT ou no bolsonarista continua com ele; os votos dos outros candidatos se dividem numa proporção que acompanha como a seção votou: onde o petismo teve, entre os dois, mais votos, a parte dele nos votos dos outros também é maior. A força dessa relação (${decimal(par.inclinacao, 1)}, numa escala em que 0 seria a mesma divisão em todo o país e 1, uma divisão que acompanha inteiramente a da seção) foi a que melhor reproduziu os municípios em 2018 e 2022. Um único número, ajustado a cada projeção, faz a soma das seções dar o total do país. O erro dessa distribuição, medido com o total nacional verdadeiro, foi proporcional ao peso dos outros candidatos no 1º turno: em cada estado, cerca de ${decimal(par.erro_uf, 2)} ponto para cada ponto dos outros (em 2018 eles tiveram 25%; em 2022, 8%). O intervalo de cada estado soma esse erro à incerteza do país.

**Como teria se saído.** Em 2018 e em 2022, a projeção refeita a cada dia entre os dois turnos, só com as pesquisas concluídas até aquele dia:

```js
const anosProj = anosValidados.map((a) => projecao.anos[a]);
```

<div class="grid grid-cols-2">
  ${anosProj.map((p) => html`<div class="card">
    <h2>${p.ano}</h2>
    <h3>% dos votos válidos no 2º turno · faixa de 80% · losango: as urnas</h3>
    ${resize((width) => graficoProjecao(p, {width, nomes: nomesDe(p.ano), height: 300}))}
  </div>`)}
</div>

```js
display(html`<div class="tabela"><table>
  <thead><tr><th>Eleição</th><th style="text-align:right">Ponto de partida</th><th style="text-align:right">Erro médio da projeção</th><th style="text-align:right">Na véspera</th><th style="text-align:right">Dias com as urnas na faixa de 80%</th><th style="text-align:right">Estados na faixa de 80%, na véspera</th></tr></thead>
  <tbody>${anosValidados.map((a) => {
    const v = projecao.validacao[a];
    return html`<tr><td style="white-space:nowrap">${a}, 2º turno</td><td style="text-align:right">${pp(v.partida, 1)}</td><td style="text-align:right;white-space:nowrap">${decimal(v.projecao.medio, 1)} ponto${v.projecao.medio >= 2 ? "s" : ""}</td>
      <td style="text-align:right">${pp(v.projecao.vespera, 1)}</td><td style="text-align:right">${pct(100 * v.projecao.dias_no_intervalo, 0)}</td>
      <td style="text-align:right">${pct(100 * v.vespera_ufs.no_intervalo, 0)}</td></tr>`;
  })}</tbody>
</table></div>`);
```

<p class="nota">Erro: projeção menos urnas, na parte do candidato do PT nos votos válidos (positivo: a projeção deu mais ao PT do que as urnas). Em 2018, as pesquisas depois do 1º turno ficaram abaixo de Fernando Haddad até a última semana, e o ponto de partida segurou a projeção perto do resultado; em 2022, as primeiras pesquisas depois do 1º turno ficaram acima de Lula, e a projeção só chegou perto das urnas na reta final. Só com o total nacional verdadeiro, a distribuição pelo país errou, por estado, ${anosValidados.map((a) => `${decimal(projecao.validacao[a].distribuicao.ufs, 1)} ponto${projecao.validacao[a].distribuicao.ufs >= 2 ? "s" : ""} em ${a}`).join(" e ")} (desvio típico), e por município ${anosValidados.map((a) => `${decimal(projecao.validacao[a].distribuicao.municipios, 1)}`).join(" e ")}. Relatório completo em <code>docs/validacao_projecao.md</code>.</p>

<div class="grid grid-cols-2">
  ${anosProj.map((p) => html`<div class="card">
    <h2>${p.ano}, estados na véspera</h2>
    <h3>Projeção do PT (ponto), faixa de 80% (barra) e urnas (losango)</h3>
    ${resize((width) => graficoLugares(p, {nivel: "ufs", width, nomes: nomesDe(p.ano)}))}
  </div>`)}
</div>

## Forecast da apuração

```js
const fc = FileAttachment("data/forecast.json").json();
const ap22t2 = FileAttachment("data/apuracao_2022_t2.json").json();
```

```js
const fp = fc.parametros;
const fv22 = fc.validacao["2022"].simples;
const fv18 = fc.validacao["2018"].simples;
const noite22 = serieDaNoite(fc.noites["2022"]);
const nomes22 = {petismo: eleicoes.eleicoes["2022"].petismo.nome, bolsonarismo: eleicoes.eleicoes["2022"].bolsonarismo.nome};
const noMarco = (v, m) => v.por_marco.find((x) => x.marco === m);
const virada22 = ap22t2.viradas.at(-1);
const cedo22 = noite22.find((f) => f.apurado >= 2);
const quando = (ap, minuto) => hora(new Date(Date.parse(ap.inicio + ":00Z") + minuto * 60000));
const atributosGanham = ["2018", "2022"].every((a) => fc.validacao[a].atributos.por_marco.every((x, i) => x.erro_medio <= fc.validacao[a].simples.por_marco[i].erro_medio));
```

Na noite do 2º turno de 2026, o forecast estima o resultado final a cada minuto, com a incerteza dele. A contagem do TSE mostra o que já foi apurado, e isso depende de quais lugares chegaram primeiro: em 2022, ${nomes22.bolsonarismo} liderou a contagem até as ${quando(ap22t2, virada22.t)}, com ${pct(virada22.pct_secoes, 0)} das seções apuradas, e perdeu. O forecast olha também para quem falta apurar.

**O ponto de partida.** Durante a noite, o TSE publica quais seções já chegaram e o resultado de cada município, e o 1º turno de cada seção é conhecido. Cada seção começa com o resultado que a projeção do 2º turno da véspera espera dela: o 1º turno da seção, com os votos dos outros candidatos divididos como na projeção. Com 0% apurado, o forecast é a própria projeção, inclusive na incerteza.

**O que a noite ensina.** Quanto cada lugar se afasta desse ponto de partida — o swing — é aprendido com o que já foi apurado, num modelo hierárquico: um município com metade das seções apuradas diz muito sobre a outra metade; um município sem nada apurado fica com o swing da sua UF, que, sem nada apurado, fica com o da região, e esta com o do país. O comparecimento (quantos votos cada lugar dá em relação ao 1º turno) segue o mesmo modelo. O resultado de cada município é lido a cada poucos minutos, e o total de cada UF, a cada minuto; o que o total da UF tem a mais que os municípios lidos entra também.

**A incerteza.** Cada nível (região, UF, município e seção) tem o seu desvio. Além deles, o que falta apurar não vota exatamente como o que já foi apurado, mesmo descontado o 1º turno de cada seção (em 2022, a parte de cada cidade que chegou por último pendeu um pouco mais para o bolsonarismo): o forecast conta com isso no país, em cada UF e em cada município. Esses desvios crescem com o peso dos outros candidatos no 1º turno — são os votos deles que se dividem de um jeito diferente do esperado — e foram medidos com o resultado verdadeiro de 2018 (outros: ${pct(100 * fp.outros["2018"], 0)} dos válidos no 1º turno) e de 2022 (${pct(100 * fp.outros["2022"], 0)}); em 2026, os outros tiveram ${pct(100 * fp.outros["2026"], 1)}. A faixa de 80% e a chance de vitória vêm de uma conta exata para esse modelo, sem sorteios.

**Como teria se saído.** As noites do 2º turno de 2018 e 2022 foram refeitas seção a seção, só com o que se sabia em cada momento: o resultado de cada município como os coletores o teriam lido, o total de cada UF a cada minuto e a hora de chegada de cada seção. Para não depender da ordem em que o país apura, cada noite foi refeita em várias ordens de chegada (${fv22.ordens} em 2022 e ${fv18.ordens} em 2018): a real; a do 1º turno; cada região por último; as UFs em ordens sorteadas; e as seções embaralhadas.

<div class="card">
  <h2>A noite do 2º turno de 2022, refeita</h2>
  <h3>% dos votos válidos já apurados e, tracejado, o resultado final que o forecast previa a cada momento, com a faixa de 80%</h3>
  ${legenda([{nome: nomes22.petismo, cor: COR.petismo}, {nome: nomes22.bolsonarismo, cor: COR.bolsonarismo}, {nome: "forecast refeito, com a faixa de 80%", cor: "var(--theme-foreground-muted)", estilo: "faixa"}])}
  ${resize((width) => graficoCampos(ap22t2, {eixo: "hora", medida: "pct", width, nomes: nomes22, previsao: {serie: noite22}}))}
</div>

<p class="nota">Às ${quando(ap22t2, cedo22.minuto)}, com ${pct(cedo22.apurado, 0)} das seções apuradas, o forecast refeito já dava ${nomes22.petismo} com ${pct(cedo22.petismo, 1)} (80% de chance entre ${pct(cedo22.inf, 1)} e ${pct(cedo22.sup, 1)}); as urnas deram ${pct(fc.noites["2022"].real, 2)}, e a projeção da véspera, ${pct(fc.noites["2022"].projecao, 2)}. A contagem só virou às ${quando(ap22t2, virada22.t)}. A mesma camada aparece na página de 2022.</p>

```js
display(html`<div class="tabela"><table>
  <thead><tr><th style="text-align:right">Seções apuradas</th><th style="text-align:right">2022: erro médio · máximo</th><th style="text-align:right">2022: faixa de 80%</th><th style="text-align:right">2018: erro médio · máximo</th><th style="text-align:right">2018: faixa de 80%</th><th style="text-align:right">Só a contagem, 2022: erro médio</th></tr></thead>
  <tbody>${[1, 2, 5, 10, 20, 50, 80, 95].map((m) => {
    const a = noMarco(fv22, m), b = noMarco(fv18, m);
    return html`<tr><td style="text-align:right">${pct(m, 0)}</td>
      <td style="text-align:right;white-space:nowrap">${decimal(a.erro_medio, 2)} · ${decimal(a.erro_max, 2)}</td><td style="text-align:right">±${decimal(1.2816 * a.desvio, 2)}</td>
      <td style="text-align:right;white-space:nowrap">${decimal(b.erro_medio, 2)} · ${decimal(b.erro_max, 2)}</td><td style="text-align:right">±${decimal(1.2816 * b.desvio, 2)}</td>
      <td style="text-align:right">${decimal(a.contagem_media, 2)}</td></tr>`;
  })}</tbody>
</table></div>`);
```

<p class="nota">Erro: forecast menos urnas, na parte do candidato do PT nos votos válidos, em pontos percentuais, em todas as ordens de chegada. Faixa: metade do intervalo de 80% (média). O resultado ficou dentro da faixa de 80% em ${pct(100 * fv22.na_faixa, 0)} dos momentos em 2022 e em ${pct(100 * fv18.na_faixa, 0)} em 2018 (de 1% apurado em diante): as faixas são conservadoras, como as da projeção. Em 2018, sem a hora de chegada de cada boletim, a ordem é estimada, e a divulgação só começou às 19h, com quase todas as seções apuradas; o teste de 2018 vale sobretudo pelas ordens inventadas, com os outros candidatos três vezes mais fortes que em 2026. Também foi testado um swing que acompanha atributos do 1º turno de cada seção (a parte dos outros candidatos, a inclinação entre os dois e o comparecimento), aprendido a cada momento nos municípios já apurados: ${atributosGanham ? "ele ganhou do modelo simples e entrou no forecast" : "ele não ganhou do modelo simples nas duas eleições e ficou de fora"}. Relatório completo em <code>docs/validacao_forecast.md</code>.</p>

**O que é estimado.** O forecast é deste estudo, não do TSE, e o resultado oficial é o do TSE. Durante a noite, o mapa mostra em cada município o que o TSE já apurou nele; a divisão desses votos entre os locais de votação do município é estimada pela mesma conta do forecast (o 1º turno de cada local e o swing estimado do município), e aparece com o selo "estimada" até o TSE publicar os boletins de urna.

## Horários

Todas as horas estão no horário de Brasília. Nos arquivos do TSE, a chegada do boletim está no horário de Brasília, e a abertura e o encerramento da urna, no horário local da seção. Em 2018, cada estado votou das 8h às 17h no horário local e a divulgação começou às 19h de Brasília; desde 2022, todo o país vota das 8h às 17h de Brasília e a divulgação começa às 17h.
