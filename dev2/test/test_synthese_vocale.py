"""
test_synthese_vocale.py - Le choix du moteur de synthese, sans jamais parler.

Aucun son n'est produit et aucun moteur reel n'est construit : les deux moteurs sont
remplaces par des faux (R5). Ce qui est teste ici, c'est la DECISION -- quel moteur est
retenu, dans quel ordre, et ce qui est DIT quand aucun ne marche.

Defaut mesure le 2026-09-20 qui a motive ce fichier : SAPI5 n'exposait sur la machine de
l'enseignant que `TTS_MS_EN-US_ZIRA_11.0` (en-US), si bien que le francais du Devoir 2
etait prononce par un moteur anglais, saccade et peu intelligible. Les trois voix French
(Canada) du poste vivent dans Speech_OneCore, invisible a SAPI5, et sont atteintes par
WinRT sans droits administrateur.
"""

from __future__ import annotations

import pytest

import voice
from voice import SortieVocale


class _FauxMoteur:
    """Enregistre ce qu'on lui demande de dire, ne produit aucun son."""

    def __init__(self, voix: str, langue: str):
        self.voix = voix
        self.langue = langue
        self.dits: list[str] = []
        self.ferme = False

    def dire(self, texte: str) -> None:
        self.dits.append(texte)

    def close(self) -> None:
        self.ferme = True


@pytest.fixture()
def moteurs(monkeypatch):
    """Remplace les deux moteurs reels par des faux, et dit lequel a ete construit."""
    construits: list[str] = []

    def faux_winrt(langue="", voix=""):
        construits.append("winrt")
        return _FauxMoteur("Microsoft Caroline", "fr-CA")

    def faux_pyttsx3():
        construits.append("pyttsx3")
        return _FauxMoteur("Microsoft Zira Desktop", "en-US")

    monkeypatch.setattr(voice, "MoteurWinRT", faux_winrt)
    monkeypatch.setattr(voice, "MoteurPyttsx3", faux_pyttsx3)
    return construits


# --------------------------------------------------------------------- le choix du moteur

def test_auto_prend_winrt_en_premier(moteurs):
    """En 'auto', la voix francaise de Windows passe avant SAPI5."""
    sortie = SortieVocale(reglages={"moteur": "auto"})

    assert moteurs == ["winrt"]
    assert sortie.disponible
    assert "fr-CA" in sortie.description


def test_auto_se_rabat_sur_pyttsx3_si_winrt_echoue(moteurs, monkeypatch):
    """Le repli existe, et il n'est pas silencieux : le moteur retenu est nomme."""
    def winrt_casse(langue="", voix=""):
        moteurs.append("winrt")
        raise RuntimeError("paquet winrt absent")

    monkeypatch.setattr(voice, "MoteurWinRT", winrt_casse)

    sortie = SortieVocale(reglages={"moteur": "auto"})

    assert moteurs == ["winrt", "pyttsx3"]
    assert sortie.disponible
    assert "Zira" in sortie.description


def test_les_deux_moteurs_en_echec_donnent_une_raison_nommant_les_deux(monkeypatch):
    """R8 : jamais de repli silencieux. La raison nomme chaque echec."""
    def casse_winrt(langue="", voix=""):
        raise RuntimeError("paquet winrt absent")

    def casse_pyttsx3():
        raise RuntimeError("aucune voix SAPI5")

    monkeypatch.setattr(voice, "MoteurWinRT", casse_winrt)
    monkeypatch.setattr(voice, "MoteurPyttsx3", casse_pyttsx3)

    sortie = SortieVocale(reglages={"moteur": "auto"})

    assert not sortie.disponible
    assert "winrt" in sortie.raison
    assert "pyttsx3" in sortie.raison
    assert "paquet winrt absent" in sortie.raison
    assert "aucune voix SAPI5" in sortie.raison


@pytest.mark.parametrize("demande,attendu", [("winrt", ["winrt"]), ("pyttsx3", ["pyttsx3"])])
def test_un_moteur_explicite_n_essaie_que_celui_la(moteurs, demande, attendu):
    """Nommer un moteur interdit le repli : on veut savoir si CE moteur marche."""
    SortieVocale(reglages={"moteur": demande})

    assert moteurs == attendu


def test_moteur_texte_ne_construit_aucun_moteur_et_le_dit(moteurs):
    sortie = SortieVocale(reglages={"moteur": "texte"})

    assert moteurs == []
    assert not sortie.disponible
    assert "texte" in sortie.raison


def test_un_moteur_inconnu_est_refuse_en_nommant_les_valeurs_admises(moteurs):
    """R3 : une valeur de configuration invalide nomme la cle et ce qui est attendu."""
    sortie = SortieVocale(reglages={"moteur": "festival"})

    assert moteurs == []
    assert not sortie.disponible
    assert "festival" in sortie.raison
    assert "winrt" in sortie.raison and "pyttsx3" in sortie.raison


def test_actif_faux_ne_construit_aucun_moteur(moteurs):
    sortie = SortieVocale(actif=False, reglages={"moteur": "auto"})

    assert moteurs == []
    assert not sortie.disponible


def test_sans_reglages_le_comportement_reste_auto(moteurs):
    """Controle negatif : un appelant qui ne passe rien garde l'ancien contrat."""
    SortieVocale()

    assert moteurs == ["winrt"]


# --------------------------------------------------------------------- dire() et close()

def test_dire_transmet_au_moteur_et_affiche(moteurs, capsys):
    sortie = SortieVocale(reglages={"moteur": "auto"})

    sortie.dire("Est-ce bien cela ?")

    assert sortie._moteur.dits == ["Est-ce bien cela ?"]
    assert "Est-ce bien cela ?" in capsys.readouterr().out


def test_un_moteur_qui_leve_pendant_dire_bascule_en_texte_seul(moteurs, monkeypatch, capsys):
    """Une panne en cours de route ne doit pas tuer le devoir, mais doit se voir."""
    sortie = SortieVocale(reglages={"moteur": "auto"})

    def dire_casse(_texte):
        raise RuntimeError("peripherique audio disparu")

    monkeypatch.setattr(sortie._moteur, "dire", dire_casse)

    sortie.dire("Plan confirme.")

    assert not sortie.disponible
    assert "peripherique audio disparu" in sortie.raison
    sorties = capsys.readouterr()
    assert "Plan confirme." in sorties.out
    assert "interrompue" in sorties.err


def test_close_ferme_le_moteur_et_est_idempotent(moteurs):
    sortie = SortieVocale(reglages={"moteur": "auto"})
    moteur = sortie._moteur

    sortie.close()
    sortie.close()

    assert moteur.ferme
    assert not sortie.disponible


def test_la_description_dit_la_voix_reellement_retenue(moteurs):
    """R9 : le journal doit nommer la voix qui parle, pas seulement 'synthese active'."""
    sortie = SortieVocale(reglages={"moteur": "auto"})

    assert "Caroline" in sortie.description
    assert "fr-CA" in sortie.description
