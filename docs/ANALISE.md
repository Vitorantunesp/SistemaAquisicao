# Análise e organização do sistema

## Estrutura

| Caminho | Responsabilidade |
| --- | --- |
| `main.py` | Entrada do aplicativo. |
| `ads1800_app/ui/app.py` | Interface PyQt6, formulários, diálogos, gráfico e atualização por QTimer. |
| `ads1800_app/controller.py` | Leitura em segundo plano e fila de gravação CSV. |
| `ads1800_app/config.py` | Experimento, canais, calibração linear e persistência JSON. |
| `ads1800_app/backends/base.py` | Contrato dos equipamentos. |
| `ads1800_app/backends/lynx.py` | Adaptação do driver LYNX ao aplicativo. |
| `ads1800_app/backends/simulator.py` | Aquisição simulada, sem rede. |
| `vendor/lynx_driver/` | Cópia do driver efetivamente importada pelo aplicativo, com correções locais documentadas. |
| `../LynxPythonDriver/` | Referência original do fabricante, exemplos e manuais; mantida sem alterações. |
| `tests/` | Testes de configuração, controlador, protocolo e interface. |
| `dados/` | Destino sugerido para arquivos CSV. |

A separação entre interface, controlador e equipamento já era adequada. Foi preservada na migração: PyQt6 não é importado pelo controlador nem pelos backends. O gráfico usa QPainter, sem dependência adicional de biblioteca de gráficos.

## Defeito ao reiniciar

Em `LDTPModule.StartDataAcquisition`, o primeiro início acrescentava posições às listas de contadores. A partir do segundo início, o ramo que reutilizava essas listas indexava-as com `devInd`, variável inexistente nessa função. Isso produz `NameError` e explica por que recriar o driver ao reconectar contornava o defeito.

A correção usa o índice `i` do laço e também reinicializa `__syncSampCount` e `__syncSampPos`. Sem isso, a contagem sincronizada da aquisição anterior podia ser exposta antes de chegarem os primeiros dados novos. Não é necessário apagar os grandes buffers: os contadores determinam os dados válidos.

Também foi corrigido `StopAcq`, que verificava a lista inteira `DataConnActive`, em vez da posição de cada equipamento. Agora só libera conexões ativas e propaga falhas de confirmação.

## Encerramento e gravação

- O controlador conserva a referência da thread se a parada ultrapassar dois segundos, impedindo que uma nova aquisição se sobreponha à antiga.
- Falhas no início tentam encerrar a aquisição parcialmente criada, preservando o erro original.
- A finalização da aquisição encerra também a gravação, inclusive quando há erro de leitura.
- A gravação sincroniza a interrupção com o produtor da fila e espera a escrita dos blocos já enfileirados. Cada arquivo recebe uma fila nova.
- Erros de escrita são encaminhados à interface e solicitam a parada da aquisição.

## Interface PyQt6

As três abas preservam conexão real/simulada, oito canais, metadados, ganho/offset, configuração JSON, relógio do equipamento, gráfico e CSV. Conectar, iniciar, parar e desconectar usam operações em segundo plano; somente a thread principal acessa os widgets. O QTimer recebe resultados e atualiza os controles. Configurações ficam bloqueadas durante aquisição e transições. Um identificador de sessão evita que blocos pendentes de uma aquisição anterior entrem no gráfico seguinte.

## Validação e limites

Os testes exercitam três ciclos na mesma instância do módulo LDTP com transporte simulado, a recuperação do controlador e três ciclos completos na interface Qt com o simulador e arquivos CSV reais. A interface também é renderizada sem uma janela visível para inspeção visual.

Não houve validação com o ADS 1800 físico. Para aceitação em bancada: conectar uma vez, realizar pelo menos três ciclos de aquisição/gravação/parada, conferir os sinais e arquivos, repetir com outros canais/frequências aceitos e verificar o modo UTC.

Pontos para evolução futura, fora desta correção:

- O driver pré-aloca 128 buffers de um milhão de valores float64, aproximadamente 1 GB. Isso merece otimização antes de expandir o uso.
- O simulador atualmente gera tempo relativo mesmo com UTC selecionado; não valida a sincronização de relógio do equipamento.
- Ganho/offset no aplicativo são calibração adicional. Configuração elétrica dos sensores continua sendo feita pelo Assistente LYNX.
- A visualização usa mínimos/máximos por faixa de pixels para preservar picos estreitos; o CSV recebe os blocos completos entregues pelo backend.
- Testes automatizados de protocolo não substituem ensaios de perda de rede, firmware e sincronização no equipamento.

## Visualização independente (24/09/2026)

`ads1800_app/ui/plots.py` concentra o buffer temporal, a redução por extremos,
os painéis por canal e o temporizador de desenho. `app.py` mantém a montagem
da aba e os controles globais. A fila de eventos é consultada a cada 20 ms;
o desenho usa um temporizador separado e ajustável de 1 a 30 Hz.
O buffer usa blocos NumPy e descarta dados pelo tempo, substituindo o antigo
limite fixo de 100000 pontos. A janela padrão é de 10 segundos e pode variar
entre 0,1 e 60 segundos. Janelas longas com muitos canais e taxas altas
consomem mais memória e processamento.

Testes cobrem retenção de 10 segundos a 24 kHz, preservação de picos, eixos
independentes, limites manuais inválidos, tempo relativo a partir de UTC,
alteração do layout e ajustes durante aquisição/gravação no simulador.

## Catálogo de sensores (24/09/2026)

- `ads1800_app/sensors.py`: perfis reutilizáveis, validação e persistência JSON
  com versão. A gravação usa substituição de arquivo temporário após validação.
- `ads1800_app/ui/sensors.py`: editor de parâmetros livres, catálogo persistente,
  importação/exportação e cálculo explícito do ganho pela sensibilidade.
- `ChannelConfig.sensor_profile`: cópia independente do cadastro, compatível
  com configurações antigas que não possuam esse campo.
- A aplicação ao canal acontece na aba de configuração, bloqueada durante
  aquisição. O perfil fica no JSON do experimento e nos metadados do CSV;
  alterações posteriores no catálogo não reescrevem a cópia do experimento.
- Testes cobrem catálogo persistente, validação sem sobrescrever dados válidos,
  importação, duplicação, campos livres, ganho de acelerômetro/martelo,
  aplicação a canal específico, recarga do experimento e metadados CSV.

## Janelas de gráficos redimensionáveis

A área de gráficos passou a usar QMdiArea e QMdiSubWindow para redimensionamento,
movimentação e maximização nativos do Qt. O fechamento de uma subjanela apenas
oculta o canal e sincroniza a caixa de seleção. O redesenho dos dados não altera
a geometria ajustada pelo operador. O botão Organizar gráficos restaura a
distribuição por colunas. Testes cobrem redimensionamento programático,
maximização, ocultação/restauração e preservação dos dados durante atualização.

## Limites e escalas

`ui/limits.py` centraliza os controles de faixa elétrica e escala do gráfico.
`ChannelConfig` preserva `input_min`, `input_max`, `input_unit`, `display_min`,
`display_max` e `display_auto`; os campos têm padrões compatíveis com JSONs
anteriores. Sinais Qt sincronizam a escala visual com cada painel sem ciclos
de atualização. O CSV registra a faixa elétrica numérica como fonte
preferencial quando definida. Os limites visuais não modificam a calibração
nem os dados gravados. Testes verificam sincronização bidirecional,
persistência, separação de unidades e importação de faixa pelo catálogo.
