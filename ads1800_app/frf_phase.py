"""Phase presentation of complex FRFs: principal value, reliability and unwrapping.

None of these functions changes the complex H1. They only decide how its angle
is shown, so that noise near ±180° or bins without excitation do not appear as
spurious phase jumps.
"""
import numpy as np

# Defaults for the acquisition view; post-processing passes its own coherence limit.
PHASE_COHERENCE_MIN = .8
EXCITATION_DROP_DB = 20.0


def principal_deg(h):
    """Principal angle in degrees, (−180, 180]. NaN bins stay NaN."""
    return np.angle(np.asarray(h, complex), deg=True)


def excitation_mask(force_autospectrum, drop_db=EXCITATION_DROP_DB, valid=None):
    """Bins whose force autospectrum is within ``drop_db`` of its in-band maximum.

    An impact hammer rolls off (and a half-sine pulse has nulls) above the
    frequency set by the contact time. Outside this useful band, H1 is the ratio
    of two noise spectra and its phase is random.
    """
    gff = np.asarray(force_autospectrum, float)
    usable = np.isfinite(gff) & (gff > 0)
    if valid is not None:
        usable &= np.asarray(valid, bool)
    if not usable.any():
        return usable
    reference = float(np.max(gff[usable]))
    return usable & (gff >= reference*10**(-drop_db/10))


def reliable_bins(h, coherence=None, coherence_min=PHASE_COHERENCE_MIN, excitation=None):
    """Finite bins with enough coherence (when available) and excitation."""
    keep = np.isfinite(np.asarray(h, complex))
    if coherence is not None:
        coherence = np.asarray(coherence, float)
        # Coherence is NaN with fewer than two hits: do not reject on it then.
        if np.isfinite(coherence[keep]).any():
            keep &= np.nan_to_num(coherence, nan=0) >= coherence_min
    if excitation is not None:
        keep &= np.asarray(excitation, bool)
    return keep


def unwrap_deg(h, keep=None):
    """Continuous phase in degrees over the kept bins; the others are NaN.

    Gaps are bridged by unwrapping the kept bins in sequence, which assumes that
    the true phase changes by less than 180° across each gap. The curve is then
    shifted by a multiple of 360° so that its first value lies in (−180, 180].
    """
    h = np.asarray(h, complex)
    keep = np.isfinite(h) if keep is None else np.asarray(keep, bool) & np.isfinite(h)
    phase = np.full(h.shape, np.nan)
    if not keep.any():
        return phase
    unwrapped = np.unwrap(np.angle(h[keep]))
    first = np.angle(np.exp(1j*unwrapped[0]))
    phase[keep] = np.degrees(unwrapped-unwrapped[0]+first)
    return phase


def wrap_breaks(values, period=360.0):
    """Indices i where values[i-1] → values[i] is a wrap (|Δ| > period/2).

    Plots break the line there instead of drawing a vertical segment.
    """
    values = np.asarray(values, float)
    if len(values) < 2:
        return np.array([], int)
    return np.flatnonzero(np.abs(np.diff(values)) > period/2)+1
