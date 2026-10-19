"""
ihr_ros.face - Suivi de visage MediaPipe, API Tasks, avec blendshapes.

Ajoute pour l'extension "emotion" du Devoir 1 (reconnaissance d'emotion faciale),
sur le meme patron que `ihr_ros.hands` : un fichier modele `.task` telecharge une
fois, et un horodatage VIDEO strictement croissant gere par la classe.

Pourquoi les blendshapes plutot qu'un modele entraine
------------------------------------------------------
Les deux depots consultes (Life-Experimentalist/Facial-Emotion-Detector,
MekhyW/Facial-Emotion-Classification) entrainent un classifieur (SVM, GNN) sur des
images ou sur les coordonnees brutes des points du visage. MekhyW documente une
troisieme approche, plus simple, qui n'entraine rien de nouveau : le modele
`face_landmarker` de MediaPipe peut rendre directement 52 "blendshapes", des scores
de style ARKit (`mouthSmileLeft`, `browDownLeft`, `jawOpen`, ...) deja normalises et
deja invariants a la pose et a l'eclairage. C'est cette troisieme voie qui est
reprise ici : `emotion_detector.py` combine quelques-uns de ces scores par des
regles, exactement comme `thumb_detector.py` combine des distances au poignet.
Aucun modele a entrainer, aucune image a collecter : le seul fichier ajoute est le
modele officiel de Google, au meme endroit que celui des mains.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

#: Modele officiel, variante float16, meme convention de nommage que hands.py.
MODEL_FILENAME = "face_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)

_DOWNLOAD_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class TrackedFace:
    """Un visage detecte : ses points de repere et ses scores de blendshapes."""

    landmarks: Sequence[Any]
    blendshapes: dict[str, float] = field(default_factory=dict)


def model_dir() -> Path:
    """Repertoire ou vivent les modeles telecharges (partage avec hands.py)."""
    return Path(__file__).resolve().parent.parent / "models"


def ensure_model(path: Path | None = None, download: bool = True) -> Path:
    """
    --------------------------------------------------------------------------
    Purpose:
        Garantir la presence du fichier de modele, en le telechargeant au besoin.
        Un modele absent est une erreur explicite qui donne l'URL, jamais un repli
        silencieux vers une detection degradee (meme contrat que hands.ensure_model).

    Inputs:
        path (Path | None): chemin du modele, defaut models/face_landmarker.task
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


class FaceTracker:
    """
    Suivi de visage sur flux video, API Tasks de MediaPipe, blendshapes actives.

    S'utilise comme gestionnaire de contexte, exactement comme `HandTracker` :

        with FaceTracker(max_faces=1) as tracker:
            for frame in frames:
                for face in tracker.process(frame):
                    ...
    """

    def __init__(self,
                 max_faces: int,
                 min_detection_confidence: float,
                 min_presence_confidence: float | None = None,
                 min_tracking_confidence: float = 0.5,
                 model_path: Path | None = None,
                 download_model: bool = True):
        """
        --------------------------------------------------------------------------
        Purpose:
            Charger le modele et preparer le detecteur en mode VIDEO, blendshapes
            de sortie actives.

        Inputs:
            max_faces (int): nombre maximal de visages suivis
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

        self._model_path = ensure_model(model_path, download=download_model)

        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self._model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=int(max_faces),
            min_face_detection_confidence=float(min_detection_confidence),
            min_face_presence_confidence=float(
                min_presence_confidence if min_presence_confidence is not None
                else min_detection_confidence
            ),
            min_tracking_confidence=float(min_tracking_confidence),
            output_face_blendshapes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

        # Meme raison que HandTracker : un horodatage VIDEO strictement croissant,
        # independant de l'horloge murale.
        self._timestamp_ms = 0
        self._closed = False

    @property
    def model_path(self) -> Path:
        """Chemin du modele reellement charge."""
        return self._model_path

    def process(self, bgr_frame, timestamp_ms: int | None = None) -> list[TrackedFace]:
        """
        --------------------------------------------------------------------------
        Purpose:
            Detecter les visages d'une trame BGR issue d'OpenCV.

        Inputs:
            bgr_frame (ndarray): trame BGR, telle que la rend cv2.VideoCapture.read
            timestamp_ms (int | None): horodatage impose, sinon un compteur interne

        Outputs:
            faces (list): une TrackedFace par visage detecte
        --------------------------------------------------------------------------
        """
        if self._closed:
            raise RuntimeError("FaceTracker deja ferme.")

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

        faces: list[TrackedFace] = []
        blendshapes_list = result.face_blendshapes or []
        for index, landmarks in enumerate(result.face_landmarks or []):
            scores: dict[str, float] = {}
            if index < len(blendshapes_list):
                scores = {c.category_name: float(c.score) for c in blendshapes_list[index]}
            faces.append(TrackedFace(landmarks=landmarks, blendshapes=scores))
        return faces

    def close(self) -> None:
        """Liberer le detecteur. Appelable deux fois sans effet."""
        if self._closed:
            return
        self._closed = True
        close = getattr(self._landmarker, "close", None)
        if close is not None:
            close()

    def __enter__(self) -> "FaceTracker":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
