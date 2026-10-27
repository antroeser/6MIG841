"""
trajectory.py - Devoir 2, plan05 : profil de vitesse trapezoidal.

Le Lab 1 se teleporte de point de passage en point de passage : aucune cinematique.
Ce module donne au Devoir 2 la croissance de complexite que l'enonce assigne : un
mouvement suit desormais un profil de vitesse trapezoidal (montee, plateau, descente),
plutot qu'une consigne constante publiee pendant une duree.

Fonctions PURES (aucun etat global, aucune horloge murale, workflow.md R5 et
code-style.md R19) : l'instant est toujours un argument. `calculer_profil` prend une
distance a parcourir (magnitude non signee, le sens etant decide ailleurs par
`state_machine.signer()`) et un temps total alloue, et en DERIVE la vitesse de crete
et les durees de montee/plateau/descente : vitesse et acceleration sont des resultats,
jamais des entrees directes (plan05.md, tableau des exigences de trajectory.py).

Derivation du profil trapezoidal
---------------------------------
Trois phases symetriques : montee a l'acceleration maximale `a` pendant `t1`, plateau a
la vitesse de crete `v` pendant `t2`, descente a `-a` pendant `t1` de nouveau. La duree
totale est `T = 2*t1 + t2` et la distance parcourue est l'aire sous la courbe de
vitesse :

    D = v*t1 (montee, aire triangulaire) + v*t2 (plateau) + v*t1 (descente)
      = v*(2*t1 + t2) - v*t1 = v*T - v*t1 = v*T - v*(v/a) = v*T - v^2/a

d'ou l'equation du second degre resolue par `calculer_profil` :

    v^2 - a*T*v + a*D = 0
    v = (a*T - sqrt((a*T)^2 - 4*a*D)) / 2   (racine la plus petite : c'est celle qui
                                              donne t1 <= T/2, donc un plateau >= 0)

Un discriminant negatif signifie que la distance est inatteignable dans le temps
alloue avec cette acceleration : `calculer_profil` leve plutot que de rendre un profil
silencieusement incorrect (aucun repli silencieux, code-style.md R8).

Cas degenere (plan05.md, tableau des exigences) : une distance nulle rend un profil de
duree totale nulle, sans la moindre division. Le cas est traite par un retour anticipe,
avant que la formule ci-dessus ne soit meme evaluee.

`repartir_temps` est une capacite separee et generale : distribuer un temps total entre
plusieurs etapes, proportionnellement a leur longueur (plan05.md, exigence « temps
total »). Une somme de longueurs nulle ne divise jamais par zero : elle rend une duree
nulle a chaque etape.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ProfilTrapeze:
    """
    Profil de vitesse trapezoidal, en magnitude NON SIGNEE (le sens vient d'ailleurs,
    voir `state_machine.signer()`).

    `duree_totale` est la duree reellement necessaire au profil, pas necessairement le
    `temps_total` demande a `calculer_profil` : les deux coincident toujours sauf pour
    le cas degenere `distance == 0`, ou `duree_totale` vaut 0 quel que soit le temps
    demande, puisqu'il n'y a rien a parcourir.
    """

    distance: float
    duree_totale: float
    duree_montee: float
    duree_plateau: float
    vitesse_crete: float
    acceleration: float


@dataclass(frozen=True)
class Echantillon:
    """Position et vitesse du profil a un instant donne."""

    position: float
    vitesse: float


def calculer_profil(distance: float, temps_total: float,
                    acceleration_max: float, vitesse_max: float) -> ProfilTrapeze:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire le profil trapezoidal (montee/plateau/descente) qui parcourt
        `distance` en `temps_total`, sous une acceleration bornee par
        `acceleration_max`. La vitesse de crete est un RESULTAT derive, jamais
        une entree (plan05.md).

    Inputs:
        distance (float): magnitude a parcourir, non signee, >= 0
        temps_total (float): temps alloue, en secondes ; ignore si distance == 0
        acceleration_max (float): acceleration maximale, > 0 (section
            'cinematique' de ihr_config.json)
        vitesse_max (float): vitesse de crete maximale admissible, > 0 (section
            'cinematique' de ihr_config.json)

    Outputs:
        profil (ProfilTrapeze): profil entierement determine
    --------------------------------------------------------------------------
    """
    distance = float(distance)
    if distance < 0.0:
        raise ValueError(
            f"distance negative ({distance}) : une magnitude a parcourir ne peut "
            "pas etre negative, le sens se decide ailleurs (state_machine.signer())."
        )

    acceleration_max = float(acceleration_max)
    if acceleration_max <= 0.0:
        raise ValueError(
            f"acceleration_max vaut {acceleration_max} : doit etre strictement "
            "positive pour qu'un profil de duree finie existe."
        )

    vitesse_max = float(vitesse_max)
    if vitesse_max <= 0.0:
        raise ValueError(
            f"vitesse_max vaut {vitesse_max} : doit etre strictement positive."
        )

    if distance == 0.0:
        # Cas degenere (plan05.md) : rien a parcourir, profil de duree nulle,
        # AUCUNE division n'est effectuee sur cette branche.
        return ProfilTrapeze(distance=0.0, duree_totale=0.0, duree_montee=0.0,
                             duree_plateau=0.0, vitesse_crete=0.0,
                             acceleration=acceleration_max)

    temps_total = float(temps_total)
    if temps_total <= 0.0:
        raise ValueError(
            f"temps_total vaut {temps_total} pour une distance de {distance} : "
            "une distance non nulle exige un temps alloue strictement positif."
        )

    a = acceleration_max
    discriminant = (a * temps_total) ** 2 - 4.0 * a * distance
    if discriminant < 0.0:
        raise ValueError(
            f"distance {distance} inatteignable en {temps_total} s avec une "
            f"acceleration maximale de {a} (discriminant negatif = "
            f"{discriminant:.6f}). Augmenter le temps alloue ou l'acceleration "
            "plutot que de rendre un profil incorrect."
        )

    vitesse_crete = (a * temps_total - math.sqrt(discriminant)) / 2.0

    if vitesse_crete > vitesse_max + 1e-9:
        raise ValueError(
            f"vitesse de crete calculee ({vitesse_crete:.6f}) depasse la borne "
            f"configuree ({vitesse_max}) pour une distance de {distance} en "
            f"{temps_total} s. Le profil ne peut pas respecter les deux "
            "contraintes a la fois ; augmenter le temps alloue."
        )

    duree_montee = vitesse_crete / a
    duree_plateau = max(0.0, temps_total - 2.0 * duree_montee)

    return ProfilTrapeze(distance=distance, duree_totale=temps_total,
                         duree_montee=duree_montee, duree_plateau=duree_plateau,
                         vitesse_crete=vitesse_crete, acceleration=a)


def evaluer(profil: ProfilTrapeze, instant: float) -> Echantillon:
    """
    --------------------------------------------------------------------------
    Purpose:
        Position et vitesse du profil a `instant`. Fonction pure : l'instant
        est un argument, jamais lu d'une horloge (code-style.md R19). Un
        instant avant le depart ou apres l'arrivee du profil est ramene aux
        bornes (immobile avant 0, arrive apres duree_totale), plutot que de
        lever : un appelant qui republie a une periode fixe finit toujours par
        interroger un instant legerement au-dela de la fin du mouvement.

    Inputs:
        profil (ProfilTrapeze): profil a evaluer
        instant (float): instant, en secondes depuis le debut du profil

    Outputs:
        echantillon (Echantillon): position parcourue et vitesse a cet instant
    --------------------------------------------------------------------------
    """
    t = float(instant)
    if t < 0.0:
        t = 0.0

    # Indice : trois phases : montee (a*t), plateau (vitesse de crete constante), descente (temps restant)
    # Tests : test_evaluer_ecrete_avant_le_depart_et_apres_la_fin, test_vitesse_nulle_aux_deux_bouts, test_vitesse_maximale_respectee
    raise NotImplementedError(
        "fonction 'evaluer' a implementer (voir l'enonce et les tests cites)"
    )


def repartir_temps(longueurs: list[float] | tuple[float, ...],
                   temps_total: float) -> list[float]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Repartir un temps total entre plusieurs etapes, proportionnellement a
        leur longueur (plan05.md, exigence « temps total »). Une somme de
        longueurs nulle ne divise jamais par zero : chaque etape recoit alors
        une duree nulle.

    Inputs:
        longueurs (list | tuple de float): longueur de chaque etape, >= 0
        temps_total (float): temps total a distribuer, >= 0

    Outputs:
        durees (list[float]): une duree par etape, dans le meme ordre, dont la
            somme egale temps_total (a l'arrondi flottant pres)
    --------------------------------------------------------------------------
    """
    temps_total = float(temps_total)
    if temps_total < 0.0:
        raise ValueError(f"temps_total negatif ({temps_total}).")

    valeurs = [float(longueur) for longueur in longueurs]
    if any(longueur < 0.0 for longueur in valeurs):
        raise ValueError(f"une longueur negative figure dans {valeurs}.")

    somme = sum(valeurs)
    if somme == 0.0:
        return [0.0 for _ in valeurs]

    # Chaque duree SAUF la derniere est calculee par proportion ; la derniere recoit le
    # reste (temps_total - somme des autres) plutot que sa propre proportion. Une
    # proportion independante par etape (temps_total * longueur / somme) ne garantit pas
    # une somme EXACTEMENT egale a temps_total pour des longueurs non triviales (l'arrondi
    # flottant s'accumule) ; assigner le reste au dernier element rend la somme exacte par
    # construction, quelle que soit la longueur de la liste.
    durees = [temps_total * longueur / somme for longueur in valeurs[:-1]]
    durees.append(temps_total - sum(durees))
    return durees
