"""Adapter for sdypy-EMA 0.31: LSCF poles, LSFD constants, MAC and stabilization.

The acquired quantity is accelerance. For an exponential common window,
divide H(alpha+iw) by (alpha+iw)^2 to identify the shifted receptance;
physical poles are obtained by adding alpha to the identified pole.
"""
from dataclasses import asdict
from importlib.metadata import version
import warnings

import numpy as np

from ads1800_app.modal_post import (PostSettings, StabilitySettings, classify_stability,
                                  suggest_modes, usable)


def _library():
    try:
        from sdypy import EMA
        return EMA
    except ImportError as exc:
        raise ValueError('Instale as dependências com instalar.bat para usar sdypy-EMA.') from exc


def _shape(constants, names):
    values = np.asarray(constants, complex)
    pivot = values[np.argmax(abs(values))]
    if not np.isfinite(values).all() or abs(pivot) < 1e-30:
        raise ValueError('Constante modal nula ou inválida.')
    values = values/pivot
    return ({name: float(v.real) for name, v in zip(names, values)},
            {name: float(v.imag) for name, v in zip(names, values)})


def _constants(model, selection):
    model.pole_ind = np.asarray(selection, dtype=int)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        return model.get_constants(method='lsfd', f_lower=model.lower, f_upper=model.freq[-1])


def identify_ema(data, settings, seeds=None, order=20, stability=None):
    """Identify all orders, reconstruct provisional shapes and select repeated poles.

    Coherence gates eligibility of points/poles and error metrics, not the uniform
    LSCF grid. Small missing spectral holes (<=2 bins, <=5%) are interpolated and
    reported; missing values outside the analysis band are never fitted.
    """
    EMA = _library()
    settings.validate(float(data.frequency[-1]))
    stability = stability or StabilitySettings()
    stability.validate()
    if not isinstance(order, int) or not 3 <= order <= 60:
        raise ValueError('Use limite de ordem LSCF entre 3 e 60 (ordem dinâmica máxima 6 a 120).')
    freq = np.asarray(data.frequency, float)
    df = float(np.median(np.diff(freq)))
    if freq[0] != 0 or not np.allclose(np.diff(freq), df, rtol=1e-5, atol=1e-9):
        raise ValueError('LSCF requer frequências uniformemente espaçadas a partir de zero.')
    band = (freq >= settings.fmin) & (freq <= settings.fmax)
    indices = np.flatnonzero(band)
    if len(indices) < max(32, 2*order+3):
        raise ValueError('Faixa/resolução insuficiente para a ordem LSCF; reduza a ordem ou amplie a faixa.')
    end = int(indices[-1])
    # Model truncates its last supplied bin; append one guard bin deliberately.
    model_freq = np.arange(end+2)*df
    models, active, notes = [], [], list(data.warnings)
    valid = usable(data, settings)
    for i, name in enumerate(data.point_ids):
        if valid[i, indices].sum() < max(20, len(indices)*.1):
            notes.append(f'{name}: excluído do LSCF por poucos bins com coerência válida.')
            continue
        h = data.frfs[i, indices].copy()
        finite = np.isfinite(h)
        gaps = np.diff(np.flatnonzero(np.r_[True, finite, True]))-1
        if not finite[0] or not finite[-1] or (~finite).mean() > .05 or gaps.max(initial=0) > 2:
            notes.append(f'{name}: excluído por lacunas espectrais; ajuste a faixa.')
            continue
        if not finite.all():
            h[~finite] = np.interp(indices[~finite], indices[finite], h[finite].real)+1j*np.interp(indices[~finite], indices[finite], h[finite].imag)
            notes.append(f'{name}: {int((~finite).sum())} bins interpolados na malha LSCF.')
        full = np.zeros(len(model_freq), complex)
        full[indices] = h/(data.alpha+2j*np.pi*freq[indices])**2
        models.append(full)
        active.append(i)
    if not active:
        raise ValueError('Nenhuma FRF adequada ao LSCF. Confira faixa, coerência e repetição das batidas.')
    names = [data.point_ids[i] for i in active]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        model = EMA.Model(np.asarray(models), model_freq, lower=float(freq[indices[0]]),
                          upper=float(model_freq[-1]), pol_order_high=order, frf_form='receptance')
        try:
            model.get_poles(method='lscf', show_progress=False)
        except (np.linalg.LinAlgError, IndexError) as exc:
            raise ValueError('LSCF mal condicionado. Reduza a ordem, confira a faixa ou selecione outros registros.') from exc
    notes.extend(str(w.message) for w in caught if not issubclass(w.category, DeprecationWarning))
    notes.append('Coerência filtra pontos, elegibilidade dos polos e erro; LSCF/LSFD usam a malha uniforme completa da faixa.')
    orders, previous = [], []
    all_modes = []
    for order_index, poles in enumerate(model.all_poles):
        selected, modes = [], []
        for pole_index, shifted in enumerate(poles):
            physical = shifted+data.alpha
            fn = abs(physical)/(2*np.pi)
            damping = -physical.real/max(abs(physical), 1e-30)
            if not np.isfinite(physical) or physical.imag <= 0 or not settings.fmin < fn < settings.fmax or not 0 < damping < .3:
                continue
            nearest = int(np.argmin(abs(freq-fn)))
            if not valid[active, nearest].any():
                continue
            selected.append([order_index, pole_index])
            modes.append({'frequency_hz': float(fn), 'damping_ratio': float(damping),
                          'damped_frequency_hz': float(physical.imag/(2*np.pi)),
                          'pole_order_index': order_index, 'pole_index': pole_index,
                          'pole_real_per_s': float(physical.real), 'pole_imag_per_s': float(physical.imag),
                          'warnings': ['Amortecimento pouco resolvido (<2 bins).'] if 2*damping*fn < 2*df else []})
        row = {'order': 2*(order_index+1), 'requested_modes': order_index+1, 'modes': [], 'error': None}
        if selected:
            try:
                _, constants = _constants(model, selected)
                for j, mode in enumerate(modes):
                    mode['shape'], mode['shape_imag'] = _shape(constants[:, j], names)
                modes = classify_stability(modes, previous, stability)
                row['modes'] = modes
            except (ValueError, np.linalg.LinAlgError) as exc:
                row['error'] = str(exc)
                modes = []
        previous = modes
        orders.append(row)
        all_modes.extend(modes)
    diagram = {'method': 'sdypy-EMA LSCF, ordens dinâmicas 2 a 2×limite; MAC de formas complexas LSFD',
               'settings': dict(asdict(stability), polynomial_order=order), 'orders': orders,
               'interpretation': 'Estabilidade entre ordens adjacentes é um indicativo, não uma certificação física.'}
    candidates = suggest_modes(data, settings) if seeds is None else list(seeds)
    if not np.isfinite(candidates).all() or any(not settings.fmin < f < settings.fmax for f in candidates):
        raise ValueError('Frequências candidatas devem estar dentro da faixa do ajuste.')
    selection = []
    selected_frequencies = []
    for seed in candidates:
        nearby = [m for m in all_modes if abs(m['frequency_hz']-seed) <= max(3*df, seed*.05)]
        repeated = [m for m in nearby if m['stability'] in ('estavel', 'frequencia_amortecimento')]
        pool = repeated or (nearby if seeds is not None else [])
        if not pool:
            notes.append(f'Candidato {seed:g} Hz: sem polo repetível próximo; revise o diagrama.')
            continue
        chosen = min(pool, key=lambda m: (abs(m['frequency_hz']-seed)/max(seed, df), -m['pole_order_index']))
        key = [chosen['pole_order_index'], chosen['pole_index']]
        if key not in selection:
            if any(abs(chosen['frequency_hz']-f) < df for f in selected_frequencies):
                notes.append(f'Candidato {seed:g} Hz: polo já representado dentro da resolução; revise o diagrama.')
                continue
            selection.append(key)
            selected_frequencies.append(chosen['frequency_hz'])
        if not repeated:
            notes.append(f'{seed:g} Hz: polo manual sem estabilidade de frequência/amortecimento.')
    context = {'model': model, 'data': data, 'settings': settings, 'active': active,
               'notes': list(dict.fromkeys(notes)), 'diagram': diagram, 'candidates': candidates}
    if not selection:
        return _base_result(context, [], np.full((len(active), len(model.freq)), np.nan, complex), [])
    return reconstruct_ema(context, selection)


def _base_result(context, modes, fitted, selection):
    data, model, settings = context['data'], context['model'], context['settings']
    active = context['active']
    size = len(model.freq)
    errors = {}
    for j, i in enumerate(active):
        mask = usable(data, settings)[i, :size] & np.isfinite(fitted[j])
        errors[data.point_ids[i]] = float(np.linalg.norm((fitted[j]-data.frfs[i, :size])[mask])/
                                         max(np.linalg.norm(data.frfs[i, :size][mask]), 1e-30)) if mask.any() else None
    notes = list(context['notes'])
    if not modes:
        notes.append('Nenhum modo selecionado automaticamente. Selecione polos no diagrama e aplique a seleção.')
    elif any(v is not None and v > .2 for v in errors.values()):
        notes.append('Erro complexo de reconstrução acima de 20%: reveja os polos e a faixa.')
    return {'method': 'sdypy-EMA LSCF + LSFD (receptância deslocada; saída em acelerância)',
            'library': {'name': 'sdypy-EMA', 'version': version('sdypy-EMA')},
            'settings': asdict(settings), 'alpha_per_s': data.alpha,
            'frequency_resolution_hz': float(np.median(np.diff(data.frequency))),
            'initial_frequencies_hz': list(context['candidates']), 'modes': modes,
            'point_ids': [data.point_ids[i] for i in active], 'relative_fit_error': errors,
            'warnings': notes, 'source_records': data.source_records, 'frequency': model.freq,
            'measured': data.frfs[active, :size], 'coherence': data.coherence[active, :size],
            'fitted': fitted, 'stabilization': context['diagram'], 'selected_poles': selection,
            '_ema_context': context}


def reconstruct_ema(context, selection):
    EMA = _library()
    model, data = context['model'], context['data']
    allowed = {(m['pole_order_index'], m['pole_index']): m for row in context['diagram']['orders'] for m in row['modes']}
    if not selection or len(selection) > 12 or len(set(map(tuple, selection))) != len(selection):
        raise ValueError('Selecione de 1 a 12 polos distintos.')
    if any(tuple(key) not in allowed for key in selection):
        raise ValueError('Polo selecionado não está no diagrama válido.')
    selection = sorted(selection, key=lambda key: allowed[tuple(key)]['frequency_hz'])
    frequencies = [allowed[tuple(key)]['frequency_hz'] for key in selection]
    df = float(np.median(np.diff(data.frequency)))
    if len(frequencies) > 1 and np.any(np.diff(frequencies) < df):
        raise ValueError('Selecione uma ocorrência por modo; polos separados por menos de um bin são ambíguos.')
    reconstructed, constants = _constants(model, selection)
    if not np.isfinite(constants).all():
        raise ValueError('LSFD retornou constantes inválidas. Revise os polos.')
    fitted = reconstructed*(data.alpha+2j*np.pi*model.freq)**2
    names = [data.point_ids[i] for i in context['active']]
    modes = []
    for j, key in enumerate(selection):
        mode = dict(allowed[tuple(key)])
        mode['shape'], mode['shape_imag'] = _shape(constants[:, j], names)
        normal = EMA.normal_modes.complex_to_normal_mode(constants[:, j]).ravel()
        normal /= normal[np.argmax(abs(normal))]
        mode['normal_shape'] = dict(zip(names, map(float, normal)))
        mode['modal_constants_real'] = dict(zip(names, map(float, constants[:, j].real)))
        mode['modal_constants_imag'] = dict(zip(names, map(float, constants[:, j].imag)))
        modes.append(mode)
    result = _base_result(context, modes, fitted, selection)
    with warnings.catch_warnings():
        # sdypy 0.31 stores a mathematically real MAC in a real matrix.
        warnings.filterwarnings('ignore', message='Casting complex values to real discards the imaginary part', category=np.exceptions.ComplexWarning)
        result['auto_mac'] = np.atleast_2d(EMA.MAC(constants, constants)).tolist()
    return result
