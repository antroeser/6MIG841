"""
ihr_ros.overlay - Dessin des annotations sur une trame OpenCV.

Partage par le Devoir 1 et le Projet.

L'ancienne API MediaPipe fournissait `mp.solutions.drawing_utils`, qui dessinait le
squelette de la main. MediaPipe 1.0.1 ne l'expose plus (voir `ihr_ros.hands`), donc le
dessin est fait ici, en OpenCV pur. Le gain n'est pas seulement de combler un manque :
le texte est desormais toujours lisible, parce que chaque chaine est tracee deux fois,
une ombre epaisse puis le texte, ce qui la garde visible sur un fond clair comme sur
un fond sombre. Sans cela, l'affichage des rendus etudiants disparaissait des qu'une
main passait derriere le compteur.

Ce module ne decide rien. Il ne fait que dessiner ce qu'on lui donne.
"""

from __future__ import annotations

from typing import Any, Sequence

# Palette BGR. Cosmetique, donc pas dans ihr_config.json.
GREEN = (80, 220, 120)
RED = (70, 70, 235)
AMBER = (60, 190, 245)
WHITE = (245, 245, 245)
CYAN = (220, 200, 80)
SHADOW = (20, 20, 20)

_FONT = 0  # cv2.FONT_HERSHEY_SIMPLEX, valeur stable de l'API OpenCV


def put_text(image, text: str, origin: tuple[int, int],
             color=WHITE, scale: float = 0.6, thickness: int = 2) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Ecrire une ligne lisible sur n'importe quel fond, par double trace.

    Inputs:
        image (ndarray): trame BGR, modifiee en place
        text (str): texte a ecrire
        origin (tuple): (x, y) du coin bas gauche du texte, en pixels
        color (tuple): couleur BGR du texte
        scale (float): facteur d'echelle de la police
        thickness (int): epaisseur du trait

    Outputs:
        aucun (l'image est modifiee en place)
    --------------------------------------------------------------------------
    """
    import cv2

    cv2.putText(image, text, origin, _FONT, scale, SHADOW, thickness + 3, cv2.LINE_AA)
    cv2.putText(image, text, origin, _FONT, scale, color, thickness, cv2.LINE_AA)


def draw_hand(image, landmarks: Sequence[Any], connections: Sequence[tuple[int, int]],
              point_color=CYAN, line_color=WHITE) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Tracer le squelette d'une main a partir de ses 21 points normalises.

    Inputs:
        image (ndarray): trame BGR, modifiee en place
        landmarks (Sequence): 21 points porteurs de .x et .y normalises
        connections (Sequence): couples d'indices, voir ihr_ros.hands.hand_connections
        point_color (tuple): couleur BGR des points
        line_color (tuple): couleur BGR des segments

    Outputs:
        aucun (l'image est modifiee en place)
    --------------------------------------------------------------------------
    """
    import cv2

    height, width = image.shape[:2]
    points: list[tuple[int, int]] = []
    for landmark in landmarks:
        x = landmark.x if hasattr(landmark, "x") else landmark[0]
        y = landmark.y if hasattr(landmark, "y") else landmark[1]
        points.append((int(x * width), int(y * height)))

    for start, end in connections:
        if start < len(points) and end < len(points):
            cv2.line(image, points[start], points[end], line_color, 2, cv2.LINE_AA)
    for point in points:
        cv2.circle(image, point, 3, point_color, -1, cv2.LINE_AA)


def draw_box(image, x1: float, y1: float, x2: float, y2: float,
             label: str = "", color=AMBER, mark_center: bool = True) -> tuple[int, int]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Tracer une boite de detection, son etiquette et son centre.

    Inputs:
        image (ndarray): trame BGR, modifiee en place
        x1, y1 (float): coin superieur gauche, en pixels
        x2, y2 (float): coin inferieur droit, en pixels
        label (str): etiquette affichee au-dessus de la boite
        color (tuple): couleur BGR
        mark_center (bool): marquer le centre d'un disque

    Outputs:
        center (tuple): (x, y) du centre, en pixels entiers
    --------------------------------------------------------------------------
    """
    import cv2

    p1 = (int(x1), int(y1))
    p2 = (int(x2), int(y2))
    cv2.rectangle(image, p1, p2, color, 2, cv2.LINE_AA)
    if label:
        put_text(image, label, (p1[0], max(16, p1[1] - 8)), color, 0.55, 2)

    center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
    if mark_center:
        cv2.circle(image, center, 5, RED, -1, cv2.LINE_AA)
    return center


def draw_lines(image, lines: Sequence[tuple[str, tuple[int, int, int]]],
               origin: tuple[int, int] = (12, 34),
               line_height: int = 26, scale: float = 0.6) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Ecrire un bloc de lignes colorees, une par entree.

    Inputs:
        image (ndarray): trame BGR, modifiee en place
        lines (Sequence): couples (texte, couleur BGR)
        origin (tuple): (x, y) de la premiere ligne
        line_height (int): pas vertical entre deux lignes, en pixels
        scale (float): facteur d'echelle de la police

    Outputs:
        aucun (l'image est modifiee en place)
    --------------------------------------------------------------------------
    """
    x, y = origin
    for index, (text, color) in enumerate(lines):
        put_text(image, text, (x, y + index * line_height), color, scale, 2)
