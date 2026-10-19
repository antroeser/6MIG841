"""
test_thumb_detector.py - Preuves du contrat de thumb_detector.py (Devoir 1, 6MIG841).

Chaque test isole une affirmation faite par le module dans son propre en-tete : les
mains sont fabriquees par fabrique_mains.py (21 points normalises), donc aucune
camera et aucun MediaPipe ne sont necessaires (workflow.md, regle R5).

Toutes les mains ici sont analysees sur une image CARREE (480x480). `_to_pixels`
multiplie x par image_width et y par image_height : sur une image non carree, cette
mise a l'echelle deformerait un angle ou une rotation faits en espace normalise
(fabrique_mains.py). Le carre elimine cette confusion pour les tests de geometrie ;
il ne change rien pour les tests qui ne verifient qu'un booleen ou une exception.
"""

from __future__ import annotations

import math

import pytest

import fabrique_mains as fm
from thumb_detector import (
    LANDMARK_COUNT,
    THUMB_IP,
    THUMB_MCP,
    THUMB_TIP,
    ThumbCounter,
    analyse_hand,
    count_folded_fingers,
    count_thumbs_up,
    hand_metrics,
    is_thumb_extended,
    to_pixels,
)

IMG_W = IMG_H = 480


# ---------------------------------------------------------------------------
# 1. Les cinq mains canoniques recoivent le verdict attendu par leur construction.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fabricant, attendu",
    [
        (fm.main_pouce_leve, True),
        (fm.main_ouverte, False),
        (fm.main_poing_ferme, False),
        (fm.main_pouce_horizontal, False),
        (fm.main_pouce_vers_le_bas, False),
    ],
    ids=["pouce_leve", "ouverte", "poing_ferme", "pouce_horizontal", "pouce_vers_le_bas"],
)
def test_verdict_des_cinq_mains_canoniques(fabricant, attendu, cfg):
    """Chaque main canonique recoit le verdict is_up attendu par sa geometrie."""
    verdict = analyse_hand(fabricant(), IMG_W, IMG_H, cfg)
    assert verdict.is_up is attendu


def test_is_thumb_extended_refuse_un_pouce_en_crochet_non_monotone():
    """
    Revue finale (constat CRITIQUE) : les cinq mains canoniques ci-dessus ne fabriquent
    que deux chaines de pouce, parfaitement croissante ou parfaitement decroissante, les
    deux seules formes ou `d[MCP] < d[IP] < d[TIP]` (le vrai critere) et
    `d[MCP] < d[TIP]` (une comparaison appauvrie qui ignorerait IP) rendent exactement le
    meme booleen. `main_pouce_en_crochet` casse la chaine a l'articulation IP, pas aux
    extremites : MCP < TIP reste vrai, mais IP depasse TIP. Ce test isole directement
    `is_thumb_extended` (pas `analyse_hand`, dont le verdict `is_up` combine trois
    criteres en ET et ne contraint donc pas ce seul critere) pour que seule cette
    fonction soit mise a l'epreuve.
    """
    main = fm.main_pouce_en_crochet()
    metrics = hand_metrics(to_pixels(main, IMG_W, IMG_H))

    # Controle : la comparaison appauvrie MCP < TIP doit rester vraie sur cette main, sinon
    # ce test ne distingue rien du cas deja couvert par les mains canoniques.
    d = metrics.distances_to_wrist
    assert d[THUMB_MCP] < d[THUMB_TIP]
    assert not (d[THUMB_MCP] < d[THUMB_IP] < d[THUMB_TIP])

    assert is_thumb_extended(metrics) is False


# ---------------------------------------------------------------------------
# 2. Invariance a l'echelle : c'est le premier defaut que les rendus etudiants
#    reproduisaient (seuils de distance fixes en coordonnees normalisees).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("facteur", [0.6, 1.5], ids=["x0.6_eloignee", "x1.5_rapprochee"])
def test_pouce_leve_reste_valide_quelle_que_soit_lechelle(facteur, cfg):
    """Le verdict ne doit pas dependre de la distance a la camera (x0.6 et x1.5)."""
    main = fm.mettre_a_echelle(fm.main_pouce_leve(), facteur)
    verdict = analyse_hand(main, IMG_W, IMG_H, cfg)
    assert verdict.is_up is True


def test_main_trop_petite_est_rejetee_pour_la_bonne_raison(cfg):
    """Controle negatif : sous min_hand_scale_px, le rejet doit nommer la taille."""
    main = fm.mettre_a_echelle(fm.main_pouce_leve(), 0.2)
    verdict = analyse_hand(main, IMG_W, IMG_H, cfg)
    assert verdict.is_up is False
    assert verdict.hand_scale_px < float(cfg["min_hand_scale_px"])
    assert "petit" in verdict.rejected_because.lower()


# ---------------------------------------------------------------------------
# 3. Invariance par rotation du critere de flexion : le second defaut des rendus
#    etudiants (comparaison d'ordonnees, qui suppose la main verticale).
# ---------------------------------------------------------------------------

def test_flexion_est_invariante_par_rotation():
    """count_folded_fingers ne doit pas changer quand la main tourne de 45 degres."""
    points = fm.main_poing_ferme()
    replies_avant = count_folded_fingers(points, hand_metrics(points))

    tournee = fm.tourner(points, math.radians(45.0))
    replies_apres = count_folded_fingers(tournee, hand_metrics(tournee))

    assert replies_avant == replies_apres == 4


# ---------------------------------------------------------------------------
# 4. Le critere d'orientation du pouce EST, lui, deliberement lie au repere image :
#    "pouce leve" se definit par rapport au monde, pas a la main (thumb_detector.py).
# ---------------------------------------------------------------------------

def test_orientation_pouce_juste_sous_le_seuil_reste_vraie(cfg):
    """A un degre sous thumb_vertical_angle_deg, thumb_points_up doit rester vrai."""
    seuil = float(cfg["thumb_vertical_angle_deg"])
    main = fm.tourner(fm.main_pouce_leve(), math.radians(seuil - 1.0))
    verdict = analyse_hand(main, IMG_W, IMG_H, cfg)
    assert verdict.thumb_points_up is True
    assert verdict.is_up is True
    # abs=1e-6 : la rotation (sin/cos) et angle_between (acos) introduisent une
    # erreur flottante de l'ordre de 1e-13 deg, mesuree a l'execution ; ce n'est
    # pas une tolerance de geometrie mais une marge sur l'arrondi machine.
    assert verdict.thumb_angle_deg == pytest.approx(seuil - 1.0, abs=1e-6)


def test_orientation_pouce_juste_au_dessus_du_seuil_devient_fausse(cfg):
    """A un degre au-dessus de thumb_vertical_angle_deg, thumb_points_up bascule a faux."""
    seuil = float(cfg["thumb_vertical_angle_deg"])
    main = fm.tourner(fm.main_pouce_leve(), math.radians(seuil + 1.0))
    verdict = analyse_hand(main, IMG_W, IMG_H, cfg)
    assert verdict.thumb_points_up is False
    assert verdict.is_up is False
    assert verdict.thumb_angle_deg == pytest.approx(seuil + 1.0, abs=1e-6)


# Note : on ne teste pas la valeur exacte du seuil (angle == thumb_vertical_angle_deg
# pile) par rotation. Mesure a l'execution : tourner main_pouce_leve() de exactement
# radians(30.0) rend un angle de 30.000000000000068 deg, et la comparaison stricte
# `angle <= max_angle` du code (thumb_detector.py) devient alors fausse a cause de
# ce depassement flottant, pas a cause d'un defaut de la logique <= elle-meme. Un
# test qui viserait ce pile serait fragile a l'implementation de sin/cos/acos, donc
# non deterministe au sens de workflow.md. La marge de 1 degre choisie ci-dessus
# (>> 1e-13) prouve le cote INCLUSIF sans dependre de cet arrondi.


# ---------------------------------------------------------------------------
# 5. Chemins d'echec obligatoires (workflow.md, regle R5).
# ---------------------------------------------------------------------------

def test_moins_de_21_points_leve_valueerror_nommant_21(cfg):
    """Une main partiellement detectee doit etre rejetee, jamais completee."""
    main_incomplete = fm.main_pouce_leve()[: LANDMARK_COUNT - 1]
    with pytest.raises(ValueError, match="21"):
        analyse_hand(main_incomplete, IMG_W, IMG_H, cfg)


def test_largeur_image_nulle_leve_valueerror(cfg):
    """Une image sans trame (largeur 0) doit etre une erreur explicite, jamais un calcul silencieux."""
    with pytest.raises(ValueError):
        analyse_hand(fm.main_pouce_leve(), 0, IMG_H, cfg)


def test_debounce_frames_zero_leve_valueerror(cfg):
    """debounce_frames=0 desactiverait le filtre sans le dire : doit etre refuse."""
    with pytest.raises(ValueError):
        ThumbCounter({**cfg, "debounce_frames": 0})


def test_update_avec_decompte_negatif_leve_valueerror(cfg):
    """Un decompte de pouces negatif n'a pas de sens physique : doit etre refuse."""
    counter = ThumbCounter(cfg)
    with pytest.raises(ValueError):
        counter.update(-1)


# ---------------------------------------------------------------------------
# 6. count_thumbs_up sur une trame a plusieurs mains.
# ---------------------------------------------------------------------------

def test_count_thumbs_up_sur_liste_mixte_retourne_le_compte_et_lordre(cfg):
    """count_thumbs_up doit compter juste ET rendre un verdict par main, dans l'ordre recu."""
    mains = [fm.main_pouce_leve(), fm.main_ouverte(),
            fm.main_pouce_leve(), fm.main_poing_ferme()]
    compte, verdicts = count_thumbs_up(mains, IMG_W, IMG_H, cfg)
    assert compte == 2
    assert len(verdicts) == len(mains)
    assert [v.is_up for v in verdicts] == [True, False, True, False]


# ---------------------------------------------------------------------------
# 7. ThumbVerdict.explain().
# ---------------------------------------------------------------------------

def test_explain_rend_la_raison_du_rejet_quand_faux(cfg):
    """explain() doit rendre rejected_because, pas une phrase generique, quand is_up est faux."""
    verdict = analyse_hand(fm.main_ouverte(), IMG_W, IMG_H, cfg)
    assert verdict.is_up is False
    assert verdict.rejected_because != ""
    assert verdict.explain() == verdict.rejected_because


def test_explain_mentionne_le_compte_de_doigts_replies_quand_vrai(cfg):
    """explain() doit mentionner le nombre de doigts replies quand is_up est vrai."""
    verdict = analyse_hand(fm.main_pouce_leve(), IMG_W, IMG_H, cfg)
    assert verdict.is_up is True
    assert str(verdict.folded_fingers) in verdict.explain()
