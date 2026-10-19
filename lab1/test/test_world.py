"""
test_world.py - Tests de planif.world, la grille des trois planificateurs (plan06).

Palier 0 : astar, thetastar, dstarlite et compare lisent tous la grille, les conversions et
l'occupation ici. Cette suite verifie le chemin heureux (conversions inverses, occupation,
ligne de vue) ET les deux chemins d'echec exiges par le plan : cellule hors grille, pas de
cellule nul (workflow.md R5).
"""

from __future__ import annotations

import json

import pytest

from planif import world


def _monde_reel() -> world.World:
    """Le monde reel de planif_config.json (jamais modifie par cette suite)."""
    return world.World()


# --------------------------------------------------------------------- chemin heureux

def test_conversion_grille_vers_unites_et_retour_est_inverse():
    """Cellule -> unites -> cellule doit rendre exactement la cellule de depart."""
    monde = _monde_reel()
    dernier_coin = (monde.largeur_cellules - 1, monde.hauteur_cellules - 1)
    for cellule in [(0, 0), (3, 4), dernier_coin]:
        point = monde.vers_unites(cellule)
        assert monde.vers_cellule(point) == cellule


def test_cellule_de_l_obstacle_est_occupee():
    """Une cellule a l'interieur du rectangle obstacle_initial est lue comme occupee."""
    monde = _monde_reel()
    # obstacle_initial : colonnes 31-33, lignes 31-33, centre sur (32, 32) (planif_config.json,
    # aligne le 2026-09-20 sur la grille 64x64 de la reference).
    assert monde.est_occupee((32, 32)) is True
    assert monde.est_occupee((0, 0)) is False


def test_ligne_de_vue_libre_a_cote_de_l_obstacle_mais_pas_a_travers():
    """La ligne de vue est libre loin de l'obstacle, bloquee si elle le traverse."""
    monde = _monde_reel()
    # Loin de l'obstacle (ligne 10, hors des lignes 31-33 occupees) : ligne de vue directe.
    assert monde.ligne_de_vue_libre((28, 10), (36, 10)) is True
    # A travers l'obstacle (ligne 32, dans les lignes 31-33 occupees) : bloquee.
    assert monde.ligne_de_vue_libre((28, 32), (36, 32)) is False


def test_ligne_de_vue_libre_diagonale_qui_traverse_une_cellule_occupee_est_bloquee():
    """
    Revue finale (constat CRITIQUE) : les deux seuls tests dedies de `ligne_de_vue_libre`
    (ci-dessus) n'utilisent que des segments HORIZONTAUX. Une diagonale parfaite (meme
    ecart en colonne et en ligne) visite chaque cellule (k, k) le long du trace de
    Bresenham -- une propriete de l'algorithme, pas du code sous test -- donc placer un
    obstacle PILE sur cette diagonale et attendre un blocage est un jugement independant
    de la fonction, pas une redite de son propre calcul.
    """
    monde = world.World({"grille": {"largeur_cellules": 5, "hauteur_cellules": 5, "taille_cellule": 1.0}})
    monde.definir_occupation([(2, 2)], True)
    assert monde.ligne_de_vue_libre((0, 0), (4, 4)) is False


def test_ligne_de_vue_libre_refuse_le_coin_partage_par_deux_cellules_occupees_en_diagonale():
    """
    Asymetrie mesuree par la revue finale : `voisins()` refuse deja explicitement une
    diagonale qui coupe le coin partage par deux cellules occupees adjacentes
    (test_voisins_refuse_une_diagonale_qui_couperait_un_coin_entre_deux_cellules_occupees
    plus bas), mais `ligne_de_vue_libre` ne testait, avant ce correctif, que les cellules
    reellement visitees par le trace de Bresenham -- jamais les deux cotes d'un pas
    diagonal. Avec des obstacles en (1, 0) et (0, 1), le trace de (0, 0) vers (2, 2) saute
    de (0, 0) a (1, 1) puis (2, 2) sans jamais visiter (1, 0) ni (0, 1) : (1, 1)
    elle-meme reste libre. Le jugement est independant de la fonction sous test : il
    applique la MEME regle geometrique que `voisins()`, pas un second appel a
    `ligne_de_vue_libre`.
    """
    monde = world.World({"grille": {"largeur_cellules": 5, "hauteur_cellules": 5, "taille_cellule": 1.0}})

    # Un seul cote occupe : le pas diagonal (0,0)->(1,1) ne coupe aucun coin partage.
    monde.definir_occupation([(1, 0)], True)
    assert monde.ligne_de_vue_libre((0, 0), (2, 2)) is True

    # Les deux cotes occupes : la meme configuration que voisins() refuse deja pour un pas
    # diagonal d'une seule cellule, ici sur une ligne de vue de deux pas.
    monde.definir_occupation([(0, 1)], True)
    assert monde.est_occupee((1, 1)) is False, "le coin lui-meme reste libre : c'est le coin, pas la cellule, qui est en cause"
    assert (1, 1) not in monde.voisins((0, 0)), "voisins() doit deja refuser ce pas diagonal"
    assert monde.ligne_de_vue_libre((0, 0), (2, 2)) is False, (
        "le segment passe exactement par le coin partage entre (1, 0) et (0, 1), la meme "
        "configuration que voisins() refuse pour un pas diagonal d'une seule cellule"
    )


def test_definir_occupation_rend_les_cellules_reellement_changees():
    """definir_occupation ne rapporte que les cellules dont l'etat a change."""
    monde = _monde_reel()
    changees = monde.definir_occupation([(0, 1), (32, 32)], True)
    # (32, 32) est deja occupee (obstacle_initial) ; seule (0, 1) change reellement.
    assert changees == [(0, 1)]
    assert monde.est_occupee((0, 1)) is True


def test_voisins_respecte_l_ordre_fixe_et_exclut_l_occupation():
    """voisins() exclut les cellules occupees et hors grille, dans l'ordre fixe de World."""
    monde = world.World({
        "grille": {"largeur_cellules": 3, "hauteur_cellules": 3, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 1, "colonne_max": 1, "ligne_min": 0, "ligne_max": 0},
    })
    voisins = monde.voisins((0, 0))
    assert (1, 0) not in voisins  # occupee
    assert (2, 2) not in voisins  # hors grille (pas 8-adjacente de (0,0) de toute facon)
    assert (0, 1) in voisins


def test_voisins_refuse_une_diagonale_qui_couperait_un_coin_entre_deux_cellules_occupees():
    """
    Une diagonale entre deux cellules occupees adjacentes coupe un coin qu'un robot reel ne
    peut pas traverser, meme si la cellule diagonale elle-meme est libre : voisins() (world.py
    lignes 278-282) refuse alors cette diagonale. Branche jamais exercee par aucun test avant
    celui-ci -- ni pour la prouver, ni pour prouver qu'elle exige les DEUX cotes occupes (le
    controle negatif : un seul cote occupe ne doit rien bloquer).
    """
    monde = world.World({"grille": {"largeur_cellules": 3, "hauteur_cellules": 3, "taille_cellule": 1.0}})

    # Un seul cote occupe : la diagonale (1, 1) reste accessible depuis (0, 0).
    monde.definir_occupation([(1, 0)], True)
    assert (1, 1) in monde.voisins((0, 0))

    # Les deux cotes occupes : la diagonale (1, 1) coupe desormais un coin, elle est refusee,
    # bien qu'elle-meme soit libre.
    monde.definir_occupation([(0, 1)], True)
    assert (1, 1) not in monde.voisins((0, 0))
    assert monde.est_occupee((1, 1)) is False


# --------------------------------------------------------------------- chemins d'echec

def test_cellule_hors_grille_leve_une_erreur_explicite():
    """Une cellule hors grille leve CelluleInvalideError, jamais un repli sur le bord."""
    monde = _monde_reel()
    hors_grille = (monde.largeur_cellules, 0)
    with pytest.raises(world.CelluleInvalideError, match=rf"\({hors_grille[0]}, 0\)"):
        monde.est_occupee(hors_grille)
    with pytest.raises(world.CelluleInvalideError):
        monde.vers_unites((-1, 0))
    with pytest.raises(world.CelluleInvalideError):
        monde.vers_cellule((-5.0, -5.0))


def test_pas_de_cellule_nul_leve_une_erreur_explicite():
    """Une taille_cellule nulle ou negative leve CelluleInvalideError a la construction."""
    with pytest.raises(world.CelluleInvalideError, match="taille_cellule"):
        world.World({"grille": {"largeur_cellules": 5, "hauteur_cellules": 5, "taille_cellule": 0}})
    with pytest.raises(world.CelluleInvalideError):
        world.World({"grille": {"largeur_cellules": 5, "hauteur_cellules": 5, "taille_cellule": -1.0}})


# --------------------------------------------------------------------- config, comme test_config.py

def test_chemin_par_defaut_pointe_vers_planif_config_json():
    """Sans PLANIF_CONFIG, config_path() resout vers planif_config.json a cote du paquet."""
    chemin = world.config_path()
    assert chemin.name == "planif_config.json"
    assert chemin.is_file()


def test_planif_config_redirige_le_chemin_resolu(tmp_path, monkeypatch):
    """La variable d'environnement PLANIF_CONFIG l'emporte sur le chemin par defaut."""
    cible = tmp_path / "ailleurs.json"
    cible.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("PLANIF_CONFIG", str(cible))
    assert world.config_path() == cible.resolve()


def test_section_absente_leve_configerror_nommant_la_section(tmp_path, monkeypatch):
    """Une section manquante leve ConfigError et nomme cette section dans le message."""
    chemin = tmp_path / "config_test.json"
    chemin.write_text(json.dumps({"grille": {}}), encoding="utf-8")
    monkeypatch.setenv("PLANIF_CONFIG", str(chemin))
    world.load_config(force_reload=True)
    with pytest.raises(world.ConfigError, match="depart"):
        world.config_section("depart")


def test_cle_absente_leve_configerror_nommant_la_cle(tmp_path, monkeypatch):
    """Une cle manquante nomme la cle absente et liste les cles reellement presentes."""
    chemin = tmp_path / "config_test.json"
    chemin.write_text(json.dumps({"grille": {"largeur_cellules": 5}}), encoding="utf-8")
    monkeypatch.setenv("PLANIF_CONFIG", str(chemin))
    world.load_config(force_reload=True)
    with pytest.raises(world.ConfigError) as exc_info:
        world.config_value("grille", "hauteur_cellules")
    message = str(exc_info.value)
    assert "hauteur_cellules" in message
    assert "largeur_cellules" in message


def test_planif_config_fichier_inexistant_leve_configerror(tmp_path, monkeypatch):
    """PLANIF_CONFIG pointant vers un fichier absent leve ConfigError, jamais un crash brut."""
    monkeypatch.setenv("PLANIF_CONFIG", str(tmp_path / "n_existe_pas.json"))
    with pytest.raises(world.ConfigError, match="introuvable"):
        world.load_config(force_reload=True)
