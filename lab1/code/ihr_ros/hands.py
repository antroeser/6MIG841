"""
ihr_ros.hands - Suivi de main MediaPipe, API Tasks.

Partage par le Devoir 1 (decompte des pouces) et le Projet (gestes de commande).

Pourquoi ce module existe
-------------------------
Mesure le 2026-09-18 : les quatre rendus etudiants de 2025 appellent tous
`mp.solutions.hands`, l'ancienne API dite "Solutions". Dans MediaPipe 1.0.1, elle
n'existe plus du tout : le paquet n'expose plus que `Image`, `ImageFormat` et `tasks`,
et `import mediapipe.python.solutions` leve `ModuleNotFoundError`. Les quatre
programmes s'arretent donc sur

    AttributeError: module 'mediapipe' has no attribute 'solutions'

avant d'avoir lu une seule trame. Ce n'est pas un defaut de leur travail, c'est une
rupture d'API survenue depuis leur remise. Le solutionnaire est ecrit sur l'API
Tasks, qui est celle que Google maintient.

Deux differences pratiques avec l'ancienne API, a expliquer en seance :

  1. Le modele n'est plus embarque dans la roue Python. Il faut un fichier
     `hand_landmarker.task`, telecharge une fois (voir `ensure_model`).
  2. Le mode VIDEO exige un horodatage en millisecondes STRICTEMENT croissant a
     chaque appel. Un horodatage qui recule fait lever MediaPipe. La classe
     `HandTracker` s'en charge, c'est la principale raison pour laquelle elle
     enveloppe l'API plutot que de la laisser a nu dans les trois travaux.

Le reste du solutionnaire ne voit que `HandTracker.process(frame)`, qui rend une
liste de mains, chaque main etant une liste de 21 points porteurs de `.x`, `.y`, `.z`
normalises. C'est exactement la forme que consommait l'ancienne API, donc la logique
de decision des devoirs n'a pas eu a changer.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

#: Modele officiel, variante float16. Nom de fichier attendu par `ensure_model`.
MODEL_FILENAME = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
#: Empreinte du fichier telecharge le 2026-09-18, 7 819 105 octets.
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"

_DOWNLOAD_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class TrackedHand:
    """Une main detectee : ses 21 points, son cote, et la confiance associee."""

    landmarks: Sequence[Any]
    handedness: str
    score: float


def model_dir() -> Path:
    """Repertoire ou vivent les modeles telecharges."""
    return Path(__file__).resolve().parent.parent / "models"


def ensure_model(path: Path | None = None, download: bool = True) -> Path:
    """
    --------------------------------------------------------------------------
    Purpose:
        Garantir la presence du fichier de modele, en le telechargeant au besoin.
        Un modele absent est une erreur explicite qui donne l'URL, jamais un repli
        silencieux vers une detection degradee.

    Inputs:
        path (Path | None): chemin du modele, defaut models/hand_landmarker.task
        download (bool): autoriser le telechargement si le fichier manque

    Outputs:
        path (Path): chemin du modele, verifie present
    --------------------------------------------------------------------------
    """
    target = Path(path) if path is not None else model_dir() / MODEL_FILENAME
    if target.is_file() and target.stat().st_size > 0:
        return target

    if not download:
        raise FileNotFoundError(
            f"Modele MediaPipe absent : {target}\n"
            f"Le telecharger avec :  curl -L -o \"{target}\" {MODEL_URL}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise FileNotFoundError(
            f"Modele MediaPipe absent et telechargement impossible : {exc}\n"
            f"Le recuperer a la main :  curl -L -o \"{target}\" {MODEL_URL}"
        ) from exc

    target.write_bytes(payload)
    return target


class HandTracker:
    """
    Suivi de main sur flux video, API Tasks de MediaPipe.

    S'utilise comme gestionnaire de contexte :

        with HandTracker(max_hands=2) as tracker:
            for frame in frames:
                for hand in tracker.process(frame):
                    ...
    """

    def __init__(self,
                 max_hands: int,
                 min_detection_confidence: float,
                 min_presence_confidence: float | None = None,
                 min_tracking_confidence: float = 0.5,
                 model_path: Path | None = None,
                 download_model: bool = True):
        """
        --------------------------------------------------------------------------
        Purpose:
            Charger le modele et preparer le detecteur en mode VIDEO.

        Inputs:
            max_hands (int): nombre maximal de mains suivies
            min_detection_confidence (float): seuil de detection, dans [0, 1]
            min_presence_confidence (float | None): seuil de presence, defaut egal
                au seuil de detection
            min_tracking_confidence (float): seuil de suivi, dans [0, 1]
            model_path (Path | None): chemin du fichier .task
            download_model (bool): telecharger le modele s'il manque

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        from mediapipe.tasks import python as mp_python  # noqa: PLC0415
        from mediapipe.tasks.python import vision  # noqa: PLC0415

        self._vision = vision
        self._model_path = ensure_model(model_path, download=download_model)

        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self._model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=int(max_hands),
            min_hand_detection_confidence=float(min_detection_confidence),
            min_hand_presence_confidence=float(
                min_presence_confidence if min_presence_confidence is not None
                else min_detection_confidence
            ),
            min_tracking_confidence=float(min_tracking_confidence),
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

        # L'horodatage doit croitre strictement. Un compteur de trames fait l'affaire
        # et evite de dependre de l'horloge murale, ce qui rend le traitement d'un
        # fichier video reproductible d'une execution a l'autre.
        self._timestamp_ms = 0
        self._closed = False

    @property
    def model_path(self) -> Path:
        """Chemin du modele reellement charge."""
        return self._model_path

    def process(self, bgr_frame, timestamp_ms: int | None = None) -> list[TrackedHand]:
        """
        --------------------------------------------------------------------------
        Purpose:
            Detecter les mains d'une trame BGR issue d'OpenCV.

        Inputs:
            bgr_frame (ndarray): trame BGR, telle que la rend cv2.VideoCapture.read
            timestamp_ms (int | None): horodatage impose, sinon un compteur interne

        Outputs:
            hands (list): une TrackedHand par main detectee
        --------------------------------------------------------------------------
        """
        if self._closed:
            raise RuntimeError("HandTracker deja ferme.")

        import cv2  # noqa: PLC0415
        import mediapipe as mp  # noqa: PLC0415

        if timestamp_ms is None:
            self._timestamp_ms += 1
            stamp = self._timestamp_ms
        else:
            stamp = int(timestamp_ms)
            if stamp <= self._timestamp_ms:
                raise ValueError(
                    f"Horodatage {stamp} ms non strictement croissant "
                    f"(precedent {self._timestamp_ms} ms). Le mode VIDEO de MediaPipe "
                    "leve sur un horodatage qui recule."
                )
            self._timestamp_ms = stamp

        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, stamp)

        hands: list[TrackedHand] = []
        handedness_list = result.handedness or []
        for index, landmarks in enumerate(result.hand_landmarks or []):
            label, score = "inconnue", 0.0
            if index < len(handedness_list) and handedness_list[index]:
                category = handedness_list[index][0]
                label = str(category.category_name)
                score = float(category.score)
            hands.append(TrackedHand(landmarks=landmarks, handedness=label, score=score))
        return hands

    def close(self) -> None:
        """Liberer le detecteur. Appelable deux fois sans effet."""
        if self._closed:
            return
        self._closed = True
        close = getattr(self._landmarker, "close", None)
        if close is not None:
            close()

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def hand_connections() -> list[tuple[int, int]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Retourner les aretes du squelette de la main, pour le dessin. L'ancienne
        API exposait `mp_hands.HAND_CONNECTIONS`, l'API Tasks les range dans
        `vision.HandLandmarksConnections`.

    Inputs:
        aucun

    Outputs:
        connections (list): couples (index_depart, index_arrivee)
    --------------------------------------------------------------------------
    """
    from mediapipe.tasks.python import vision  # noqa: PLC0415

    return [(int(c.start), int(c.end))
            for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]
