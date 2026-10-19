"""
test_thumb_counter.py - Preuves du filtre temporel ThumbCounter (Devoir 1, 6MIG841).

Aucun rendu etudiant ne filtrait dans le temps (thumb_detector.py, en-tete) : le
compteur affiche clignotait d'une trame a l'autre. Un filtre qui ne publierait
JAMAIS passerait un test a sens unique ; chaque test ici verifie donc aussi bien ce
qui doit se publier que ce qui doit rester bloque.
"""

from __future__ import annotations

from thumb_detector import ThumbCounter


def test_valeur_repetee_window_fois_est_publiee(cfg):
    """Une valeur identique repetee `window` fois de suite devient le decompte stable."""
    counter = ThumbCounter(cfg)
    stable = 0
    for _ in range(counter.window):
        stable = counter.update(2)
    assert stable == 2
    assert counter.stable_count == 2


def test_valeur_repetee_moins_que_window_fois_nest_pas_publiee(cfg):
    """Une valeur qui ne tient pas toute la fenetre laisse l'ancien decompte stable inchange."""
    counter = ThumbCounter(cfg)
    fenetre = counter.window

    # Etablir un decompte stable connu avant de le perturber.
    for _ in range(fenetre):
        counter.update(0)
    assert counter.stable_count == 0

    stable = 0
    for _ in range(fenetre - 1):
        stable = counter.update(2)
    assert stable == 0
    assert counter.stable_count == 0


def test_valeurs_alternees_ne_publient_jamais(cfg):
    """Une alternance stricte ne remplit jamais une fenetre unanime : le stable ne bouge plus.

    La comparaison se fait contre un stable CONNU et NON NUL (5), etabli avant
    l'alternance : un test qui se contenterait de verifier un retour a 0 serait
    incapable de distinguer "jamais publie" de "republie a la valeur par defaut".
    """
    counter = ThumbCounter(cfg)
    fenetre = counter.window

    for _ in range(fenetre):
        counter.update(5)
    assert counter.stable_count == 5

    stable = counter.stable_count
    for i in range(fenetre * 4):
        stable = counter.update(i % 2)
    assert stable == 5
    assert counter.stable_count == 5


def test_reset_remet_le_decompte_stable_a_zero(cfg):
    """reset() doit vider l'historique et remettre le decompte stable a 0."""
    counter = ThumbCounter(cfg)
    for _ in range(counter.window):
        counter.update(3)
    assert counter.stable_count == 3

    counter.reset()
    assert counter.stable_count == 0


def test_les_premieres_maj_ne_publient_quau_dernier_tour_de_la_fenetre(cfg):
    """Sur les toutes premieres trames, seule la window-ieme mise a jour doit publier."""
    counter = ThumbCounter(cfg)
    fenetre = counter.window
    resultats = [counter.update(1) for _ in range(fenetre)]
    assert resultats[:-1] == [0] * (fenetre - 1)
    assert resultats[-1] == 1
