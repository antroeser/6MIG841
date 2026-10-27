"""
test_voice.py - Tests des entrees/sorties vocales du Devoir 2 (voice.py).

Aucun materiel n'est touche ici : ni microphone, ni reseau, ni modele faster-whisper
reel (workflow.md R5). `ScriptedInput` reste la seule entree testee en profondeur pour
le dialogue complet du Devoir 2. `MicrophoneInput` EST construite depuis le 2026-09-19
(.sdd/6mig841-ameliorations/stt-local-report.md), mais toujours avec le module
`speech_recognition` REMPLACE par `faux_speech_recognition.construire_faux_module()`
(aucun peripherique reel n'est jamais ouvert) et un `transcripteur` INJECTE (jamais
`charger_transcripteur_whisper`, qui chargerait un vrai modele). `SortieVocale(actif=True)`
n'est pas instanciee : elle chargerait un vrai moteur pyttsx3.

Depuis plan09.md (2026-09-20), l'attente d'Entree ne passe plus par `input()` mais par
l'interface d'affichage injectable de `MicrophoneInput` (voir voice_window.VoiceWindow en
production) : `_FausseFenetre`, ci-dessous, remplace toujours cette fenetre dans ces tests,
jamais une vraie fenetre tkinter (workflow.md R5, meme principe que test_voice_window.py).
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import voice  # noqa: E402
from faux_speech_recognition import construire_faux_module  # noqa: E402
from voice import (  # noqa: E402
    MicrophoneInput,
    ScriptedInput,
    SortieVocale,
    _ajouter_repertoires_dll_cuda,
    charger_modele_whisper,
    charger_transcripteur_whisper,
    ouvrir_entree,
    transcrire_avec_whisper,
)


# --------------------------------------------------------------------- ScriptedInput

def test_scripted_input_rend_les_phrases_dans_l_ordre_puis_la_fin_en_boucle():
    """ScriptedInput rend ses phrases dans l'ordre, puis la phrase de fin indefiniment, sans jamais lever."""
    entree = ScriptedInput(["avance", "oui"], phrase_de_fin="quitter")

    assert entree.ecouter("Commande ?") == "avance"
    assert entree.ecouter("oui ou non ?") == "oui"
    assert entree.ecouter("oui ou non ?") == "quitter"
    assert entree.ecouter("oui ou non ?") == "quitter"  # la file est vide : jamais IndexError
    assert entree.restantes == 0


def test_scripted_input_enregistre_les_invites_et_les_phrases_entendues():
    """ScriptedInput enregistre chaque invite recue et chaque phrase rendue, dans l'ordre des appels."""
    entree = ScriptedInput(["avance", "oui"], phrase_de_fin="quitter")

    entree.ecouter("Commande ?")
    entree.ecouter("oui ou non ?")
    entree.ecouter("oui ou non ?")

    assert entree.invites == ["Commande ?", "oui ou non ?", "oui ou non ?"]
    assert entree.entendues == ["avance", "oui", "quitter"]


# --------------------------------------------------------------------- ouvrir_entree()

def test_ouvrir_entree_mode_script_retourne_un_scripted_input(cfg):
    """ouvrir_entree('script', cfg, phrases) retourne bien une instance de ScriptedInput."""
    entree = ouvrir_entree("script", cfg, ["avance", "oui"])
    assert isinstance(entree, ScriptedInput)
    assert entree.ecouter() == "avance"


def test_ouvrir_entree_mode_script_sans_phrases_leve_valueerror(cfg):
    """ouvrir_entree('script', cfg, None) leve ValueError : le mode script exige une suite de phrases."""
    with pytest.raises(ValueError):
        ouvrir_entree("script", cfg, None)


def test_ouvrir_entree_mode_inconnu_leve_valueerror_listant_les_modes_valides(cfg):
    """Un mode d'entree inconnu leve ValueError dont le message liste les valeurs acceptees."""
    with pytest.raises(ValueError) as exc_info:
        ouvrir_entree("teleportation", cfg, None)

    message = str(exc_info.value)
    for mode_valide in ("micro", "clavier", "script", "auto"):
        assert mode_valide in message


# --------------------------------------------------------------------- SortieVocale desactivee

def test_sortie_vocale_inactive_n_est_pas_disponible_et_donne_une_raison():
    """SortieVocale(actif=False) n'est pas disponible et explique pourquoi, sans jamais charger pyttsx3."""
    voix = SortieVocale(actif=False)
    assert voix.disponible is False
    assert voix.raison


def test_sortie_vocale_inactive_dire_imprime_sans_lever(capsys):
    """dire() sur une SortieVocale inactive affiche le texte et ne leve jamais, meme sans moteur."""
    voix = SortieVocale(actif=False)

    voix.dire("tourner_gauche envoyee")  # ne doit pas lever

    sortie = capsys.readouterr().out
    assert "tourner_gauche envoyee" in sortie


def test_sortie_vocale_inactive_close_est_sans_effet():
    """close() sur une SortieVocale sans moteur ne leve jamais (contrat idempotent)."""
    voix = SortieVocale(actif=False)
    voix.close()
    voix.close()  # deux fois, ne doit pas lever


# --------------------------------------------------------------------- moteur local (faster-whisper)
# Remplacement de recognize_google le 2026-09-19 (stt-local-report.md). Ces tests ne
# chargent JAMAIS faster_whisper.WhisperModel : celui-ci est monkeypatche par un faux
# qui enregistre ses arguments d'appel, exactement comme faux_ollama.py le fait pour le
# client Ollama ailleurs dans cette suite.

class _FauxWhisperModel:
    """Faux WhisperModel : enregistre ses arguments de construction et d'appel."""

    dernier_construit: "_FauxWhisperModel | None" = None

    def __init__(self, taille, device=None, compute_type=None):
        self.taille = taille
        self.device = device
        self.compute_type = compute_type
        self.appels_transcribe: list[tuple] = []
        self.segments_a_rendre: list[str] = ["avance"]
        type(self).dernier_construit = self

    def transcribe(self, audio, language=None):
        self.appels_transcribe.append((audio, language))
        info = None
        return ([_Segment(t) for t in self.segments_a_rendre], info)


class _Segment:
    def __init__(self, texte: str) -> None:
        self.text = texte


def test_charger_modele_whisper_construit_avec_les_parametres_donnes(monkeypatch):
    """charger_modele_whisper() passe taille/device/compute_type tels quels a WhisperModel."""
    monkeypatch.setattr("faster_whisper.WhisperModel", _FauxWhisperModel)

    modele = charger_modele_whisper("small", "int8", "cpu")

    assert isinstance(modele, _FauxWhisperModel)
    assert (modele.taille, modele.device, modele.compute_type) == ("small", "cpu", "int8")


def test_charger_modele_whisper_leve_une_erreur_nommant_le_modele_et_le_cache(monkeypatch):
    """
    Echec de construction (modele absent du cache ET reseau injoignable) : l'erreur
    nomme le modele attendu, jamais un echec obscur (R3).
    """
    def _echoue(taille, device=None, compute_type=None):
        raise OSError("reseau injoignable")

    monkeypatch.setattr("faster_whisper.WhisperModel", _echoue)

    with pytest.raises(RuntimeError) as exc_info:
        charger_modele_whisper("small", "int8", "cpu")

    message = str(exc_info.value)
    assert "small" in message
    assert "cache" in message.lower()


# --------------------------------------------------------------------- rechauffement (defaut 2026-09-20)
# VRAM mesuree VIDE au demarrage (.sdd/6mig841-ameliorations/vram-et-transcription-report.md,
# defaut 2) : ctranslate2 charge les poids au constructeur mais n'alloue les noyaux
# cuBLAS/cuDNN qu'au premier calcul reel. charger_modele_whisper() force desormais ce calcul.

def test_charger_modele_whisper_rechauffe_le_calcul_au_chargement(monkeypatch):
    """Un calcul reel (transcribe sur un silence numerique) a lieu au chargement, pas a la premiere phrase."""
    monkeypatch.setattr("faster_whisper.WhisperModel", _FauxWhisperModel)

    modele = charger_modele_whisper("small", "int8", "cpu")

    assert len(modele.appels_transcribe) == 1
    (appel_audio, appel_langue), = modele.appels_transcribe
    assert appel_langue is None
    assert getattr(appel_audio, "shape", None) is not None  # un tableau numpy, pas un WAV


def test_charger_modele_whisper_rechauffement_echoue_n_empeche_pas_le_chargement(monkeypatch, capsys):
    """
    Un rechauffement en echec (ex. calcul incompatible) est un avertissement, jamais un
    blocage du demarrage du noeud (R8) : le modele est quand meme rendu.
    """
    class _ModeleQuiEchoueAuRechauffement(_FauxWhisperModel):
        def transcribe(self, audio, language=None):
            raise RuntimeError("erreur de calcul factice")

    monkeypatch.setattr("faster_whisper.WhisperModel", _ModeleQuiEchoueAuRechauffement)

    modele = charger_modele_whisper("small", "int8", "cpu")  # ne doit pas lever

    assert isinstance(modele, _ModeleQuiEchoueAuRechauffement)
    assert "rechauffement" in capsys.readouterr().err


def test_transcrire_avec_whisper_joint_les_segments_ignorant_les_espaces():
    """Les textes de segments sont retires de leurs espaces puis joints par un espace."""
    modele = _FauxWhisperModel("small")
    modele.segments_a_rendre = [" avance ", "doucement "]
    audio = _FauxAudioAvecWav(b"donnees-wav")

    texte = transcrire_avec_whisper(modele, audio, "fr")

    assert texte == "avance doucement"
    (appel_audio, appel_langue), = modele.appels_transcribe
    assert appel_langue == "fr"
    assert appel_audio.read() == b"donnees-wav"


def test_transcrire_avec_whisper_rend_une_chaine_vide_si_aucun_segment():
    """Un tampon sans rien d'intelligible rend une chaine vide, jamais une exception."""
    modele = _FauxWhisperModel("small")
    modele.segments_a_rendre = []
    audio = _FauxAudioAvecWav(b"silence")

    assert transcrire_avec_whisper(modele, audio, "fr") == ""


class _FauxAudioAvecWav:
    """Equivalent minimal de sr.AudioData : seul get_wav_data() est utilise."""

    def __init__(self, donnees: bytes) -> None:
        self._donnees = donnees

    def get_wav_data(self) -> bytes:
        return self._donnees


def test_charger_transcripteur_whisper_convertit_fr_fr_en_fr_et_charge_une_seule_fois(monkeypatch):
    """
    La langue courte ('fr') derive de speech_language ('fr-FR'), jamais dupliquee en
    configuration. Le modele est charge UNE SEULE FOIS, meme si le transcripteur rendu
    est appele plusieurs fois (R4 : le modele ne se recharge jamais par phrase).
    """
    monkeypatch.setattr("faster_whisper.WhisperModel", _FauxWhisperModel)
    settings = {
        "speech_model_size": "small",
        "speech_compute_type": "int8",
        "speech_device": "cpu",
        "speech_language": "fr-FR",
    }

    transcrire = charger_transcripteur_whisper(settings)
    audio = _FauxAudioAvecWav(b"un")
    transcrire(audio)
    transcrire(audio)

    modele = _FauxWhisperModel.dernier_construit
    # Le premier appel est le rechauffement force par charger_modele_whisper (silence
    # numerique, langue=None, defaut 2026-09-20) ; les deux suivants sont les vraies
    # transcriptions demandees par ce test.
    assert len(modele.appels_transcribe) == 3
    appel_rechauffement, *appels_reels = modele.appels_transcribe
    assert appel_rechauffement[1] is None
    assert all(langue == "fr" for _audio, langue in appels_reels)


# --------------------------------------------------------------------- DLL CUDA (plan09.md)
# Defaut mesure le 2026-09-20 en executant l'epreuve reelle de plan09.md (etape 6) :
# voice_input mourait AVANT d'ouvrir la fenetre, sur cette machine ou envs/ihr (conda,
# ROS2) n'a jamais recu nvidia-cublas-cu12 ni nvidia-cudnn-cu12.

def test_ajouter_repertoires_dll_cuda_ne_leve_pas_si_nvidia_est_entierement_absent(monkeypatch):
    """
    Controle negatif : importlib.util.find_spec('nvidia.cublas') importe d'abord le
    paquet PARENT et leve ModuleNotFoundError (au lieu de rendre None) quand 'nvidia'
    est entierement absent, pas seulement le sous-module cible. Le docstring de la
    fonction promet deja de ne jamais lever ici (R8) ; ce cas y manquait avant le
    2026-09-20.
    """
    monkeypatch.setattr(sys, "platform", "win32")

    def _leve_module_absent(nom: str):
        raise ModuleNotFoundError(f"No module named '{nom.split('.')[0]}'")

    monkeypatch.setattr("importlib.util.find_spec", _leve_module_absent)

    _ajouter_repertoires_dll_cuda("cuda")  # ne doit pas lever


def test_ajouter_repertoires_dll_cuda_ne_fait_rien_hors_cuda(monkeypatch):
    """Controle de non-effet : un peripherique 'cpu' ne touche jamais find_spec."""
    monkeypatch.setattr(sys, "platform", "win32")

    def _echoue_si_appele(nom: str):
        raise AssertionError("find_spec ne doit pas etre appele hors CUDA")

    monkeypatch.setattr("importlib.util.find_spec", _echoue_si_appele)

    _ajouter_repertoires_dll_cuda("cpu")  # ne doit pas lever ni appeler find_spec


# --------------------------------------------------------------------- MicrophoneInput
# `speech_recognition` est REMPLACE par le faux module (aucun peripherique reel), et le
# transcripteur est TOUJOURS injecte (jamais charger_transcripteur_whisper, qui
# chargerait un vrai modele) : workflow.md R5.

class _FausseFenetre:
    """
    Fausse fenetre injectee a la place de voice_window.VoiceWindow (plan09.md,
    2026-09-20) : n'ouvre jamais tkinter, enregistre les textes affiches dans
    l'ordre, et rend une confirmation PROGRAMMEE des l'appel a
    attendre_confirmation() (jamais de vrai clavier ni de vraie boucle
    d'evenements Tk). `delai_s` simule le temps qu'un vrai etudiant met a
    presser Entree, pour laisser le fil d'acquisition accumuler au moins une
    trame avant la fin de l'ecoute (meme role que le sommeil de 0.05 s que
    l'ancienne simulation d'input() utilisait).
    """

    def __init__(self, confirmation: str | None = "", delai_s: float = 0.0) -> None:
        self.textes_affiches: list[str] = []
        self.etats_ecoute: list[bool] = []
        self._confirmation = confirmation
        self._delai = delai_s
        self.fermee = False

    def afficher_texte(self, texte: str) -> None:
        self.textes_affiches.append(texte)

    def afficher_ecoute(self, active: bool) -> None:
        self.etats_ecoute.append(active)

    def attendre_confirmation(self) -> str | None:
        if self._delai:
            time.sleep(self._delai)
        return self._confirmation

    def close(self) -> None:
        self.fermee = True


@pytest.fixture
def micro_factice(monkeypatch, cfg):
    """MicrophoneInput construite sur le faux sr.Microphone, transcripteur et fenetre injectables."""
    faux_sr = construire_faux_module()
    monkeypatch.setitem(sys.modules, "speech_recognition", faux_sr)

    def _construire(transcripteur, affichage=None):
        fenetre = affichage if affichage is not None else _FausseFenetre()
        return MicrophoneInput(cfg, device_index=0, transcripteur=transcripteur,
                               affichage=fenetre)

    return _construire


def test_texte_depuis_tampon_ne_transcrit_pas_un_tampon_vide(micro_factice):
    """Un tampon vide ne rend jamais le transcripteur : rien n'a ete capte, rien a transcrire."""
    def _leve_si_appele(_audio):
        raise AssertionError("le transcripteur ne doit pas etre appele sur un tampon vide")

    micro = micro_factice(_leve_si_appele)

    assert micro._texte_depuis_tampon([], threading.Lock()) == ""


def test_texte_depuis_tampon_rend_le_texte_du_transcripteur_injecte(micro_factice):
    """Un tampon non vide est transcrit par la fonction injectee, jamais par un vrai modele."""
    micro = micro_factice(lambda audio: "tourne a gauche")

    texte = micro._texte_depuis_tampon([b"trame"], threading.Lock())

    assert texte == "tourne a gauche"


def test_texte_depuis_tampon_rend_une_chaine_vide_si_le_transcripteur_echoue(micro_factice, capsys):
    """
    Chemin d'echec : le transcripteur leve (modele local en anomalie) -> ecouter() ne
    doit jamais planter, une chaine vide est rendue et l'anomalie est journalisee.
    """
    def _transcripteur_casse(_audio):
        raise RuntimeError("ctranslate2 en echec")

    micro = micro_factice(_transcripteur_casse)

    texte = micro._texte_depuis_tampon([b"trame"], threading.Lock())

    assert texte == ""
    assert "ctranslate2 en echec" in capsys.readouterr().err


def test_texte_depuis_tampon_refuse_un_tampon_au_dela_de_la_limite_riff(
    micro_factice, capsys, monkeypatch
):
    """
    Rejoue le cas exact du defaut 1 (2026-09-20, correction du diagnostic de
    vram-et-transcription-report.md) : un tampon dont la taille atteint la
    limite structurelle du format WAV (_LIMITE_RIFF_OCTETS, champ RIFF 4
    octets non signe) doit rendre une chaine vide AVEC un diagnostic clair,
    jamais laisser sr.AudioData.get_wav_data() lever struct.error. La vraie
    limite (~4,29 Go) n'est pas allouee ici : la constante du module est
    abaissee a 10 octets pour le test, la garde ne dependant que de
    `len(donnees) >= _LIMITE_RIFF_OCTETS`.
    """
    monkeypatch.setattr(voice, "_LIMITE_RIFF_OCTETS", 10)

    def _leve_si_appele(_audio):
        raise AssertionError(
            "le transcripteur ne doit pas etre appele au-dela de la limite RIFF"
        )

    micro = micro_factice(_leve_si_appele)

    texte = micro._texte_depuis_tampon([b"x" * 11], threading.Lock())

    assert texte == ""
    erreur = capsys.readouterr().err
    assert "limite du format WAV" in erreur
    assert "11 octets" in erreur


def test_texte_depuis_tampon_transcrit_normalement_sous_la_limite_riff(
    micro_factice, monkeypatch
):
    """Controle negatif : sous la limite, la garde ne bloque rien (comportement inchange)."""
    monkeypatch.setattr(voice, "_LIMITE_RIFF_OCTETS", 10)

    micro = micro_factice(lambda audio: "avance")

    texte = micro._texte_depuis_tampon([b"x" * 9], threading.Lock())

    assert texte == "avance"


def test_ecouter_capte_puis_rend_la_transcription_a_l_appui_sur_entree(micro_factice):
    """
    Bout en bout (fils de fond compris) : le fil d'acquisition accumule des trames
    factices pendant que le fil appelant attend la confirmation de la fenetre (ici
    simulee par un court delai), puis la transcription finale, injectee, est rendue.
    """
    fenetre = _FausseFenetre(confirmation="peu importe", delai_s=0.05)
    micro = micro_factice(lambda audio: "avance", affichage=fenetre)

    texte = micro.ecouter("Commande ?")

    assert texte == "avance"
    assert "avance" in fenetre.textes_affiches


def test_ecouter_ne_publie_pas_de_transcription_vide(micro_factice):
    """Rien d'intelligible capte : ecouter() rend une chaine vide et l'affiche UNE fois."""
    fenetre = _FausseFenetre(confirmation="peu importe")
    micro = micro_factice(lambda audio: "", affichage=fenetre)

    texte = micro.ecouter()

    assert texte == ""
    assert "(rien d'intelligible n'a ete capte)" in fenetre.textes_affiches


def test_ecouter_fenetre_fermee_rend_une_chaine_vide_sans_lever(micro_factice):
    """
    Controle negatif exige par plan09.md : si la fenetre est fermee pendant l'attente
    (attendre_confirmation() rend None), ecouter() se termine comme une ecoute vide,
    sans jamais publier ni lever.
    """
    fenetre = _FausseFenetre(confirmation=None)
    micro = micro_factice(lambda audio: "avance", affichage=fenetre)

    texte = micro.ecouter()

    assert texte == ""


# --------------------------------------------------------------------- duree maximale d'ecoute (defaut 2026-09-20)
# Sans detection de fin de parole, rien ne bornait la duree d'une ecoute : une fenetre
# jamais confirmee accumulait un tampon jusqu'a depasser le champ 4 octets non signe du
# format WAV (~4,29 Go, struct.error 'L' format requires 0 <= number <= 4294967295,
# reproduit hors ROS2 dans .sdd/6mig841-ameliorations/vram-et-transcription-report.md).

def test_ecouter_respecte_la_duree_maximale_d_ecoute(micro_factice, cfg, monkeypatch):
    """
    Une horloge simulee fait immediatement depasser microphone_duree_max_ecoute_s (aucune
    attente reelle de dix minutes) : le fil d'acquisition doit alors cesser de lire de
    nouvelles trames et avertir a l'ecran, plutot que d'accumuler indefiniment.
    """
    seuil_depasse = cfg["microphone_duree_max_ecoute_s"] + 1.0
    horloge = iter([0.0, seuil_depasse])

    def _horloge_qui_depasse_immediatement(*_args, **_kwargs):
        return next(horloge, seuil_depasse)

    monkeypatch.setattr("voice.time.monotonic", _horloge_qui_depasse_immediatement)
    fenetre = _FausseFenetre(confirmation="peu importe", delai_s=0.05)
    micro = micro_factice(lambda audio: "avance", affichage=fenetre)

    micro.ecouter("Commande ?")

    assert any("duree maximale" in texte for texte in fenetre.textes_affiches)
