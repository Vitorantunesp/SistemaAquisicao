"""Measured modal setup, independent of Qt and of the acquisition hardware.

Pilot records stay at their original rate. Polyphase resampling only predicts
the proposed configuration; new measurements at that rate must confirm it.
"""
from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from pathlib import Path
import json
import math

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import resample_poly

from ads1800_app.modal import ModalConfig, analyze_hit, ensemble, windows
from ads1800_app.modal_coherence import assess_setup_coherence


@dataclass(frozen=True)
class SetupSettings:
    fmin: float = 1
    fmax: float = 500
    noise_seconds: float = 3
    observation_seconds: float = 8
    minimum_hits: int = 6
    minimum_points: int = 2
    confirmation_hits: int = 3
    sampling_margin: float = 2.56
    allow_exponential: bool = False

    def validate(self):
        if not all(math.isfinite(x) for x in (self.fmin, self.fmax, self.noise_seconds,
                                              self.observation_seconds, self.sampling_margin)):
            raise ValueError('Parâmetros do assistente devem ser finitos.')
        if not 0 < self.fmin < self.fmax or self.sampling_margin < 2.5:
            raise ValueError('Informe uma banda positiva e margem de amostragem ≥2,5.')
        if not .2 <= self.noise_seconds <= 120 or not .5 <= self.observation_seconds <= 600:
            raise ValueError('Use ruído de 0,2–120 s e observação de 0,5–600 s.')
        if not 1 <= self.minimum_hits <= 100 or not 1 <= self.minimum_points <= self.minimum_hits or not 1 <= self.confirmation_hits <= 100:
            raise ValueError('Use uma quantidade positiva de batidas e pontos.')


def select_sample_rate(rates, fmax, margin=2.56):
    """Smallest advertised rate with a transition band above the requested band."""
    if not math.isfinite(fmax) or fmax <= 0 or not math.isfinite(margin) or margin < 2.5:
        raise ValueError('Banda ou margem de amostragem inválida.')
    available = sorted({float(r) for r in rates if math.isfinite(r) and r > 0})
    for rate in available:
        if rate >= margin*fmax:
            return rate
    raise ValueError(f'Nenhuma taxa disponível comporta {fmax:g} Hz com margem {margin:g}.')


def noise_profile(values):
    """Robust offsets and noise; do not learn a hammer pulse as background."""
    values = np.asarray(values, float)
    if values.ndim != 2 or len(values) < 8 or not np.isfinite(values).all():
        raise ValueError('Registro de ruído incompleto ou inválido.')
    offset = np.median(values, axis=0)
    centered = values-offset
    sigma = np.maximum(1.4826*np.median(abs(centered), axis=0), 1e-12)
    if np.any(np.max(abs(centered), axis=0) > 15*sigma):
        raise ValueError('Ruído contém impacto ou transiente. Aguarde repouso e meça novamente.')
    return {'offset': offset.tolist(), 'sigma': sigma.tolist(),
            'rms': np.sqrt(np.mean(centered**2, axis=0)).tolist()}


def _resample(values, source_rate, target_rate):
    ratio = Fraction(float(target_rate)/float(source_rate)).limit_denominator(100000)
    return resample_poly(values, ratio.numerator, ratio.denominator, axis=0, padtype='line')


def inspect_decay(response, fs, pre, sigma):
    """Last sustained RMS above background, including late beat revivals.

    A quiet interval at the record end is mandatory. No decay time is
    extrapolated from a truncated or noise-only record.
    """
    y = np.asarray(response, float)
    y = y-np.median(y[:max(2, pre//2)])
    count = max(4, round(.05*fs))
    rms = np.sqrt(np.maximum(0, uniform_filter1d(y*y, size=count, mode='nearest')))
    peak = float(np.max(rms[pre:]))
    # A percentage of the overall peak would hide weak, slowly decaying modes
    # behind a strong, rapidly decaying mode. Use measured background instead.
    floor = max(3*float(sigma), 1e-12)
    if peak < max(6*float(sigma), 1e-11):
        return dict(observable=False, settled=False, seconds=None, floor=floor,
                    peak_rms=peak, tail_rms=float(np.sqrt(np.mean(y[-count:]**2))))
    active = np.flatnonzero(rms[pre:] > floor)
    last = pre+int(active[-1]) if len(active) else pre
    # At least 0.25 s of quiet; the extra 15% guards against marginal truncation.
    guard = max(.25, .15*(last-pre)/fs)
    seconds = (last-pre)/fs+guard
    settled = pre+math.ceil(seconds*fs) < len(y)
    return dict(observable=True, settled=settled, seconds=seconds if settled else None,
                floor=floor, peak_rms=peak,
                tail_rms=float(np.sqrt(np.mean(y[-max(count, round(.1*len(y))):]**2))))


def _check_record(data, config):
    data = np.asarray(data, float)
    if data.shape != (config.n, 2+len(config.sensors)) or not np.isfinite(data).all():
        raise ValueError('Registro exploratório incompleto ou inválido.')
    if not np.allclose(np.diff(data[:, 0]), 1/config.sample_rate, rtol=.05, atol=1e-8):
        raise ValueError('Registro exploratório com perda ou descontinuidade de amostras.')
    return data.copy()


def _quality(config, data):
    # These checks run on originals, without windows or digital bandpass.
    check = replace(config, bandpass_enabled=False, force_window='Retangular',
                    response_window='Retangular', exponential_end=1)
    issues = []
    for i, sensor in enumerate(config.sensors):
        analysis = analyze_hit(check.for_sensor(i), data[:, [0, 1, i+2]])
        issues.extend(f"{sensor['name']}: {s}" for s in analysis['issues']
                      if 'saturação' in s or 'duplo' in s or 'baixo sinal/ruído' in s)
    return list(dict.fromkeys(issues))


@dataclass
class SetupRecommendation:
    config: ModalConfig
    ranges: list
    warnings: list
    blockers: list
    metrics: dict


class CalibrationStudy:
    def __init__(self, config, rates, settings=None):
        self.base = ModalConfig.from_dict(json.loads(json.dumps(asdict(config))))
        self.rates = sorted(set(float(r) for r in rates))
        self.settings = settings or SetupSettings()
        self.settings.validate()
        self.target_rate = select_sample_rate(self.rates, self.settings.fmax, self.settings.sampling_margin)
        # Four times the target is useful for a pilot, but only actual device options.
        target_pilot = max(8000, 4*self.target_rate)
        self.pilot_rate = next((r for r in self.rates if r >= target_pilot), max(self.rates))
        self.baseline = None
        self.noise = None
        self.pilots = []
        self.confirmations = []
        self.confirmation_noise_data = None
        self.confirmation_noise = None
        self.recommendation = None
        self.validated = False

    def set_noise(self, values):
        values = np.asarray(values, float)
        if values.shape[1:] != (1+len(self.base.sensors),) or len(values) < round(self.settings.noise_seconds*self.pilot_rate):
            raise ValueError('A medição de ruído não contém todos os canais e amostras necessários.')
        self.noise = noise_profile(values)
        self.baseline = values.copy()
        self.pilots.clear()
        self._invalidate()

    def _invalidate(self):
        self.recommendation = None
        self.confirmations.clear()
        self.confirmation_noise_data = self.confirmation_noise = None
        self.validated = False

    def pilot_config(self):
        if self.noise is None:
            raise ValueError('Meça primeiro o ruído sem batidas.')
        c = replace(self.base, sample_rate=self.pilot_rate, duration=self.settings.observation_seconds,
                    pretrigger=min(.1, self.settings.observation_seconds/10),
                    threshold=max(8*self.noise['sigma'][0], 1e-8),
                    trigger_offset=self.noise['offset'][0], bandpass_enabled=False,
                    analysis_band=None, force_window='Retangular', response_window='Retangular',
                    exponential_end=1, rearm_noise_limits=(), quiet_duration=.1)
        c.validate()
        return c

    def add_pilot(self, point, data):
        c = self.pilot_config()
        if point not in [p[0] for p in c.points]:
            raise ValueError('Ponto exploratório desconhecido.')
        data = _check_record(data, c)
        issues = _quality(c, data)
        self.pilots.append(dict(point=point, data=data, accepted=not issues, issues=issues))
        self._invalidate()
        return self.pilots[-1]

    def reject_pilot(self, index):
        self.pilots[index]['accepted'] = False
        self._invalidate()

    def suggest(self):
        if self.noise is None:
            raise ValueError('Meça primeiro o ruído.')
        hits = [h for h in self.pilots if h['accepted']]
        if not hits:
            raise ValueError('Faça pelo menos uma batida exploratória válida.')
        c = self.pilot_config()
        warnings, blockers = [], []
        if len(hits) < self.settings.minimum_hits:
            blockers.append(f'Obtenha {self.settings.minimum_hits} batidas válidas (atuais: {len(hits)}).')
        if len({h['point'] for h in hits}) < self.settings.minimum_points:
            blockers.append(f'Explore pelo menos {self.settings.minimum_points} pontos distintos.')
        sigma = np.asarray(self.noise['sigma'])
        offsets = np.asarray(self.noise['offset'])
        decays, pulse_ends, onset_lags, peaks = [], [], [], []
        observed = np.zeros(len(c.sensors), bool)
        tails, floors = [], []
        for hit in hits:
            v = hit['data'][:, 1:]-offsets
            force = abs(v[:, 0])
            peak = float(np.max(force))
            peaks.append(np.max(abs(v), axis=0))
            contact = np.flatnonzero(force > max(6*sigma[0], .01*peak))
            if not len(contact):
                blockers.append('Contato não distinguível do ruído.')
                continue
            onset_lags.append(max(0, (c.pre-int(contact[0]))/c.sample_rate))
            pulse_ends.append(max(1/c.sample_rate, (int(contact[-1])-c.pre)/c.sample_rate))
            for i in range(len(c.sensors)):
                decay = inspect_decay(v[:, i+1], c.sample_rate, c.pre, sigma[i+1])
                observed[i] |= decay['observable']
                if decay['observable']:
                    if decay['settled']:
                        decays.append(decay['seconds'])
                    else:
                        tails.append(decay['tail_rms'])
                        floors.append(decay['floor'])
        for i, active in enumerate(observed):
            if not active:
                blockers.append(f"{c.sensors[i]['name']}: resposta não distinguível do ruído nos pontos explorados.")
        if tails and not self.settings.allow_exponential:
            blockers.append('Resposta ainda ativa no fim. Aumente a observação e repita as batidas; exponencial é opcional.')
        if not decays and not tails:
            blockers.append('Não foi possível medir o decaimento da resposta.')
        pre = max(.02, max(onset_lags, default=0)+.02)
        post = c.duration-c.pretrigger if tails else max(decays, default=c.duration-c.pretrigger)
        if not tails:
            post += max(.1, .1*post)
        n = math.ceil((pre+post)*self.target_rate)
        duration = n/self.target_rate
        end = 1.0
        if tails and self.settings.allow_exponential:
            end = float(np.clip(min(f/t for f, t in zip(floors, tails)), .001, .9))
            warnings.append('Exponencial solicitada: acrescenta amortecimento aparente, corrigido na identificação.')
        converted = [_resample(h['data'][:, 1:], c.sample_rate, self.target_rate) for h in hits]
        lower_noise = noise_profile(_resample(self.baseline, c.sample_rate, self.target_rate))
        weak_peak = min(float(np.max(abs(v[:, 0]-lower_noise['offset'][0]))) for v in converted)
        threshold = max(6*lower_noise['sigma'][0], .15*weak_peak)
        if threshold > .3*weak_peak:
            blockers.append('Trigger sem separação suficiente do ruído na taxa sugerida.')
        # The plateau must cover the pulse. The existing force taper occupies 20%.
        width = max(.002, (max(pulse_ends, default=.002)+8/self.target_rate)/.8)
        proposed = replace(self.base, sample_rate=self.target_rate, duration=duration,
                           pretrigger=math.ceil(pre*self.target_rate)/self.target_rate,
                           threshold=threshold, trigger_offset=lower_noise['offset'][0],
                           force_width=width, force_window='Força',
                           response_window='Retangular' if end == 1 else 'Exponencial',
                           exponential_end=end, bandpass_enabled=False,
                           analysis_band=(self.settings.fmin, self.settings.fmax),
                           rearm_noise_limits=tuple(3*max(s, r, 1e-12) for s, r in
                                                   zip(lower_noise['sigma'][1:], lower_noise['rms'][1:])),
                           quiet_duration=max(.2, min(10, 1/self.settings.fmin)))
        proposed.validate()
        extrema = np.max(peaks, axis=0)*1.4
        ranges = []
        for i, (name, unit, limits) in enumerate([('Martelo', 'N', c.force_limits),
                            *[(s['name'], 'm/s²', s.get('limits')) for s in c.sensors]]):
            bound = float(extrema[i])
            ranges.append(dict(channel=c.force_channel if i == 0 else c.sensors[i-1]['channel'],
                               name=name, unit=unit, recommended_min=-bound, recommended_max=bound,
                               current_limits=limits, automatic=False))
        warnings.append('Ranges são recomendações em unidades físicas. Ajuste o condicionador no Assistente LYNX, reconecte e repita o assistente se mudar a faixa.')
        warnings.append('A margem de amostragem pressupõe os filtros internos adequados. As novas batidas confirmam a taxa; ausência de picos não comprova ausência de modos.')
        metrics = dict(pilot_rate=c.sample_rate, suggested_rate=proposed.sample_rate,
                       measured_decay_s=max(decays) if decays else None,
                       duration_s=proposed.duration, block_size=proposed.n,
                       frequency_spacing_hz=proposed.sample_rate/proposed.n,
                       bytes_per_hit=8*proposed.n*(2+len(c.sensors)),
                       pilot_valid_hits=len(hits), pilot_points=sorted({h['point'] for h in hits}))
        self.confirmations.clear()
        self.confirmation_noise_data = self.confirmation_noise = None
        self.validated = False
        self.recommendation = SetupRecommendation(proposed, ranges, warnings,
                                                   list(dict.fromkeys(blockers)), metrics)
        return self.recommendation

    def set_confirmation_noise(self, values):
        if self.recommendation is None or self.recommendation.blockers:
            raise ValueError('Conclua as batidas exploratórias e revise a sugestão.')
        self.reset_confirmation()
        c = self.recommendation.config
        values = np.asarray(values, float)
        if values.shape[1:] != (1+len(c.sensors),) or len(values) < round(self.settings.noise_seconds*c.sample_rate):
            raise ValueError('Ruído de confirmação incompleto.')
        profile = noise_profile(values)
        if 6*profile['sigma'][0] > c.threshold:
            raise ValueError('Ruído de força aumentou: o trigger sugerido não é adequado. Repita a configuração.')
        self.confirmation_noise_data = values.copy()
        self.confirmation_noise = profile
        self.recommendation.config = replace(c, trigger_offset=profile['offset'][0],
            rearm_noise_limits=tuple(3*max(s, r, 1e-12) for s, r in zip(profile['sigma'][1:], profile['rms'][1:])))

    def reset_confirmation(self):
        self.confirmations.clear()
        self.confirmation_noise_data = self.confirmation_noise = None
        self.validated = False
        if self.recommendation:
            self.recommendation.metrics.pop('confirmation_frf_scatter', None)
            self.recommendation.metrics.pop('confirmation_pilot_error', None)

    def add_confirmation(self, point, data):
        if self.confirmation_noise is None:
            raise ValueError('Meça o ruído na taxa sugerida antes de confirmar.')
        c = self.recommendation.config
        data = _check_record(data, c)
        if point not in [p[0] for p in c.points]:
            raise ValueError('Ponto de confirmação desconhecido.')
        issues = _quality(c, data)
        for i, sensor in enumerate(c.sensors):
            decay = inspect_decay(data[:, i+2], c.sample_rate, c.pre,
                                  self.confirmation_noise['sigma'][i+1])
            if not decay['observable']:
                issues.append(f"{sensor['name']}: resposta insuficiente para confirmar.")
            elif not decay['settled'] and c.response_window != 'Exponencial':
                issues.append(f"{sensor['name']}: resposta não terminou na duração sugerida.")
        analyses = [analyze_hit(c.for_sensor(i), data[:, [0, 1, i+2]]) for i in range(len(c.sensors))]
        # A shorter force window must not hide a second contact or truncate force.
        issues.extend(s for s in analyses[0]['issues'] if 'fora da janela' in s)
        wf, _ = windows(c)
        noise_power = self.confirmation_noise['sigma'][0]**2*float(np.sum(wf**2))
        freq = np.fft.rfftfreq(c.n, 1/c.sample_rate)
        band = (freq >= self.settings.fmin) & (freq <= self.settings.fmax)
        coverage = float(np.mean(abs(analyses[0]['F'][band])**2 > 10*noise_power)) if band.any() else 0.0
        if coverage < .9:
            issues.append('Excitação insuficiente em mais de 10% da banda; confira a ponteira e a força.')
        self.confirmations.append(dict(point=point, data=data, accepted=not issues,
                                       issues=list(dict.fromkeys(issues)), coverage=coverage))
        good = [h for h in self.confirmations if h['accepted'] and h['point'] == point]
        self.validated = False
        if len(good) >= self.settings.confirmation_hits:
            # Complex FRF scatter only where response and input are above noise;
            # coherence remains a diagnostic, not the sole acceptance criterion.
            valid = band.copy()
            all_h, pilot_errors = [], []
            pilot_c = self.pilot_config()
            start = round((pilot_c.pretrigger-c.pretrigger)*c.sample_rate)
            reference = []
            for h in self.pilots:
                if not h['accepted'] or h['point'] != point:
                    continue
                values = _resample(h['data'][:, 1:], pilot_c.sample_rate, c.sample_rate)
                if start < 0 or start+c.n > len(values):
                    continue
                reference.append(np.column_stack([np.arange(c.n)/c.sample_rate, values[start:start+c.n]]))
            for i in range(len(c.sensors)):
                spectra = [analyze_hit(c.for_sensor(i), h['data'][:, [0, 1, i+2]]) for h in good]
                _, mean_h, _ = ensemble(c, spectra)
                individual = np.asarray([s['A']/np.where(abs(s['F']) > 1e-20, s['F'], np.nan) for s in spectra])
                response_power = np.mean([abs(s['A'])**2 for s in spectra], axis=0)
                _, wa = windows(c)
                response_noise = self.confirmation_noise['sigma'][i+1]**2*np.sum(wa**2)
                mask = valid & np.isfinite(mean_h) & (response_power > 10*response_noise)
                if not mask.any():
                    break
                scatter = float(np.linalg.norm(individual[:, mask]-mean_h[mask])/
                                max(np.sqrt(len(good))*np.linalg.norm(mean_h[mask]), 1e-30))
                all_h.append(scatter)
                if reference:
                    refs = [analyze_hit(c.for_sensor(i), raw[:, [0, 1, i+2]]) for raw in reference]
                    _, reference_h, _ = ensemble(c, refs)
                    comparison = mask & np.isfinite(reference_h)
                    pilot_errors.append(float(np.linalg.norm(mean_h[comparison]-reference_h[comparison])/
                                              max(np.linalg.norm(reference_h[comparison]), 1e-30)) if comparison.any() else math.inf)
            self.recommendation.metrics['confirmation_frf_scatter'] = all_h
            self.recommendation.metrics['confirmation_pilot_error'] = [e if math.isfinite(e) else None for e in pilot_errors]
            self.validated = (len(all_h) == len(c.sensors) and max(all_h) <= .25 and
                              len(pilot_errors) == len(c.sensors) and max(pilot_errors) <= .25)
        return self.confirmations[-1]

    def matches(self, config):
        return bool(self.validated and self.recommendation and
                    json.dumps(asdict(config), sort_keys=True) ==
                    json.dumps(asdict(self.recommendation.config), sort_keys=True))

    def report(self):
        if self.recommendation is None:
            raise ValueError('Ainda não existe sugestão.')
        clean = lambda h: {k: v for k, v in h.items() if k != 'data'}
        return dict(schema=1, validated=self.validated, settings=asdict(self.settings),
                    available_sample_rates=self.rates, noise=self.noise,
                    confirmation_noise=self.confirmation_noise,
                    recommendation=asdict(self.recommendation),
                    pilot_records=[clean(h) for h in self.pilots],
                    confirmation_records=[clean(h) for h in self.confirmations])

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        np.savez_compressed(directory/'ruido.npz', values=self.baseline, fs=self.pilot_rate)
        if self.confirmation_noise_data is not None:
            np.savez_compressed(directory/'ruido_confirmacao.npz', values=self.confirmation_noise_data,
                                fs=self.recommendation.config.sample_rate)
        for prefix, records in [('exploracao', self.pilots), ('confirmacao', self.confirmations)]:
            for i, hit in enumerate(records, 1):
                np.savez_compressed(directory/f'{prefix}_{i:03d}.npz', data=hit['data'])
        (directory/'configuracao.json').write_text(json.dumps(self.report(), ensure_ascii=False,
                                               indent=2, allow_nan=False), encoding='utf-8')


def two_hit_metrics(data, config, profile, sensor=0):
    """Measure contact and natural decay; quiet observation is not block padding."""
    values = np.asarray(data, float)
    if len(values) <= config.pre+4:
        return dict(observable=False, settled=False, decay_s=None)
    force = values[:, 1]-np.median(values[:max(2, config.pre//2), 1])
    response = values[:, sensor+2]-np.median(values[:max(2, config.pre//2), sensor+2])
    peak = float(np.max(abs(force)))
    contacts = np.flatnonzero(abs(force) > max(6*profile['sigma'][0], .01*peak))
    onset = int(contacts[0]) if len(contacts) else config.pre
    end = int(contacts[-1]) if len(contacts) else config.pre
    size = max(4, round(.05*config.sample_rate))
    rms = np.sqrt(np.maximum(0, uniform_filter1d(response**2, size=size, mode='nearest')))
    floor = max(3*profile['sigma'][sensor+1], 1e-12)
    observable = float(np.max(rms[config.pre:])) > 6*profile['sigma'][sensor+1]
    active = np.flatnonzero(rms[onset:] > floor)
    last = onset+int(active[-1]) if len(active) else onset
    quiet_s = (len(values)-1-last)/config.sample_rate
    return dict(peak_N=peak, sign=1 if force[np.argmax(abs(force))] >= 0 else -1,
                contact_s=max(1, end-onset+1)/config.sample_rate,
                onset_lag_s=max(0, config.pre-onset)/config.sample_rate,
                force_end_s=max(0, end-config.pre)/config.sample_rate,
                observable=bool(observable), settled=bool(observable and quiet_s >= .25),
                decay_s=max(1/config.sample_rate, (last-onset)/config.sample_rate) if observable else None,
                noise_floor=float(floor), quiet_s=quiet_s,
                tail_rms=float(np.sqrt(np.mean(response[-size:]**2))))


class TwoHitStudy(CalibrationStudy):
    """First hit defines settings; a second hit checks peak and decay consistency."""
    def __init__(self, config, rates, settings=None, sensor=0, tolerance=.1,
                 coherence_threshold=.9, coherence_fraction=.8):
        settings = settings or SetupSettings(noise_seconds=.5, minimum_hits=1,
                                             minimum_points=1, confirmation_hits=1)
        super().__init__(config, rates, settings)
        if not 0 <= sensor < len(config.sensors) or not 0 < tolerance <= .5:
            raise ValueError('Canal de referência ou tolerância de consistência inválido.')
        self.reference_sensor = sensor
        self.tolerance = tolerance
        self.first_metrics = None
        self.coherence_threshold = coherence_threshold
        self.coherence_fraction = coherence_fraction
        self.coherence_result = None

    def initial_threshold(self):
        if not self.noise:
            raise ValueError('Aguarde a medição inicial do ruído.')
        offset = self.noise['offset'][0]
        if self.base.force_limits:
            low, high = self.base.force_limits
            amplitude = (high-offset if self.base.polarity == 'Positivo' else offset-low
                         if self.base.polarity == 'Negativo' else max(abs(high-offset), abs(low-offset)))
            return max(.05*amplitude, 6*self.noise['sigma'][0], 1e-8)
        return max(6*self.noise['sigma'][0], 1e-8)

    def pilot_config(self):
        return replace(super().pilot_config(), threshold=self.initial_threshold())

    def add_pilot(self, point, data, config=None):
        c = config or self.pilot_config()
        data = _check_record(data, c)
        if point not in [p[0] for p in c.points]:
            raise ValueError('Ponto da primeira batida desconhecido.')
        issues = _quality(c, data)
        metrics = two_hit_metrics(data, c, self.noise, self.reference_sensor)
        if not metrics['observable']:
            issues.append('Aceleração do canal escolhido não se distingue do ruído.')
        self.pilots = [dict(point=point, data=data, config=asdict(c), metrics=metrics,
                            accepted=not issues, issues=issues)]
        self._invalidate()
        self.first_metrics = metrics
        return self.pilots[0]

    def suggest(self):
        if not self.pilots or not self.pilots[0]['accepted']:
            raise ValueError('Obtenha uma primeira batida válida.')
        h, m = self.pilots[0], self.first_metrics
        c = ModalConfig.from_dict(h['config'])
        blockers, warnings = [], []
        if not m['settled']:
            blockers.append('A resposta não terminou no tempo observado. Aumente o tempo máximo e repita a primeira batida.')
            warnings.append('Janela exponencial indicada para um registro limitado; prefira observar o decaimento completo antes de confirmar.')
        profile = noise_profile(_resample(self.baseline, self.pilot_rate, self.target_rate))
        pre = math.ceil(max(.02, m['onset_lag_s']+.02)*self.target_rate)/self.target_rate
        decay = m['decay_s'] or (c.duration-c.pretrigger)
        duration = math.ceil((pre+1.05*decay)*self.target_rate)/self.target_rate
        width = max(.002, (m['force_end_s']+8/self.target_rate)/.8)
        proposed = replace(self.base, sample_rate=self.target_rate, duration=duration,
            pretrigger=pre, threshold=.5*m['peak_N'], trigger_offset=profile['offset'][0],
            force_window='Força', force_width=width, bandpass_enabled=False,
            response_window='Retangular' if m['settled'] else 'Exponencial',
            exponential_end=1 if m['settled'] else float(np.clip(m['noise_floor']/max(m['tail_rms'], 1e-12), .001, .9)),
            analysis_band=(self.settings.fmin, self.settings.fmax),
            rearm_noise_limits=tuple(3*max(a, b, 1e-12) for a, b in zip(profile['sigma'][1:], profile['rms'][1:])),
            quiet_duration=max(.2, min(10, 1/self.settings.fmin)))
        proposed.validate()
        if proposed.threshold < 6*profile['sigma'][0]:
            blockers.append('O trigger de 50% do pico ficou próximo demais do ruído.')
        if not self.base.force_limits:
            warnings.append('Faixa do martelo não informada: a primeira detecção usou o ruído em vez de 5% da entrada.')
        warnings.append('Ranges são recomendações para ajuste físico no condicionador, sem alteração automática da aquisição.')
        metrics = dict(strategy='two_hits', initial_detection_N=self.initial_threshold(),
                       reference_sensor=self.base.sensors[self.reference_sensor]['name'],
                       peak_N=m['peak_N'], measured_decay_s=m['decay_s'], duration_margin=.05,
                       pilot_rate=self.pilot_rate, suggested_rate=self.target_rate,
                       duration_s=proposed.duration, block_size=proposed.n,
                       frequency_spacing_hz=self.target_rate/proposed.n,
                       bytes_per_hit=8*proposed.n*(2+len(proposed.sensors)),
                       consistency_tolerance=self.tolerance,
                       windowing={'force': 'Força: recortar ruído após o contato',
                                  'response': 'Retangular: decaimento completo' if m['settled'] else 'Exponencial indicada: resposta truncada'})
        self.reset_confirmation()
        self.recommendation = SetupRecommendation(proposed, self._ranges([h]), warnings, blockers, metrics)
        self.evaluate_quality()
        return self.recommendation

    def _ranges(self, hits):
        maxima = []
        for hit in hits:
            pre = round(hit['config']['pretrigger']*hit['config']['sample_rate'])
            values = hit['data'][:, 1:]
            baseline = np.median(values[:max(2, pre//2)], axis=0)
            maxima.append(np.max(abs(values-baseline), axis=0))
        peaks = np.max(maxima, axis=0)*1.4
        channels = [(self.base.force_channel, 'Martelo', 'N', self.base.force_limits),
                    *[(s['channel'], s['name'], 'm/s²', s.get('limits')) for s in self.base.sensors]]
        return [dict(channel=channel, name=name, unit=unit, recommended_min=-float(bound),
                     recommended_max=float(bound), current_limits=limits, automatic=False)
                for (channel, name, unit, limits), bound in zip(channels, peaks)]

    def confirmation_config(self):
        if not self.recommendation or self.recommendation.blockers or not self.confirmation_noise:
            raise ValueError('Aguarde uma primeira batida válida e o ruído na taxa final.')
        c = self.recommendation.config
        # Observe beyond the proposed block so an inconsistent second decay
        # remains measurable rather than silently truncated.
        return replace(c, duration=max(self.settings.observation_seconds, 1.25*c.duration),
                       response_window='Retangular', exponential_end=1, force_window='Retangular')

    def reset_confirmation(self):
        records = list(self.confirmations)
        super().reset_confirmation()
        self.confirmations = records
        self.coherence_result = None

    def add_confirmation(self, point, data, config=None):
        c = config or self.confirmation_config()
        data = _check_record(data, c)
        m = two_hit_metrics(data, c, self.confirmation_noise, self.reference_sensor)
        physical_issues = _quality(c, data)
        issues = list(physical_issues)
        if point != self.pilots[0]['point']:
            issues.append('A segunda batida deve ocorrer no mesmo ponto da primeira.')
        if not m['settled']:
            issues.append('Decaimento da segunda batida incompleto ou não observável.')
        first = self.first_metrics
        variations = dict(peak=abs(m['peak_N']/max(first['peak_N'], 1e-12)-1),
                          decay=None if m['decay_s'] is None else abs(m['decay_s']/first['decay_s']-1),
                          contact=abs(m['contact_s']/max(first['contact_s'], 1e-12)-1))
        if variations['peak'] > self.tolerance:
            issues.append(f"Pico variou {variations['peak']:.1%} (limite {self.tolerance:.0%}).")
        if variations['decay'] is not None and variations['decay'] > self.tolerance:
            issues.append(f"Decaimento variou {variations['decay']:.1%} (limite {self.tolerance:.0%}).")
        if m['sign'] != first['sign']:
            issues.append('O sentido da força mudou entre as duas batidas.')
        record = dict(point=point, data=data, config=asdict(c), metrics=m, noise=self.confirmation_noise,
                      variations=variations, accepted=not issues, issues=issues,
                      base_issues=list(issues), spectrally_valid=not physical_issues)
        self.confirmations.append(record)
        self.validated = not issues
        self.recommendation.metrics['consistency'] = variations
        if self.validated:
            result = self.recommendation.config
            # Keep the trigger at exactly 50% of the first peak. The same 5%
            # block margin covers the slower of two consistent decays.
            post = max(first['decay_s'], m['decay_s'])*1.05
            n = math.ceil((result.pretrigger+post)*result.sample_rate)
            width = max(result.force_width, (m['force_end_s']+8/result.sample_rate)/.8)
            result = replace(result, duration=n/result.sample_rate, force_width=width)
            result.validate()
            self.recommendation.config = result
            self.recommendation.ranges = self._ranges([self.pilots[0], record])
            self.recommendation.metrics.update(duration_s=result.duration, block_size=result.n,
                measured_decay_s=max(first['decay_s'], m['decay_s']),
                frequency_spacing_hz=result.sample_rate/result.n,
                bytes_per_hit=8*result.n*(2+len(result.sensors)))
        self.evaluate_quality()
        return record

    def evaluate_quality(self):
        if not self.recommendation:
            self.validated = False
            return None
        if not 0 < self.coherence_threshold <= 1 or not 0 < self.coherence_fraction <= 1:
            raise ValueError('Os critérios de coerência devem estar entre zero e um.')
        config = self.recommendation.config
        records = self.pilots[:1]
        profile = noise_profile(_resample(self.baseline, self.pilot_rate, config.sample_rate))
        profiles = [profile]
        if self.confirmations:
            records = records+[self.confirmations[-1]]
            profiles.append(self.confirmations[-1]['noise'])
        self.coherence_result = assess_setup_coherence(records, config, profiles, self.reference_sensor,
            threshold=self.coherence_threshold, required_fraction=self.coherence_fraction)
        summary = self.coherence_result['summary']
        self.recommendation.metrics['coherence_quality'] = summary
        if self.confirmations:
            last = self.confirmations[-1]
            last['issues'] = list(last['base_issues'])+list(summary['reasons'])
            last['accepted'] = not last['issues'] and not self.recommendation.blockers and summary['passed']
            self.validated = last['accepted']
        else:
            self.validated = False
        return self.coherence_result

    def save(self, directory):
        super().save(directory)
        if self.coherence_result:
            np.savez_compressed(Path(directory)/'coerencia.npz',
                frequency=self.coherence_result['frequency'], coherence=self.coherence_result['coherence'],
                usable=self.coherence_result['usable'])
