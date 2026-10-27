"""
test_hallucinations.py - Whisper ne doit pas faire parler l'etudiant a sa place.

Defaut signale par l'enseignant le 2026-09-20 : la fenetre de saisie vocale affichait
« Sous-titres realises par l'Amara.org » puis « Merci d'avoir regarde cette video » alors
qu'il n'avait rien dit. Ce ne sont pas des erreurs de reconnaissance : Whisper a ete
entraine sur des sous-titres de videos, et sur du silence il rend les formules de fin de
generique qu'il a le plus vues.

La transcription du Devoir 2 etant PROGRESSIVE (le tampon est retranscrit toutes les
`speech_rafraichissement_secondes`, y compris avant que l'etudiant ait commence a parler),
le tampon quasi silencieux est ici la norme, pas l'exception.

Deux garde-fous sont eprouves ici, et ils ne se remplacent pas : le VAD supprime la CAUSE
en ecartant les plages sans parole, la liste noire est le FILET si une hallucination passe
quand meme. Aucun modele n'est charge dans ce fichier (R5) : le VAD est verifie par les
OPTIONS transmises a `transcribe`, la liste noire par comparaison de chaines. La preuve
sur le vrai modele est notee dans le journal, mesuree le 2026-09-20 : sur quatre secondes
de silence numerique, la transcription passe de « Sous-titres realises par la communaute
d'Amara.org » a la chaine vide.
"""

from __future__ import annotations

import pytest

from voice import est_hallucination, transcrire_avec_whisper


class _FauxSegment:
    def __init__(self, texte: str):
        self.text = texte


class _FauxModele:
    """Enregistre les options recues et rend les segments qu'on lui a donnes."""

    def __init__(self, textes):
        self._textes = list(textes)
        self.options: dict = {}

    def transcribe(self, _audio, **options):
        self.options = options
        return (_FauxSegment(t) for t in self._textes), None


class _FauxAudio:
    def get_wav_data(self):
        return b"RIFF....WAVE"


# --------------------------------------------------------------------- la liste noire

@pytest.mark.parametrize("phrase", [
    "Sous-titres realises par l'Amara.org",
    "Sous-titres réalisés par l'Amara.org",
    "Merci d'avoir regardé cette vidéo.",
    "Merci d'avoir regardé ce vidéo",
    "MERCI D'AVOIR REGARDE CETTE VIDEO !",
])
def test_les_formules_vues_par_l_enseignant_sont_reconnues(cfg, phrase):
    """Accents et ponctuation ne doivent pas faire echouer la comparaison."""
    assert est_hallucination(phrase, cfg["transcription"]["phrases_hallucinees"])


@pytest.mark.parametrize("phrase", [
    "avance de deux metres",
    "tourne a gauche de 45 degres",
    "Merci d'avoir regarde cette video, avance de deux metres",
    "J'accepte.",
])
def test_une_vraie_commande_n_est_jamais_prise_pour_une_hallucination(cfg, phrase):
    """
    Controle negatif, et le troisieme cas est celui qui compte : la comparaison porte
    sur la phrase ENTIERE. Filtrer une sous-chaine couperait une commande reelle qui
    contiendrait la formule par hasard.
    """
    assert not est_hallucination(phrase, cfg["transcription"]["phrases_hallucinees"])


def test_un_texte_vide_n_est_pas_une_hallucination(cfg):
    assert not est_hallucination("", cfg["transcription"]["phrases_hallucinees"])
    assert not est_hallucination("   ", cfg["transcription"]["phrases_hallucinees"])


def test_une_liste_vide_ne_filtre_rien():
    """Sans catalogue, rien n'est jete : le filet est optionnel, pas implicite."""
    assert not est_hallucination("Merci d'avoir regarde cette video", ())


# --------------------------------------------------------------------- le VAD

def test_les_reglages_activent_le_vad_et_coupent_le_contexte(cfg):
    """
    Le VAD est la correction de FOND : il ecarte les plages sans parole avant le
    modele. `condition_on_previous_text=False` empeche par ailleurs une hallucination
    unique de se repeter a chaque rafraichissement en servant de contexte a la suivante.
    """
    modele = _FauxModele(["avance"])

    transcrire_avec_whisper(modele, _FauxAudio(), "fr", cfg["transcription"])

    assert modele.options["vad_filter"] is True
    assert modele.options["condition_on_previous_text"] is False
    assert modele.options["vad_parameters"]["min_silence_duration_ms"] == int(
        cfg["transcription"]["vad_duree_silence_min_ms"])
    assert modele.options["language"] == "fr"


def test_sans_reglages_les_options_restent_celles_d_avant(cfg):
    """
    Controle negatif : un appelant qui ne passe pas de reglages garde EXACTEMENT
    l'ancien appel, sans VAD ni option supplementaire.
    """
    modele = _FauxModele(["avance"])

    transcrire_avec_whisper(modele, _FauxAudio(), "fr")

    assert modele.options == {"language": "fr"}


# --------------------------------------------------------------------- les deux ensemble

def test_une_hallucination_rendue_par_le_modele_est_jetee(cfg):
    """Si le VAD laisse passer la formule, la liste noire la rattrape."""
    modele = _FauxModele(["Sous-titres réalisés par la communauté d'Amara.org"])

    texte = transcrire_avec_whisper(modele, _FauxAudio(), "fr", cfg["transcription"])

    assert texte == ""


def test_une_vraie_commande_traverse_intacte(cfg):
    modele = _FauxModele(["avance de deux", " metres"])

    texte = transcrire_avec_whisper(modele, _FauxAudio(), "fr", cfg["transcription"])

    assert texte == "avance de deux metres"
