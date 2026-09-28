# Correcoes locais do driver LYNX

- `LDTP_Module.py`, `DataAcqSetup`: converter a quantidade de amostras por
  canal em inteiro antes da serializacao LDTP. Com frequencia float (por
  exemplo, 1000.0 Hz), a divisao `// 10` produzia 100.0 e `struct.pack`
  falhava com `required argument is not an integer`. A frequencia enviada
  permanece inalterada, inclusive para valores fracionarios.
- Cobertura: `tests/test_ldtp_setup.py` exercita o calculo e a serializacao
  reais com transporte simulado, para um, tres e oito canais.

Preservar esta correcao ao substituir os arquivos por outra versao do fabricante.

## Reinício e encerramento (setembro de 2026)

- `LDTP_Module.py`, `StartDataAcquisition`: substituir `devInd` (inexistente
  nessa função) por `i` ao reinicializar listas existentes. O defeito causava
  `NameError` a partir da segunda aquisição na mesma conexão.
- Zerar também `__syncSampCount` e `__syncSampPos` a cada início, impedindo
  que a nova aquisição exponha contagens da sessão anterior.
- `LynxDriver.py`, `StopAcq`: testar `DataConnActive[iDev]` e retornar o
  resultado combinado de parada/liberação, em vez de sempre retornar sucesso.
- Cobertura: `tests/test_ldtp_restart.py`, sem sockets reais, repetindo três
  ciclos com a mesma instância do módulo e contadores previamente preenchidos.

A pasta original `LynxPythonDriver` não foi modificada.

## Taxas de 1 Hz a 24 kHz e frequências reportadas pelo equipamento

- `LDTP_Module.py`, `DataAcqSetup`: garantir ao menos uma amostra por canal
  no pacote. As taxas documentadas de 1 e 5 Hz antes calculavam zero.
- `tests/test_ldtp_setup.py`: acrescentada cobertura de 1/5 Hz, 12/24/48 kHz,
  incluindo 8 canais, sem alterar a frequência enviada ao equipamento.

## 2026-09-28 — Limites de engenharia

Em `LynxDriverV1.__GetAnChannelConf`, LOWLIM passa a preencher `LowLim` e
HIGHLIM passa a preencher `HighLim`. As atribuições estavam invertidas.
Os coeficientes existentes agora correspondem à interpolação do Guia-Driver:
`(superior-inferior)*(x+1)/2+inferior`, para x normalizado.
`GetAllSamples()` entrega a engenharia diretamente, sem calibração adicional
no aplicativo. Teste: `tests/test_engineering.py`, com respostas de parâmetros
e amostras brutas simuladas, inclusive escala assimétrica e extrapolação.
Ainda não validado com equipamento físico.
