"""
test_history.py - Tests de l'historique borne des tours de dialogue (history.py).

Aucune entree-sortie, aucun modele : `Historique` est un objet Python pur (workflow.md
R5). Deux chemins d'echec couverts : `tours_max` non positif leve ValueError, et
`formater()` sur un historique vide rend une chaine vide plutot qu'un en-tete suivi de
rien (ce qui couterait des jetons pour rien dans l'invite).
"""

from __future__ import annotations

import pytest

from history import Historique, formater_lignes


def test_ajouter_puis_rendre_donne_le_tour_forme_commande_fleche_resume():
    """ajouter() puis rendre() donne un tour forme 'commande -> resume'."""
    historique = Historique(tours_max=3)

    historique.ajouter("avance de deux metres", "avancer")

    assert historique.rendre() == ("avance de deux metres -> avancer",)


def test_la_fenetre_est_bornee_seuls_les_tours_max_plus_recents_sont_retenus():
    """Ajouter plus de tours_max tours ne garde que les DERNIERS, le plus ancien oublie en premier."""
    historique = Historique(tours_max=2)

    historique.ajouter("avance", "avancer")
    historique.ajouter("recule", "reculer")
    historique.ajouter("tourne a droite", "tourner")

    tours = historique.rendre()
    assert len(tours) == 2
    assert "avance -> avancer" not in tours  # le plus ancien a ete oublie
    assert "recule -> reculer" in tours
    assert "tourne a droite -> tourner" in tours


def test_tours_max_nul_leve_valueerror():
    """tours_max=0 leve ValueError : un historique de fenetre nulle ne retiendrait jamais rien."""
    with pytest.raises(ValueError):
        Historique(tours_max=0)


def test_tours_max_negatif_leve_valueerror():
    """tours_max negatif leve aussi ValueError, meme motif que la fenetre nulle."""
    with pytest.raises(ValueError):
        Historique(tours_max=-1)


def test_formater_sur_historique_vide_rend_une_chaine_vide():
    """
    formater() sur un historique vide rend une chaine VIDE : un en-tete « Historique »
    suivi de rien coute des jetons pour rien, sans rien apporter au modele.
    """
    historique = Historique(tours_max=3)

    assert historique.formater() == ""


def test_formater_sur_historique_non_vide_contient_les_tours_dans_l_ordre():
    """formater() sur un historique non vide contient chaque tour, du plus ancien au plus recent."""
    historique = Historique(tours_max=3)
    historique.ajouter("avance de deux metres", "avancer")
    historique.ajouter("et maintenant tourne a droite", "tourner")

    bloc = historique.formater()

    assert "avance de deux metres -> avancer" in bloc
    position_premier = bloc.index("avance de deux metres")
    position_second = bloc.index("et maintenant tourne a droite")
    assert position_premier < position_second


def test_vider_oublie_tous_les_tours_retenus():
    """vider() ramene l'historique a l'etat vide : rendre() est vide et formater() aussi."""
    historique = Historique(tours_max=3)
    historique.ajouter("avance", "avancer")

    historique.vider()

    assert historique.rendre() == ()
    assert historique.formater() == ""


def test_formater_lignes_ignore_les_entrees_vides():
    """formater_lignes() ecarte les chaines vides, pour ne jamais produire une ligne '- ' sans contenu."""
    bloc = formater_lignes(["avance -> avancer", "", "recule -> reculer"])

    assert "- avance -> avancer" in bloc
    assert "\n- \n" not in bloc


def test_formater_lignes_suite_vide_rend_une_chaine_vide():
    """formater_lignes() sur une suite vide (ou entierement vide) rend une chaine vide."""
    assert formater_lignes([]) == ""
    assert formater_lignes(["", ""]) == ""
