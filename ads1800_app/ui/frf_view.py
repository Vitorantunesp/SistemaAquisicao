"""Display components of a complex accelerance without changing its data."""
import numpy as np

FRF_VIEWS = ['Magnitude + Fase', 'Parte real + Fase', 'Parte real + Parte imaginária']


def frf_components(values, view):
    first = (np.abs(values), 'Magnitude [(m/s²)/N]', None) if view == 0 else (
        np.real(values), 'Parte real [(m/s²)/N]', None)
    second = (np.imag(values), 'Parte imaginária [(m/s²)/N]', None) if view == 2 else (
        np.angle(values, deg=True), 'Fase [graus]', (-180, 180))
    return first, second
