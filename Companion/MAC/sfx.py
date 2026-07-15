"""
Tiny SFX player for the Companion.

Scans a folder for .wav files and maps them to UX events by filename:
  * death : "...Ascending Pop..."  (only the death animation)
  * cursor: "...Menu Cursor..."    (opening the menu / waking / moving between
                                    menu items)
  * select: "...Select Confirm..." (choosing an item)
  * poof  : "...Puff/Disappear..." (going to sleep)
  * poop  : "...Single Mouth Pop..." (the poop easter egg)

Anything missing falls back to another available sound, so it still makes
noise even if you rename files. WAV only (QSoundEffect = low latency, can
overlap). If QtMultimedia is unavailable it silently does nothing.
"""

import os

from PySide6 import QtCore

try:
    from PySide6.QtMultimedia import QSoundEffect
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False


class Sfx:
    def __init__(self, folder, volume=0.6):
        self._effects = {}
        self._keep = []
        if not _AVAILABLE or not folder or not os.path.isdir(folder):
            return
        files = [os.path.join(folder, f) for f in os.listdir(folder)
                 if os.path.splitext(f)[1].lower() == ".wav"]
        if not files:
            return
        low = {f: os.path.basename(f).lower() for f in files}

        def find(*subs):
            for sub in subs:
                for f in files:
                    if sub in low[f]:
                        return f
            return None

        death = find("ascending pop", "pop", "death")
        non_death = [f for f in files if f != death] or files
        fallback = non_death[0]
        mapping = {
            "death": death,
            "cursor": find("menu cursor", "cursor", "click") or fallback,
            "select": find("select confirm", "confirm", "select") or fallback,
            "poof": find("puff", "disappear", "magical") or fallback,
            "poop": find("single mouth pop", "mouth pop", "explainer") or fallback,
        }
        for key, path in mapping.items():
            if not path:
                continue
            eff = QSoundEffect()
            eff.setSource(QtCore.QUrl.fromLocalFile(path))
            eff.setVolume(volume)
            self._effects[key] = eff
            self._keep.append(eff)

    def play(self, key):
        eff = self._effects.get(key)
        if eff is not None:
            try:
                eff.play()
            except Exception:
                pass
