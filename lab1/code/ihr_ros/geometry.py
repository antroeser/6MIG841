"""
ihr_ros.geometry - Geometrie plane partagee par les trois travaux.

Etage 0 du solutionnaire. Le Devoir 1 y prend ses angles de doigts, le Projet ses
erreurs de cap et ses conversions image -> turtlesim. Aucune dependance externe :
ces fonctions sont testables sans camera, sans ROS2 et sans numpy.
"""

from __future__ import annotations

import math

# Constantes mathematiques du domaine, pas de la configuration.
_FULL_TURN = 2.0 * math.pi


def normalize_angle(angle_rad: float) -> float:
    """
    --------------------------------------------------------------------------
    Purpose:
        Ramener un angle dans l'intervalle ]-pi, pi], forme attendue par une
        commande de cap. Sans cette normalisation, une erreur de cap de +350 deg
        fait tourner la tortue dans le mauvais sens sur presque un tour complet.

    Inputs:
        angle_rad (float): angle en radians, quelconque

    Outputs:
        angle (float): angle equivalent dans ]-pi, pi]
    --------------------------------------------------------------------------
    """
    wrapped = math.fmod(angle_rad + math.pi, _FULL_TURN)
    if wrapped <= 0.0:
        wrapped += _FULL_TURN
    return wrapped - math.pi


def distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    """
    --------------------------------------------------------------------------
    Purpose:
        Distance euclidienne entre deux points du plan.

    Inputs:
        point_a (tuple): (x, y)
        point_b (tuple): (x, y)

    Outputs:
        distance (float): distance, dans l'unite des entrees
    --------------------------------------------------------------------------
    """
    return math.hypot(point_b[0] - point_a[0], point_b[1] - point_a[1])


def bearing(origin: tuple[float, float], target: tuple[float, float]) -> float:
    """
    --------------------------------------------------------------------------
    Purpose:
        Cap absolu, en radians, de `origin` vers `target`.

    Inputs:
        origin (tuple): (x, y) du point de depart
        target (tuple): (x, y) du point vise

    Outputs:
        bearing (float): angle dans ]-pi, pi], 0 vers les x croissants
    --------------------------------------------------------------------------
    """
    return math.atan2(target[1] - origin[1], target[0] - origin[0])


def heading_error(current_theta: float, origin: tuple[float, float],
                  target: tuple[float, float]) -> float:
    """
    --------------------------------------------------------------------------
    Purpose:
        Erreur de cap normalisee entre l'orientation courante et la direction de
        la cible. C'est l'entree du correcteur proportionnel du Projet.

    Inputs:
        current_theta (float): orientation courante, radians
        origin (tuple): (x, y) position courante
        target (tuple): (x, y) position visee

    Outputs:
        error (float): erreur dans ]-pi, pi], positive pour tourner a gauche
    --------------------------------------------------------------------------
    """
    return normalize_angle(bearing(origin, target) - current_theta)


def angle_between(vector_u: tuple[float, float],
                  vector_v: tuple[float, float],
                  min_norm: float) -> float | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Angle non signe entre deux vecteurs du plan, en radians.

    Inputs:
        vector_u (tuple): (x, y)
        vector_v (tuple): (x, y)
        min_norm (float): norme sous laquelle un vecteur est juge degenere

    Outputs:
        angle (float | None): angle dans [0, pi], ou None si un vecteur est degenere
    --------------------------------------------------------------------------
    """
    norm_u = math.hypot(*vector_u)
    norm_v = math.hypot(*vector_v)
    if norm_u < min_norm or norm_v < min_norm:
        return None
    dot = vector_u[0] * vector_v[0] + vector_u[1] * vector_v[1]
    cosine = max(-1.0, min(1.0, dot / (norm_u * norm_v)))
    return math.acos(cosine)


def angle_at_vertex(point_a: tuple[float, float],
                    vertex: tuple[float, float],
                    point_c: tuple[float, float],
                    min_norm: float) -> float | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Angle non signe forme en `vertex` par les segments vers `point_a` et
        `point_c`. Sert a mesurer la flexion d'une articulation de doigt.

    Inputs:
        point_a (tuple): (x, y) premiere extremite
        vertex (tuple): (x, y) sommet de l'angle
        point_c (tuple): (x, y) seconde extremite
        min_norm (float): norme sous laquelle un segment est juge degenere

    Outputs:
        angle (float | None): angle dans [0, pi], ou None si un segment est degenere
    --------------------------------------------------------------------------
    """
    side_a = (point_a[0] - vertex[0], point_a[1] - vertex[1])
    side_c = (point_c[0] - vertex[0], point_c[1] - vertex[1])
    return angle_between(side_a, side_c, min_norm)


def image_to_turtlesim(pixel: tuple[float, float],
                       image_width: int,
                       image_height: int,
                       canvas_width: float,
                       canvas_height: float) -> tuple[float, float]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Convertir un point image en coordonnees turtlesim. L'axe y est inverse :
        l'origine image est en haut a gauche, celle de turtlesim en bas a gauche.
        Cette inversion est la source d'erreur la plus frequente du Projet, une
        tortue qui part vers le bas quand l'objet monte.

    Inputs:
        pixel (tuple): (x, y) en pixels dans l'image
        image_width (int): largeur de l'image en pixels
        image_height (int): hauteur de l'image en pixels
        canvas_width (float): largeur du canevas turtlesim en unites
        canvas_height (float): hauteur du canevas turtlesim en unites

    Outputs:
        point (tuple): (x, y) en unites turtlesim, borne au canevas
    --------------------------------------------------------------------------
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError(
            f"Dimensions d'image invalides : {image_width}x{image_height}. "
            "La camera n'a probablement pas fourni de trame."
        )
    x_unit = (pixel[0] / image_width) * canvas_width
    y_unit = ((image_height - pixel[1]) / image_height) * canvas_height
    x_unit = max(0.0, min(canvas_width, x_unit))
    y_unit = max(0.0, min(canvas_height, y_unit))
    return (x_unit, y_unit)


def box_center(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Centre d'une boite englobante YOLO donnee au format xyxy.

    Inputs:
        x1, y1 (float): coin superieur gauche
        x2, y2 (float): coin inferieur droit

    Outputs:
        center (tuple): (x, y) du centre
    --------------------------------------------------------------------------
    """
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
