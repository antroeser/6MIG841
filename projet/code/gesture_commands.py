"""
gesture_commands.py - Traduire les gestes de la main en consignes pour la tortue.

Projet de session. C'est ici que le DEVOIR 1 est reutilise : la decision "pouce leve"
et le comptage des doigts replies viennent de `thumb_detector`, sans une ligne
recopiee. Le Projet ajoute l'orientation de la main et l'arret d'urgence.

Fonctions pures, testables sans camera ni MediaPipe.

Vocabulaire gestuel
-------------------

    paume ouverte (0 doigt replie)  -> ARRET D'URGENCE, l'emporte sur tout
    pouce leve, une main            -> rotation, proportionnelle a l'inclinaison
    deux mains detectees            -> avance
    autre                           -> aucune consigne, la modalite se tait

Ce que faisait le rendu Projet2
-------------------------------
`banano.py` calculait l'orientation de la main entre le bout du pouce et la base de
l'auriculaire, puis ecrivait `cmd.angular.z = angle` : l'angle EN RADIANS devenait
directement une vitesse angulaire. Une main inclinee d'un quart de tour commandait
donc 1,57 rad/s, et une main a l'envers 3,14 rad/s. Il n'y avait ni gain, ni
saturation, ni zone morte, si bien que la tortue tournait en permanence des qu'une
main etait vue, meme immobile et droite.

Trois corrections ici : un gain et une saturation lus dans la configuration, une zone
morte autour de la verticale pour qu'une main a peu pres droite ne commande rien, et
un arret d'urgence qui n'existait dans aucun rendu.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# Le Devoir 1 est reutilise tel quel : c'est l'integration que le Projet demande.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "Devoir1" / "code"))

from ihr_ros.backends.base import Twist  # noqa: E402
from ihr_ros.geometry import angle_between  # noqa: E402

from thumb_detector import (  # noqa: E402
    PINKY_MCP,
    THUMB_TIP,
    analyse_hand,
    count_folded_fingers,
    count_thumbs_up,
    hand_metrics,
    to_pixels,
)

#: Zone morte autour de la verticale, en degres. En deca, la main est jugee droite
#: et ne commande aucune rotation. Sans elle, la main tremble et la tortue aussi.
ZONE_MORTE_DEG = 12.0

#: Vecteur vertical ascendant du repere image.
IMAGE_UP = (0.0, -1.0)


@dataclass(frozen=True)
class Geste:
    """Geste reconnu sur une trame."""

    nom: str
    twist: Twist
    urgence: bool = False
    detail: str = ""

    def describe(self) -> str:
        """Ligne courte pour l'affichage tete haute."""
        marque = "URGENCE " if self.urgence else ""
        return f"{marque}{self.nom}{' - ' + self.detail if self.detail else ''}"


def inclinaison_main(landmarks: Sequence[Any],
                     image_width: int,
                     image_height: int,
                     min_vector_norm: float) -> float | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Mesurer l'inclinaison de la main par rapport a la verticale, SIGNEE, en
        degres. Positif quand la main penche vers la gauche de l'image, ce qui
        commandera une rotation a gauche.

        Le vecteur choisi va de la base de l'auriculaire au bout du pouce, comme
        dans le rendu Projet2 : il traverse la paume et reste stable quand les
        doigts bougent.

    Inputs:
        landmarks (Sequence): 21 points de repere normalises
        image_width (int): largeur de l'image, pixels
        image_height (int): hauteur de l'image, pixels
        min_vector_norm (float): norme sous laquelle le vecteur est degenere

    Outputs:
        angle (float | None): angle signe en degres, None si degenere
    --------------------------------------------------------------------------
    """
    points = to_pixels(landmarks, image_width, image_height)
    base = points[PINKY_MCP]
    pointe = points[THUMB_TIP]
    vecteur = (pointe[0] - base[0], pointe[1] - base[1])

    amplitude = angle_between(vecteur, IMAGE_UP, min_vector_norm)
    if amplitude is None:
        return None

    # Le produit vectoriel en 2D donne le SENS. `angle_between` rend une amplitude
    # non signee, qui ne distingue pas une main penchee a gauche d'une main penchee
    # a droite : sans ce signe, la tortue tournerait toujours du meme cote.
    croix = vecteur[0] * IMAGE_UP[1] - vecteur[1] * IMAGE_UP[0]
    signe = -1.0 if croix > 0 else 1.0
    return math.degrees(amplitude) * signe


def reconnaitre(hands_landmarks: Sequence[Sequence[Any]],
                image_width: int,
                image_height: int,
                devoir1_cfg: dict[str, Any],
                projet_cfg: dict[str, Any]) -> Geste | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Reconnaitre le geste d'une trame et en faire une consigne.

        L'ordre d'evaluation EST la regle de securite : la paume ouverte est
        cherchee en premier, sur TOUTES les mains, avant tout autre geste. Un
        arret d'urgence que l'on ne verifie qu'en dernier n'en est pas un.

    Inputs:
        hands_landmarks (Sequence): une entree de 21 points par main detectee
        image_width (int): largeur de l'image, pixels
        image_height (int): hauteur de l'image, pixels
        devoir1_cfg (dict): section devoir1, pour la decision "pouce leve"
        projet_cfg (dict): section projet, pour les gains et les seuils

    Outputs:
        geste (Geste | None): geste reconnu, None si aucun
    --------------------------------------------------------------------------
    """
    if not hands_landmarks:
        return None

    # 1. ARRET D'URGENCE : paume ouverte (0 doigt replie) sur TOUTES les mains.
    # L'ordre d'evaluation EST la regle de securite.
    for hand in hands_landmarks:
        verdict = analyse_hand(hand, image_width, image_height, devoir1_cfg)
        if verdict.folded_fingers == 0:
            return Geste(
                nom="arret_urgence",
                twist=Twist(0.0, 0.0),
                urgence=True,
                detail="paume ouverte"
            )

    # 2. AVANCE : deux mains detectees (ni l'une ni l'autre ouverte).
    if len(hands_landmarks) >= 2:
        # La vitesse lineaire est lue dans la configuration (R0).
        # Si la cle n'existe pas, on leve une erreur explicite (R3).
        if "vitesse_lineaire_max" not in projet_cfg:
            raise ValueError("La cle 'vitesse_lineaire_max' est absente de la configuration 'projet'.")
        vitesse_lineaire = float(projet_cfg["vitesse_lineaire_max"])
        return Geste(
            nom="avance",
            twist=Twist(linear_x=vitesse_lineaire, angular_z=0.0),
            urgence=False
        )

    # 3. ROTATION : une main, pouce leve, orientation selon l'inclinaison.
    # On cherche une main avec le pouce leve.
    pouce_leve_hand = None
    for hand in hands_landmarks:
        verdict = analyse_hand(hand, image_width, image_height, devoir1_cfg)
        if verdict.is_up:
            pouce_leve_hand = hand
            break

    if pouce_leve_hand is None:
        return None

    # Calcul de l'inclinaison.
    if "min_vector_norm" not in devoir1_cfg:
        raise ValueError("La cle 'min_vector_norm' est absente de la configuration 'devoir1'.")
    min_norm = float(devoir1_cfg["min_vector_norm"])
    
    angle = inclinaison_main(pouce_leve_hand, image_width, image_height, min_norm)
    if angle is None:
        return None

    # Zone morte : si l'angle est dans la zone morte, on ne commande rien.
    if abs(angle) < ZONE_MORTE_DEG:
        return Geste(
            nom="pouce_leve_neutre",
            twist=Twist(0.0, 0.0),
            urgence=False,
            detail=f"inclinaison {angle:.1f} deg (zone morte)"
        )

    # Calcul de la vitesse angulaire avec gain et saturation.
    if "angular_gain" not in projet_cfg:
        raise ValueError("La cle 'angular_gain' est absente de la configuration 'projet'.")
    if "vitesse_angulaire_max" not in projet_cfg:
        raise ValueError("La cle 'vitesse_angulaire_max' est absente de la configuration 'projet'.")
    
    gain = float(projet_cfg["angular_gain"])
    v_max = float(projet_cfg["vitesse_angulaire_max"])
    
    # L'angle est en degres, on le convertit en radians pour le calcul.
    angle_rad = math.radians(angle)
    angular_z = gain * angle_rad
    
    # Saturation.
    if angular_z > v_max:
        angular_z = v_max
    elif angular_z < -v_max:
        angular_z = -v_max

    return Geste(
        nom="pouce_leve_rotation",
        twist=Twist(linear_x=0.0, angular_z=angular_z),
        urgence=False,
        detail=f"inclinaison {angle:.1f} deg"
    )
