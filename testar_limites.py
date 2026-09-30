"""Consulta somente a configuracao dos limites; nao inicia aquisicao."""
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor' / 'lynx_driver'))
import LDTP_Const
import LDTP_Module
import LynxDriver


def ler_limites(ip):
    driver = LynxDriver.LynxDriverV1()
    try:
        if not driver.ConnectTo(ip):
            raise RuntimeError(f'Nao foi possivel conectar a {ip}.')

        quantidade = driver.Module.GetDevInfo(0).NumAnInCh
        limites = {}
        for numero in (LDTP_Const.LDTP_PARAM_ANIN_LOWLIM,
                       LDTP_Const.LDTP_PARAM_ANIN_HIGHLIM):
            parametro = LDTP_Module.Param_Data()
            parametro.ParamNum = numero
            parametro.Size = 4
            parametro.IndexI = parametro.IndexJ = 0
            parametro.CountI = quantidade
            parametro.CountJ = 1
            # Uma consulta por parametro, como nos exemplos internos do driver.
            sucesso, resposta = driver.Module.RequestParam(0, [parametro])
            if not sucesso or not resposta or resposta[0].ParamNum != numero:
                raise RuntimeError(f'Falha ao consultar o parametro {numero}.')
            # Reinterpreta os bits recebidos como float32.
            limites[numero] = [struct.unpack('<f', struct.pack('<I', v))[0]
                               for v in resposta[0].Values]

        inferior = limites[LDTP_Const.LDTP_PARAM_ANIN_LOWLIM]
        superior = limites[LDTP_Const.LDTP_PARAM_ANIN_HIGHLIM]
        if len(inferior) != quantidade or len(superior) != quantidade:
            raise RuntimeError('Resposta incompleta do equipamento.')
        return list(zip(inferior, superior))
    finally:
        # Fecha tambem os recursos de uma tentativa de conexao incompleta.
        driver.Module.CloseConnection(0)


if __name__ == '__main__':
    ip = sys.argv[1] if len(sys.argv) > 1 else '192.168.1.180'
    try:
        for canal, (inferior, superior) in enumerate(ler_limites(ip), start=1):
            print(f'Canal {canal}: inferior = {inferior:g}; superior = {superior:g}')
    except Exception as erro:
        sys.exit(f'Erro: {erro}')
