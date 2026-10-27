"""
test_voice_window.py - Devoir 2, plan09 : les six cas exiges de VoiceWindow.

Aucune fenetre reelle n'est jamais ouverte ici (workflow.md R5) : tkinter est
remplace par faux_tkinter.construire_faux_module(). Les gestionnaires poses par
bind('<Return>', ...) et protocol('WM_DELETE_WINDOW', ...) sont declenches
DIRECTEMENT via FauxTk.declencher_entree()/declencher_fermeture(), ce qui
suffit a exercer toute la logique de VoiceWindow sans jamais passer par une
vraie boucle d'evenements Tk ni par un vrai fil de fond.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faux_tkinter import construire_faux_module  # noqa: E402


@pytest.fixture
def fenetre_cfg(cfg):
    """Section devoir2.fenetre_voix de la configuration commune."""
    return cfg["fenetre_voix"]


@pytest.fixture
def faux_tk(monkeypatch):
    """Remplace le module tkinter par le faux avant chaque construction de VoiceWindow."""
    module = construire_faux_module()
    monkeypatch.setitem(sys.modules, "tkinter", module)
    return module


def _construire(fenetre_cfg, on_fermeture=None):
    from voice_window import VoiceWindow

    return VoiceWindow(fenetre_cfg, on_fermeture=on_fermeture)


# --------------------------------------------------------------------- 1. texte reecrit en place

def test_afficher_texte_remplace_le_precedent_jamais_empile(faux_tk, fenetre_cfg):
    """Controle negatif de plan09.md : un affichage qui empile rend la lecture impossible."""
    fenetre = _construire(fenetre_cfg)

    fenetre.afficher_texte("tourne")
    fenetre.pump()
    fenetre.afficher_texte("tourne a gauche")
    fenetre.pump()

    assert fenetre._label_texte.text == "tourne a gauche"
    assert "tourne\ntourne a gauche" not in fenetre._label_texte.text


# --------------------------------------------------------------------- 2. Entree publie

def test_entree_publie_le_texte_courant(faux_tk, fenetre_cfg):
    """C'est le geste que l'enonce exige : Entree fige et rend le texte courant."""
    fenetre = _construire(fenetre_cfg)
    fenetre.afficher_texte("avance")

    fenetre._root.declencher_entree()
    texte = fenetre.attendre_confirmation()

    assert texte == "avance"


# --------------------------------------------------------------------- 3. Entree sur texte vide

def test_entree_sur_texte_vide_ne_publie_rien(faux_tk, fenetre_cfg):
    """Sinon la machine d'etat recevrait une phrase vide (plan09.md, controle negatif)."""
    fenetre = _construire(fenetre_cfg)

    fenetre._root.declencher_entree()

    assert fenetre._confirmation_en_attente is None


# --------------------------------------------------------------------- 4. porte fermee

def test_porte_fermee_empeche_la_saisie(faux_tk, fenetre_cfg):
    """Le micro se tait pendant l'execution : Entree n'a aucun effet, meme sur un texte non vide."""
    fenetre = _construire(fenetre_cfg)
    fenetre.afficher_texte("avance")
    fenetre.afficher_ecoute(False)

    fenetre._root.declencher_entree()

    assert fenetre._confirmation_en_attente is None


def test_porte_rouverte_permet_de_nouveau_la_saisie(faux_tk, fenetre_cfg):
    """Controle de symetrie : rouvrir la porte redonne effet a Entree."""
    fenetre = _construire(fenetre_cfg)
    fenetre.afficher_texte("avance")
    fenetre.afficher_ecoute(False)
    fenetre._root.declencher_entree()
    assert fenetre._confirmation_en_attente is None

    fenetre.afficher_ecoute(True)
    fenetre._root.declencher_entree()

    assert fenetre._confirmation_en_attente == "avance"


# --------------------------------------------------------------------- 5. fermeture arrete le noeud

def test_la_fermeture_arrete_le_noeud_sans_processus_orphelin(faux_tk, fenetre_cfg):
    """La croix de la fenetre avertit l'appelant (voice_input_node), controle de nettoyage."""
    arrets: list[bool] = []
    fenetre = _construire(fenetre_cfg, on_fermeture=lambda: arrets.append(True))

    fenetre._root.declencher_fermeture()

    assert arrets == [True]
    assert fenetre.fermee is True
    assert fenetre._root.detruite is True


def test_attendre_confirmation_rend_none_si_deja_fermee(faux_tk, fenetre_cfg):
    """attendre_confirmation() ne bloque jamais indefiniment sur une fenetre deja fermee."""
    fenetre = _construire(fenetre_cfg)
    fenetre.close()

    assert fenetre.attendre_confirmation() is None


def test_attendre_confirmation_n_appelle_jamais_tkinter(faux_tk, fenetre_cfg):
    """
    Corrige le 2026-09-20 (plan09.md, etape 6, epreuve reelle) : tkinter sous Windows
    leve RuntimeError si un widget est touche depuis un fil autre que le fil
    principal. attendre_confirmation() est appelee depuis le fil de fond qui porte la
    capture (voice.MicrophoneInput.ecouter()) : elle ne doit donc plus jamais pomper
    elle-meme, seul pump() (fil principal) le fait desormais.
    """
    fenetre = _construire(fenetre_cfg)
    fenetre.afficher_texte("avance")
    fenetre._root.declencher_entree()
    appels_avant = fenetre._root.appels_update

    texte = fenetre.attendre_confirmation()

    assert texte == "avance"
    assert fenetre._root.appels_update == appels_avant


# --------------------------------------------------------------------- 6. tkinter indisponible

def test_tkinter_indisponible_leve_en_nommant_la_cause(monkeypatch, fenetre_cfg):
    """Chemin d'echec : jamais un blocage muet (R3), l'erreur nomme la cause reelle."""
    module = construire_faux_module()

    def _echoue() -> None:
        raise RuntimeError("aucun affichage disponible (pas de serveur X)")

    module.Tk = _echoue
    monkeypatch.setitem(sys.modules, "tkinter", module)

    from voice_window import VoiceWindow

    with pytest.raises(RuntimeError) as exc_info:
        VoiceWindow(fenetre_cfg)

    message = str(exc_info.value)
    assert "aucun affichage disponible" in message
    assert "tkinter" in message.lower()


# --------------------------------------------------------------------- close() idempotent

def test_close_est_idempotent(faux_tk, fenetre_cfg):
    """Rappelable deux fois sans effet, meme contrat que EntreeVocale.close()."""
    fenetre = _construire(fenetre_cfg)

    fenetre.close()
    fenetre.close()  # ne doit pas lever

    assert fenetre.fermee is True
