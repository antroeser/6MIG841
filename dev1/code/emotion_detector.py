"""
emotion_detector.py - Devoir 1 (extension) : reconnaissance d'emotion faciale.

Isole de la camera et de MediaPipe, comme thumb_detector.py : ce module ne recoit
que des scores de blendshapes deja calcules et rend un verdict motive. C'est ce qui
le rend testable sans materiel (workflow.md R5).

Pourquoi une regle plutot qu'un modele entraine
------------------------------------------------
Deux depots ont ete consultes pour cette extension :
  - github.com/Life-Experimentalist/Facial-Emotion-Detector (SVM entraine sur des
    images, via un cascade Haar puis MediaPipe),
  - github.com/MekhyW/Facial-Emotion-Classification (SVM/GNN entraines sur les
    coordonnees de points, avec une troisieme approche entrainee sur les
    blendshapes du modele `face_landmarker`).

Les deux exigent de collecter des images et d'entrainer un modele : c'est le
changement le plus important possible au code existant. La troisieme approche de
MekhyW n'entraine rien : les blendshapes que `face_landmarker` calcule deja (scores
de style ARKit, dans [0, 1], invariants a la pose et a l'eclairage) suffisent a une
regle simple, exactement comme thumb_detector.py decide a partir de distances
plutot que d'un reseau de neurones. C'est cette troisieme voie qui est reprise ici,
pour rester fidele a l'esprit du solutionnaire (une decision motivee, pas une boite
noire) et pour ne modifier que le minimum de code existant.

Cinq categories, cinq blendshapes ARKit
-----------------------------------------
Chaque categorie est la moyenne d'un petit nombre de blendshapes rendus par
`ihr_ros.face.FaceTracker`, la meme main gauche/main droite etant toujours moyennee
ensemble pour rester symetrique a un visage legerement tourne :

  - heureux   : mouthSmileLeft, mouthSmileRight (sourire),
  - triste    : mouthFrownLeft, mouthFrownRight (bouche tombante),
  - en_colere : browDownLeft, browDownRight (sourcils froncés),
  - surpris   : eyeWideLeft, eyeWideRight, jawOpen (yeux ecarquilles, bouche ouverte).

La categorie de score le plus eleve l'emporte, a condition de depasser un seuil
minimal (devoir1.emotion.min_score dans ihr_config.json) ; sinon le verdict est
"neutre". Comme pour ThumbCounter, un filtre temporel (EmotionStabilizer) evite que
l'etiquette affichee clignote d'une trame a l'autre.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Sequence

from ihr_ros import config

HEUREUX = "heureux"
TRISTE = "triste"
EN_COLERE = "en_colere"
SURPRIS = "surpris"
NEUTRE = "neutre"

#: Categories d'emotion et les blendshapes ARKit dont la moyenne les mesure.
#: Nommage `face_landmarker` officiel (voir la documentation MediaPipe Tasks).
EMOTION_BLENDSHAPES: dict[str, tuple[str, ...]] = {
    HEUREUX: ("mouthSmileLeft", "mouthSmileRight"),
    TRISTE: ("mouthFrownLeft", "mouthFrownRight"),
    EN_COLERE: ("browDownLeft", "browDownRight"),
    SURPRIS: ("eyeWideLeft", "eyeWideRight", "jawOpen"),
}


@dataclass(frozen=True)
class EmotionVerdict:
    """Verdict motive pour un visage."""

    label: str
    scores: dict[str, float] = field(default_factory=dict)

    def explain(self) -> str:
        """Phrase courte pour l'affichage tete haute et pour le journal."""
        if self.label == NEUTRE:
            return "neutre"
        return f"{self.label} ({self.scores.get(self.label, 0.0):.2f})"


def _category_score(blendshapes: dict[str, float], names: tuple[str, ...]) -> float:
    """Moyenne des scores nommes, 0.0 pour un nom absent (visage partiel)."""
    if not names:
        return 0.0
    return sum(blendshapes.get(name, 0.0) for name in names) / len(names)


def analyse_emotion(blendshapes: dict[str, float],
                    settings: dict[str, Any] | None = None) -> EmotionVerdict:
    """
    --------------------------------------------------------------------------
    Purpose:
        Rendre le verdict d'emotion pour un visage. Les quatre scores sont
        calcules et RAPPORTES, meme quand un seul suffit a conclure : la meme
        justification pedagogique que thumb_detector.analyse_hand.

    Inputs:
        blendshapes (dict): scores ARKit nommes, tels que rendus par
                            ihr_ros.face.FaceTracker (TrackedFace.blendshapes)
        settings (dict | None): section devoir1.emotion de la configuration, lue
                                si absente

    Outputs:
        verdict (EmotionVerdict): categorie retenue et scores de toutes les
                                  categories
    --------------------------------------------------------------------------
    """
    cfg = settings if settings is not None else config.section("devoir1")["emotion"]
    min_score = float(cfg["min_score"])

    scores = {label: _category_score(blendshapes, names)
              for label, names in EMOTION_BLENDSHAPES.items()}

    best_label = max(scores, key=scores.get)
    if scores[best_label] < min_score:
        return EmotionVerdict(NEUTRE, scores)
    return EmotionVerdict(best_label, scores)


def analyse_faces(faces_blendshapes: Sequence[dict[str, float]],
                  settings: dict[str, Any] | None = None) -> list[EmotionVerdict]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Juger tous les visages d'une trame.

    Inputs:
        faces_blendshapes (Sequence): un dict de blendshapes par visage detecte
        settings (dict | None): section devoir1.emotion de la configuration

    Outputs:
        verdicts (list): un EmotionVerdict par visage, dans l'ordre recu
    --------------------------------------------------------------------------
    """
    cfg = settings if settings is not None else config.section("devoir1")["emotion"]
    return [analyse_emotion(blendshapes, cfg) for blendshapes in faces_blendshapes]


class EmotionStabilizer:
    """
    Filtre temporel sur l'etiquette d'emotion, meme principe que ThumbCounter :
    une etiquette n'est publiee qu'apres `debounce_frames` trames consecutives
    identiques, ce qui evite qu'elle clignote entre deux categories voisines en
    score d'une trame a l'autre.
    """

    def __init__(self, settings: dict[str, Any] | None = None):
        cfg = settings if settings is not None else config.section("devoir1")["emotion"]
        self._window = int(cfg["debounce_frames"])
        if self._window < 1:
            raise ValueError(
                f"debounce_frames doit valoir au moins 1, {self._window} lu dans la "
                "configuration. Zero desactiverait le filtre sans le dire."
            )
        self._history: deque[str] = deque(maxlen=self._window)
        self._stable = NEUTRE

    @property
    def window(self) -> int:
        """Nombre de trames consecutives exigees."""
        return self._window

    @property
    def stable_label(self) -> str:
        """Derniere etiquette jugee stable."""
        return self._stable

    def update(self, raw_label: str) -> str:
        """
        --------------------------------------------------------------------------
        Purpose:
            Soumettre l'etiquette brute d'une trame et obtenir l'etiquette stable.

        Inputs:
            raw_label (str): etiquette vue sur cette trame (HEUREUX, TRISTE, ...)

        Outputs:
            stable (str): etiquette publiee, inchangee tant que la fenetre n'est
                          pas unanime
        --------------------------------------------------------------------------
        """
        self._history.append(str(raw_label))
        if len(self._history) == self._window and len(set(self._history)) == 1:
            self._stable = self._history[0]
        return self._stable

    def reset(self) -> None:
        """Vider l'historique et remettre l'etiquette stable a neutre."""
        self._history.clear()
        self._stable = NEUTRE
