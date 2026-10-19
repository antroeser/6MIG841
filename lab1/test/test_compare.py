"""
test_compare.py - Tests de planif.compare, le banc qui compare les trois planificateurs (plan06).

Le banc fait tourner A*, Theta* et D*-Lite sur le MEME objet World, puis rend trois grandeurs
par planificateur (longueur, points de passage, cellules reexaminees) et un rapport JSON a
cote du texte humain (workflow.md R16, R17). Cette suite verifie que le monde n'est pas
duplique, que les trois grandeurs sont bien presentes, le rapport JSON du CLI (ecrit et
dry-run), et le chemin d'echec exige : depart ou but absent de la configuration (R5).
"""

from __future__ import annotations

import json

import pytest

from planif import compare, world


# --------------------------------------------------------------------- chemin heureux

def test_les_trois_planificateurs_tournent_sur_le_meme_monde():
    """
    Le monde passe en argument est reellement partage entre les trois planificateurs : il
    porte l'obstacle_replanification apres l'appel, preuve que compare.py n'a pas travaille
    sur des copies (le banc ne compare pas des mondes differents).
    """
    monde = world.World()
    rectangle = world.load_config()["obstacle_replanification"]
    cellules = world.rectangle_vers_cellules(rectangle)
    assert all(not monde.est_occupee(cellule) for cellule in cellules)

    rapport = compare.executer_comparaison(monde)

    assert all(monde.est_occupee(cellule) for cellule in cellules)
    assert rapport["grille"]["largeur_cellules"] == monde.largeur_cellules
    assert rapport["grille"]["hauteur_cellules"] == monde.hauteur_cellules


def test_rapport_rend_les_trois_grandeurs_pour_chaque_planificateur():
    """Chaque planificateur du rapport porte exactement longueur, points_de_passage et
    cellules_reexaminees, avec des valeurs coherentes (chemin trouve, non vide)."""
    rapport = compare.executer_comparaison()
    for nom in ("astar", "thetastar", "dstarlite"):
        ligne = rapport["planificateurs"][nom]
        assert set(ligne) == {"longueur", "points_de_passage", "cellules_reexaminees"}
        assert ligne["longueur"] > 0
        assert ligne["points_de_passage"] > 0
        assert ligne["cellules_reexaminees"] > 0


def test_main_ecrit_un_rapport_json_lisible(tmp_path):
    """Le CLI ecrit un rapport JSON valide, lisible par un caller sans decouper de la prose (R17)."""
    cible = tmp_path / "rapport.json"
    code = compare.main(["--sortie", str(cible)])
    assert code == 0
    assert cible.is_file()
    contenu = json.loads(cible.read_text(encoding="utf-8"))
    assert set(contenu["planificateurs"]) == {"astar", "thetastar", "dstarlite"}


def test_dry_run_n_ecrit_rien(tmp_path):
    """--dry-run n'ecrit jamais le rapport, meme s'il l'affiche (R16)."""
    cible = tmp_path / "rapport_absent.json"
    code = compare.main(["--sortie", str(cible), "--dry-run"])
    assert code == 0
    assert not cible.exists()


# --------------------------------------------------------------------- chemin d'echec

def test_depart_ou_but_absent_leve_une_erreur_explicite():
    """Une configuration sans depart ni but leve ValueError, jamais un rapport partiel."""
    monde = world.World({"grille": {"largeur_cellules": 5, "hauteur_cellules": 5, "taille_cellule": 1.0}})
    with pytest.raises(ValueError, match="depart"):
        compare.executer_comparaison(monde)
