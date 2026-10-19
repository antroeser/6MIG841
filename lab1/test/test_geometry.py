"""
test_geometry.py - Tests de ihr_ros.geometry, geometrie plane partagee par les trois travaux.

Fonctions pures, sans dependance externe (voir l'en-tete du module) : testables sans
camera, sans ROS2 et sans numpy. Les valeurs attendues ci-dessous ont ete verifiees par
execution directe des fonctions avant redaction, puis inscrites avec leur calcul en
commentaire (workflow.md R7 : une valeur mesuree porte ce qui l'a mesuree).
"""

from __future__ import annotations

import math

import pytest

from ihr_ros import geometry


# --------------------------------------------------------------------- normalize_angle

def test_normalize_angle_ramene_un_grand_angle_positif_dans_l_intervalle():
    """Un angle de 3*pi (un tour et demi) est ramene a pi, borne haute de ]-pi, pi] incluse."""
    assert geometry.normalize_angle(3.0 * math.pi) == pytest.approx(math.pi)


def test_normalize_angle_conserve_pi_car_la_borne_haute_est_incluse():
    """pi lui-meme reste pi : l'intervalle documente est ]-pi, pi], pi y appartient."""
    assert geometry.normalize_angle(math.pi) == pytest.approx(math.pi)


def test_normalize_angle_moins_pi_est_ramene_a_pi_car_la_borne_basse_est_exclue():
    """-pi est hors de ]-pi, pi] (borne basse exclue) : il doit ressortir en +pi."""
    assert geometry.normalize_angle(-math.pi) == pytest.approx(math.pi)


def test_normalize_angle_un_tour_complet_retombe_a_zero():
    """2*pi (un tour complet depuis 0) doit retomber exactement sur 0.0."""
    assert geometry.normalize_angle(2.0 * math.pi) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------- distance / bearing

def test_distance_triangle_rectangle_3_4_5():
    """Triangle rectangle classique 3-4-5 : distance((0,0),(3,4)) == 5.0."""
    assert geometry.distance((0.0, 0.0), (3.0, 4.0)) == pytest.approx(5.0)


def test_bearing_vers_les_x_croissants_est_nul():
    """Un cap direct vers +x correspond a un angle de 0 radian (convention du module)."""
    assert geometry.bearing((0.0, 0.0), (1.0, 0.0)) == pytest.approx(0.0)


def test_bearing_vers_les_y_croissants_est_un_quart_de_tour():
    """Un cap direct vers +y correspond a pi/2 radian."""
    assert geometry.bearing((0.0, 0.0), (0.0, 1.0)) == pytest.approx(math.pi / 2.0)


def test_heading_error_compose_bearing_et_normalisation():
    """Cap vers (1,1) depuis l'origine, orientation courante 0 : erreur normalisee = pi/4."""
    erreur = geometry.heading_error(0.0, (0.0, 0.0), (1.0, 1.0))
    assert erreur == pytest.approx(math.pi / 4.0)


# --------------------------------------------------------------------- angle_between

def test_angle_between_vecteurs_perpendiculaires():
    """Deux vecteurs perpendiculaires (1,0) et (0,1) forment un angle de pi/2."""
    angle = geometry.angle_between((1.0, 0.0), (0.0, 1.0), min_norm=1e-6)
    assert angle == pytest.approx(math.pi / 2.0)


def test_angle_between_vecteur_nul_retourne_none_jamais_zero():
    """Un vecteur degenere (norme nulle) doit retourner None, pas 0.0 (piege silencieux)."""
    angle = geometry.angle_between((0.0, 0.0), (1.0, 0.0), min_norm=1e-6)
    assert angle is None


def test_angle_between_norme_juste_sous_le_seuil_est_jugee_degeneree():
    """Une norme de 1e-7, sous le seuil min_norm=1e-6, est degeneree : None attendu."""
    angle = geometry.angle_between((1e-7, 0.0), (1.0, 0.0), min_norm=1e-6)
    assert angle is None


def test_angle_between_norme_egale_au_seuil_n_est_pas_degeneree():
    """Controle negatif : une norme EXACTEMENT au seuil n'est pas degeneree (comparaison stricte '<')."""
    angle = geometry.angle_between((1e-6, 0.0), (1.0, 0.0), min_norm=1e-6)
    assert angle is not None
    assert angle == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------------------------- angle_at_vertex

def test_angle_at_vertex_angle_droit():
    """Sommet a l'origine, deux cotes unitaires perpendiculaires : angle de pi/2."""
    angle = geometry.angle_at_vertex((1.0, 0.0), (0.0, 0.0), (0.0, 1.0), min_norm=1e-6)
    assert angle == pytest.approx(math.pi / 2.0)


def test_angle_at_vertex_sommet_confondu_avec_une_extremite_est_degenere():
    """Si le sommet coincide avec point_a, ce cote devient un vecteur nul : None attendu."""
    angle = geometry.angle_at_vertex((0.0, 0.0), (0.0, 0.0), (0.0, 1.0), min_norm=1e-6)
    assert angle is None


# --------------------------------------------------------------------- image_to_turtlesim

def test_image_to_turtlesim_centre_image_tombe_au_centre_du_canevas():
    """Le pixel central d'une image 640x480 tombe au centre du canevas turtlesim (5.544, 5.544),
    exactement la pose de depart de turtlesim : bon indice que l'inversion d'axe est correcte."""
    x, y = geometry.image_to_turtlesim((320.0, 240.0), 640, 480, 11.088, 11.088)
    assert x == pytest.approx(5.544)
    assert y == pytest.approx(5.544)


def test_image_to_turtlesim_borne_au_minimum_du_canevas():
    """Un pixel hors image cote negatif est borne a 0.0 en x, jamais laisse negatif."""
    x, y = geometry.image_to_turtlesim((-50.0, -50.0), 640, 480, 11.088, 11.088)
    assert x == pytest.approx(0.0)
    assert y == pytest.approx(11.088)


def test_image_to_turtlesim_borne_au_maximum_du_canevas():
    """Un pixel tres au-dela de l'image est borne a canvas_width/canvas_height, jamais depasse."""
    x, y = geometry.image_to_turtlesim((10000.0, 10000.0), 640, 480, 11.088, 11.088)
    assert x == pytest.approx(11.088)
    assert y == pytest.approx(0.0)


def test_image_to_turtlesim_largeur_nulle_leve_valueerror():
    """Une largeur d'image nulle (camera n'ayant pas fourni de trame) leve ValueError."""
    with pytest.raises(ValueError, match="0x480"):
        geometry.image_to_turtlesim((1.0, 1.0), 0, 480, 11.088, 11.088)


def test_image_to_turtlesim_hauteur_nulle_leve_valueerror():
    """Une hauteur d'image nulle leve ValueError, symetrique du cas largeur nulle."""
    with pytest.raises(ValueError, match="640x0"):
        geometry.image_to_turtlesim((1.0, 1.0), 640, 0, 11.088, 11.088)


# --------------------------------------------------------------------- box_center

def test_box_center_boite_simple():
    """Le centre d'une boite englobante (0,0)-(10,10) est (5,5)."""
    assert geometry.box_center(0.0, 0.0, 10.0, 10.0) == pytest.approx((5.0, 5.0))
