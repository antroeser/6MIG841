"""
faux_speech_recognition.py - Faux module speech_recognition pour les tests du Devoir 2.

Mis a jour le 2026-09-19 (.sdd/6mig841-ameliorations/stt-local-report.md) : la
reconnaissance vocale n'est plus recognize_google mais faster-whisper, en dehors de ce
module (voir voice.charger_transcripteur_whisper). `recognize_google` et les exceptions
`UnknownValueError`/`RequestError` sont donc RETIREES, plus rien ne les appelle.

`voice.MicrophoneInput` capture desormais par lecture continue d'un flux PyAudio (via
`sr.Microphone`, jamais par `Recognizer.listen()`), jusqu'a l'appui sur Entree par
l'etudiant : `FauxMicrophone` expose `.stream.read(size)`, `.CHUNK`, `.SAMPLE_RATE`
et `.SAMPLE_WIDTH`, exactement comme le vrai `sr.Microphone` apres `__enter__`.
`FauxAudioData` reste l'equivalent factice de `sr.AudioData(frame_data, sample_rate,
sample_width)`. `diagnostic_micro.py` utilise encore `Recognizer` (calibration et
`record()`, pour `mesurer_amplitude`) et `AudioFile` (pour rejouer un WAV synthetique
dans la bissection) : ces deux points restent factices ici.

AUCUN micro ni reseau reel n'est jamais touche par les tests qui utilisent ce module
(workflow.md R5).

Ce fichier n'est PAS un module de test : aucune fonction ni classe ne s'appelle `test_*`.
"""

from __future__ import annotations

from typing import Any


class FauxAudioData:
    """Equivalent factice de sr.AudioData(frame_data, sample_rate, sample_width)."""

    def __init__(self, frame_data: bytes, sample_rate: int = 16000,
                 sample_width: int = 2) -> None:
        self.frame_data = frame_data
        self.sample_rate = sample_rate
        self.sample_width = sample_width

    def get_wav_data(self) -> bytes:
        """Suffisant pour les tests : le contenu importe peu, seule sa presence compte."""
        return self.frame_data


class FauxRecognizer:
    """
    Faux Recognizer configurable : calibration et enregistrement sont des appels
    enregistres, jamais du vrai audio (utilise par diagnostic_micro.mesurer_amplitude).
    """

    def __init__(self, frame_data: bytes = b"", energy_threshold: float = 100.0) -> None:
        self.energy_threshold = energy_threshold
        self._frame_data = frame_data
        self.appels_calibration: list[float] = []
        self.appels_enregistrement: list[float | None] = []

    def adjust_for_ambient_noise(self, source: Any, duration: float) -> None:
        self.appels_calibration.append(duration)

    def record(self, source: Any, duration: float | None = None) -> FauxAudioData:
        self.appels_enregistrement.append(duration)
        return FauxAudioData(self._frame_data)


class _FausseSourcePyAudio:
    def get_default_input_device_info(self) -> dict[str, Any]:
        return {"index": 1, "name": "Peripherique 1 (factice)"}

    def terminate(self) -> None:
        pass


class _FauxModulePyAudio:
    def PyAudio(self) -> _FausseSourcePyAudio:
        return _FausseSourcePyAudio()


class FauxMicrophoneStream:
    """
    Flux factice lu par le fil d'acquisition de `MicrophoneInput._lire_audio` :
    `read(size)` rend une trame fixe, autant de fois qu'on l'appelle. Le nombre
    d'appels enregistres permet de verifier qu'un test a bien laisse le fil lire
    au moins une trame avant l'appui sur Entree.
    """

    def __init__(self, trame: bytes = b"\x00\x00" * 160) -> None:
        self._trame = trame
        self.appels_lecture = 0

    def read(self, size: int) -> bytes:
        self.appels_lecture += 1
        return self._trame


class FauxMicrophone:
    """
    Faux sr.Microphone : un context manager qui n'ouvre rien de reel. Expose
    `.stream`, `.CHUNK`, `.SAMPLE_RATE`, `.SAMPLE_WIDTH` a la sortie de `__enter__`,
    exactement comme le vrai sr.Microphone.
    """

    noms_enumeres: list[str] = ["Peripherique 0 (factice)", "Peripherique 1 (factice)"]

    def __init__(self, device_index: int | None = None,
                 trame: bytes = b"\x00\x00" * 160) -> None:
        self.device_index = device_index
        self.CHUNK = 1024
        self.SAMPLE_RATE = 16000
        self.SAMPLE_WIDTH = 2
        self.stream = FauxMicrophoneStream(trame)

    def __enter__(self) -> "FauxMicrophone":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        return False

    @classmethod
    def list_microphone_names(cls) -> list[str]:
        return list(cls.noms_enumeres)

    @staticmethod
    def get_pyaudio() -> _FauxModulePyAudio:
        return _FauxModulePyAudio()


class FauxAudioFile:
    """Faux sr.AudioFile : un context manager qui ne lit aucun fichier reel."""

    def __init__(self, chemin: str) -> None:
        self.chemin = chemin

    def __enter__(self) -> "FauxAudioFile":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        return False


def construire_faux_module(
    frame_data: bytes = b"",
    energy_threshold: float = 100.0,
    trame_microphone: bytes = b"\x00\x00" * 160,
) -> Any:
    """
    --------------------------------------------------------------------------
    Purpose:
        Assembler un faux module speech_recognition complet, utilisable partout
        ou diagnostic_micro et voice.MicrophoneInput attendent `sr`.

    Inputs:
        frame_data (bytes): trame brute que Recognizer.record() doit rendre
            (diagnostic_micro.mesurer_amplitude)
        energy_threshold (float): seuil d'energie rendu apres calibration
        trame_microphone (bytes): trame rendue par Microphone().stream.read()
            (voice.MicrophoneInput, fil d'acquisition continue)

    Outputs:
        module (types.SimpleNamespace): objet portant les memes attributs que le
            vrai module speech_recognition
    --------------------------------------------------------------------------
    """
    import types

    recognizer_construit = FauxRecognizer(
        frame_data=frame_data,
        energy_threshold=energy_threshold,
    )

    class _MicrophoneConfigure(FauxMicrophone):
        """Sous-classe qui fige la trame de ce faux module, sans changer la
        signature (device_index=None) que le vrai sr.Microphone() attend."""

        def __init__(self, device_index: int | None = None) -> None:
            super().__init__(device_index=device_index, trame=trame_microphone)

    module = types.SimpleNamespace()
    module.Microphone = _MicrophoneConfigure
    module.AudioFile = FauxAudioFile
    module.AudioData = FauxAudioData
    module.Recognizer = lambda: recognizer_construit
    return module
