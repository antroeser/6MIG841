"""
test_hud.py - Preuves de build_hud (detect_thumbs.py, Devoir 1, 6MIG841).

`build_hud` est la seule fonction pure de detect_thumbs.py : elle ne touche ni a
OpenCV ni a la camera, elle compose seulement des lignes (texte, couleur) a partir
de verdicts deja calcules. C'est la seule partie de ce fichier testable sans
materiel (voir son propre en-tete et workflow.md, regle R5).

`import detect_thumbs` est sans danger ici : les imports couteux du module
(`ihr_ros.hands`, qui importe MediaPipe, et OpenCV) sont tous LOCAUX aux fonctions
qui touchent la camera (`open_source`, `run`) ou au suivi de main, jamais executes
au chargement du module. Aucun autre appel de detect_thumbs (run, open_source,
main) n'est fait ici.
"""

from __future__ import annotations

import detect_thumbs
import fabrique_mains as fm
from thumb_detector import analyse_hand

IMG_W = IMG_H = 480


def test_build_hud_sans_main_ne_rend_que_les_deux_lignes_dentete():
    """Sans main detectee, build_hud doit rendre exactement les deux lignes d'entete."""
    lignes = detect_thumbs.build_hud([], stable_count=2, raw_count=3, fps=15.0)
    assert len(lignes) == 2
    texte_stable, _ = lignes[0]
    texte_trame, _ = lignes[1]
    assert "2" in texte_stable
    assert "3" in texte_trame


def test_build_hud_rend_une_ligne_par_main_en_plus_de_lentete(cfg):
    """build_hud doit rendre 2 lignes d'entete + une ligne par main, dans l'ordre recu."""
    verdicts = [
        analyse_hand(fm.main_pouce_leve(), IMG_W, IMG_H, cfg),
        analyse_hand(fm.main_ouverte(), IMG_W, IMG_H, cfg),
        analyse_hand(fm.main_poing_ferme(), IMG_W, IMG_H, cfg),
    ]
    lignes = detect_thumbs.build_hud(verdicts, stable_count=1, raw_count=1, fps=29.7)
    assert len(lignes) == 2 + len(verdicts)


def test_build_hud_distingue_la_couleur_dune_main_acceptee_et_rejetee(cfg):
    """La couleur de la ligne d'une main acceptee doit differer de celle d'une main rejetee."""
    verdict_accepte = analyse_hand(fm.main_pouce_leve(), IMG_W, IMG_H, cfg)
    verdict_rejete = analyse_hand(fm.main_poing_ferme(), IMG_W, IMG_H, cfg)
    assert verdict_accepte.is_up is True
    assert verdict_rejete.is_up is False

    lignes = detect_thumbs.build_hud([verdict_accepte, verdict_rejete],
                                     stable_count=1, raw_count=1, fps=30.0)
    _, couleur_acceptee = lignes[2]
    _, couleur_rejetee = lignes[3]
    assert couleur_acceptee != couleur_rejetee


def test_build_hud_ligne_de_main_reprend_lexplication_du_verdict(cfg):
    """La ligne d'une main doit contenir exactement l'explication rendue par son verdict."""
    verdict = analyse_hand(fm.main_poing_ferme(), IMG_W, IMG_H, cfg)
    lignes = detect_thumbs.build_hud([verdict], stable_count=0, raw_count=0, fps=30.0)
    texte_main, _ = lignes[2]
    assert verdict.explain() in texte_main
