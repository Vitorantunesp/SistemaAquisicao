"""Display components of a complex accelerance without changing its data."""
import numpy as np

from ads1800_app.frf_phase import principal_deg, unwrap_deg

FRF_VIEWS = ['Magnitude + Fase', 'Parte real + Fase', 'Parte real + Parte imaginária',
             'Magnitude + Fase desdobrada']


def frf_components(values, view, keep=None, reference=None):
    """Return ((first, label, fixed), (second, label, fixed)) for a view index.

    ``keep`` marks reliable bins (coherence/excitation). The principal phase is
    shown everywhere, since its wraps are split by the plot; the unwrapped phase
    uses only kept bins, because unwrapping through noise adds false 360° steps.
    ``reference`` (an unwrapped measured phase) shifts this curve by a multiple
    of 360° to overlay it, as for the fitted FRF in post-processing.
    """
    values = np.asarray(values, complex)
    first = (np.abs(values), 'Magnitude [(m/s²)/N]', None) if view in (0, 3) else (
        np.real(values), 'Parte real [(m/s²)/N]', None)
    if view == 2:
        second = (np.imag(values), 'Parte imaginária [(m/s²)/N]', None)
    elif view == 3:
        phase = unwrap_deg(values, keep)
        if reference is not None and len(phase):
            both = np.isfinite(phase) & np.isfinite(reference)
            if both.any():
                phase -= 360*np.round(np.median(phase[both]-np.asarray(reference)[both])/360)
        second = (phase, 'Fase desdobrada [graus]', None)
    else:
        second = (principal_deg(values), 'Fase [graus]', (-180, 180))
    return first, second
