# Sistema de aquisicao LYNX ADS 1800

Aplicativo desktop em Python para conectar ao ADS 1800, configurar os oito canais analogicos, visualizar sinais em tempo real e gravar os resultados em CSV.

## Primeira instalacao

1. Instale o Python 3.11 ou mais recente para Windows, marcando a opcao de adiciona-lo ao PATH.
2. Execute `instalar.bat` uma vez.
3. Depois, abra o programa com `iniciar.bat`.

O projeto inclui uma copia dos modulos Python fornecidos pela LYNX em `vendor/lynx_driver`. O driver usa comunicacao LDTP direta pela rede e requer apenas o pacote `numpy`.

## Uso

1. Na aba **Conexao**, escolha `ADS 1800 real`, informe o IP e conecte. O endereco padrao documentado pela LYNX e `192.168.1.180`.
2. Na aba **Canais e experimento**, selecione os canais e informe tipo de sensor, nome, unidade, ganho e offset. O valor salvo e `valor_recebido * ganho + offset`.
3. Escolha uma frequencia aceita pelo equipamento. Depois da conexao, a lista e substituida pelas frequencias informadas pelo proprio ADS 1800.
4. Na aba **Visualizacao e gravacao**, inicie a aquisicao e, quando desejar, a gravacao CSV.

O modo **Simulador** permite testar todo o fluxo sem o hardware.

## Configuracao fisica dos sensores

Faixa eletrica, excitacao, ponte, IEPE e demais parametros internos devem ser configurados e salvos previamente no ADS 1800 pelo ADS1800Assistant/Lynx@Net. O driver Python fornecido le do equipamento o nome, a unidade e os limites ja gravados. Os campos deste aplicativo registram metadados do experimento e aplicam uma calibracao linear adicional.

## CSV

O arquivo usa `;` como separador e UTF-8 com BOM, facilitando a abertura no Excel em configuracoes brasileiras. As primeiras linhas guardam nome, operador, descricao, horario e frequencia; depois vem uma coluna de tempo e uma por canal.

## Testes

Com o ambiente instalado:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Observacoes de rede

- O computador e o ADS 1800 precisam ter rota entre si, normalmente na mesma sub-rede.
- O protocolo usa a porta UDP 44001 e portas de dados negociadas pelo equipamento; o firewall do Windows pode pedir liberacao.
- A leitura e feita a cada 20 ms, dentro da recomendacao do exemplo do fabricante de consultar as amostras em intervalos menores que 100 ms.

## Interface e manutenção

A interface utiliza **PyQt6**. Em instalações anteriores, execute novamente
`instalar.bat` para instalar a nova dependência; depois use `iniciar.bat`.
A instalação segue a distribuição oficial de [PyQt6 pela Riverbank](https://www.riverbankcomputing.com/software/pyqt/download).

A aquisição pode ser iniciada e parada repetidamente na mesma conexão.
A configuração fica bloqueada enquanto uma aquisição está ativa ou encerrando.
Aguarde a finalização da gravação antes de iniciar outro ciclo.

Consulte [a análise da arquitetura e da correção](docs/ANALISE.md) e o
[registro das alterações locais no driver](vendor/lynx_driver/LOCAL_CHANGES.md).
Os testes de interface usam Qt em modo offscreen e não precisam do equipamento.

## Frequências de aquisição

O ADS 1800 padrão suporta até **24000 Hz por canal**, conforme o manual rev. 13,
páginas 6 e 16–17. A lista inicial e o simulador incluem as taxas documentadas:
1, 5, 25, 50, 100, 200, 250, 400, 500, 800, 1000, 2000, 4000, 8000, 12000 e 24000 Hz.

Ao conectar, a lista passa a usar integralmente `GetAvailableSampFreq()` do
aparelho, e a interface exibe o máximo informado. Não há teto fixo de 8 ou
24 kHz aplicado às frequências reportadas: variantes com taxas superiores
podem utilizá-las se anunciadas pelo equipamento. Valores digitados fora da
lista reportada são rejeitados antes de enviar a configuração de aquisição.

Selecione `24000` no campo **Frequência (Hz)** para adquirir a 24 kHz.
A taxa selecionada é por canal; não deve ser dividida pelo número de canais.
A validação automatizada inclui CSV e reinícios a 24 kHz no simulador e
serialização LDTP a 24/48 kHz. O desempenho com o hardware físico depende
da comunicação e do computador e precisa de validação em bancada.

## Controles de visualização

Cada canal habilitado aparece em um gráfico independente, com nome e unidade.
Use **Gráficos** para escolher uma ou duas colunas; a área permite rolagem
quando há muitos canais.

- **Janela horizontal:** de 0,1 a 60 segundos, acompanhando os dados mais recentes.
  A duração independe da frequência de aquisição. Ao aumentar a janela, o
  histórico já descartado não volta; o espaço será preenchido com novos dados.
- **Atualização visual:** de 1 a 30 Hz (padrão: 10 Hz). Controla o redesenho
  dos gráficos, sem modificar a taxa de aquisição ou os dados gravados no CSV.
  A taxa efetiva depende do computador e da chegada de novos dados.
- **Y automático:** ajusta separadamente a escala vertical de cada canal.
  Desmarque para definir **Mín.** e **Máx.**, nas unidades daquele canal.
  Limites inválidos mantêm a última escala válida e exibem uma mensagem.

Esses controles podem ser alterados durante a aquisição. Os gráficos mostram
segundos desde a primeira amostra da sessão, inclusive quando o equipamento
fornece timestamps UTC; os timestamps originais continuam no CSV.
A redução de pontos para desenhar preserva mínimos e máximos, evitando ocultar
picos estreitos por simples salto de amostras.

### Mostrar/ocultar canais e acompanhar em tempo real

Após iniciar, use as caixas em **Mostrar gráficos** para exibir ou ocultar
qualquer canal adquirido. A grade reorganiza os gráficos visíveis. A escolha
é mantida entre aquisições enquanto o programa permanecer aberto.
Ocultar um gráfico não desabilita o canal, não altera o CSV e não apaga
seus dados da janela temporal. Ao reexibi-lo, aparecem os dados atuais e a
escala vertical escolhida permanece durante a sessão.

O eixo horizontal acompanha a última amostra recebida, na frequência de
atualização visual escolhida, desde o primeiro bloco. A indicação **Última
amostra** permite observar seu avanço. No início, a região anterior a zero
fica vazia até que haja dados suficientes para preencher a janela. Ao parar
a aquisição ou deixar de receber dados, os gráficos preservam a última
amostra; o programa não inventa sinais durante a ausência de dados.

## Catálogo de acelerômetros e martelos

Na aba **Canais e experimento**:

1. Abra **Catálogo de sensores...** e clique em **Novo**.
2. Preencha nome, tipo (acelerômetro, martelo de impacto ou texto livre),
   fabricante, modelo, série, sensibilidade e sua unidade, unidade de saída,
   ganho, offset e observações.
3. Em **Parâmetros adicionais**, adicione livremente pares de nome e valor:
   massa, faixa de medição, frequência de ressonância, IEPE, ponta do martelo,
   data de calibração, certificado etc.
4. Clique em **Salvar**. O cadastro persiste em `configuracoes/sensores.json`,
   dentro do projeto, e pode ser editado, duplicado ou excluído no catálogo.
5. Feche o catálogo, selecione o sensor na lista e o canal de destino e clique
   em **Aplicar ao canal**. O estado da caixa **Usar** é mantido; marque-a para
   adquirir aquele canal. Nome, tipo, unidade, ganho, offset, observações e
   uma cópia integral dos parâmetros passam para o canal.
6. **Salvar configuração...** preserva também essa cópia do sensor no JSON do
   experimento. Editar o catálogo depois não modifica experimentos anteriores.
   Para atualizar um canal, aplique novamente o cadastro desejado.

**Importar lista JSON...** adiciona registros de um catálogo exportado pelo
programa sem substituir os já existentes. Importações repetidas criam cópias.
**Exportar lista JSON...** permite compartilhar a lista com outro operador.
O formato é um objeto com `version: 1` e `sensors`, uma lista de registros;
os campos livres ficam no objeto `parameters` de cada registro.

### Sensibilidade e conversão

A conversão numérica continua sendo `valor recebido × ganho + offset`.
A sensibilidade cadastrada não altera o ganho automaticamente. Use
**Calcular ganho pela sensibilidade...** para preenchê-lo explicitamente,
indicando se o driver entrega os valores em V ou mV. A unidade de sensibilidade
precisa corresponder à saída, por exemplo `mV/g` para saída `g` ou `mV/N` para
saída `N`. Por exemplo, 100 mV/g com entrada em V resulta em ganho 10 g/V;
2,5 mV/N com entrada em V resulta em ganho 400 N/V. O offset continua editável.

O driver LYNX já entrega valores escalados conforme o equipamento. Se eles já
estiverem em g, m/s² ou N, não aplique novamente a conversão de tensão por
sensibilidade: defina o ganho adicional apropriado (1 quando não houver outra
conversão). Os demais parâmetros são metadados; IEPE, excitação e faixas
elétricas continuam sendo configurados pelo Assistente LYNX.

O CSV inclui linhas `Sensor_canal` com o cadastro aplicado e `Calibracao_canal`
com o ganho, offset e unidade efetivamente usados. Configurações antigas sem
catálogo continuam sendo aceitas.

### Redimensionar gráficos com o mouse

Cada gráfico é uma janela interna da aba de visualização:

- Arraste as bordas ou os cantos para aumentar ou diminuir largura e altura.
- Arraste a barra de título para mover a janela dentro da área de gráficos.
- Use o botão de maximizar ou dê duplo clique no título para ampliar/restaurar.
- Clique em **Organizar gráficos** para distribuir novamente em uma ou duas
  colunas. Alterar o número de colunas ou a seleção de canais também reorganiza.
- O **X** da janela apenas oculta o gráfico; marque novamente seu canal em
  **Mostrar gráficos** para restaurá-lo, sem interromper aquisição ou CSV.

As dimensões manuais são mantidas enquanto os dados chegam. Redimensionar a
janela muda apenas o espaço ocupado pelo gráfico, sem alterar a janela de
tempo, a escala vertical ou a frequência de aquisição.

### Leitura numérica em tempo real

Acima de cada gráfico aparece o valor da **última amostra recebida**, com
seis algarismos significativos e a unidade configurada (por exemplo g, m/s²
ou N). O indicador já considera o ganho e offset do canal e informa o instante
da amostra. Ele acompanha a atualização visual selecionada entre 1 e 30 Hz.
Não representa média, RMS ou pico; o CSV continua recebendo todas as amostras.
Antes de receber dados mostra um traço; amostras não finitas mostram
**Inválido**. Ao parar, a última leitura permanece com seu instante; ao iniciar
outra aquisição, o indicador é reinicializado.

### Tipo e escala de entrada

O catálogo e a tabela de canais possuem campos próprios para **Tipo de entrada
elétrica** (tensão, IEPE/CCP, corrente etc.) e **Escala de entrada**, com unidade
(ex.: ±10 V, ±100 mV). Os campos são editáveis e copiados ao aplicar o sensor,
persistidos no JSON do experimento e registrados como `Entrada_canal` no CSV.
Eles documentam a configuração: não alteram a faixa elétrica nem habilitam
IEPE no hardware. Essas operações continuam sendo feitas no Assistente LYNX.

A aplicação da sensibilidade já está disponível por **Calcular ganho pela
sensibilidade...**, seguida de **Salvar** e **Aplicar ao canal**. O ganho
resultante é utilizado no gráfico, no indicador numérico e nas amostras CSV.
Alterar apenas o número cadastrado em Sensibilidade não recalcula o ganho;
é necessário usar o botão para recalcular quando a sensibilidade mudar.

A atualização visual não é igual à taxa de amostragem. A tela é redesenhada
de 1 a 30 vezes por segundo e recebe blocos de amostras; a aquisição e a
 gravação mantêm a frequência selecionada (por exemplo, 24000 amostras/s por
canal). O gráfico representa a janela temporal com redução por extremos,
e o indicador numérico mostra a última amostra de cada atualização. Igualar
redesenhos de tela a 24 kHz não é uma capacidade oferecida pelo aplicativo.

## Aba Limites e escalas

A aba **3. Limites e escalas** centraliza dois grupos independentes:

- **Faixa elétrica de entrada:** marque **Definir faixa** e informe mínimo,
  máximo e unidade elétrica (V, mV, mA etc.). O resumo **Escala de entrada** na
  tabela de canais é atualizado automaticamente. O catálogo também aceita
  mínimo, máximo e unidade elétrica, copiados ao aplicar o sensor. Esta faixa
  é um registro; a programação física continua pelo Assistente LYNX.
- **Limites do gráfico:** na unidade calibrada do canal (g, m/s², N etc.),
  desmarque **Y automático** para definir mínimo e máximo. As alterações são
  sincronizadas nos dois sentidos com os controles da janela do gráfico e
  podem ser feitas durante a aquisição. A faixa elétrica fica bloqueada
  durante a aquisição, assim como as demais configurações de entrada.

**Salvar configuração...** nessa aba preserva ambos os grupos no JSON do
experimento. Limites manuais também são restaurados no próximo início.
Os valores devem ser finitos e mínimo deve ser menor que máximo. Esses
controles não saturam, recortam nem recalibram amostras ou CSV.

Configurações anteriores continuam válidas: sem campos numéricos de entrada,
a descrição textual antiga é preservada sem adivinhar unidades/limites.
Para unificar um cadastro antigo, preencha a faixa numérica explicitamente.
