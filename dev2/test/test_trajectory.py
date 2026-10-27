"""
test_trajectory.py - Devoir 2, plan05 : suite du profil de vitesse trapezoidal.

Purement numerique (workflow.md R5) : aucun ROS2, aucune tortue, aucun temps reel.
Chaque test appelle trajectory.py avec un instant EXPLICITE (code-style.md R19), jamais
time.time(). Utilise la fixture `cinematique` de conftest.py (section 'cinematique' de
ihr_config.json), pour que les bornes testees soient celles que motion_node lira
reellement, plutot que des valeurs inventees ici.

Cinq des sept tests sont exiges par plan05.md (colonnes 1 a 5 du tableau des tests) :
position finale, vitesse nulle aux deux bouts, vitesse maximale respectee, distance
nulle degeneree, temps reparti proportionnellement a la longueur. Les deux derniers
sont des controles supplementaires (chemin d'echec explicite, testing.md R20).
"""

from __future__ import annotations

import math

import pytest

import trajectory


def test_position_finale_egale_la_distance_demandee(cinematique):
    """La position au dernier instant du profil egale exactement la distance demandee."""
    profil = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )

    echantillon_final = trajectory.evaluer(profil, profil.duree_totale)

    assert echantillon_final.position == pytest.approx(2.0, abs=1e-9)


def test_vitesse_nulle_aux_deux_bouts(cinematique):
    """Le mouvement demarre et finit a l'arret : vitesse nulle en t=0 et en t=duree_totale."""
    profil = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )

    depart = trajectory.evaluer(profil, 0.0)
    arrivee = trajectory.evaluer(profil, profil.duree_totale)

    assert depart.vitesse == pytest.approx(0.0, abs=1e-9)
    assert arrivee.vitesse == pytest.approx(0.0, abs=1e-9)


def test_vitesse_maximale_respectee(cinematique):
    """Le plateau du profil ne depasse jamais la vitesse maximale configuree."""
    profil = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )

    assert profil.vitesse_crete <= cinematique["vitesse_lineaire_max"] + 1e-9

    pas = 0.01
    nb_echantillons = int(profil.duree_totale / pas) + 1
    vitesses = [trajectory.evaluer(profil, i * pas).vitesse for i in range(nb_echantillons)]
    assert all(v <= cinematique["vitesse_lineaire_max"] + 1e-9 for v in vitesses)


def test_evaluer_a_l_interieur_de_la_descente_egale_la_formule_cinematique(cinematique):
    """
    Revue finale (constat CRITIQUE) : tous les tests qui appellent `evaluer` a une
    frontiere (`profil.duree_totale`, `duree_totale + marge`) sortent par la clause de
    garde `t >= profil.duree_totale` AVANT d'atteindre la formule de la phase de
    descente. `test_vitesse_maximale_respectee` echantillonne bien les trois phases,
    mais seulement la vitesse et avec une borne a sens unique, jamais `.position`. Ce
    test choisit un instant STRICTEMENT a l'interieur de la descente (apres la fin du
    plateau, avant duree_totale) et compare `.position` a la formule cinematique
    calculee independamment : la distance restant a parcourir jusqu'a l'arret, sous
    deceleration constante `a`, vaut 0.5*a*temps_restant**2, donc la position au temps
    t vaut distance - 0.5*a*temps_restant**2. Un signe inverse dans la formule de
    descente (position = distance + 0.5*a*temps_restant**2) passerait tous les autres
    tests du fichier sans changement, mais ferait depasser la tortue au-dela de sa
    cible en fin de chaque mouvement (motion_node.executer_etape).
    """
    profil = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    fin_plateau = profil.duree_montee + profil.duree_plateau
    instant = fin_plateau + 0.9 * (profil.duree_totale - fin_plateau)
    assert fin_plateau < instant < profil.duree_totale, (
        "l'instant choisi doit tomber strictement a l'interieur de la phase de "
        "descente, sinon ce test n'atteint pas la formule visee"
    )

    echantillon = trajectory.evaluer(profil, instant)

    temps_restant = profil.duree_totale - instant
    position_attendue = profil.distance - 0.5 * profil.acceleration * temps_restant ** 2
    vitesse_attendue = profil.acceleration * temps_restant

    assert echantillon.position == pytest.approx(position_attendue, abs=1e-9)
    assert echantillon.vitesse == pytest.approx(vitesse_attendue, abs=1e-9)


def test_distance_nulle_rend_un_profil_de_duree_nulle_sans_division(cinematique):
    """Cas degenere : une distance nulle rend un profil de duree nulle, sans lever."""
    profil = trajectory.calculer_profil(
        distance=0.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )

    assert profil.duree_totale == 0.0
    assert profil.vitesse_crete == 0.0

    echantillon = trajectory.evaluer(profil, 0.5)
    assert echantillon.position == 0.0
    assert echantillon.vitesse == 0.0


def test_temps_reparti_proportionnellement_a_la_longueur():
    """Deux etapes de longueurs 1 et 3 recoivent 25 % et 75 % du temps total."""
    durees = trajectory.repartir_temps([1.0, 3.0], 8.0)

    assert durees[0] == pytest.approx(2.0)
    assert durees[1] == pytest.approx(6.0)
    assert durees[0] / 8.0 == pytest.approx(0.25)
    assert durees[1] / 8.0 == pytest.approx(0.75)


def test_temps_reparti_somme_nulle_ne_divise_pas_par_zero():
    """Chemin d'echec/degenere : une somme de longueurs nulle ne leve pas et rend des zeros."""
    durees = trajectory.repartir_temps([0.0, 0.0], 5.0)

    assert durees == [0.0, 0.0]


def test_distance_inatteignable_leve_une_erreur_explicite(cinematique):
    """Chemin d'echec : une distance hors de portee du temps et de l'acceleration alloues leve, plutot que de rendre un profil silencieusement incorrect (code-style.md R8)."""
    with pytest.raises(ValueError):
        trajectory.calculer_profil(
            distance=1000.0, temps_total=1.0,
            acceleration_max=cinematique["acceleration_max"],
            vitesse_max=cinematique["vitesse_lineaire_max"],
        )


def test_vitesse_crete_calculee_au_dela_de_la_borne_leve(cinematique):
    """
    Chemin d'echec distinct du discriminant negatif : la distance EST atteignable avec
    cette acceleration (discriminant >= 0), mais la vitesse de crete que cela exige
    depasse la vitesse_max configuree. Trouve par comparaison avec la reference Aider
    (solution_robot_dimension/trajectory.py) : cette branche (trajectory.py lignes
    148-154) n'avait aucun test, alors que le discriminant negatif en a un separe.
    """
    # Une grande acceleration rend le discriminant tres positif (la distance EST
    # atteignable rapidement), mais impose alors une vitesse de crete elevee que
    # vitesse_max, elle, plafonne.
    with pytest.raises(ValueError):
        trajectory.calculer_profil(
            distance=5.0, temps_total=1.0,
            acceleration_max=100.0,
            vitesse_max=cinematique["vitesse_lineaire_max"],
        )


def test_evaluer_ecrete_avant_le_depart_et_apres_la_fin(cinematique):
    """
    Le docstring de `evaluer` justifie l'ecretage aux bornes par un appelant qui
    republie a une periode fixe et finit toujours par interroger un instant legerement
    au-dela de la fin du mouvement (motion_node.py, boucle de publication) -- mais rien
    ne le verifiait. Trouve par comparaison avec la reference Aider, qui teste
    explicitement value(-1.0) et value(duration + marge) sur TrapezoidProfile.
    """
    profil = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )

    avant_depart = trajectory.evaluer(profil, -1.0)
    assert avant_depart.position == 0.0
    assert avant_depart.vitesse == 0.0

    apres_fin = trajectory.evaluer(profil, profil.duree_totale + 5.0)
    assert apres_fin.position == pytest.approx(profil.distance, abs=1e-9)
    assert apres_fin.vitesse == 0.0


def test_temps_reparti_longueur_negative_leve(cinematique):
    """Chemin d'echec : une longueur negative dans la liste leve plutot que de produire une duree negative silencieuse (code-style.md R8)."""
    with pytest.raises(ValueError):
        trajectory.repartir_temps([1.0, -2.0], 5.0)


def test_temps_reparti_temps_total_negatif_leve(cinematique):
    """Chemin d'echec : un temps_total negatif leve plutot que de produire des durees negatives."""
    with pytest.raises(ValueError):
        trajectory.repartir_temps([1.0, 2.0], -5.0)


def test_temps_reparti_une_seule_etape_recoit_tout_le_temps():
    """Cas limite : une seule etape recoit l'integralite du temps total."""
    durees = trajectory.repartir_temps([7.0], 3.5)

    assert len(durees) == 1
    assert durees[0] == pytest.approx(3.5)


def test_temps_reparti_somme_exactement_egale_au_temps_total_avec_longueurs_irrationnelles():
    """
    La somme des durees rendues doit egaler temps_total EXACTEMENT, pas seulement a
    l'arrondi flottant pres, meme avec des longueurs non triviales (ici une racine
    carree). Trouve par comparaison avec la reference Aider
    (test_sum_equals_total_time_exactly, qui utilise sqrt(31**2 + 61**2)) : notre seul
    test de somme utilisait des nombres ronds (1, 3) qui ne peuvent pas reveler un
    ecart flottant. repartir_temps assigne desormais le reste au dernier element,
    exactement comme allocate_times de la reference, pour garantir cette exactitude.
    """
    longueurs = [30.0, math.sqrt(31.0 ** 2 + 61.0 ** 2), math.sqrt(2.0)]
    durees = trajectory.repartir_temps(longueurs, 10.0)

    assert sum(durees) == 10.0
