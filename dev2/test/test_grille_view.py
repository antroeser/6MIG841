"""
test_grille_view.py - La fenetre du quadrillage du Devoir 2, testee SANS ouvrir de fenetre.

Aucune figure n'est construite ici : `VueGrilleDevoir2.construire()` n'est jamais appelee,
et seules les parties pures sont eprouvees (changement de repere, bornes, refus). C'est ce
qui permet a ces tests de tourner dans la suite par defaut, sans ecran (R5).

Le controle qui porte tout le reste est
`test_la_pose_de_depart_turtlesim_tombe_au_centre_de_la_grille` : si la conversion est
fausse, la tortue ne sera pas au centre au demarrage, et c'est visible a l'oeil nu.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_CODE_LAB1 = Path(__file__).resolve().parent.parent.parent / "Lab1" / "code"
if str(_CODE_LAB1) not in sys.path:
    sys.path.insert(0, str(_CODE_LAB1))

from planif.world import World, load_config as charger_config_planif  # noqa: E402

from grille_view import (  # noqa: E402
    VueGrilleDevoir2,
    echelle_turtlesim_par_cellule,
    occupation_disque,
    turtlesim_vers_grille,
)


@pytest.fixture()
def planif():
    return charger_config_planif()


@pytest.fixture()
def monde(planif):
    return World(planif)


# --------------------------------------------------------------------- le changement de repere

def test_l_echelle_est_derivee_des_deux_configurations_et_non_ecrite_en_dur(cfg, monde):
    """
    L'echelle vaut canvas_width / largeur_cellules, calculee a l'execution.

    devoir2.obstacle.echelle_grille_vers_turtlesim porte encore 0.924, valeur calculee
    le 2026-09-19 pour une grille de 12 cellules de large remplacee par 64 le
    2026-09-20 : ce test verifie qu'on ne la lit PAS.
    """
    import json

    turtlesim_cfg = json.loads(
        (Path(__file__).resolve().parent.parent.parent
         / "Lab1" / "code" / "ihr_config.json").read_text(encoding="utf-8")
    )["turtlesim"]

    echelle = echelle_turtlesim_par_cellule(turtlesim_cfg, monde)

    attendue = float(turtlesim_cfg["canvas_width"]) / monde.largeur_cellules
    assert echelle == pytest.approx(attendue)
    assert echelle != pytest.approx(0.924), (
        "l'echelle perimee de devoir2.obstacle ne doit jamais etre utilisee ici"
    )


def test_la_pose_de_depart_turtlesim_tombe_au_centre_de_la_grille(cfg, monde):
    """
    Controle le plus simple de la conversion : la tortue demarre au centre du canevas
    turtlesim, elle doit donc apparaitre au centre du quadrillage.
    """
    import json

    ihr = json.loads(
        (Path(__file__).resolve().parent.parent.parent
         / "Lab1" / "code" / "ihr_config.json").read_text(encoding="utf-8")
    )
    turtlesim_cfg = ihr["turtlesim"]
    echelle = echelle_turtlesim_par_cellule(turtlesim_cfg, monde)

    xg, yg = turtlesim_vers_grille(float(turtlesim_cfg["start_x"]),
                                   float(turtlesim_cfg["start_y"]), echelle)

    assert xg == pytest.approx(monde.largeur_cellules / 2.0)
    assert yg == pytest.approx(monde.hauteur_cellules / 2.0)


def test_l_origine_turtlesim_tombe_sur_l_origine_de_la_grille(monde):
    assert turtlesim_vers_grille(0.0, 0.0, 0.17325) == pytest.approx((0.0, 0.0))


def test_le_coin_oppose_du_canevas_tombe_sur_le_coin_oppose_de_la_grille(cfg, monde):
    import json

    turtlesim_cfg = json.loads(
        (Path(__file__).resolve().parent.parent.parent
         / "Lab1" / "code" / "ihr_config.json").read_text(encoding="utf-8")
    )["turtlesim"]
    echelle = echelle_turtlesim_par_cellule(turtlesim_cfg, monde)

    xg, yg = turtlesim_vers_grille(float(turtlesim_cfg["canvas_width"]),
                                   float(turtlesim_cfg["canvas_height"]), echelle)

    assert xg == pytest.approx(monde.largeur_cellules)
    assert yg == pytest.approx(monde.hauteur_cellules)


@pytest.mark.parametrize("echelle_invalide", [0.0, -1.0])
def test_une_echelle_nulle_ou_negative_est_refusee(echelle_invalide):
    with pytest.raises(ValueError, match="echelle"):
        turtlesim_vers_grille(1.0, 1.0, echelle_invalide)


def test_un_canevas_de_largeur_nulle_est_refuse_en_nommant_la_cle(monde):
    with pytest.raises(ValueError, match="canvas_width"):
        echelle_turtlesim_par_cellule({"canvas_width": 0.0}, monde)


# --------------------------------------------------------------------- la vue, sans figure

def _vue_non_construite(monde, planif, cfg):
    import json

    turtlesim_cfg = json.loads(
        (Path(__file__).resolve().parent.parent.parent
         / "Lab1" / "code" / "ihr_config.json").read_text(encoding="utf-8")
    )["turtlesim"]
    return VueGrilleDevoir2(monde, planif["affichage"], turtlesim_cfg, cfg["grille"],
                            cfg["obstacle"])


def test_construire_n_est_pas_appelee_a_la_construction_donc_aucune_figure(monde, planif, cfg):
    """Aucune fenetre ne s'ouvre tant que construire() n'a pas ete appelee (R5)."""
    vue = _vue_non_construite(monde, planif, cfg)

    assert vue.figure is None
    assert vue.ax is None


def test_maj_tortue_rend_la_position_en_coordonnees_de_grille_sans_figure(monde, planif, cfg):
    """La conversion fonctionne meme sans artistes matplotlib : la vue reste utilisable."""
    vue = _vue_non_construite(monde, planif, cfg)

    xg, yg = vue.maj_tortue(5.544, 5.544, 0.0)

    assert xg == pytest.approx(32.0)
    assert yg == pytest.approx(32.0)


def test_la_trace_est_bornee_par_trace_max_points(monde, planif, cfg):
    """R10 : une session longue ne doit pas faire grandir la trace indefiniment."""
    vue = _vue_non_construite(monde, planif, cfg)
    borne = int(cfg["grille"]["trace_max_points"])

    for i in range(borne + 50):
        vue.maj_tortue(float(i % 11), 5.544, 0.0)

    assert len(vue._trace_x) == borne
    assert len(vue._trace_y) == borne


def test_fermer_sur_une_vue_jamais_construite_ne_leve_pas(monde, planif, cfg):
    """Fermer ce qui n'a pas ete ouvert est un no-op, pas une erreur."""
    vue = _vue_non_construite(monde, planif, cfg)

    vue.fermer()

    assert vue.figure is None


def test_pomper_sur_une_vue_jamais_construite_ne_leve_pas(monde, planif, cfg):
    vue = _vue_non_construite(monde, planif, cfg)

    vue.pomper()


# --------------------------------------------------------------------- le quadrillage partage

def test_la_vue_du_devoir2_utilise_le_meme_module_de_trace_que_le_lab1():
    """
    Le quadrillage ne doit exister qu'UNE fois dans le depot.

    Si un jour quelqu'un recopie le trace dans grille_view.py au lieu d'importer
    planif.vue, les deux quadrillages derivent en silence : une couleur changee d'un
    cote, une ligne de bord oubliee de l'autre, et plus rien ne dit lequel est bon.
    """
    import grille_view
    from planif import app, vue

    assert grille_view.vue is vue
    assert app.vue is vue


def test_le_quadrillage_a_une_ligne_par_frontiere_de_cellule(monde, planif):
    """
    Une grille de N cellules a N+1 frontieres : oublier le +1 laisse le bord droit et
    le bord haut ouverts. Verifie sans figure, en comptant les appels.
    """
    from planif import vue as module_vue

    class FauxAxes:
        def __init__(self):
            self.verticales = 0
            self.horizontales = 0
            self.rectangles = 0

        def axvline(self, *_args, **_kwargs):
            self.verticales += 1

        def axhline(self, *_args, **_kwargs):
            self.horizontales += 1

        def add_patch(self, *_args, **_kwargs):
            self.rectangles += 1

    faux = FauxAxes()
    module_vue.tracer_grille(faux, monde, planif["affichage"])

    assert faux.verticales == monde.largeur_cellules + 1
    assert faux.horizontales == monde.hauteur_cellules + 1
    assert faux.rectangles == len(monde.cellules_obstacle())


# --------------------------------------------------------------------- la grille d'occupation

def test_un_rayon_nul_n_occupe_aucune_cellule(monde):
    """Sans obstacle, toute la grille est libre : blanc partout, jamais du gris."""
    occupation = occupation_disque(monde, 32.0, 32.0, 0.0, 4)

    assert occupation.shape == (monde.hauteur_cellules, monde.largeur_cellules)
    assert occupation.max() == 0.0


def test_toute_valeur_est_une_probabilite(monde):
    """Chaque case porte une probabilite : rien en dehors de [0, 1]."""
    occupation = occupation_disque(monde, 34.67, 40.0, 2.886, 4)

    assert occupation.min() >= 0.0
    assert occupation.max() <= 1.0


def test_le_centre_du_disque_est_une_case_pleinement_occupee(monde):
    """Au centre, la probabilite de presence vaut 1 : la case est noire."""
    occupation = occupation_disque(monde, 32.5, 32.5, 3.0, 4)

    assert occupation[32, 32] == pytest.approx(1.0)


def test_une_case_loin_du_disque_reste_libre(monde):
    """Controle negatif : sans lui, une implementation qui noircirait tout passerait."""
    occupation = occupation_disque(monde, 32.5, 32.5, 3.0, 4)

    assert occupation[0, 0] == 0.0
    assert occupation[63, 63] == 0.0


def test_la_couronne_du_disque_porte_des_valeurs_intermediaires(monde):
    """
    C'est ce qui distingue une grille d'occupation d'un masque binaire : les cases
    que le bord du disque traverse sont PARTIELLEMENT occupees, donc grises.
    """
    occupation = occupation_disque(monde, 32.5, 32.5, 3.0, 4)

    partielles = ((occupation > 0.0) & (occupation < 1.0)).sum()
    assert partielles > 0, "aucune case partielle : le disque est rasterise en binaire"


def test_l_aire_occupee_approche_celle_du_disque(monde):
    """
    La somme des fractions est l'aire du disque en cellules. C'est le controle qui
    prouve que l'echantillonnage mesure vraiment une couverture, et pas autre chose.
    """
    rayon = 3.0
    occupation = occupation_disque(monde, 32.5, 32.5, rayon, 8)

    aire_theorique = math.pi * rayon ** 2
    assert occupation.sum() == pytest.approx(aire_theorique, rel=0.02)


def test_un_echantillonnage_plus_fin_approche_mieux_l_aire(monde):
    """Le parametre sert a quelque chose : plus d'echantillons, moins d'erreur."""
    rayon = 3.0
    aire_theorique = math.pi * rayon ** 2

    grossier = abs(occupation_disque(monde, 32.5, 32.5, rayon, 1).sum() - aire_theorique)
    fin = abs(occupation_disque(monde, 32.5, 32.5, rayon, 8).sum() - aire_theorique)

    assert fin < grossier


def test_le_calcul_est_deterministe(monde):
    """R19 : aucun tirage aleatoire, donc le meme rendu a chaque appel."""
    premier = occupation_disque(monde, 34.67, 40.0, 2.886, 4)
    second = occupation_disque(monde, 34.67, 40.0, 2.886, 4)

    assert (premier == second).all()


@pytest.mark.parametrize("echantillons", [0, -1])
def test_un_echantillonnage_non_positif_est_refuse_en_nommant_la_cle(monde, echantillons):
    with pytest.raises(ValueError, match="echantillons_par_cellule"):
        occupation_disque(monde, 32.0, 32.0, 3.0, echantillons)


def test_maj_obstacle_recalcule_l_occupation_sans_figure(monde, planif, cfg):
    """La vue reste utilisable sans fenetre : l'occupation se calcule quand meme."""
    vue = _vue_non_construite(monde, planif, cfg)

    vue.maj_obstacle(6.006, 6.930)

    occupation = vue.occupation()
    assert occupation is not None
    assert occupation.sum() > 0.0


def test_le_rayon_de_l_obstacle_est_converti_en_cellules(monde, planif, cfg):
    """
    Le rayon est une grandeur du monde, en unites turtlesim. Sur la grille il vaut
    rayon / echelle : 0.5 / 0.17325 vaut environ 2.89 cellules.
    """
    vue = _vue_non_construite(monde, planif, cfg)

    attendu = float(cfg["obstacle"]["rayon"]) / vue.echelle
    assert vue.rayon_obstacle_grille == pytest.approx(attendu)


def test_le_robot_ne_demarre_pas_dans_l_obstacle(monde, planif, cfg):
    """
    Defaut signale par l'enseignant le 2026-09-20 : la vue tracait AUSSI l'obstacle
    du planificateur du Lab 1, au centre de la grille, et la pose de depart de
    turtlesim tombe exactement au centre. Le robot etait donc dessine a l'interieur
    d'un obstacle qui n'existe pas dans la simulation, pendant qu'on annoncait un
    evitement de collision.
    """
    import json as _json

    vue = _vue_non_construite(monde, planif, cfg)
    ihr = _json.loads(
        (Path(__file__).resolve().parent.parent.parent
         / "Lab1" / "code" / "ihr_config.json").read_text(encoding="utf-8"))

    xt, yt = vue.maj_tortue(float(ihr["turtlesim"]["start_x"]),
                            float(ihr["turtlesim"]["start_y"]), 0.0)
    xo, yo = vue.maj_obstacle(6.006, 6.930)

    distance = math.hypot(xt - xo, yt - yo)
    assert distance > vue.rayon_obstacle_grille, (
        "le robot demarre dans l'obstacle affiche"
    )


def test_la_vue_du_devoir2_ne_trace_pas_l_obstacle_du_planificateur(monde, planif):
    """
    Le seul obstacle reel du Devoir 2 est la tortue engendree dans turtlesim. Celui
    de planif_config.json appartient a l'exercice du Lab 1.
    """
    from planif import vue as module_vue

    class FauxAxes:
        def __init__(self):
            self.rectangles = 0

        def axvline(self, *_a, **_k):
            pass

        def axhline(self, *_a, **_k):
            pass

        def add_patch(self, *_a, **_k):
            self.rectangles += 1

    sans = FauxAxes()
    module_vue.tracer_grille(sans, monde, planif["affichage"], avec_obstacle=False)
    assert sans.rectangles == 0

    # Controle dans l'autre sens : le Lab 1, lui, DOIT le tracer.
    avec = FauxAxes()
    module_vue.tracer_grille(avec, monde, planif["affichage"], avec_obstacle=True)
    assert avec.rectangles == len(monde.cellules_obstacle())
