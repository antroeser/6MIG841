"""
fabrique_mains.py - Fabrique de mains synthetiques pour les tests du Devoir 1.

Construit des listes de 21 points (x, y) NORMALISES dans [0, 1], la forme que
`thumb_detector.analyse_hand` recoit de MediaPipe (ou d'un test). Aucune camera,
aucun modele charge : la geometrie est ecrite a la main pour satisfaire ou violer
chaque critere du module de maniere non ambigue (workflow.md, regle R5).

Ce n'est PAS un module de test : aucune fonction ici ne commence par `test_`, donc
pytest ne le collecte pas comme suite. Les constantes numeriques ci-dessous sont des
donnees de montage (fixtures), pas de la configuration du programme : elles ne
viennent pas de ihr_config.json et n'ont pas a en venir. `code-style.md` (R0) exempte
explicitement "une valeur fixee a l'interieur d'une fixture de test".

Convention geometrique
-----------------------
Repere image : x vers la droite, y vers le BAS (comme MediaPipe et OpenCV). Un point
est place a une `distance` du poignet, dans une direction donnee par un angle en
degres mesure depuis la verticale ASCENDANTE (0 deg = tout droit vers le haut,
90 deg = horizontale, 180 deg = tout droit vers le bas) :

    x = poignet.x + distance * sin(angle)
    y = poignet.y - distance * cos(angle)

Ce choix n'est pas arbitraire : `thumb_detector.thumb_vertical_angle` mesure
exactement cet angle, entre le segment IP->TIP du pouce et la verticale ascendante
de l'image (IMAGE_UP). Fixer `angle` ici fixe donc directement `thumb_angle_deg` en
sortie du module, sans trigonometrie inverse a refaire dans les tests.

Simplification assumee et documentee : les quatre doigts hors pouce sont modelises
comme des segments RECTILIGNES depuis le poignet ; un doigt "replie" a son extremite
ramenee plus pres du poignet SUR LE MEME RAYON, plutot que par une flexion
articulaire realiste (le DIP n'entre d'ailleurs dans aucun critere de
thumb_detector.py : FINGERS ne retient que MCP/PIP/TIP). Seule la distance au
poignet compte pour `count_folded_fingers`, donc cette simplification ne change
aucun verdict teste.
"""

from __future__ import annotations

import math
from typing import Sequence

from thumb_detector import (
    INDEX_DIP,
    INDEX_MCP,
    INDEX_PIP,
    INDEX_TIP,
    LANDMARK_COUNT,
    MIDDLE_DIP,
    MIDDLE_MCP,
    MIDDLE_PIP,
    MIDDLE_TIP,
    PINKY_DIP,
    PINKY_MCP,
    PINKY_PIP,
    PINKY_TIP,
    RING_DIP,
    RING_MCP,
    RING_PIP,
    RING_TIP,
    THUMB_CMC,
    THUMB_IP,
    THUMB_MCP,
    THUMB_TIP,
    WRIST,
)

Point = tuple[float, float]

# Poignet commun a toutes les mains fabriquees ici : centre-bas de l'image, comme une
# main levee devant la camera. Choisi pour laisser assez de marge dans les deux sens
# verticaux : une rotation de 45 deg ou une mise a l'echelle 1.5x d'une main construite
# ici reste dans [0, 1] (verifie a la main pour chaque fabricant plus bas).
_POIGNET: Point = (0.50, 0.55)

# Distances au poignet (unites normalisees) des quatre doigts hors pouce. MCP et PIP
# sont FIXES ; seul TIP change entre "etendu" et "replie", ce qui isole exactement ce
# que count_folded_fingers compare (distances[TIP] vs distances[PIP], thumb_detector.py).
# MIDDLE_MCP sert aussi d'echelle de reference a hand_metrics (poignet -> base du
# majeur) : 0.22 * 480 px (image carree des tests) = 105.6 px, confortablement
# au-dessus de min_hand_scale_px = 40 px (ihr_config.json, section devoir1).
_D_MCP_DOIGT = 0.22
_D_PIP_DOIGT = 0.34
_D_TIP_DOIGT_ETENDU = 0.46  # > _D_PIP_DOIGT : le doigt n'est pas replie
_D_TIP_DOIGT_REPLIE = 0.16  # < _D_PIP_DOIGT : le doigt est replie

# Angles de depart (deg depuis la verticale) des quatre doigts, pour un eventail
# plausible. N'affecte aucun verdict : count_folded_fingers ne regarde que des
# distances au poignet, jamais une direction.
_ANGLE_INDEX = -18.0
_ANGLE_MAJEUR = -6.0
_ANGLE_ANNULAIRE = 6.0
_ANGLE_AURICULAIRE = 18.0

# Distances au poignet pour le pouce. La chaine "etendue" est strictement croissante
# (is_thumb_extended compare MCP < IP < TIP) ; la chaine "repliee" casse cette
# croissance des la premiere comparaison (MCP > IP), donc quel que soit TIP.
_D_CMC_POUCE = 0.06
_D_MCP_POUCE = 0.10
_D_IP_POUCE_ETENDU = 0.16
_D_TIP_POUCE_ETENDU = 0.24
_D_IP_POUCE_REPLIE = 0.09
_D_TIP_POUCE_REPLIE = 0.07

# Chaine "en crochet" (revue finale, constat CRITIQUE) : ni parfaitement croissante ni
# parfaitement decroissante. MCP < TIP reste vrai (0.10 < 0.15), comme un pouce deploye,
# mais IP depasse TIP (0.20 > 0.15) : la chaine casse au milieu, a l'articulation, pas
# aux extremites. Distingue le vrai critere MCP < IP < TIP (faux ici) de sa version
# appauvrie MCP < TIP (vraie ici), que les deux chaines ci-dessus ne distinguent jamais.
_D_IP_POUCE_CROCHET = 0.20
_D_TIP_POUCE_CROCHET = 0.15

# Angles du pouce (deg depuis la verticale) : c'est le seul levier de
# thumb_vertical_angle, donc le seul qui distingue "leve" de "horizontal"/"vers le bas".
_ANGLE_POUCE_LEVE = 0.0
_ANGLE_POUCE_HORIZONTAL = 90.0
_ANGLE_POUCE_VERS_LE_BAS = 180.0


def _point_depuis_poignet(distance: float, angle_deg: float) -> Point:
    """Point a `distance` du poignet, dans la direction `angle_deg` depuis le haut."""
    angle = math.radians(angle_deg)
    return (
        _POIGNET[0] + distance * math.sin(angle),
        _POIGNET[1] - distance * math.cos(angle),
    )


def _doigt(angle_deg: float, d_mcp: float, d_pip: float,
           d_tip: float) -> tuple[Point, Point, Point, Point]:
    """MCP, PIP, DIP, TIP d'un doigt hors pouce, alignes sur le meme rayon depuis
    le poignet. DIP n'entre dans aucun critere de thumb_detector.py : il est place
    a mi-chemin de PIP et TIP pour rester geometriquement plausible."""
    d_dip = (d_pip + d_tip) / 2.0
    return (
        _point_depuis_poignet(d_mcp, angle_deg),
        _point_depuis_poignet(d_pip, angle_deg),
        _point_depuis_poignet(d_dip, angle_deg),
        _point_depuis_poignet(d_tip, angle_deg),
    )


def _pouce(angle_deg: float, d_cmc: float, d_mcp: float, d_ip: float,
           d_tip: float) -> tuple[Point, Point, Point, Point]:
    """CMC, MCP, IP, TIP du pouce, alignes sur le meme rayon depuis le poignet."""
    return (
        _point_depuis_poignet(d_cmc, angle_deg),
        _point_depuis_poignet(d_mcp, angle_deg),
        _point_depuis_poignet(d_ip, angle_deg),
        _point_depuis_poignet(d_tip, angle_deg),
    )


def _construire_main(*, angle_pouce: float, pouce_etendu: bool,
                     doigts_replies: bool,
                     d_ip_pouce: float | None = None,
                     d_tip_pouce: float | None = None) -> list[Point]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Assembler les 21 points d'une main synthetique a partir de trois leviers
        independants : orientation du pouce, extension du pouce, flexion des
        quatre autres doigts. Les cinq mains canoniques du module en sont des cas
        particuliers. `d_ip_pouce`/`d_tip_pouce` permettent d'ecrire une chaine de
        pouce autre que les deux formes monotones par defaut (par exemple un
        pouce "en crochet", ni croissant ni decroissant partout).

    Inputs:
        angle_pouce (float): angle du pouce, deg depuis la verticale ascendante
        pouce_etendu (bool): chaine du pouce strictement croissante si vrai, sert
            aussi de defaut pour d_ip_pouce/d_tip_pouce quand ils sont omis
        doigts_replies (bool): les quatre doigts hors pouce sont replies si vrai
        d_ip_pouce (float | None): distance IP-poignet a imposer ; par defaut,
            celle de la chaine monotone choisie par pouce_etendu
        d_tip_pouce (float | None): distance TIP-poignet a imposer ; par defaut,
            celle de la chaine monotone choisie par pouce_etendu

    Outputs:
        points (list): 21 couples (x, y) normalises, index MediaPipe standard
    --------------------------------------------------------------------------
    """
    if pouce_etendu:
        d_ip = _D_IP_POUCE_ETENDU if d_ip_pouce is None else d_ip_pouce
        d_tip = _D_TIP_POUCE_ETENDU if d_tip_pouce is None else d_tip_pouce
    else:
        d_ip = _D_IP_POUCE_REPLIE if d_ip_pouce is None else d_ip_pouce
        d_tip = _D_TIP_POUCE_REPLIE if d_tip_pouce is None else d_tip_pouce
    thumb = _pouce(angle_pouce, _D_CMC_POUCE, _D_MCP_POUCE, d_ip, d_tip)

    d_tip_doigt = _D_TIP_DOIGT_REPLIE if doigts_replies else _D_TIP_DOIGT_ETENDU
    index = _doigt(_ANGLE_INDEX, _D_MCP_DOIGT, _D_PIP_DOIGT, d_tip_doigt)
    majeur = _doigt(_ANGLE_MAJEUR, _D_MCP_DOIGT, _D_PIP_DOIGT, d_tip_doigt)
    annulaire = _doigt(_ANGLE_ANNULAIRE, _D_MCP_DOIGT, _D_PIP_DOIGT, d_tip_doigt)
    auriculaire = _doigt(_ANGLE_AURICULAIRE, _D_MCP_DOIGT, _D_PIP_DOIGT, d_tip_doigt)

    points: list[Point | None] = [None] * LANDMARK_COUNT
    points[WRIST] = _POIGNET
    (points[THUMB_CMC], points[THUMB_MCP],
     points[THUMB_IP], points[THUMB_TIP]) = thumb
    (points[INDEX_MCP], points[INDEX_PIP],
     points[INDEX_DIP], points[INDEX_TIP]) = index
    (points[MIDDLE_MCP], points[MIDDLE_PIP],
     points[MIDDLE_DIP], points[MIDDLE_TIP]) = majeur
    (points[RING_MCP], points[RING_PIP],
     points[RING_DIP], points[RING_TIP]) = annulaire
    (points[PINKY_MCP], points[PINKY_PIP],
     points[PINKY_DIP], points[PINKY_TIP]) = auriculaire

    assert all(p is not None for p in points), "index de repere oublie dans _construire_main"
    return points  # type: ignore[return-value]


def main_pouce_leve() -> list[Point]:
    """Pouce deploye et vertical, 4 doigts replies : le geste "pouce leve" -> vrai."""
    return _construire_main(angle_pouce=_ANGLE_POUCE_LEVE, pouce_etendu=True,
                            doigts_replies=True)


def main_ouverte() -> list[Point]:
    """Main grande ouverte : pouce deploye et vertical, mais aucun doigt replie -> faux."""
    return _construire_main(angle_pouce=_ANGLE_POUCE_LEVE, pouce_etendu=True,
                            doigts_replies=False)


def main_poing_ferme() -> list[Point]:
    """Poing ferme : pouce replie et 4 doigts replies, rien n'est deploye -> faux."""
    return _construire_main(angle_pouce=_ANGLE_POUCE_LEVE, pouce_etendu=False,
                            doigts_replies=True)


def main_pouce_horizontal() -> list[Point]:
    """Pouce deploye et doigts replies, mais pouce a l'horizontale -> faux."""
    return _construire_main(angle_pouce=_ANGLE_POUCE_HORIZONTAL, pouce_etendu=True,
                            doigts_replies=True)


def main_pouce_vers_le_bas() -> list[Point]:
    """Pouce deploye et doigts replies, mais pouce pointant vers le bas -> faux."""
    return _construire_main(angle_pouce=_ANGLE_POUCE_VERS_LE_BAS, pouce_etendu=True,
                            doigts_replies=True)


def main_pouce_en_crochet() -> list[Point]:
    """
    Main dont le pouce n'est ni parfaitement deploye ni parfaitement replie : la chaine
    poignet -> MCP -> IP -> TIP monte puis redescend (MCP=0.10 < IP=0.20, mais
    TIP=0.15 < IP). MCP < TIP reste vrai (comme un pouce deploye), donc une comparaison
    appauvrie qui ignorerait IP jugerait ce pouce deploye a tort. Les quatre autres
    doigts sont replies, comme un vrai pouce en crochet le serait en pratique.
    """
    return _construire_main(angle_pouce=_ANGLE_POUCE_LEVE, pouce_etendu=True,
                            doigts_replies=True,
                            d_ip_pouce=_D_IP_POUCE_CROCHET,
                            d_tip_pouce=_D_TIP_POUCE_CROCHET)


def tourner(points: Sequence[Point], angle_rad: float) -> list[Point]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Faire tourner une main autour de son poignet, en espace NORMALISE. Sert a
        prouver qu'un critere est invariant (ou non) par rotation de la main
        devant la camera, sans jamais changer sa taille ni sa position.

    Inputs:
        points (Sequence): 21 couples (x, y) normalises, poignet a l'index 0
        angle_rad (float): angle de rotation, radians (matrice de rotation standard)

    Outputs:
        points (list): 21 couples (x, y) tournes, nouvelle liste (aucune mutation
                       des points recus)
    --------------------------------------------------------------------------
    """
    wrist = points[0]
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    tournes: list[Point] = []
    for x, y in points:
        dx, dy = x - wrist[0], y - wrist[1]
        tournes.append((
            wrist[0] + dx * cos_a - dy * sin_a,
            wrist[1] + dx * sin_a + dy * cos_a,
        ))
    return tournes


def mettre_a_echelle(points: Sequence[Point], facteur: float) -> list[Point]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Changer la taille d'une main autour de son poignet, en espace NORMALISE.
        Simule un eloignement (facteur < 1) ou un rapprochement (facteur > 1) de
        la camera, sans changer ni sa forme ni son orientation.

    Inputs:
        points (Sequence): 21 couples (x, y) normalises, poignet a l'index 0
        facteur (float): facteur d'echelle, positif ; 1.0 laisse la main inchangee

    Outputs:
        points (list): 21 couples (x, y) mis a l'echelle, nouvelle liste (aucune
                       mutation des points recus)
    --------------------------------------------------------------------------
    """
    wrist = points[0]
    return [
        (wrist[0] + (x - wrist[0]) * facteur, wrist[1] + (y - wrist[1]) * facteur)
        for x, y in points
    ]
