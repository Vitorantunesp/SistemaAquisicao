"""Shared-pole, real-mode accelerance fitting for reciprocal roving-hammer tests.

H(s) = sum(r_j*s²/(s²+2*zeta_j*wn_j*s+wn_j²)) + c0 + c2*(s/2pi)².
The same exponential applied to both signals evaluates H at s=alpha+i*w;
fitting there estimates physical rather than window-broadened damping.
"""
from dataclasses import asdict, dataclass, replace
import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares, linear_sum_assignment
from scipy.signal import find_peaks

from ads1800_app.modal import ensemble, processed_signals


@dataclass
class PostSettings:
    fmin: float = 5
    fmax: float = 200
    max_modes: int = 6
    prominence_db: float = 3
    min_coherence: float = .8
    min_hits: int = 2
    exponential_end: float = .01

    def validate(self, nyquist):
        if not np.isfinite([self.fmin, self.fmax, self.prominence_db, self.min_coherence, self.exponential_end]).all():
            raise ValueError('Os parâmetros do ajuste devem ser finitos.')
        if not 0 < self.fmin < self.fmax <= nyquist:
            raise ValueError('Escolha uma faixa positiva, abaixo ou igual a Nyquist.')
        if not 1 <= self.max_modes <= 12 or not 1 <= self.min_hits <= 10000:
            raise ValueError('Use 1 a 12 modos e pelo menos uma batida aceita.')
        if not 0 <= self.min_coherence <= 1 or not 0 < self.exponential_end <= 1 or self.prominence_db <= 0:
            raise ValueError('Coerência, resíduo exponencial ou proeminência inválidos.')


@dataclass
class ModalData:
    frequency: np.ndarray
    frfs: np.ndarray  # rows = points, columns = frequency bins
    coherence: np.ndarray
    point_ids: list
    counts: list
    alpha: float
    warnings: list
    source_records: list


def prepare_data(session, settings):
    """Rebuild only accepted ensembles, using original SI records, not old windows."""
    c = session.config
    settings.validate(c.sample_rate/2)
    if c.bandpass_enabled and not c.low_cut <= settings.fmin < settings.fmax <= c.high_cut:
        raise ValueError(f'A faixa do ajuste deve ficar dentro do passa-banda do ensaio ({c.low_cut:g} a {c.high_cut:g} Hz).')
    alpha = -np.log(settings.exponential_end)/((c.n-1)/c.sample_rate)
    window = np.exp(-alpha*np.arange(c.n)/c.sample_rate)
    ids, counts, frfs, coherences, sources, warnings = [], [], [], [], [], []
    for name, *_ in c.points:
        records = [r for r in session.records if r['point'] == name and r['status'] == 'aceita']
        if len(records) < settings.min_hits:
            warnings.append(f'{name}: excluído ({len(records)} batidas aceitas; mínimo {settings.min_hits}).')
            continue
        hits = []
        for record in records:
            with np.load(session.directory/record['file'], allow_pickle=False) as saved:
                f, a = saved['force_N'].copy(), saved['acceleration_m_s2'].copy()
            if f.shape != (c.n,) or a.shape != (c.n,) or not np.isfinite([f, a]).all():
                raise ValueError(f'{name}: captura inválida.')
            f, a = processed_signals(c, f, a)
            hits.append({'F': np.fft.rfft(f*window), 'A': np.fft.rfft(a*window)})
            sources.append({'point': name, 'file': record['file']})
            if record.get('issues'):
                warnings.append(f"{name}: batida aceita com alertas: {', '.join(record['issues'])}.")
        freq, h, coherence = ensemble(c, hits)
        ids.append(name)
        counts.append(len(hits))
        frfs.append(h)
        coherences.append(coherence)
        if len(hits) == 1:
            warnings.append(f'{name}: uma única batida; coerência indisponível e não filtrada.')
    if not ids:
        raise ValueError('Nenhum ponto atende ao mínimo de batidas aceitas.')
    if len(ids) < 3:
        warnings.append('Menos de três pontos: visualização espacial limitada aos pontos medidos.')
    if settings.exponential_end == 1:
        warnings.append('Sem exponencial: confira se os sinais decaem completamente no registro.')
    if c.bandpass_enabled:
        warnings.append(f'Passa-banda comum de {c.low_cut:g} a {c.high_cut:g} Hz aplicado antes da exponencial. Confira transientes e decaimento.')
    return ModalData(freq, np.asarray(frfs), np.asarray(coherences), ids, counts,
                     float(alpha), list(dict.fromkeys(warnings)), sources)


def usable(data, settings):
    mask = np.isfinite(data.frfs)
    for i, count in enumerate(data.counts):
        if count >= 2:
            mask[i] &= np.isfinite(data.coherence[i]) & (data.coherence[i] >= settings.min_coherence)
    return mask & (data.frequency >= settings.fmin) & (data.frequency <= settings.fmax)


def indicator(data, settings):
    mask = usable(data, settings)
    amplitudes = abs(data.frfs)
    scale = np.max(np.where(mask, amplitudes, 0), axis=1)
    normalized = np.where(mask, amplitudes/np.maximum(scale[:, None], 1e-30), 0)
    count = mask.sum(axis=0)
    value = np.sqrt(np.sum(normalized**2, axis=0)/np.maximum(count, 1))
    return np.where(count > 0, value, np.nan)


def suggest_modes(data, settings):
    """Peaks are candidates only, never asserted to be structural modes."""
    curve = indicator(data, settings)
    db = 20*np.log10(np.maximum(curve, 1e-12))
    # Measure prominence within finite runs: masked bands must not become deep
    # artificial valleys that inflate the prominence of a boundary peak.
    edges = np.diff(np.r_[False, np.isfinite(db), False].astype(int))
    candidates = []
    for start, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        peaks, props = find_peaks(db[start:stop], prominence=settings.prominence_db, distance=2)
        candidates.extend((float(prominence), int(start+p))
                          for p, prominence in zip(peaks, props['prominences'])
                          if settings.fmin < data.frequency[start+p] < settings.fmax)
    strongest = sorted(candidates, reverse=True)[:settings.max_modes]
    return sorted(float(data.frequency[p]) for _, p in strongest)


def modal_basis(frequency, frequencies, damping, alpha=0):
    s = alpha+2j*np.pi*np.asarray(frequency)
    w = 2*np.pi*np.asarray(frequencies)
    modes = s[:, None]**2/(s[:, None]**2+2*np.asarray(damping)*w*s[:, None]+w*w)
    return np.column_stack([modes, np.ones(len(s)), (s/(2*np.pi))**2])


def fit_modes(data, settings, seeds=None):
    settings.validate(float(data.frequency[-1]))
    seeds = np.asarray(suggest_modes(data, settings) if seeds is None else seeds, float)
    if seeds.ndim != 1 or not 1 <= len(seeds) <= 12 or not np.isfinite(seeds).all():
        raise ValueError('Nenhum candidato válido. Informe 1 a 12 frequências iniciais separadas por ponto e vírgula.')
    seeds = np.sort(seeds)
    df = float(np.median(np.diff(data.frequency)))
    if seeds[0] <= settings.fmin or seeds[-1] >= settings.fmax or np.any(np.diff(seeds) < df):
        raise ValueError('Candidatos devem estar dentro da faixa e separados por pelo menos um bin de frequência.')
    mask = usable(data, settings)
    bins = np.flatnonzero(mask.any(axis=0))
    if len(bins) < max(20, 6*len(seeds)):
        raise ValueError('Poucos bins válidos: amplie a faixa ou confira a coerência e a excitação.')
    warnings = list(data.warnings)
    if len(bins) > 6000:
        # Bound the fit cost while retaining original resolution around each pole.
        keep = [bins[np.linspace(0, len(bins)-1, 6000).astype(int)]]
        keep.extend(bins[np.argsort(abs(data.frequency[bins]-seed))[:201]] for seed in seeds)
        bins = np.unique(np.concatenate(keep))
        warnings.append('Ajuste com redução de bins fora das vizinhanças dos candidatos.')
    f = data.frequency[bins]
    valid = mask[:, bins]
    active = np.flatnonzero(valid.sum(axis=1) >= max(20, 4*(len(seeds)+2)))
    if not len(active):
        raise ValueError('Nenhum ponto tem bins suficientes após o filtro de coerência.')
    for i in set(range(len(data.point_ids)))-set(active):
        warnings.append(f'{data.point_ids[i]}: excluído do ajuste por falta de bins válidos.')
    scales = [max(np.sqrt(np.mean(abs(data.frfs[i, bins][valid[i]])**2)), 1e-30) for i in active]
    bounds_mid = (seeds[:-1]+seeds[1:])/2
    lower_f = np.r_[settings.fmin, bounds_mid]
    upper_f = np.r_[bounds_mid, settings.fmax]
    m = len(seeds)

    def solve(parameters, details=False):
        basis = modal_basis(f, parameters[:m], parameters[m:], data.alpha)
        residuals, coefficients, conditions = [], [], []
        for i, scale in zip(active, scales):
            valid_i = valid[i]
            b = basis[valid_i]
            h = data.frfs[i, bins][valid_i]/scale
            design = np.vstack([b.real, b.imag])
            norms = np.maximum(np.linalg.norm(design, axis=0), 1e-30)
            x, _, _, singular = np.linalg.lstsq(design/norms, np.r_[h.real, h.imag], rcond=None)
            x /= norms
            residuals.append(np.r_[(b@x-h).real, (b@x-h).imag])
            coefficients.append(x*scale)
            conditions.append(float(singular[0]/max(singular[-1], 1e-30)))
        return (np.concatenate(residuals), np.asarray(coefficients), conditions) if details else np.concatenate(residuals)

    fit = least_squares(solve, np.r_[seeds, np.full(m, .02)],
                        bounds=(np.r_[lower_f, np.full(m, .00001)], np.r_[upper_f, np.full(m, .3)]),
                        x_scale='jac', max_nfev=350, ftol=1e-9, xtol=1e-9, gtol=1e-9)
    if not fit.success or not np.isfinite(fit.x).all():
        raise ValueError('O ajuste não convergiu. Reduza a faixa, revise os candidatos ou aumente a qualidade das medições.')
    _, coefficients, conditions = solve(fit.x, True)
    fitted = modal_basis(data.frequency, fit.x[:m], fit.x[m:], data.alpha)@coefficients.T
    errors = []
    for col, i in enumerate(active):
        v = mask[i]
        errors.append(float(np.linalg.norm((fitted[:, col]-data.frfs[i])[v])/max(np.linalg.norm(data.frfs[i, v]), 1e-30)))
    if max(conditions) > 1e7:
        warnings.append('Matriz do ajuste mal condicionada; revise o número e a separação dos modos.')
    if max(errors) > .2:
        warnings.append('Erro de ajuste acima de 20% em pelo menos um ponto; parâmetros devem ser revisados.')
    modes = []
    for j in range(m):
        shape = coefficients[:, j].copy()
        largest = int(np.argmax(abs(shape)))
        if abs(shape[largest]) < 1e-15:
            warnings.append(f'Candidato {j+1}: contribuição modal desprezível.')
            continue
        shape /= shape[largest]  # arbitrary phase/sign; largest component = +1
        fn, zeta = float(fit.x[j]), float(fit.x[m+j])
        notes = []
        if 2*zeta*fn < 2*df:
            notes.append('Largura modal menor que 2 bins; amortecimento pouco resolvido.')
        if zeta < .00002 or zeta > .299:
            notes.append('Amortecimento no limite de busca; estimativa não confiável.')
        if min(fn-lower_f[j], upper_f[j]-fn) < df:
            notes.append('Frequência próxima ao limite do intervalo do candidato.')
        modes.append({'frequency_hz': fn, 'damping_ratio': zeta,
                      'damped_frequency_hz': fn*np.sqrt(1-zeta*zeta),
                      'shape': {data.point_ids[i]: float(v) for i, v in zip(active, shape)},
                      'warnings': notes})
    if not modes:
        raise ValueError('Nenhum modo com contribuição identificável.')
    return {'method': 'Ajuste conjunto de acelerância; modos reais e resíduos reais; H(alpha + iω)',
            'settings': asdict(settings), 'alpha_per_s': data.alpha, 'frequency_resolution_hz': df,
            'initial_frequencies_hz': seeds.tolist(), 'modes': modes,
            'point_ids': [data.point_ids[i] for i in active],
            'relative_fit_error': dict(zip([data.point_ids[i] for i in active], errors)),
            'warnings': warnings, 'source_records': data.source_records,
            'frequency': data.frequency, 'measured': data.frfs[active],
            'fitted': fitted.T, 'coherence': data.coherence[active]}


def export_results(result, directory):
    """Export to a new directory selected by the caller; no raw measurements changed."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    report = {k: v for k, v in result.items() if not k.startswith('_') and k not in ('frequency', 'measured', 'fitted', 'coherence')}
    (directory/'modos.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    with (directory/'modos.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['modo', 'frequencia_natural_Hz', 'amortecimento_percentual', 'frequencia_amortecida_Hz', 'alertas'])
        for i, mode in enumerate(result['modes'], 1):
            writer.writerow([i, mode['frequency_hz'], 100*mode['damping_ratio'], mode['damped_frequency_hz'], ' | '.join(mode['warnings'])])
    with (directory/'formas_modais.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['ponto']+[f'modo_{i+1}_Z_{part}' for i in range(len(result['modes'])) for part in ('real', 'imag')])
        for point in result['point_ids']:
            writer.writerow([point]+[v for m in result['modes'] for v in (m['shape'][point], m.get('shape_imag', {}).get(point, 0))])
    np.savez_compressed(directory/'frfs_ajustadas.npz', frequency_Hz=result['frequency'],
                        measured=result['measured'], fitted=result['fitted'], coherence=result['coherence'],
                        point_ids=np.asarray(result['point_ids']))
    if 'stabilization' in result:
        with (directory/'estabilizacao.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.writer(stream, delimiter=';')
            writer.writerow(['ordem_dinamica', 'modo', 'frequencia_Hz', 'amortecimento_percentual',
                             'classe', 'variacao_f_relativa', 'variacao_zeta_relativa', 'MAC', 'modo_anterior'])
            for row in result['stabilization']['orders']:
                for index, mode in enumerate(row['modes'], 1):
                    writer.writerow([row['order'], index, mode['frequency_hz'], mode['damping_ratio']*100,
                                     mode['stability'], mode['frequency_change'], mode['damping_change'],
                                     mode['mac'], mode['previous_mode']])


@dataclass
class StabilitySettings:
    max_modes: int = 6
    frequency_tolerance: float = .01
    damping_tolerance: float = .05
    min_mac: float = .95

    def validate(self):
        if not isinstance(self.max_modes, int) or not 2 <= self.max_modes <= 12:
            raise ValueError('A estabilização deve usar entre 2 e 12 modos (ordens 4 a 24).')
        if not np.isfinite([self.frequency_tolerance, self.damping_tolerance, self.min_mac]).all() or not (
                0 < self.frequency_tolerance <= .5 and 0 < self.damping_tolerance <= 1 and 0 <= self.min_mac <= 1):
            raise ValueError('Tolerâncias de estabilização inválidas.')


def shape_mac(first, second):
    """MAC is scale/sign invariant; one scalar reference cannot validate a shape."""
    common = sorted(set(first) & set(second))
    if len(common) < 2:
        return None
    a = np.asarray([first[k] for k in common], complex)
    b = np.asarray([second[k] for k in common], complex)
    denominator = float(np.vdot(a, a).real*np.vdot(b, b).real)
    if not np.isfinite(denominator) or denominator <= 1e-30:
        return None
    return float(np.clip(abs(np.vdot(a, b))**2/denominator, 0, 1))


def classify_stability(current, previous, settings):
    """One-to-one frequency matching against the immediately preceding order."""
    modes = [dict(mode, stability='novo', frequency_change=None, damping_change=None,
                  mac=None, previous_mode=None) for mode in current]
    if not current or not previous:
        return modes
    changes = np.array([[abs(m['frequency_hz']-p['frequency_hz'])/p['frequency_hz']
                         for p in previous] for m in current])
    rows, cols = linear_sum_assignment(np.where(changes <= settings.frequency_tolerance, changes, 1e6))
    for row, col in zip(rows, cols):
        if changes[row, col] > settings.frequency_tolerance:
            continue
        mode, old = modes[row], previous[col]
        delta = abs(mode['damping_ratio']-old['damping_ratio'])/max(old['damping_ratio'], 1e-12)
        def complex_shape(item):
            return {name: complex(value, item.get('shape_imag', {}).get(name, 0)) for name, value in item['shape'].items()}
        mac = shape_mac(complex_shape(mode), complex_shape(old))
        mode.update(frequency_change=float(changes[row, col]), damping_change=float(delta),
                    mac=mac, previous_mode=int(col+1), stability='frequencia')
        if delta <= settings.damping_tolerance:
            mode['stability'] = 'frequencia_amortecimento'
            if mac is not None and mac >= settings.min_mac:
                mode['stability'] = 'estavel'
    return modes


def stabilization_diagram(data, settings, stability, seeds=None):
    """Refit real-mode accelerance models of 1..M modes (dynamic orders 2..2M).

    This is a sweep of the existing constrained nonlinear model, not PolyMAX/SSI.
    The residual terms do not add dynamic poles. Failed orders break matching.
    """
    stability.validate()
    settings.validate(float(data.frequency[-1]))
    df = float(np.median(np.diff(data.frequency)))
    curve = indicator(data, settings)
    detected = suggest_modes(data, replace(settings, max_modes=12))
    candidates = list(seeds) if seeds is not None else detected
    if not candidates or not np.isfinite(candidates).all() or any(not settings.fmin < f < settings.fmax for f in candidates):
        raise ValueError('Sem candidatos para estabilização. Calcule/revise primeiro o ajuste modal.')
    candidates = sorted(candidates, key=lambda f: -float(np.nan_to_num(curve[np.argmin(abs(data.frequency-f))], nan=0)))
    # Add further observed peaks, then spread auxiliary candidates across the band.
    for value in detected:
        if all(abs(value-f) >= df for f in candidates):
            candidates.append(value)
    while len(candidates) < stability.max_modes:
        edges = np.sort([settings.fmin, *candidates, settings.fmax])
        gap = int(np.argmax(np.diff(edges)))
        value = float((edges[gap]+edges[gap+1])/2)
        if min(abs(value-f) for f in edges) < df:
            break
        candidates.append(value)
    orders = []
    previous = []
    for count in range(1, stability.max_modes+1):
        row = {'order': 2*count, 'requested_modes': count, 'modes': [], 'error': None}
        try:
            if len(candidates) < count:
                raise ValueError('Resolução insuficiente para acrescentar candidatos distintos.')
            result = fit_modes(data, settings, sorted(candidates[:count]))
            row['modes'] = classify_stability(result['modes'], previous, stability)
            row['max_relative_fit_error'] = max(result['relative_fit_error'].values())
            row['warnings'] = result['warnings']
            row['initial_frequencies_hz'] = result['initial_frequencies_hz']
            previous = result['modes']
        except (ValueError, np.linalg.LinAlgError) as exc:
            row['error'] = str(exc)
            previous = []
        orders.append(row)
    return {'method': 'Varredura do ajuste modal real; ordem dinâmica = 2 × número de modos; resíduos sem polos',
            'settings': asdict(stability), 'orders': orders,
            'interpretation': 'Estabilidade numérica entre ordens adjacentes não certifica um modo físico. '
                              'Avalie erro da FRF, resolução e observabilidade na referência.'}
