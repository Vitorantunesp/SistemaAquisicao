"""Ensemble coherence of independent setup hits, with a common analysis plan."""
from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly

from ads1800_app.modal import ModalConfig, ensemble, hit_spectra, windows


def project_setup_record(record, config):
    """Resample and align to the final trigger, without inventing missing samples."""
    source = ModalConfig.from_dict(record['config'])
    values = np.asarray(record['data'])[:, 1:]
    if not np.isclose(source.sample_rate, config.sample_rate):
        ratio = Fraction(float(config.sample_rate/source.sample_rate)).limit_denominator(100000)
        values = resample_poly(values, ratio.numerator, ratio.denominator, axis=0, padtype='line')
    pre = max(2, round(source.pretrigger*config.sample_rate)//2)
    force = values[:, 0]-np.median(values[:pre, 0])
    level = abs(force) if config.polarity == 'Absoluto' else force if config.polarity == 'Positivo' else -force
    crossing = np.flatnonzero(level >= config.threshold)
    if not len(crossing):
        return None
    start = int(crossing[0])-config.pre
    if start < 0 or start+config.n > len(values):
        return None
    return np.column_stack([np.arange(config.n)/config.sample_rate,
                            values[start:start+config.n]])


def spectrum_density(spectrum, window, fs):
    """One-sided, window-energy-normalized density, in squared units per Hz."""
    window = np.asarray(window)
    density = abs(np.asarray(spectrum))**2/(fs*np.sum(window**2))
    density[1:-1 if len(window) % 2 == 0 else None] *= 2
    return density


def assess_setup_coherence(records, config, profiles, sensor=0, *, threshold=.9, required_fraction=.8):
    """A single transient has no ensemble coherence; weak spectral bins are masked."""
    freq = np.fft.rfftfreq(config.n, 1/config.sample_rate)
    curve = np.full(len(freq), np.nan)
    usable = np.zeros(len(freq), bool)
    summary = dict(status='insuficiente', passed=False, hit_count=len(records),
                   threshold=threshold, required_fraction=required_fraction,
                   usable_bins=0, band_bins=0, usable_fraction=0., median=None,
                   fraction_above=None, reasons=[])
    result = dict(frequency=freq, coherence=curve, usable=usable, summary=summary)
    if len(records) < 2:
        summary['reasons'] = ['Coerência indisponível: são necessárias duas batidas independentes do mesmo ponto.']
        return result
    if len({h['point'] for h in records}) != 1:
        summary['reasons'] = ['Coerência não combina batidas de pontos diferentes.']
        return result
    if any(not h.get('spectrally_valid', h.get('accepted', False)) for h in records):
        summary['reasons'] = ['Batida com saturação, duplo impacto ou sinal inválido não pode validar a coerência.']
        return result
    wf, wa = windows(config)
    spectra, force_noise, response_noise = [], [], []
    for record, profile in zip(records, profiles):
        data = project_setup_record(record, config)
        if data is None:
            summary['reasons'] = ['As batidas não cobrem o mesmo bloco e pré-trigger. Aumente a observação e repita.']
            return result
        F, A, _, _ = hit_spectra(config, data[:, 1], data[:, sensor+2])
        if config.force_window == 'Força':
            force = data[:, 1]-np.mean(data[:max(1, config.pre//2), 1])
            pulse = abs(force) > .05*np.max(abs(force))
            gate = wf/wa if config.response_window == 'Exponencial' else wf
            if np.any(gate[pulse] < .99):
                summary['reasons'] = ['A janela de força atenua ou corta parte do contato. Aumente sua duração.']
                return result
        spectra.append({'F': F, 'A': A})
        force_noise.append(profile['sigma'][0]**2*np.sum(wf**2))
        response_noise.append(profile['sigma'][sensor+1]**2*np.sum(wa**2))
    _, _, estimated = ensemble(config, spectra)
    band = np.ones(len(freq), bool)
    if config.analysis_band:
        band &= (freq >= config.analysis_band[0]) & (freq <= config.analysis_band[1])
    if config.bandpass_enabled:
        band &= (freq >= config.low_cut) & (freq <= config.high_cut)
    ff = np.mean([abs(h['F'])**2 for h in spectra], axis=0)
    aa = np.mean([abs(h['A'])**2 for h in spectra], axis=0)
    usable = band & np.isfinite(estimated) & (ff > 10*np.mean(force_noise)) & (aa > 10*np.mean(response_noise))
    curve[usable] = estimated[usable]
    count, total = int(usable.sum()), int(band.sum())
    summary.update(usable_bins=count, band_bins=total, usable_fraction=count/max(1, total))
    result['usable'] = usable
    if count:
        summary.update(median=float(np.median(curve[usable])),
                       fraction_above=float(np.mean(curve[usable] >= threshold)))
    if count < 8 or summary['usable_fraction'] < .2:
        summary['reasons'] = ['Poucas frequências com força e resposta acima do ruído para avaliar a coerência.']
    elif summary['fraction_above'] < required_fraction:
        summary.update(status='baixa', reasons=[f"Coerência ≥{threshold:.2f} em {summary['fraction_above']:.0%} da banda avaliável; mínimo {required_fraction:.0%}."])
    else:
        summary.update(status='adequada', passed=True)
    return result
