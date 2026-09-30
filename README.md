# Sistema de aquisicao LYNX ADS 1800

Aplicativo desktop em Python para conectar ao ADS 1800, selecionar os canais analogicos, visualizar sinais em tempo real e gravar os resultados em CSV.

## Primeira instalacao

1. Instale o Python 3.11 ou mais recente para Windows, marcando a opcao de adiciona-lo ao PATH.
2. Execute `instalar.bat` uma vez.
3. Depois, abra o programa com `iniciar.bat`.

O projeto inclui uma copia dos modulos Python fornecidos pela LYNX em `vendor/lynx_driver`. O driver usa comunicacao LDTP direta pela rede e requer apenas o pacote `numpy`.

## Uso

A interface de monitoramento da ponte foi incorporada de `MonitorPonte.zip`.
Abra **iniciar_ponte.bat** (ou execute `monitorar_ponte.py` no PyCharm) para
usar a imagem da ponte, posicionar sensores, aplicar o passa-banda e consultar
FFT, PSD, RMS, pico e média. Instale as dependências com `instalar.bat` se necessário.
**iniciar.bat** e `main.py` continuam abrindo a interface de aquisição original.
Veja [as instruções do monitoramento](MONITORAMENTO_PONTE.md).

O monitoramento inclui **Aquisição automática**: configure o trigger, pré-trigger,
duração total e frequências em **Configurar trigger…**. Qualquer canal dispara uma
captura conjunta; ao final, aparecem os escalogramas Morlet complexa. Capturas são
salvas automaticamente em `dados/capturas/`. O PyWavelets foi adicionado às dependências.

1. Na aba **Conexao**, escolha `ADS 1800 real`, informe o IP e conecte. O endereco padrao documentado pela LYNX e `192.168.1.180`.
2. Na aba **Canais e experimento**, marque os canais que serão lidos. Nomes, unidades e limites vêm do equipamento; passe o mouse sobre a caixa para consultar os limites.
3. Escolha uma frequencia aceita pelo equipamento. Depois da conexao, a lista e substituida pelas frequencias informadas pelo proprio ADS 1800.
4. Na aba **Visualizacao e gravacao**, inicie a aquisicao e, quando desejar, a gravacao CSV.

O modo **Simulador** permite testar todo o fluxo sem o hardware.

## Configuracao fisica dos sensores

Faixa eletrica, excitacao, ponte, IEPE e demais parametros internos devem ser configurados e salvos previamente no ADS 1800 pelo ADS1800Assistant/Lynx@Net. O driver Python fornecido le do equipamento o nome, a unidade e os limites ja gravados. O aplicativo usa esses dados sem aplicar ganho ou offset adicionais. Após alterar a configuração no Assistente, desconecte e conecte novamente para reler os parâmetros.

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

## Conversão para unidades de engenharia

Ao conectar, o driver consulta nome (1901), unidade (1902), limite inferior
(1921) e limite superior (1922) dos canais analógicos. Esses parâmetros são
lidos pela conexão de comandos, antes da aquisição; não são deduzidos da
amplitude observada no gráfico.

Conforme o Guia-Driver, para a amostra normalizada `x` na faixa nominal [-1, 1]:

`engenharia = (superior - inferior) * (x + 1) / 2 + inferior`

No driver Python, a amostra recebida é um inteiro com sinal. A faixa nominal
total é `R = LDTP_ANIN_RANGE_NOT_OVERRANGE = 3932160000`, com `x = 2 * bruto / R`.
A forma equivalente aplicada por `GetAllSamples()` é:

`engenharia = bruto * (superior - inferior) / R + (superior + inferior) / 2`

A cópia local do driver foi corrigida: a resposta de LOWLIM era atribuída a
HighLim e a de HIGHLIM a LowLim, invertendo o sentido da conversão. O diretório
original do fabricante permanece preservado. Testes usam respostas LDTP
simuladas e verificam os extremos, o ponto médio e valores fora da faixa nominal,
sem recortar as amostras. A validação física ainda deve ser feita em bancada.

Gráficos, indicadores e CSV recebem os mesmos valores de engenharia, com uma
única conversão. Para obter g, m/s² ou N, a escala e a unidade correspondentes
devem estar configuradas no equipamento. Se ele informar V, a leitura será em V.
O CSV registra `Limites_engenharia_canal` com canal, inferior, superior e unidade.

A configuração manual dos canais, o catálogo e a aba de limites foram retirados
da interface. Os arquivos antigos do catálogo permanecem preservados. Ao carregar
um experimento antigo, somente seleção dos canais, preferências do gráfico e dados
do experimento são restaurados; os parâmetros de calibração antigos são ignorados.
Os controles Mín./Máx. em cada gráfico alteram apenas a escala visual.

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
ou N). O indicador usa a conversão pelos limites do equipamento e informa o instante
da amostra. Ele acompanha a atualização visual selecionada entre 1 e 30 Hz.
Não representa média, RMS ou pico; o CSV continua recebendo todas as amostras.
Antes de receber dados mostra um traço; amostras não finitas mostram
**Inválido**. Ao parar, a última leitura permanece com seu instante; ao iniciar
outra aquisição, o indicador é reinicializado.

