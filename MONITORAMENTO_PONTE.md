# Monitoramento da ponte

Abra **iniciar_ponte.bat** para a nova interface. **iniciar.bat** continua abrindo a interface original.
As dependências estão em requirements.txt, incluindo SciPy. Use **instalar.bat**
para instalá-las no ambiente `.venv` do projeto. Opcionalmente, **instalar_ponte.bat**
cria um ambiente separado `.venv-ponte`. O inicializador dá prioridade a esse
ambiente quando existir e aceita `.venv` como alternativa. O ambiente virtual
incluído no ZIP não foi copiado, pois contém caminhos e executáveis de outra instalação.

1. Na guia **Conexão**, escolha ADS 1800 real ou Simulador e conecte.
2. Em **Configurações**, selecione os canais, a frequência de aquisição e os dados do experimento.
   A lista de frequências usa os valores existentes no programa e é atualizada pelo equipamento.
3. Opcionalmente, ative o passa-banda e informe os cortes mínimo e máximo em Hz.
   É necessário `0 < mínimo < máximo < fs/2`. Configurações ficam bloqueadas durante a aquisição.
4. Abra **Monitoramento** e clique em **Iniciar aquisição**. A gravação CSV é iniciada separadamente.
5. Alterne entre **Tempo**, **FFT**, **Espectro (PSD)** e **Todos**. Janela e atualização visual
   não alteram a frequência de aquisição. Use uma coluna para ampliar os três gráficos no modo Todos.
6. Pare antes de alterar canais, frequência ou filtro. É possível iniciar novamente sem reconectar.

Arraste a barra horizontal entre o painel da ponte e os gráficos para distribuir
a altura entre as duas áreas. O ajuste pode ser feito durante a aquisição;
os botões superiores permanecem acessíveis e a imagem acompanha o tamanho disponível.

## Medidas e processamento

- Nomes e unidades vêm do equipamento. O programa não transforma automaticamente volts em aceleração:
  configure a calibração dos acelerômetros no Assistente LYNX para obter m/s².
- O painel usa a foto da ponte enviada, com o fundo removido e transparência real em PNG.
  Os marcadores iniciais são sugestões; ajuste sua posição real em **Configurações → Posicionar sensores**.
- RMS, pico absoluto e média usam a janela temporal visível, depois do filtro quando habilitado.
- Passa-banda Butterworth causal, protótipo de ordem 4 (8 polos no passa-banda), calculado em
  seções de segunda ordem. O estado é preservado entre blocos e reiniciado em nova aquisição
  ou descontinuidade temporal. Há transiente inicial e atraso de fase; não é filtro de fase zero.
- FFT: espectro unilateral de amplitude de pico, média removida, janela Hann e normalização pelo
  ganho coerente. Unidade igual à do sensor. Resolução aproximada `fs/N`, com N amostras na janela.
- Espectro: densidade espectral de potência (PSD), método de Welch, janela Hann,
  segmentos de até 4096 amostras, sobreposição de 50%, remoção da média e unidade sensor²/Hz.
  A integral da PSD estima a variância do sinal. Não se trata de espectrograma tempo-frequência.
- Análises espectrais precisam de pelo menos oito amostras válidas consecutivas.
  Os gráficos de frequência vão de zero ao corte superior quando o passa-banda está ativo;
  sem filtro, vão até Nyquist (fs/2). Não há interpolação de amostras perdidas.
- O eixo vertical do sinal no tempo usa os limites de engenharia inferior e superior
  lidos de cada canal (incluindo os acelerômetros). Se não houver limites válidos,
  usa escala automática. FFT e PSD têm escala vertical automática própria,
  calculada sobre a faixa de frequência visível.
- Cada gráfico possui **Zoom Y +**, **−** e **Restaurar**. O botão + reduz a faixa
  vertical pela metade, ampliando o sinal; − dobra a faixa. O ajuste é independente
  por canal e por gráfico, permanece durante as atualizações e não altera as amostras
  nem o CSV. Restaurar recupera os limites do canal no tempo e a escala automática
  na FFT/PSD. Uma nova aquisição reinicia esses ajustes.
- **Limpar gráficos** apaga somente o histórico visual; mantém o tempo da sessão, o estado do
  filtro, a contagem e a gravação. Não apaga os arquivos.
- CSV mantém os dados originais nas unidades de engenharia, sem o filtro de visualização.
  Salve a configuração da ponte em JSON para registrar os cortes utilizados.
- O tempo adquirido é a contagem de amostras por canal dividida pela taxa configurada;
  não representa tempo de parede quando há perda de amostras.

## Configurações salvas

O JSON da nova interface inclui bandpass_enabled, low_cut e high_cut. Use arquivos separados
(por exemplo, ponte.json) dos arquivos usados pela interface antiga, que não conhece esses campos.
A nova interface também lê configurações antigas; nesse caso o filtro começa desativado.

## Aquisição automática e escalogramas

1. Conecte, selecione os canais e a taxa de amostragem.
2. Na aba Monitoramento, abra **Configurar trigger…** e marque **Aquisição automática**.
3. O padrão por canal é `0,10 × abs(limite superior de engenharia)` lido do equipamento.
   O valor absoluto da amostra é comparado a esse limiar: picos positivos e negativos disparam.
   O percentual é ajustável; desmarque **Usar percentual** para informar um limiar individual
   na unidade daquele canal. Uma escala superior nula ou ausente exige limiar explícito.
4. Configure **Pré-trigger** e **Duração total**, que inclui o pré-trigger. Por exemplo,
   1 s de pré-trigger e 6 s totais capturam 1 s antes e 5 s a partir do disparo.
   Os tempos são arredondados à amostra mais próxima. O instante do trigger é `t = 0`.
5. Defina as frequências mínima e máxima da Morlet, com `0 < mínima < máxima < fs/2`.
   Essa faixa é independente do filtro passa-banda do monitoramento.
6. Inicie a aquisição. O sistema primeiro preenche o histórico e aguarda um cruzamento
   de limiar. **Qualquer canal dispara todos os canais selecionados, sincronizados**.
   Para medir aceleração em g ou m/s², configure essas unidades e a calibração no ADS 1800;
   a aplicação não converte automaticamente canais configurados em V.
7. Ao concluir a captura, o sinal é salvo e a Morlet é calculada em segundo plano.
   A visualização muda para **Escalogramas**, com seleção de evento, sinal no tempo e
   um mapa tempo–frequência por canal. Os modos Tempo/FFT/PSD/Todos continuam disponíveis.

O trigger e os escalogramas usam o sinal original em unidades de engenharia, **sem o
passa-banda de visualização**. O monitoramento e o CSV contínuo mantêm seu funcionamento.
As configurações automáticas são bloqueadas durante a aquisição e entram no JSON do
experimento; arquivos antigos iniciam com o modo automático desativado.

### Rearme, continuidade e armazenamento

- Um cruzamento é a passagem de abaixo do limiar para valor absoluto maior ou igual a ele.
  Um nível sustentado não produz capturas repetidas; o canal precisa baixar e cruzar novamente.
  Outro canal pode disparar mesmo se o primeiro continuar acima de seu limiar.
- Não há capturas sobrepostas. Durante uma captura e seu cálculo, novos disparos são
  ignorados; o monitoramento continua e o histórico de pré-trigger continua sendo atualizado.
  Após exibir o resultado, o trigger é rearmado automaticamente para o próximo cruzamento.
- Lacunas temporais e amostras não finitas invalidam a captura em andamento. O histórico é
  reiniciado, sem interpolação, e a interface mostra a contagem de capturas incompletas.
  Parar uma aquisição também descarta a captura incompleta. Capturas completas continuam
  sendo processadas após Parar; fechar o aplicativo ou iniciar outra sessão cancela cálculos
  pendentes, preservando o sinal original já salvo.
- Cada sessão cria `dados/capturas/AAAAMMDD_HHMMSS_microssegundos/`. Os arquivos
  `evento_0001.npz` contêm `times` (segundos relativos ao trigger), `values`
  (canais × amostras originais) e `metadata` (JSON com horário do trigger, canais,
  taxa, limiares, nomes, unidades e limites). `configuracao.json` registra a configuração.
- `evento_0001_morlet.npz` contém `frequencies`, `times`, `power`, `analysis_rate` e `wavelet`.
  `power` armazena |CWT|² antes da normalização visual, na grade reduzida de exibição.
  Os arquivos podem ser abertos com `numpy.load(..., allow_pickle=False)`.
- A tela conserva os últimos três eventos da sessão. Todos os eventos concluídos ficam
  no disco. Falha de gravação ou de análise suspende novos disparos e exibe um erro;
  o monitoramento continua. Uma nova aquisição reinicia o estado automático.
- Limites operacionais: até 120 s e 64 MB de amostras por evento; a janela e a faixa
  precisam fornecer ao menos oito amostras para análise. A interface valida antes de iniciar.

### Método da wavelet

Usa a CWT do PyWavelets com **Morlet complexa `cmor1.5-1.0`**, largura de banda 1,5 e
frequência central 1,0. As escalas são convertidas das frequências em Hz usando o período
de amostragem. Referência: [documentação oficial da CWT](https://pywavelets.readthedocs.io/en/latest/ref/cwt.html).

A média é removida para a análise. Quando possível, somente o sinal de análise é
reamostrado com filtro antialias, mantendo taxa de pelo menos quatro vezes a frequência
máxima solicitada; as amostras salvas e o trigger mantêm a taxa original. A transformação
é calculada em 96 frequências lineares, uma frequência por vez para limitar a memória.
O mapa tem até 1200 colunas temporais, preservando a potência máxima de cada intervalo
quando há redução. Cores mostram potência relativa de 0 a 1, normalizada pelo máximo de
cada canal; não devem ser usadas para comparar amplitudes entre canais. As bordas da
janela têm maior incerteza por suporte incompleto da wavelet. Não é uma PSD calibrada.

Dependência adicional: `PyWavelets>=1.6,<2`, incluída em requirements.txt.

## Imagem da ponte e posição dos sensores

1. A imagem tratada já vem selecionada em `assets/ponte_sem_fundo.png`.
2. Para substituí-la, use **Configurações → Selecionar imagem da ponte…** (PNG ou JPG).
   O arquivo é copiado para assets; o original não é alterado. Outras fotografias são importadas
   como estão: o aplicativo não remove automaticamente o fundo das novas imagens.
3. Conecte ao equipamento ou simulador, marque os canais e clique em **Posicionar sensores…**.
4. Na janela ampliada, arraste cada círculo CH até a posição real do sensor e clique em **Salvar posições**.
   Cancelar descarta as alterações. Marcadores não movidos continuam identificados como posições sugeridas.
5. A imagem e as posições são restauradas ao abrir o programa novamente e também entram no JSON
   de **Salvar experimento**. Os dados locais ficam em `configuracoes/ponte_visual.json`.

As coordenadas são relativas à imagem e associadas ao número do canal, permanecendo alinhadas
ao redimensionar a janela e ao ocultar/reselecionar canais. Selecionar uma imagem diferente
reinicia as posições para evitar reutilizar coordenadas de outra fotografia. Para transferir
a configuração a outro computador, copie também a pasta assets. A configuração visual fica
bloqueada durante aquisição, como as demais configurações. O SciPy continua sendo utilizado.

A remoção do fundo foi feita pela ferramenta integrada de edição de imagens. A fotografia
tratada serve para identificar posições visualmente, não para extrair dimensões geométricas.
O registro da edição está em `assets/EDICAO_IMAGEM.md`.

## Validação

Execute `.venv\Scripts\python.exe -m unittest discover -s tests -v`
(ou use `.venv-ponte` se tiver escolhido o ambiente separado).
Os testes adicionais verificam FFT, energia da PSD, atenuação e continuidade do filtro,
validação dos cortes, persistência, conexão simulada, oito canais, alternância de telas,
CSV, limpeza e reinício em 1000 e 24000 Hz. O driver e o controlador de aquisição originais
não foram alterados. O funcionamento com o ADS 1800 físico precisa ser conferido em bancada.
