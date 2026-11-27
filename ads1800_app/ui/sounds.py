"""Distinct audible cues, so the operator does not need to look at the screen.

- ready:    one short high tone - the trigger is armed, hit now.
- success:  two rising tones - hit saved and accepted.
- failure:  one long low tone - hit rejected (alert); repeat the hit.
- point:    three rising tones - point complete, moving to the next one.
- finished: long rising sequence - all points complete / configuration OK.

Tones play in a background thread (winsound.Beep blocks). Outside Windows,
or when winsound is unavailable, the system beep is used. Sounds are muted
for the offscreen Qt platform used by the automated tests, or when the
environment variable ADS1800_MUTE is set.
"""
import os
import threading

try:
    import winsound
except ImportError:  # pragma: no cover - not Windows
    winsound = None

PATTERNS = {
    'ready': [(1800, 70)],
    'success': [(1000, 90), (1500, 140)],
    'failure': [(300, 550)],
    'point': [(900, 110), (1200, 110), (1600, 220)],
    'finished': [(800, 140), (1000, 140), (1300, 140), (1700, 420)],
}

_lock = threading.Lock()


def muted():
    return bool(os.environ.get('ADS1800_MUTE')) or os.environ.get('QT_QPA_PLATFORM') == 'offscreen'


def play(kind):
    if kind not in PATTERNS:
        raise ValueError(f'Sinal sonoro desconhecido: {kind}')
    if muted():
        return
    if winsound is None:
        from PyQt6.QtWidgets import QApplication
        for _ in PATTERNS[kind]:
            QApplication.beep()
        return

    def run():
        # Serialize cues: a "point complete" never overlaps the "success" tone.
        with _lock:
            for frequency, duration in PATTERNS[kind]:
                try:
                    winsound.Beep(frequency, duration)
                except RuntimeError:
                    return
    threading.Thread(target=run, daemon=True).start()
