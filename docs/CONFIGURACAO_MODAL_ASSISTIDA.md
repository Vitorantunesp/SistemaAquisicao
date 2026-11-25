# Configuração do ensaio e assistente com duas batidas

Abra `iniciar_modal.bat`. A navegação da esquerda seleciona **Configuração do
ensaio**, **Monitor de impactos** ou **Pós-processamento**.

## Abas da configuração

- **Conexão e canais:** conecta ao ADS1800 ou simulador, lista os parâmetros
  informados por cada canal e atribui martelo, acelerômetro fixo A1 e acelerômetros
  adicionais. As conversões para N e m/s² ficam junto dos canais. Valores não
  retornados pelo equipamento aparecem como “Não informado”.
- **Geometria:** define contorno, pontos de impacto, posição de A1 e posições
  dos acelerômetros adicionais. As posições e canais compartilham a mesma
  configuração; mover um sensor não troca sua atribuição de canal.
- **Parâmetros das batidas:** contém taxa padrão, duração, bloco calculado,
  pré-trigger, trigger, janelas, filtro e médias. Permite configuração manual
  ou medição pelo assistente.

## Fluxo automático do assistente

1. Abra **Assistente por batidas…**. O martelo bruto começa a aparecer no topo.
   Os ajustes ficam à esquerda. Abaixo, os gráficos mostram a última batida
   completa: força e sua PSD, aceleração e sua PSD ou coerência.
   Há medição inicial do ruído de 0,5 s; aguarde o aviso sonoro antes de bater.
2. Faça a primeira batida no ponto escolhido. A detecção inicial usa 5% da amplitude
   disponível no canal do martelo, relativa à linha de base, respeitando o ruído.
   Para um canal bipolar de -500 a +500 N e linha de base zero, o nível é 25 N.
   Se os limites não estiverem disponíveis, o ruído define a detecção provisória.
3. O programa mede o pico, o contato e o tempo de decaimento no acelerômetro
   selecionado. O próximo trigger é exatamente **50% do primeiro pico**.
   A duração inclui pré-trigger e **decaimento acrescido de 5%**.
4. A aquisição passa à taxa final sugerida e mede novamente o ruído.
   Após o novo aviso sonoro, faça a segunda batida no mesmo ponto e sentido.
5. A tabela compara os valores. Pico e decaimento devem variar até **10%**,
   além de passar pelas verificações de sinal, saturação, duplo impacto e coerência.
   Havendo consistência, a duração final cobre o mais lento dos dois decaimentos
   com os mesmos 5% de margem. O trigger permanece em 50% do primeiro pico.
6. Clique em **Usar configuração confirmada**. Os parâmetros aparecem na terceira
   aba da configuração. Inicie então o ensaio; as duas batidas do assistente não
   entram nas médias de medição.

É possível repetir a segunda batida sem refazer a primeira. Tentativas rejeitadas
permanecem no diagnóstico. Alterar banda, acelerômetro de referência ou ponto
invalida a medição; clique em **Recomeçar**. Para inspeção dos registros, troque
**Última batida** por **Primeira batida** ou **Segunda batida**. O martelo bruto
do topo permanece ao vivo, independentemente do registro selecionado abaixo.

## Duração, taxa e janelas

O decaimento usa uma envoltória RMS e o nível de ruído medido, evitando que modos
fracos sejam ocultados por uma porcentagem do maior pico. É observado um trecho
quieto de pelo menos 0,25 s para confirmar o término da resposta. Esse trecho de
observação não vira uma margem adicional na duração final. Quando necessário,
a observação quieta é prolongada para cobrir também os 5% do bloco sugerido.

O tempo de observação máximo inicial é 8 s. A captura pode terminar antes desse
limite quando a resposta já terminou. Se não terminar, a interface indica a
necessidade de exponencial e pede observação mais longa para medir o decaimento;
não apresenta uma duração natural desconhecida como confirmada.

A janela de força é recomendada para remover o ruído após o contato, mantendo o
pulso inteiro na parte plana. Para resposta completamente decaída, a indicação é
retangular. A exponencial acrescenta amortecimento aparente e sua constante deve
ser considerada pela identificação modal, como no processamento compartilhado
do programa.

As regiões verdes dos gráficos temporais mostram o peso das janelas, sem
modificar a curva do sinal original. A janela de força mantém uma região plana
e fecha suavemente após o contato; a exponencial aparece como uma região
decrescente. Resposta retangular não recebe sombreamento de atenuação. Os ajustes
de janela à esquerda recalculam os espectros e a qualidade sobre os dados
preservados. Uma janela de força que atenua o contato impede a aprovação.

A taxa final é a menor opção anunciada pelo equipamento com
`fs >= 2,56 × frequência máxima desejada`. Por exemplo, uma banda até 500 Hz usa
2000 Hz quando essa opção está disponível. A margem pressupõe filtros internos
adequados. O pré-trigger mantém o início do contato e mais 20 ms de linha de base.
O bloco resulta de `N = ceil(fs × duração)`, sem arredondar para potência de dois.

Os ranges recomendados incluem margem de 40%. São orientações em unidades físicas;
o ajuste elétrico de faixa, IEPE e condicionamento permanece no Assistente LYNX.
Após alterar a configuração física, reconecte para reler os canais e repita o
assistente. Não há escrita automática de ranges no equipamento.

## PSDs e unidades

As densidades inferiores pertencem ao bloco da última batida. Usam FFT de um
lado, com normalização pela frequência de amostragem e pela energia da janela
selecionada; o ruído de base é removido antes da aplicação da janela. Não há uma
janela Hann adicional ou atualização dos espectros por ruído posterior à batida.
A aceleração e sua PSD pertencem ao mesmo canal. A visualização oferece magnitude
ou dB:

| Canal | Magnitude | Escala em dB |
| --- | --- | --- |
| Força | N²/Hz | 10 log10(PSD / 1 N²/Hz) |
| Aceleração | (m/s²)²/Hz | 10 log10(PSD / 1 (m/s²)²/Hz) |

O martelo bruto do topo mostra os últimos 5 s sem filtros ou janelas. Os gráficos
inferiores ficam estáveis até completar outra batida. A amplitude da PSD depende
do bloco e da janela selecionada; não substitui FRFs e médias do ensaio.

## Coerência como critério de configuração

Em **Função da resposta**, alterne a PSD da aceleração por **Coerência força ×
aceleração**. A coerência mantém escala linear de 0 a 1, mesmo com PSD em dB.
A linha tracejada indica o limiar selecionado.

O cálculo usa médias dos autoespectros e do espectro cruzado de duas batidas
independentes do mesmo ponto. A primeira batida é reamostrada com anti-aliasing
e ambas são alinhadas pelo trigger final e processadas com o mesmo bloco,
pré-trigger e janelas. Não são acrescentadas amostras inventadas para cobrir
blocos incompletos. Com uma única batida, a coerência fica indisponível.

O padrão requer **coerência ≥0,90 em pelo menos 80% da banda avaliável**. Esses
dois limites podem ser ajustados à esquerda. Frequências com força ou resposta
a menos de 10 dB acima do ruído são excluídas, evitando reprovar apenas por
antirressonâncias ou excitação insuficiente localizada. É necessário ter pelo
menos oito linhas espectrais e 20% da banda desejada avaliáveis.

Saturação, duplo impacto, ponto diferente, blocos incompletos ou janela de força
que corta o contato impedem a aprovação. A coerência complementa os critérios
de pico e decaimento, não os substitui. Uma inversão da resposta, por exemplo,
pode manter pico e decaimento semelhantes e reprovar pela coerência.
Com apenas duas batidas, essa avaliação é preliminar.

## Dados e validação

**Salvar diagnóstico…** exporta parâmetros, ruído e sinais originais. Ao iniciar
o ensaio com a configuração confirmada, a pasta `configuracao/` guarda o relatório
e os NPZ das duas etapas, inclusive tentativas rejeitadas. `session.json` também
registra os parâmetros e a comparação. `coerencia.npz` preserva a curva, as
frequências e a máscara de frequências avaliáveis; o relatório guarda os limites,
a mediana, a parcela aprovada e os motivos de rejeição.

Uma modificação nos parâmetros principais invalida a confirmação anterior.
Repita o assistente ou selecione **Usar configuração manual**. Desconectar obriga
a reler os canais e repetir a confirmação. Duas batidas consistentes verificam
esta configuração; não garantem excitação e observabilidade de todos os modos.

Os testes verificam navegação, atribuição e posições de canais, fluxo automático,
regra de 50%, margem de 5%, consistência, falhas de comunicação, PSDs, coerência,
regiões de janelamento e conservação
dos registros. Execute `.venv\Scripts\python.exe -m unittest discover -s tests -v`.
A conferência com ADS1800 físico continua necessária.
