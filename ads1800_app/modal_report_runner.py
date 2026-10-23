"""Run report rendering outside the acquisition/Qt process."""
from dataclasses import asdict
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

import numpy as np


def generate_report_isolated(session, result, path, identification='MISO', reference=0):
    destination = Path(path).resolve()
    if not destination.parent.is_dir():
        raise ValueError('A pasta de destino do relatório não existe. Escolha outra pasta.')
    arrays = ('frequency', 'measured', 'fitted', 'coherence')
    metadata = {k: v for k, v in result.items() if not k.startswith('_') and k not in arrays}
    payload = dict(config=asdict(session.config), metadata=session.metadata, records=session.records,
                   directory=str(session.directory.resolve()), result=metadata,
                   identification=identification, reference=reference, destination=str(destination))
    with tempfile.TemporaryDirectory(prefix='modal_report_') as folder:
        root = Path(folder)
        (root/'request.json').write_text(json.dumps(payload, ensure_ascii=False,
            default=lambda value: value.item() if isinstance(value, np.generic) else value.tolist()), encoding='utf-8')
        np.savez_compressed(root/'spectra.npz', **{k: result[k] for k in arrays})
        env = dict(os.environ, MPLBACKEND='Agg', MPLCONFIGDIR=str(root/'matplotlib'), PYTHONIOENCODING='utf-8')
        try:
            process = subprocess.run([sys.executable, '-X', 'faulthandler', '-m',
                'ads1800_app.modal_report_worker', str(root)], cwd=Path(__file__).resolve().parent.parent,
                env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('A geração do relatório excedeu 3 minutos. Tente novamente com menos modos.') from exc
        if process.returncode != 0:
            detail = (process.stderr or process.stdout or 'O processo de figuras foi interrompido.')[-5000:]
            raise RuntimeError(f'Não foi possível gerar o relatório (código {process.returncode}). '
                               'O ensaio e os resultados permanecem abertos. Confira se o projeto foi atualizado '
                               'por completo e execute instalar.bat para atualizar as dependências.\n\n'+detail)
        if not destination.is_file():
            raise RuntimeError('A geração terminou sem criar o relatório. Escolha outra pasta e tente novamente.')
    return destination
