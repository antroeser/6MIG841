"""
arcs.py - Devoir 2, plan05 : echantillonnage de l'arc et verification de collision.

La lecon que ce module porte (plan05.md)
------------------------------------------
Le Lab 1 prouve qu'un SEGMENT est libre : ses trois planificateurs (A*, Theta*,
D*-Lite) raisonnent sur des lignes droites entre points de passage, sans aucune
cinematique. Le Devoir 2 ajoute la cinematique : des qu'une vitesse lineaire et une
vitesse angulaire sont commandees SIMULTANEMENT, la trajectoire reellement parcourue
est un ARC, pas la ligne droite que le planificateur a declaree libre. Un arc peut donc
entrer dans un obstacle que le segment evitait.

Consequence de conception : l'arc doit etre ECHANTILLONNE et chaque echantillon testE
contre l'obstacle. Une collision est signalee bruyamment (son instant, sa position),
jamais silencieusement acceptee, lissee ou rognee (code-style.md R8).

Fonctions PURES (workflow.md R5, code-style.md R19) : la pose de depart et l'obstacle
sont des arguments, jamais un etat global ni une lecture de capteur. `arcs.py` ne
connait rien du catalogue d'actions du Devoir 2 ni du sens (is_forward/is_clockwise) :
il recoit deux profils de `trajectory.py` (magnitudes non signees) et un multiplicateur
de sens par axe, ce qui le garde reutilisable et testable independamment de
`state_machine.py`.

Modele cinematique : le modele unicycle standard, integre par Euler explicite au pas
`resolution_s` (section 'cinematique' de ihr_config.json) :

    dx = v(t) * cos(theta) * dt
    dy = v(t) * sin(theta) * dt
    dtheta = w(t) * dt

ou v(t) et w(t) sont les vitesses lineaire et angulaire SIGNEES a l'instant t, lues sur
les deux profils simultanement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from trajectory import ProfilTrapeze, evaluer


@dataclass(frozen=True)
class Obstacle:
    """Obstacle circulaire du plan turtlesim : centre et rayon, en unites turtlesim."""

    x: float
    y: float
    rayon: float


@dataclass(frozen=True)
class EchantillonArc:
    """Pose echantillonnee a un instant du parcours de l'arc."""

    instant: float
    x: float
    y: float
    theta: float


@dataclass(frozen=True)
class Collision:
    """Premiere collision detectee sur l'arc : son instant et sa position."""

    instant: float
    x: float
    y: float


@dataclass(frozen=True)
class ResultatArc:
    """
    Trajectoire echantillonnee et, s'il y en a une, la PREMIERE collision. Quand une
    collision est trouvee, l'echantillonnage s'arrete la : rien n'est avale, et rien
    n'est simule au-dela d'un point ou le robot a deja heurte.
    """

    echantillons: tuple[EchantillonArc, ...]
    collision: Collision | None


def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _en_collision(x: float, y: float, obstacle: Obstacle | None,
                  tolerance_collision: float) -> bool:
    if obstacle is None:
        return False
    return _distance(x, y, obstacle.x, obstacle.y) <= obstacle.rayon + tolerance_collision


def echantillonner_arc(pose_depart: tuple[float, float, float],
                       profil_lineaire: ProfilTrapeze, sens_lineaire: float,
                       profil_angulaire: ProfilTrapeze, sens_angulaire: float,
                       duree_etape: float, resolution_s: float,
                       obstacle: Obstacle | None,
                       tolerance_collision: float) -> ResultatArc:
    """
    --------------------------------------------------------------------------
    Purpose:
        Integrer la pose de la tortue le long de l'arc decrit par les deux
        profils simultanes, a la resolution configuree, sur toute la duree de
        l'etape, et signaler la PREMIERE collision avec `obstacle` s'il y en a
        une. Sans obstacle declare, aucune collision n'est possible et la
        fonction ne leve jamais pour ce motif (plan05.md, exigence « absence
        d'obstacle »).

    Inputs:
        pose_depart (tuple): (x, y, theta) au debut de l'etape, en unites
            turtlesim et radians
        profil_lineaire (ProfilTrapeze): profil de vitesse lineaire, magnitude
            non signee (trajectory.calculer_profil)
        sens_lineaire (float): +1.0 pour avancer, -1.0 pour reculer
            (state_machine.signer() en decide, jamais ce module)
        profil_angulaire (ProfilTrapeze): profil de vitesse angulaire,
            magnitude non signee
        sens_angulaire (float): +1.0 antihoraire, -1.0 horaire (convention
            REP-103, la meme que state_machine.signer())
        duree_etape (float): duree totale de l'etape a echantillonner, en
            secondes (action.duree_s), >= 0
        resolution_s (float): pas d'echantillonnage, > 0 (section
            'cinematique' de ihr_config.json, cle resolution_echantillonnage_s)
        obstacle (Obstacle | None): obstacle a tester, aucune collision
            possible si absent
        tolerance_collision (float): marge ajoutee au rayon de l'obstacle
            (section 'cinematique', cle tolerance_collision)

    Outputs:
        resultat (ResultatArc): echantillons pris jusqu'a la fin de l'etape ou
            jusqu'a la premiere collision, et cette collision si elle existe
    --------------------------------------------------------------------------
    """
    if resolution_s <= 0.0:
        raise ValueError(
            f"resolution_s vaut {resolution_s} : doit etre strictement "
            "positive, sans quoi l'echantillonnage ne progresse jamais."
        )

    duree_etape = float(duree_etape)
    if duree_etape < 0.0:
        raise ValueError(f"duree_etape negative ({duree_etape}).")

    x, y, theta = pose_depart
    echantillons: list[EchantillonArc] = []
    collision: Collision | None = None

    # Test de la pose de depart (avant le premier pas)
    if _en_collision(x, y, obstacle, tolerance_collision):
        collision = Collision(instant=0.0, x=x, y=y)
        echantillons.append(EchantillonArc(instant=0.0, x=x, y=y, theta=theta))
        return ResultatArc(echantillons=tuple(echantillons), collision=collision)

    if duree_etape == 0.0:
        return ResultatArc(echantillons=tuple(echantillons), collision=None)

    pas = resolution_s
    t = 0.0

    # Boucle d'integration par Euler explicite
    # On avance par pas de `pas` jusqu'a `duree_etape`
    # On s'assure de ne pas depasser `duree_etape` en ajustant le dernier pas si necessaire
    while t < duree_etape:
        # Ajuster le pas pour ne pas depasser la duree totale
        dt = min(pas, duree_etape - t)

        # Evaluer les vitesses a l'instant t (modeles de profils trapezoidaux)
        # evaluer retourne un tuple (vitesse, acceleration) selon trajectory.py
        # On prend la vitesse (1er element)
        v_lineaire = sens_lineaire * evaluer(profil_lineaire, t).vitesse
        v_angulaire = sens_angulaire * evaluer(profil_angulaire, t).vitesse

        # Calculer les nouvelles positions (Euler explicite)
        # dx = v * cos(theta) * dt
        # dy = v * sin(theta) * dt
        # dtheta = w * dt
        nx = x + v_lineaire * math.cos(theta) * dt
        ny = y + v_lineaire * math.sin(theta) * dt
        ntheta = theta + v_angulaire * dt

        t_next = t + dt

        # Tester la collision a la nouvelle position AVANT de l'accepter
        if _en_collision(nx, ny, obstacle, tolerance_collision):
            collision = Collision(instant=t_next, x=nx, y=ny)
            echantillons.append(EchantillonArc(instant=t_next, x=nx, y=ny, theta=ntheta))
            return ResultatArc(echantillons=tuple(echantillons), collision=collision)

        # Pas de collision, on met a jour l'etat et on enregistre l'echantillon
        x, y, theta = nx, ny, ntheta
        t = t_next
        echantillons.append(EchantillonArc(instant=t, x=x, y=y, theta=theta))

    return ResultatArc(echantillons=tuple(echantillons), collision=None)
