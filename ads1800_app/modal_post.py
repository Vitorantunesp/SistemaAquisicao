"""Shared-pole, real-mode accelerance fitting for reciprocal roving-hammer tests.

H(s) = sum(r_j*s²/(s²+2*zeta_j*wn_j*s+wn_j²)) + c0 + c2*(s/2pi)².
The same exponential applied to both signals evaluates H at s=alpha+i*w;
fitting there estimates physical rather than window-broadened damping.
"""
from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import find_peaks

from ads1800_app.modal import ensemble


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
            baseline = max(1, c.pre//2)
            f -= np.mean(f[:baseline])
            a -= np.mean(a[:baseline])
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
    peaks, props = find_peaks(np.where(np.isfinite(db), db, -240), prominence=settings.prominence_db, distance=2)
    # A hole in the coherence mask must not create a peak at the edge of a gap.
    peaks_ok = [i for i, p in enumerate(peaks) if 0 < p < len(db)-1 and
                np.isfinite(db[p-1:p+2]).all() and settings.fmin < data.frequency[p] < settings.fmax]
    strongest = sorted(peaks_ok, key=lambda i: props['prominences'][i], reverse=True)[:settings.max_modes]
    return sorted(float(data.frequency[peaks[i]]) for i in strongest)


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
    report = {k: v for k, v in result.items() if k not in ('frequency', 'measured', 'fitted', 'coherence')}
    (directory/'modos.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    with (directory/'modos.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['modo', 'frequencia_natural_Hz', 'amortecimento_percentual', 'frequencia_amortecida_Hz', 'alertas'])
        for i, mode in enumerate(result['modes'], 1):
            writer.writerow([i, mode['frequency_hz'], 100*mode['damping_ratio'], mode['damped_frequency_hz'], ' | '.join(mode['warnings'])])
    with (directory/'formas_modais.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['ponto']+[f'modo_{i+1}_Z_relativo' for i in range(len(result['modes']))])
        for point in result['point_ids']:
            writer.writerow([point]+[m['shape'][point] for m in result['modes']])
    np.savez_compressed(directory/'frfs_ajustadas.npz', frequency_Hz=result['frequency'],
                        measured=result['measured'], fitted=result['fitted'], coherence=result['coherence'],
                        point_ids=np.asarray(result['point_ids']))
