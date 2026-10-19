# Análise modal por impacto — roving hammer

Execute **iniciar_modal.bat**. O programa usa o ambiente instalado por `instalar.bat`
e o mesmo driver da versão atual de aquisição. `iniciar.bat` e `iniciar_ponte.bat`
continuam disponíveis para os programas anteriores.

## Uso

1. Conecte ao **Simulador modal** ou ao **ADS 1800 real**. No equipamento, configure
   previamente sensores, unidades, faixas e condicionamento no Assistente LYNX.
2. Selecione canais distintos para martelo e acelerômetro. Os valores do equipamento
   já são de engenharia: mantenha fator 1 para N e m/s²; para aceleração em g,
   use 9,80665. Outros fatores podem incluir inversão de sinal para a convenção +Z.
   Faixas de saturação são obtidas do equipamento e convertidas pelos mesmos fatores.
3. Informe o contorno da peça por vértices XY em metros, na ordem da borda,
   e um ponto de impacto por linha (`nome; x; y`). Os nomes devem ser únicos.
   Não há quantidade fixa de pontos. A posição XY do acelerômetro é fixa durante
   todo o ensaio. Força e aceleração são normais ao plano XY, em Z.
4. Ajuste a taxa, o registro total (inclui o pré-trigger), o limiar em N e as janelas.
   O passa-banda fica ativado inicialmente entre **1 e 500 Hz**, com amostragem
   padrão de **2000 Hz**. É possível desativá-lo ou ajustar os dois cortes.
   **Atualizar desenho** confere a configuração e mostra a geometria.
5. Clique **Iniciar novo ensaio** e escolha a pasta. Uma subpasta exclusiva recebe
   configuração, metadados dos canais, sinais e resultados.
6. Na segunda aba, escolha o ponto e clique **Armar trigger**. Após preencher o
   pré-trigger e observar força abaixo de 50% do limiar, o próximo cruzamento
   dispara uma captura. Um aviso sonoro e a mensagem **Pronto** indicam quando
   o operador pode bater. Há polaridade absoluta, positiva ou negativa.
7. Confira os sinais, FFTs e alertas. **Aceitar batida** inclui a captura nas médias
   daquele ponto; **Rejeitar batida** preserva os dados, mas os exclui das médias.
   Ao aceitar, o trigger é rearmado automaticamente se a aquisição continuar ativa;
   aguarde novamente o aviso sonoro. Rejeitar não rearma automaticamente.
   A meta de médias é orientativa e não limita capturas.
8. Troque o ponto com o sistema desarmado e sem revisão pendente. O acelerômetro
   permanece na mesma posição. **Parar aquisição** cancela registros incompletos,
   preservando capturas completas para revisão.

Durante a aquisição, use **Cancelar espera** e **Configurar trigger…** para mudar
o limiar em N, a polaridade e o intervalo mínimo sem contato para detectar impacto
duplo (padrão 2 ms). Conclua a revisão pendente antes de alterar. Duração,
pré-trigger e janelas são mantidos para garantir registros compatíveis nas médias.
As próximas capturas registram os parâmetros de trigger utilizados; os alertas
das capturas anteriores permanecem preservados.

**Sair do ensaio** interrompe a aquisição, libera a revisão pendente na interface
e retorna à configuração, sem apagar capturas já salvas. Funciona mesmo quando
a pasta foi removida ou ficou indisponível. Uma captura incompleta é descartada;
batidas completas ainda pendentes permanecem nesse estado no disco disponível.

As curvas temporais mostram dados em SI com passa-banda quando ativado; as FFTs
usam os sinais com remoção de linha de base, passa-banda e janelamento. Enquanto armado, os gráficos temporais
mostram os últimos dois segundos ao vivo. Depois do impacto, mostram o registro
com tempo relativo ao trigger. As FRFs e a coerência usam apenas capturas aceitas.

O seletor de visualização da FRF permite **Magnitude + Fase**, **Parte real + Fase**
ou **Parte real + Parte imaginária**, tanto na aquisição quanto no pós-processamento.
A fase é apresentada em graus, de −180° a +180°; as demais componentes usam
`(m/s²)/N`. No pós-processamento, os dois gráficos comparam a FRF medida e a
ajustada. A troca não recalcula nem invalida os resultados modais.

**Abrir ensaio salvo** reabre a subpasta que contém `session.json`, inclusive sem
conexão ao hardware. Clique em uma captura para rever os sinais e alterar sua
aceitação. A mudança recalcula as médias e atualiza os arquivos. Para um novo
ensaio, a configuração é feita na primeira aba. Configurações JSON podem ser
salvas separadamente e carregadas após conectar, para conferir canais e taxa.

## Janelas propostas

| Sinal | Janela | Comportamento |
|---|---|---|
| Martelo | Força (padrão) | Mantém pré-trigger e pulso; fecha após a duração configurada, com transição cosseno nos últimos 20% do pós-trigger da janela. |
| Martelo e aceleração | Retangular | Usa todo o registro sem atenuação. Adequada quando o transitório termina no registro. |
| Martelo e aceleração | Hann | Atenua as extremidades; pode diminuir muito um impacto próximo ao início. |
| Aceleração | Exponencial (padrão) | Valor 1 até o trigger, decaindo até o resíduo final escolhido; 0,01 corresponde a 1%. |

A janela de força deve conter todo o contato. A exponencial reduz vazamento, mas
introduz amortecimento artificial e pode enviesar a FRF. A FRF de aquisição não é
corrigida; o pós-processamento usa uma exponencial comum com correção própria,
descrita abaixo. Para resultados quantitativos, prefira registrar
todo o decaimento e conferir o efeito das janelas.

Referência para escolha das janelas: [NI — Understanding FFTs and Windowing](https://www.ni.com/en/shop/data-acquisition/measurement-fundamentals/analog-fundamentals/understanding-ffts-and-windowing.html).

## Cálculos e qualidade

- A linha de base é a média da primeira metade do pré-trigger, subtraída antes do
  janelamento. Os dados originais permanecem salvos.
- Para cada ponto, `H1 = média(A · conjugado(F)) / média(|F|²)`, em `(m/s²)/N`.
  São mostrados módulo e fase principal em graus. As médias são espectrais,
  com pesos iguais, sem misturar pontos e sem fazer média dos quocientes individuais.
  O cálculo explicita as densidades unilaterais `G_AF` e `G_FF`, com fator
  comum `1/(fs·N)` e duplicação dos bins internos: `H1 = G_AF/G_FF`.
  São densidades dos sinais já janelados, sem correção de ganho das janelas.
  O fator comum cancela no quociente. O estimador anterior já usava os produtos
  espectrais corretos; não se substitui H1 por `G_AA/G_FF`, que perderia a fase.
- Coerência: `|média(A · conjugado(F))|² / (média(|F|²) · média(|A|²))`.
  É omitida até haver duas batidas aceitas. Duas são o mínimo matemático; várias
  repetições são necessárias para uma avaliação robusta. Coerência alta isolada
  não garante ausência de erro sistemático.
- Frequências com potência de força abaixo de `1e-10` do máximo (ou potência de
  resposta numericamente nula) são mascaradas como NaN. Isso evita divisões
  numéricas inválidas, mas não substitui a seleção da faixa útil de excitação.
- FFT unilateral de amplitude: `|FFT|/N`, duplicando os bins internos, sem duplicar
  DC ou Nyquist. Não há correção de ganho coerente das janelas. Para transitórios,
  as amplitudes dependem do comprimento do registro e da janela; não são PSD.
- Alertas: contatos de mesma polaridade acima de 20% do pico ou seis desvios
  do ruído (o maior), separados por pelo menos 2 ms abaixo de 5% do pico ou três
  desvios do ruído (o maior). O intervalo é ajustável; pequenas interrupções e
  oscilações de polaridade oposta não são contadas como novos contatos.
  Possível saturação requer atingir/exceder um limite de engenharia ou duas
  amostras consecutivas próximas do mesmo limite (margem de 0,1% da faixa).
  Um pico isolado nessa margem recebe apenas aviso de proximidade do limite.
  Sem limites de engenharia conhecidos não se infere saturação. Outros alertas:
  força com S/R abaixo de 20 dB, RMS no último décimo do registro acima de 20%
  do RMS pós-trigger, e força fora da janela acima de 5% do pico.
- Os critérios são heurísticos, não certificam a batida e não a rejeitam automaticamente.
  Perdas de amostras, descontinuidade temporal e valores não finitos cancelam a captura.

## Arquivos

- `session.json`: geometria, configuração congelada, canais, fatores, pontos,
  arquivos de captura, critérios de qualidade e decisões de revisão.
- `impacto_<id>.npz`: tempo original, força em N, aceleração em m/s² e espectros
  complexos janelados. Todas as capturas completas são salvas antes da revisão.
- `frf_ponto_<índice>.csv`: frequência, partes real e imaginária da H1, módulo,
  fase em graus e coerência. O índice corresponde à ordem dos pontos em `session.json`.
- **Exportar sinais da batida selecionada**: CSV com tempo, força e aceleração.
  Com filtro ativado, inclui as colunas originais e as colunas de força e aceleração
  filtradas, identificadas no cabeçalho.

## Filtro passa-banda

A configuração contém **Ativar filtro passa-banda em todos os resultados**, corte
inferior e corte superior em Hz. Novos ensaios usam o filtro ativado em 1–500 Hz.
O corte superior precisa ser estritamente menor que metade da amostragem: 1000 Hz
de amostragem não comporta esse corte; o novo padrão de amostragem é 2000 Hz.
Não há alteração automática dos cortes quando o usuário escolhe outra taxa.

O filtro é Butterworth causal, implementado em seções de segunda ordem (SOS), com
protótipo de ordem 4 (passa-banda de 8 polos). A mesma função de transferência é
aplicada à força e à aceleração. No registro capturado, remove-se a linha de base
do pré-trigger, aplica-se o filtro e só então as janelas e FFTs. As FRFs H1 e a
coerência usam esses espectros; frequências fora dos cortes são mascaradas. O
pós-processamento modal aplica o mesmo filtro aos sinais originais antes de sua
janela exponencial comum, e restringe o ajuste à banda configurada.

Na visualização ao vivo, o filtro conserva o estado entre blocos. Para cada batida
completa, ele é reiniciado sobre o registro com pré-trigger e linha de base removida,
para garantir reprocessamento determinístico. Pode haver diferença de transiente
entre a curva ao vivo e o registro final. Confira o início e o decaimento dos sinais
filtrados e ajuste pré-trigger, duração e janela de força para incluir sua resposta.
O filtro introduz atraso e transientes; não é um filtro de fase zero.

O trigger e os indicadores de qualidade da batida usam os sinais originais, evitando
que o filtro esconda saturação ou que seu transiente seja confundido com impacto
duplo. Os arquivos NPZ preservam esses sinais originais e os espectros processados;
o CSV de exportação permite comparar sinais originais e filtrados. O relatório modal
exportado também registra a configuração do filtro.

A configuração do filtro é salva com o ensaio. Arquivos antigos que não possuem
esses campos são abertos com filtro desativado para preservar suas FRFs existentes;
novas configurações e ensaios partem do filtro ativado por padrão.

O simulador gera impactos periódicos e duas respostas modais causais, próximas
de 35 e 90 Hz. Serve para experimentar o fluxo e verificar a apresentação; não
usa a geometria para resolver um modelo físico da peça.

Esta versão implementa aquisição, análise de FRFs e pós-processamento modal,
com um acelerômetro fixo. A conexão real reutiliza o driver existente; deve ser
validada na bancada com os sensores e o ADS 1800 conectados.

## Pós-processamento: frequências, amortecimentos e formas modais

Na aba **3. Pós-processamento modal**, após parar a aquisição ou abrir um ensaio salvo:

1. Defina a faixa de análise em Hz, a coerência mínima (padrão 0,8) e o mínimo de
   batidas aceitas por ponto (padrão 2). Pontos sem dados suficientes são excluídos
   e identificados nos alertas; suas amplitudes não são preenchidas com zero.
2. Escolha o resíduo da exponencial comum: 0,01 por padrão; 1 usa sinais sem janela.
   O pós-processamento sempre recalcula as FRFs dos sinais originais das batidas
   **atualmente aceitas**. As janelas usadas na aquisição e suas FRFs permanecem intactas.
3. Deixe os candidatos vazios para detecção de picos, ou informe frequências
   iniciais separadas por `;`, por exemplo `35; 90`. Ajuste a proeminência dos
   picos e o máximo de candidatos automáticos (até 12). Picos são candidatos,
   não uma certificação de que existe um modo estrutural.
4. Clique **Calcular frequências, amortecimentos e modos**. O ajuste ocorre em
   segundo plano. A tabela apresenta frequência natural não amortecida em Hz e
   razão de amortecimento ζ em porcentagem. A frequência amortecida também é exportada.
5. Selecione uma linha da tabela para animar a forma modal, pausar a animação ou
   alterar sua ampliação. A tabela inferior contém os valores assinados em cada
   ponto. A maior componente é normalizada para +1; não são deslocamentos em metros.
6. Compare FRF medida (azul) e ajustada (laranja), escolhendo cada ponto. O erro
   mostrado usa a FRF complexa nos bins válidos, não somente seu módulo. Revise
   candidatos e faixa se o ajuste não representar as ressonâncias medidas.
7. **Salvar pós-processamento** cria uma subpasta exclusiva no ensaio com `modos.json`,
   `modos.csv`, `formas_modais.csv` e `frfs_ajustadas.npz`. O JSON inclui geometria,
   parâmetros, alertas e identificação das capturas utilizadas. O NPZ contém as
   FRFs medidas e ajustadas complexas, frequências, coerência e nomes dos pontos.

Mudar configurações ou a aceitação de uma captura invalida o resultado exibido.
Os relatórios já exportados são snapshots das capturas listadas no próprio relatório.
Não é necessário conectar ao ADS para pós-processar um ensaio salvo.

### sdypy-EMA: identificação e diagrama de estabilização

O motor padrão é **sdypy-EMA 0.31.0**, sucessor do pyEMA, instalado por
`instalar.bat`. Usa LSCF para identificar polos em várias ordens e LSFD para
obter constantes modais complexas e reconstruir as FRFs. A ordem polinomial
máxima padrão é 20, correspondente à ordem dinâmica máxima 40.

Na aba **Diagrama de estabilização**, as cores distinguem polos novos,
estabilidade de frequência, frequência + amortecimento e também forma modal
(MAC). As tolerâncias iniciais são 1%, 5% e MAC mínimo 0,95, ajustáveis.
O MAC entre ordens exige pelo menos dois pontos comuns. Estabilidade numérica
não certifica um modo físico. A seleção automática procura polos repetidos
próximos dos picos; quando não há candidatos, o diagrama fica disponível para
seleção manual. Clique em uma ocorrência de cada modo e em **Aplicar polos
selecionados (LSFD)** para recalcular. Evite selecionar várias ordens do mesmo modo.

As frequências selecionadas aparecem como linhas tracejadas no diagrama, na
comparação de FRFs e nos gráficos espectrais da aquisição. O Auto-MAC compara
as formas selecionadas; com um único ponto não permite distinguir formas.
A animação preserva a fase relativa das componentes complexas. O relatório inclui
partes real e imaginária das formas, constantes modais, formas reais equivalentes,
Auto-MAC e `estabilizacao.csv`, além dos arquivos descritos acima.

A acelerância com janela comum é convertida em receptância dividindo por
`(α + iω)²`. Os polos identificados são corrigidos somando `α` à parte real;
a reconstrução é reconvertida para acelerância. Essa correção não elimina
truncamento, ruído ou erros de modelo. A coerência determina a elegibilidade
dos pontos e polos e os bins usados no erro; o LSCF usa uma grade uniforme,
sem ponderação por coerência. Apenas falhas espectrais de até dois bins e
no máximo 5% da faixa são interpoladas, com aviso; lacunas maiores excluem o ponto.

Referências: [projeto sdypy-EMA](https://github.com/sdypy/sdypy-EMA),
[documentação da biblioteca](https://sdypy-ema.readthedocs.io/en/latest/code_documentation.html).
A dependência é distribuída sob licença MIT.

### Motor alternativo: ajuste de modos reais e efeito da janela

O modelo é uma soma de modos reais de acelerância com frequências e amortecimentos
comuns a todas as FRFs. Os coeficientes modais reais são ajustados separadamente
por ponto, preservando sinais relativos. O modelo usa:

`H(s) = Σ r_j s² / (s² + 2 ζ_j ω_j s + ω_j²) + c0 + c2 (s / 2π)²`

Os dois termos adicionais aproximam contribuições de modos fora da faixa. Um ajuste
de mínimos quadrados complexo estima frequências e amortecimentos; a cada iteração,
os coeficientes são resolvidos por mínimos quadrados lineares reais. Cada FRF é
normalizada por seu RMS na faixa para evitar que apenas o ponto mais forte domine
o ajuste. Bins com baixa coerência ou divisão espectral inválida são excluídos.
Com mínimo de uma batida, a ausência de coerência é avisada e o filtro não se aplica
àquele ponto. Em faixas muito extensas, há redução de bins para limitar o custo,
preservando vizinhanças dos candidatos na resolução original.

A mesma janela `exp(-αt)` é aplicada à força e à aceleração, após remover
a média da primeira metade do pré-trigger e aplicar o passa-banda, se ativado.
`α = -ln(resíduo) / duração entre primeira
e última amostra`. A resposta transformada corresponde a `H(α + iω)`, onde o modelo
é avaliado durante o ajuste. Assim, o amortecimento retornado é o parâmetro físico
do modelo, levando em conta o decaimento exponencial introduzido. Isso evita aplicar
uma correção simplificada a FRFs calculadas com janelas diferentes nos dois canais.
A correção não elimina erros de truncamento, ruído ou inadequação do modelo.

Referências: [B&K — Structural Testing, Part 2](https://www.bksv.com/doc/br0507.pdf),
[artigo sobre aplicação e correção da janela exponencial](https://www.sciencedirect.com/science/article/pii/S0888327096900849),
[SciPy — least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html).

### Interpretação das formas e limitações

Para uma estrutura linear, recíproca e com modos reais, o coeficiente modal da FRF
de cada ponto é proporcional ao produto da componente naquele ponto pela componente
na referência fixa. Isso permite recuperar formas relativas por roving hammer.
Não há normalização por massa nem intervalos estatísticos de confiança.
O motor sdypy-EMA permite formas complexas e diagrama de estabilização;
o motor alternativo mantém a hipótese de modos reais.

A animação representa apenas os graus de liberdade Z nos pontos medidos, em
perspectiva do plano XY. Não interpola uma superfície entre pontos nem atribui
deformação aos vértices não medidos do contorno. O marcador do acelerômetro indica
a posição da referência, não um apoio ou restrição de deslocamento. A animação
é lenta e a amplitude é ampliada para visualização; não reproduz o tempo físico.

Modos com nó no acelerômetro fixo ou pouco excitados pelo martelo podem ser
inobserváveis. Modos repetidos e muito próximos podem não ser separados por uma
única referência. A busca automática pode omitir modos fracos; use candidatos
manuais e compare o ajuste das FRFs. O ajuste atual restringe ζ entre 0,001% e 30%.
São sinalizados amortecimento no limite, largura modal menor que dois bins,
frequência no limite de um candidato, mau condicionamento e erro de ajuste acima
de 20%. Os parâmetros continuam sendo estimativas que precisam de avaliação.

## Importação de ensaios CSV históricos

Na configuração, defina a geometria e os pontos e use **Importar CSV**.
São aceitos os cabeçalhos do sistema ADS antigo e do programa atual, com
tempo, martelo e acelerômetro. Unidades lbf e g são convertidas para N e m/s²;
unidades desconhecidas e descontinuidades temporais são rejeitadas.

Escolha explicitamente início/fim, ponto de impacto, trigger, duração,
pré-trigger e filtro. Confirme que o intervalo corresponde à mesma estrutura
e ponto. Cada importação cria um ensaio separado para o intervalo escolhido.
Não há agrupamento automático de dez batidas nem inferência de coordenadas.
Batidas usadas para demarcar séries devem ficar fora do intervalo selecionado.

Todas as capturas entram como **pendentes**: revise os sinais e alertas antes
de aceitar ou rejeitar cada uma. Contatos adicionais dentro de um registro
permanecem no sinal para a avaliação de impacto duplo. A origem, as conversões
e o intervalo ficam registrados; o CSV original permanece intacto.
Para arquivos amostrados a 1000 Hz, o corte superior sugerido é 450 Hz,
pois o corte precisa ficar abaixo de Nyquist (500 Hz).
