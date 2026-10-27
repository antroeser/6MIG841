"""
test_arcs.py - Devoir 2, plan05 : suite d'echantillonnage de l'arc et de collision.

Purement numerique (workflow.md R5) : aucun ROS2, aucune tortue, aucun temps reel.
Utilise la fixture `cinematique` de conftest.py (section 'cinematique' de
ihr_config.json).

Le NEUVIEME test du tableau de plan05.md (`test_arc_dont_le_segment_etait_libre...`)
est le test CENTRAL du plan : sans lui, rien ne prouve que la cinematique change quoi
que ce soit au verdict de collision. Il construit la scene, verifie PROGRAMMATIQUEMENT
(pas a la main) que le segment direct depart -> arrivee serait declare libre par un
planificateur sans cinematique comme Theta* (aucun point de l'obstacle a moins de
rayon + tolerance de ce segment), puis prouve que l'arc reellement parcouru,
lui, heurte cet obstacle.
"""

from __future__ import annotations

import math

import pytest

import arcs
import trajectory


def _distance_point_segment(px: float, py: float,
                            ax: float, ay: float,
                            bx: float, by: float) -> float:
    """Distance d'un point au segment [A, B] (projection bornee), pour verifier
    hors de arcs.py qu'un planificateur sans cinematique jugerait ce segment libre."""
    dx, dy = bx - ax, by - ay
    longueur_carree = dx * dx + dy * dy
    if longueur_carree == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / longueur_carree))
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def test_arc_en_ligne_droite_rotation_nulle_donne_un_segment(cinematique):
    """Controle negatif : un profil angulaire degenere (rotation nulle) donne une trajectoire en ligne droite, pas un arc."""
    profil_lineaire = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    profil_angulaire = trajectory.calculer_profil(
        distance=0.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_angulaire_max"],
    )

    resultat = arcs.echantillonner_arc(
        pose_depart=(0.0, 0.0, 0.0),
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=1.0, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=None, tolerance_collision=cinematique["tolerance_collision"],
    )

    assert all(e.theta == pytest.approx(0.0, abs=1e-9) for e in resultat.echantillons)
    assert all(e.y == pytest.approx(0.0, abs=1e-9) for e in resultat.echantillons)
    # Tolerance liee a l'integration d'Euler explicite au pas resolution_s, pas a une
    # erreur : le pas d'echantillonnage introduit une erreur numerique bornee, pas une
    # erreur systematique de sens.
    assert resultat.echantillons[-1].x == pytest.approx(2.0, abs=0.01)
    assert resultat.collision is None


def test_arc_frole_l_obstacle_sans_le_toucher(cinematique):
    """Controle negatif : un obstacle juste hors de portee (rayon + tolerance + marge) ne declenche aucune collision, ce qui empeche un detecteur trop sensible."""
    profil_lineaire = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    profil_angulaire = trajectory.calculer_profil(
        distance=0.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_angulaire_max"],
    )
    rayon = 0.2
    marge = 0.05
    obstacle = arcs.Obstacle(
        x=1.0, y=rayon + cinematique["tolerance_collision"] + marge, rayon=rayon,
    )

    resultat = arcs.echantillonner_arc(
        pose_depart=(0.0, 0.0, 0.0),
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=1.0, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=obstacle, tolerance_collision=cinematique["tolerance_collision"],
    )

    assert resultat.collision is None


def test_arc_entre_dans_l_obstacle_est_detecte(cinematique):
    """L'obstacle est directement sur la trajectoire : la collision est detectee, avec son instant et sa position."""
    profil_lineaire = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    profil_angulaire = trajectory.calculer_profil(
        distance=0.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_angulaire_max"],
    )
    obstacle = arcs.Obstacle(x=1.0, y=0.0, rayon=0.2)

    resultat = arcs.echantillonner_arc(
        pose_depart=(0.0, 0.0, 0.0),
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=1.0, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=obstacle, tolerance_collision=cinematique["tolerance_collision"],
    )

    assert resultat.collision is not None
    assert 0.0 < resultat.collision.instant < 1.0
    # La collision est signalee des l'entree dans le rayon + tolerance de l'obstacle,
    # donc AVANT que le centre ne soit atteint : c'est la position exacte de detection
    # qui est verifiee, pas une coincidence avec le centre de l'obstacle.
    distance_au_centre = math.hypot(resultat.collision.x - obstacle.x,
                                    resultat.collision.y - obstacle.y)
    assert distance_au_centre <= obstacle.rayon + cinematique["tolerance_collision"] + 1e-9
    assert resultat.collision.x < obstacle.x


def test_arc_dont_le_segment_etait_libre_est_refuse(cinematique):
    """
    Test CENTRAL (plan05.md, neuvieme ligne du tableau) : le segment direct
    depart -> arrivee serait valide par un planificateur sans cinematique comme
    Theta*, mais l'arc reellement parcouru (vitesse lineaire ET angulaire
    simultanement non nulles) s'en ecarte assez pour heurter un obstacle que ce
    segment evitait. Sans ce test, rien ne prouve que la cinematique change
    quoi que ce soit au verdict de collision.
    """
    distance = 2.0
    angle_rad = math.radians(60.0)
    temps_total = 1.0
    pose_depart = (0.0, 0.0, 0.0)

    profil_lineaire = trajectory.calculer_profil(
        distance=distance, temps_total=temps_total,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    profil_angulaire = trajectory.calculer_profil(
        distance=angle_rad, temps_total=temps_total,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_angulaire_max"],
    )

    # Trajectoire reelle, sans obstacle, pour choisir un point sur l'arc VRAI.
    trajectoire_libre = arcs.echantillonner_arc(
        pose_depart=pose_depart,
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=temps_total, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=None, tolerance_collision=cinematique["tolerance_collision"],
    )
    assert len(trajectoire_libre.echantillons) > 1

    # L'obstacle est place EXACTEMENT sur le dernier point de l'arc reel.
    echantillon_vise = trajectoire_libre.echantillons[-1]
    rayon_obstacle = 0.05
    obstacle = arcs.Obstacle(x=echantillon_vise.x, y=echantillon_vise.y, rayon=rayon_obstacle)

    # Le « segment » que Theta* aurait valide : une ligne droite du depart vers
    # un point situe a `distance` le long du cap initial, puisque le Lab 1 n'a
    # aucun modele cinematique et suppose une translation pure sans rotation.
    segment_arrivee = (
        pose_depart[0] + distance * math.cos(pose_depart[2]),
        pose_depart[1] + distance * math.sin(pose_depart[2]),
    )
    distance_au_segment = _distance_point_segment(
        obstacle.x, obstacle.y,
        pose_depart[0], pose_depart[1],
        segment_arrivee[0], segment_arrivee[1],
    )
    seuil_collision = obstacle.rayon + cinematique["tolerance_collision"]
    assert distance_au_segment > seuil_collision, (
        "l'obstacle doit etre hors de portee du SEGMENT direct pour que le test "
        "demontre que c'est bien l'ARC, et non le segment, qui heurte"
    )

    # L'arc reel, lui, heurte cet obstacle.
    trajectoire_avec_obstacle = arcs.echantillonner_arc(
        pose_depart=pose_depart,
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=temps_total, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=obstacle, tolerance_collision=cinematique["tolerance_collision"],
    )
    assert trajectoire_avec_obstacle.collision is not None


def test_arc_sens_lineaire_negatif_recule_et_detecte_l_obstacle_derriere(cinematique):
    """
    Paire en opposition sur sens_lineaire (revue finale, constat CRITIQUE) : aucun des
    huit tests precedents n'appelait jamais `echantillonner_arc` avec sens_lineaire=-1.0,
    donc rien ne prouvait que `v = sens_lineaire * evaluer(...).vitesse` fait autre chose
    que `v = evaluer(...).vitesse`. Reculer (sens_lineaire=-1.0) doit integrer la pose en
    x negatif, jamais en x positif : un obstacle place DERRIERE le point de depart doit
    donc etre detecte quand la tortue recule, et jamais quand elle avance vers l'avant
    avec le meme obstacle. C'est exactement le chemin reel : `motion_node.verifier_
    etape_libre` passe a cette fonction le sens signe rendu par `state_machine.signer()`,
    potentiellement -1.0 pour un « reculer ».
    """
    profil_lineaire = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    profil_angulaire = trajectory.calculer_profil(
        distance=0.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_angulaire_max"],
    )
    obstacle_derriere = arcs.Obstacle(x=-1.0, y=0.0, rayon=0.2)

    resultat_recule = arcs.echantillonner_arc(
        pose_depart=(0.0, 0.0, 0.0),
        profil_lineaire=profil_lineaire, sens_lineaire=-1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=1.0, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=obstacle_derriere, tolerance_collision=cinematique["tolerance_collision"],
    )
    resultat_avance = arcs.echantillonner_arc(
        pose_depart=(0.0, 0.0, 0.0),
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=1.0, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=obstacle_derriere, tolerance_collision=cinematique["tolerance_collision"],
    )

    assert resultat_recule.collision is not None, (
        "reculer doit heurter l'obstacle place derriere le point de depart"
    )
    assert resultat_recule.collision.x < 0.0
    assert resultat_avance.collision is None, (
        "avancer s'eloigne de l'obstacle place derriere : aucune collision attendue, "
        "sinon les deux sens produisent la meme trajectoire"
    )
    assert resultat_avance.echantillons[-1].x == pytest.approx(2.0, abs=0.01)


def test_arc_sens_angulaire_negatif_tourne_a_l_oppose_du_sens_positif(cinematique):
    """
    Paire en opposition sur sens_angulaire (revue finale, constat CRITIQUE) : aucun des
    huit tests precedents n'appelait jamais `echantillonner_arc` avec
    sens_angulaire=-1.0, donc rien ne prouvait que
    `w = sens_angulaire * evaluer(...).vitesse` fait autre chose que
    `w = evaluer(...).vitesse`. Un virage antihoraire (sens_angulaire=1.0) courbe vers y
    positif ; le meme profil avec sens_angulaire=-1.0 doit courber vers y negatif, donc
    manquer un obstacle place sur le cote antihoraire alors que le virage antihoraire,
    lui, le heurte. Sans la multiplication par sens_angulaire, un « tourner a droite »
    (is_clockwise=True) serait integre comme un virage a gauche, et un obstacle du cote
    droit reel ne serait jamais vu par `motion_node.verifier_etape_libre`.
    """
    distance = 2.0
    angle_rad = math.radians(60.0)
    temps_total = 1.0
    pose_depart = (0.0, 0.0, 0.0)

    profil_lineaire = trajectory.calculer_profil(
        distance=distance, temps_total=temps_total,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    profil_angulaire = trajectory.calculer_profil(
        distance=angle_rad, temps_total=temps_total,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_angulaire_max"],
    )

    # Trajectoire antihoraire (sens_angulaire=1.0) sans obstacle, pour choisir un point
    # sur son arc VRAI, du cote ou elle courbe reellement.
    trajectoire_gauche_libre = arcs.echantillonner_arc(
        pose_depart=pose_depart,
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=temps_total, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=None, tolerance_collision=cinematique["tolerance_collision"],
    )
    point_vise = trajectoire_gauche_libre.echantillons[-1]
    assert point_vise.y > 0.05, (
        "l'arc antihoraire doit reellement courber vers y positif pour que le test "
        "distingue les deux sens"
    )
    obstacle = arcs.Obstacle(x=point_vise.x, y=point_vise.y, rayon=0.05)

    resultat_gauche = arcs.echantillonner_arc(
        pose_depart=pose_depart,
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=temps_total, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=obstacle, tolerance_collision=cinematique["tolerance_collision"],
    )
    resultat_droite = arcs.echantillonner_arc(
        pose_depart=pose_depart,
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=-1.0,
        duree_etape=temps_total, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=obstacle, tolerance_collision=cinematique["tolerance_collision"],
    )

    assert resultat_gauche.collision is not None, (
        "le virage antihoraire doit heurter l'obstacle place sur son propre arc"
    )
    assert resultat_droite.collision is None, (
        "le virage horaire (sens_angulaire=-1.0) courbe du cote oppose et doit manquer "
        "cet obstacle ; sinon les deux sens produisent la meme trajectoire"
    )


def test_aucun_obstacle_declare_aucune_collision_sans_lever(cinematique):
    """Sans obstacle declare, aucune collision n'est jamais possible, et la fonction ne leve jamais pour ce motif."""
    profil_lineaire = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    profil_angulaire = trajectory.calculer_profil(
        distance=math.radians(90.0), temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_angulaire_max"],
    )

    resultat = arcs.echantillonner_arc(
        pose_depart=(0.0, 0.0, 0.0),
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=1.0, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=None, tolerance_collision=cinematique["tolerance_collision"],
    )

    assert resultat.collision is None
    assert len(resultat.echantillons) > 1


def test_resolution_non_positive_leve_une_erreur(cinematique):
    """Chemin d'echec : une resolution d'echantillonnage nulle ou negative leve, plutot que de ne jamais progresser (code-style.md R8)."""
    profil = trajectory.calculer_profil(
        distance=1.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )

    with pytest.raises(ValueError):
        arcs.echantillonner_arc(
            pose_depart=(0.0, 0.0, 0.0),
            profil_lineaire=profil, sens_lineaire=1.0,
            profil_angulaire=profil, sens_angulaire=0.0,
            duree_etape=1.0, resolution_s=0.0,
            obstacle=None, tolerance_collision=cinematique["tolerance_collision"],
        )


def test_duree_etape_negative_leve_une_erreur(cinematique):
    """Chemin d'echec : une duree_etape negative leve plutot que d'echantillonner un intervalle de temps impossible (code-style.md R8). Branche existante (arcs.py) jamais exercee avant ce test."""
    profil = trajectory.calculer_profil(
        distance=1.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )

    with pytest.raises(ValueError):
        arcs.echantillonner_arc(
            pose_depart=(0.0, 0.0, 0.0),
            profil_lineaire=profil, sens_lineaire=1.0,
            profil_angulaire=profil, sens_angulaire=0.0,
            duree_etape=-1.0, resolution_s=cinematique["resolution_echantillonnage_s"],
            obstacle=None, tolerance_collision=cinematique["tolerance_collision"],
        )


def test_arc_a_portee_du_rayon_plus_tolerance_mais_hors_du_rayon_brut_est_detecte(cinematique):
    """
    Isole la marge tolerance_collision, trouve par comparaison avec la reference Aider
    (TestVerifyArcSafetyZone, deux tests symetriques) : un echantillon STRICTEMENT hors
    du rayon brut de l'obstacle mais DEDANS rayon + tolerance_collision doit quand meme
    etre signale comme collision. Sans ce test isole, un bug qui ignorerait
    silencieusement tolerance_collision dans _en_collision ne serait detecte par aucun
    test existant : test_arc_frole_l_obstacle_sans_le_toucher verifie seulement
    l'ABSENCE de collision hors de portee, et test_arc_entre_dans_l_obstacle_est_detecte
    place l'obstacle en plein sur la trajectoire, a l'interieur meme du rayon brut -- ni
    l'un ni l'autre ne prouve que la marge elle-meme fait quelque chose.
    """
    profil_lineaire = trajectory.calculer_profil(
        distance=2.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_lineaire_max"],
    )
    profil_angulaire = trajectory.calculer_profil(
        distance=0.0, temps_total=1.0,
        acceleration_max=cinematique["acceleration_max"],
        vitesse_max=cinematique["vitesse_angulaire_max"],
    )
    rayon = 0.2
    tolerance = cinematique["tolerance_collision"]
    obstacle = arcs.Obstacle(x=1.0, y=rayon + tolerance * 0.5, rayon=rayon)

    resultat = arcs.echantillonner_arc(
        pose_depart=(0.0, 0.0, 0.0),
        profil_lineaire=profil_lineaire, sens_lineaire=1.0,
        profil_angulaire=profil_angulaire, sens_angulaire=1.0,
        duree_etape=1.0, resolution_s=cinematique["resolution_echantillonnage_s"],
        obstacle=obstacle, tolerance_collision=tolerance,
    )

    assert resultat.collision is not None
    distance_au_centre = math.hypot(resultat.collision.x - obstacle.x,
                                    resultat.collision.y - obstacle.y)
    assert distance_au_centre > rayon, (
        "la collision doit venir de la marge tolerance_collision, et non du rayon brut "
        "de l'obstacle, sans quoi ce test ne demontre rien de plus que le test existant"
    )
    assert distance_au_centre <= rayon + tolerance + 1e-9
