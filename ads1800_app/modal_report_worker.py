"""Private subprocess entry point. Receives only snapshots made by the app."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys

import numpy as np


def main():
    from ads1800_app.modal import ModalConfig
    from ads1800_app.modal_report import generate_report
    root = Path(sys.argv[1])
    payload = json.loads((root/'request.json').read_text(encoding='utf-8'))
    result = payload['result']
    with np.load(root/'spectra.npz', allow_pickle=False) as spectra:
        result.update({k: spectra[k] for k in spectra.files})
    session = SimpleNamespace(config=ModalConfig.from_dict(payload['config']), metadata=payload['metadata'],
                              records=payload['records'], directory=Path(payload['directory']))
    generate_report(session, result, payload['destination'], payload['identification'], payload['reference'])


if __name__ == '__main__':
    main()
