"""
thumb_detector.py - Decision "pouce leve", isolee de la camera et de MediaPipe.

Devoir 1 du cours 6MIG841. Ce module ne sait rien d'OpenCV, rien de MediaPipe et
rien d'une webcam : il recoit 21 points de repere deja normalises et rend un verdict
motive. C'est ce qui rend le Devoir 1 testable sans materiel (workflow.md R5).

Ce que les rendus etudiants faisaient, et pourquoi le solutionnaire s'en ecarte
--------------------------------------------------------------------------------
Les quatre rendus consultes jugeaient le geste sur des comparaisons d'ordonnees dans
le repere de l'IMAGE :

  - Devoir1-2 et Projet3 : `thumb_tip.y < index_mcp.y` plus des distances comparees
    a des seuils fixes, 0.08 et 0.1 en coordonnees normalisees,
  - l'annexe du rapport WAVRIN/SZKREDKA : `thumb_tip_y < thumb_ip_y < thumb_mcp_y`,
    et un doigt tendu des que `tip_y < pip_y`,
  - Devoir1-1 : des angles entre segments, deja plus robuste, mais la detection de
    flexion restait un OU entre deux articulations.

Trois defauts en decoulent, tous reproductibles devant la camera :

  1. Un seuil de distance fixe en coordonnees normalisees depend de la DISTANCE a la
     camera. La main a 30 cm et la meme main a 1 m ne donnent pas le meme verdict.
  2. Comparer des ordonnees suppose la main VERTICALE. Une main inclinee de 45 degres
     replie ses doigts sans que leur ordonnee change dans le bon sens.
  3. Aucun des rendus ne filtrait dans le temps. Le compteur affiche clignotait entre
     deux valeurs d'une trame a l'autre, ce qui, en interaction humain-robot, est une
     commande qui part toute seule.

Le solutionnaire repond aux trois :

  1. tout se mesure en DISTANCE AU POIGNET, rapportee a la taille de la main. Une
     grandeur sans dimension ne depend plus de l'eloignement,
  2. un doigt est replie quand son extremite est PLUS PRES du poignet que son
     articulation PIP. Cette relation ne change pas quand la main tourne,
  3. un decompte n'est retenu qu'apres `debounce_frames` trames consecutives
     identiques, ce que fait la classe `ThumbCounter`.

Le seul critere qui reste lie au repere de l'image est l'orientation du pouce vers le
haut, et c'est normal : "pouce leve" est defini par rapport au monde, pas a la main.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Sequence

from ihr_ros import config
from ihr_ros.geometry import angle_between

# Indices des 21 points de repere de MediaPipe Hands. Constantes du modele, pas de
# la configuration : elles ne sont pas reglables, elles sont imposees par MediaPipe.
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

LANDMARK_COUNT = 21

#: Les quatre doigts hors pouce, (MCP, PIP, TIP).
FINGERS = (
    (INDEX_MCP, INDEX_PIP, INDEX_TIP),
    (MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP),
    (RING_MCP, RING_PIP, RING_TIP),
    (PINKY_MCP, PINKY_PIP, PINKY_TIP),
)

#: Vecteur "vers le haut" dans le repere image, dont l'origine est en haut a gauche.
IMAGE_UP = (0.0, -1.0)


@dataclass(frozen=True)
class ThumbVerdict:
    """Verdict motive pour une main."""

    is_up: bool
    thumb_extended: bool
    thumb_points_up: bool
    folded_fingers: int
    hand_scale_px: float
    thumb_angle_deg: float | None
    rejected_because: str = ""

    def explain(self) -> str:
        """Phrase courte pour l'affichage tete haute et pour le journal."""
        if self.is_up:
            return f"pouce leve ({self.folded_fingers} doigts replies)"
        return self.rejected_because or "pouce non leve"


@dataclass
class HandMetrics:
    """Mesures intermediaires, exposees pour l'enseignement et pour les tests."""

    scale_px: float
    distances_to_wrist: list[float] = field(default_factory=list)


def to_pixels(landmarks: Sequence[Any],
              image_width: int,
              image_height: int) -> list[tuple[float, float]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Convertir 21 points de repere en pixels, qu'ils viennent de MediaPipe
        (objets porteurs de .x et .y) ou d'un test (tuples (x, y) normalises).

    Inputs:
        landmarks (Sequence): 21 points, normalises dans [0, 1]
        image_width (int): largeur de l'image en pixels
        image_height (int): hauteur de l'image en pixels

    Outputs:
        points (list): 21 couples (x, y) en pixels
    --------------------------------------------------------------------------
    """
    if len(landmarks) != LANDMARK_COUNT:
        raise ValueError(
            f"MediaPipe Hands fournit {LANDMARK_COUNT} points de repere, "
            f"{len(landmarks)} recus. Une main partiellement detectee n'est pas "
            "une main : elle doit etre ecartee en amont, pas completee ici."
        )
    if image_width <= 0 or image_height <= 0:
        raise ValueError(
            f"Dimensions d'image invalides : {image_width}x{image_height}. "
            "La camera n'a probablement pas fourni de trame."
        )

    points: list[tuple[float, float]] = []
    for landmark in landmarks:
        if hasattr(landmark, "x"):
            x, y = float(landmark.x), float(landmark.y)
        else:
            x, y = float(landmark[0]), float(landmark[1])
        points.append((x * image_width, y * image_height))
    return points


#: Ancien nom prive, conserve parce que le Projet et les tests l'ont importe ainsi.
#: `to_pixels` est le nom public : un module d'un AUTRE travail qui importe un nom
#: souligne signale que l'interface n'avait pas ete pensee pour lui.
_to_pixels = to_pixels


def _distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    return math.hypot(point_b[0] - point_a[0], point_b[1] - point_a[1])


def hand_metrics(points: Sequence[tuple[float, float]]) -> HandMetrics:
    """
    --------------------------------------------------------------------------
    Purpose:
        Mesurer la main dans son propre repere. L'echelle retenue est la distance
        poignet -> base du majeur : c'est le segment le plus stable de la main, il
        ne bouge ni avec la flexion des doigts ni avec l'ouverture du pouce.
        Toutes les autres mesures lui sont rapportees, ce qui rend la decision
        independante de la distance a la camera.

    Inputs:
        points (Sequence): 21 couples (x, y) en pixels

    Outputs:
        metrics (HandMetrics): echelle en pixels et distances au poignet
    --------------------------------------------------------------------------
    """
    wrist = points[WRIST]
    scale = _distance(wrist, points[MIDDLE_MCP])
    return HandMetrics(
        scale_px=scale,
        distances_to_wrist=[_distance(wrist, p) for p in points],
    )


def count_folded_fingers(points: Sequence[tuple[float, float]],
                         metrics: HandMetrics) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Compter les doigts replies, pouce exclu. Un doigt est replie quand son
        extremite est plus proche du poignet que son articulation PIP. Cette
        comparaison est invariante par rotation de la main, contrairement a la
        comparaison d'ordonnees des rendus etudiants.

    Inputs:
        points (Sequence): 21 couples (x, y) en pixels
        metrics (HandMetrics): mesures de la main

    Outputs:
        count (int): nombre de doigts replies, entre 0 et 4
    --------------------------------------------------------------------------
    """
    distances = metrics.distances_to_wrist
    return sum(1 for _mcp, pip, tip in FINGERS if distances[tip] < distances[pip])


def is_thumb_extended(metrics: HandMetrics) -> bool:
    """
    --------------------------------------------------------------------------
    Purpose:
        Dire si le pouce est deploye. La chaine poignet -> MCP -> IP -> TIP doit
        s'eloigner du poignet a chaque articulation. Un pouce replie casse cette
        croissance.

    Inputs:
        metrics (HandMetrics): mesures de la main

    Outputs:
        extended (bool): vrai si la chaine du pouce est strictement croissante
    --------------------------------------------------------------------------
    """
    distances = metrics.distances_to_wrist
    d_mcp = distances[THUMB_MCP]
    d_ip = distances[THUMB_IP]
    d_tip = distances[THUMB_TIP]
    
    return d_mcp < d_ip < d_tip


def thumb_vertical_angle(points: Sequence[tuple[float, float]],
                         min_vector_norm: float) -> float | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Angle, en degres, entre la derniere phalange du pouce et la verticale
        ascendante de l'image. C'est le seul critere volontairement lie au repere
        image : "pouce leve" se definit par rapport au monde.

    Inputs:
        points (Sequence): 21 couples (x, y) en pixels
        min_vector_norm (float): norme sous laquelle le pouce est juge degenere

    Outputs:
        angle (float | None): angle en degres, ou None si le segment est degenere
    --------------------------------------------------------------------------
    """
    tip = points[THUMB_TIP]
    ip = points[THUMB_IP]
    vector = (tip[0] - ip[0], tip[1] - ip[1])
    angle = angle_between(vector, IMAGE_UP, min_vector_norm)
    return None if angle is None else math.degrees(angle)


def analyse_hand(landmarks: Sequence[Any],
                 image_width: int,
                 image_height: int,
                 settings: dict[str, Any] | None = None) -> ThumbVerdict:
    """
    --------------------------------------------------------------------------
    Purpose:
        Rendre le verdict complet pour une main. Les trois criteres sont evalues
        et RAPPORTES, meme quand le premier suffit a conclure : un etudiant qui
        voit lequel a echoue corrige son geste, la ou un booleen nu ne dit rien.

    Inputs:
        landmarks (Sequence): 21 points de repere normalises
        image_width (int): largeur de l'image en pixels
        image_height (int): hauteur de l'image en pixels
        settings (dict | None): section devoir1 de la configuration, lue si absente

    Outputs:
        verdict (ThumbVerdict): decision et justification
    --------------------------------------------------------------------------
    """
    cfg = settings if settings is not None else config.section("devoir1")

    points = to_pixels(landmarks, image_width, image_height)
    metrics = hand_metrics(points)

    min_scale = float(cfg["min_hand_scale_px"])
    if metrics.scale_px < min_scale:
        return ThumbVerdict(
            is_up=False, thumb_extended=False, thumb_points_up=False,
            folded_fingers=0, hand_scale_px=metrics.scale_px, thumb_angle_deg=None,
            rejected_because=(
                f"main trop petite ({metrics.scale_px:.0f} px < {min_scale:.0f} px), "
                "trop loin de la camera pour etre jugee"
            ),
        )

    extended = is_thumb_extended(metrics)
    folded = count_folded_fingers(points, metrics)
    angle = thumb_vertical_angle(points, float(cfg["min_vector_norm"]))

    max_angle = float(cfg["thumb_vertical_angle_deg"])
    points_up = angle is not None and angle <= max_angle
    required = int(cfg["required_folded_fingers"])
    enough_folded = folded >= required

    if extended and points_up and enough_folded:
        return ThumbVerdict(True, True, True, folded, metrics.scale_px, angle)

    if not extended:
        reason = "pouce replie"
    elif not points_up:
        reason = (f"pouce oriente a {angle:.0f} deg de la verticale "
                  f"(maximum {max_angle:.0f})" if angle is not None
                  else "orientation du pouce indeterminee")
    else:
        reason = f"{folded} doigt(s) replie(s) sur {required} exiges"

    return ThumbVerdict(False, extended, points_up, folded,
                        metrics.scale_px, angle, reason)


class ThumbCounter:
    """
    Compteur temporellement stable.

    Aucun rendu etudiant ne filtrait dans le temps, et le compteur affiche sautait
    entre deux valeurs d'une trame a l'autre des que la main bougeait un peu. Ici, un
    decompte doit se repeter `debounce_frames` fois de suite avant d'etre publie.
    Le prix est un retard d'autant de trames, soit un dixieme de seconde a 30 images
    par seconde, ce qui est invisible a l'usage et transforme une commande qui part
    toute seule en une commande stable.
    """

    def __init__(self, settings: dict[str, Any] | None = None):
        cfg = settings if settings is not None else config.section("devoir1")
        self._window = int(cfg["debounce_frames"])
        if self._window < 1:
            raise ValueError(
                f"debounce_frames doit valoir au moins 1, {self._window} lu dans la "
                "configuration. Zero desactiverait le filtre sans le dire."
            )
        self._history: deque[int] = deque(maxlen=self._window)
        self._stable = 0

    @property
    def window(self) -> int:
        """Nombre de trames consecutives exigees."""
        return self._window

    @property
    def stable_count(self) -> int:
        """Dernier decompte juge stable."""
        return self._stable

    def update(self, raw_count: int) -> int:
        """
        --------------------------------------------------------------------------
        Purpose:
            Soumettre le decompte brut d'une trame et obtenir le decompte stable.

        Inputs:
            raw_count (int): nombre de pouces leves vus sur cette trame

        Outputs:
            stable (int): decompte publie, inchange tant que la fenetre n'est pas
                          unanime
        --------------------------------------------------------------------------
        """
        if raw_count < 0:
            raise ValueError(f"Un decompte de pouces ne peut pas etre negatif : {raw_count}.")
        
        self._history.append(raw_count)
        
        if len(self._history) == self._window:
            if all(v == raw_count for v in self._history):
                self._stable = raw_count
                
        return self._stable

    def reset(self) -> None:
        """Vider l'historique et remettre le decompte stable a zero."""
        self._history.clear()
        self._stable = 0


def count_thumbs_up(hands_landmarks: Sequence[Sequence[Any]],
                    image_width: int,
                    image_height: int,
                    settings: dict[str, Any] | None = None) -> tuple[int, list[ThumbVerdict]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Juger toutes les mains d'une trame et rendre le decompte brut.

    Inputs:
        hands_landmarks (Sequence): une entree de 21 points par main detectee
        image_width (int): largeur de l'image en pixels
        image_height (int): hauteur de l'image en pixels
        settings (dict | None): section devoir1 de la configuration

    Outputs:
        count (int): nombre de pouces leves sur cette trame
        verdicts (list): un ThumbVerdict par main, dans l'ordre recu
    --------------------------------------------------------------------------
    """
    cfg = settings if settings is not None else config.section("devoir1")
    verdicts = [analyse_hand(hand, image_width, image_height, cfg)
                for hand in hands_landmarks]
    return sum(1 for verdict in verdicts if verdict.is_up), verdicts
