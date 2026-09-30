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
  Os gráficos de frequência vão de zero a Nyquist. Não há interpolação de amostras perdidas.
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
