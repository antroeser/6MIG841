"""
voice.py - Entrees parlees et sorties vocales du Devoir 2.

Trois entrees interchangeables derriere une meme interface :

  - `MicrophoneInput` : capture audio via SpeechRecognition (sr.Microphone),
                        transcription LOCALE et PROGRESSIVE via faster-whisper
                        (modele 'small', calcul int8, voir plus bas) ; c'est
                        l'etudiant qui termine la phrase, en appuyant sur
                        Entree, jamais une heuristique de silence,
  - `KeyboardInput`   : saisie au clavier, pour travailler sans micro ou en salle
                        bruyante, et pour rejouer un scenario a l'identique,
  - `ScriptedInput`   : suite de phrases fixee d'avance, utilisee par les tests.

Remplacement de recognize_google par faster-whisper, decision de l'enseignant du
2026-09-19 (.sdd/6mig841-ameliorations/stt-local-report.md)
----------------------------------------------------------------------------
`MicrophoneInput` envoyait chaque phrase au service de reconnaissance Google
(recognize_google), en contradiction avec l'architecture du cours : spec.md
budgete STT 1,5 Go sur le Jetson cible, ce qui n'a de sens que pour un moteur
LOCAL ; le LLM (Ollama) est deja local ; ROS_LOCALHOST_ONLY garde DDS sur
loopback. En pratique, cela exigeait Internet en salle, subissait les limites
du point d'acces gratuit de Google, et faisait sortir la voix des etudiants de
l'universite. Le moteur retenu, sans comparaison d'alternative (decision prise,
non rediscutee) : faster-whisper, modele 'small', calcul int8 (environ 0,5 Go,
deux a quatre fois plus rapide que l'implementation de reference sur CPU), qui
tient largement sous le budget de 1,5 Go alors que le LLM (Qwen3-4B) occupe deja
environ 2,5 Go des 6144 Mio de la carte de developpement. Le nom du modele
(taille), le type de calcul, le peripherique de calcul et l'intervalle de
rafraichissement viennent de la configuration (devoir2.speech_model_size /
speech_compute_type / speech_device / speech_rafraichissement_secondes,
ihr_config.json, R7), avec provenance datee (R4, R13). Le modele se charge UNE
SEULE FOIS a la construction de `MicrophoneInput`, jamais a chaque phrase.

Conception de la capture, reprise DEUX FOIS par l'enseignant le soir du
2026-09-19 (le detail complet, y compris les mesures de temps de transcription,
vit dans la provenance de ihr_config.json, devoir2_stt_local ; ce qui suit est
le repere pour lire `ecouter()`)
----------------------------------------------------------------------------
Aucune detection automatique de fin de parole (ni seuil d'energie, ni la
detection d'activite vocale de Whisper comme decoupeur) : la machine d'etat le
prevoyait depuis l'origine ("le micro ecoute et transcrit le texte entendu,
l'etudiant appuie sur Entree pour envoyer"). `ecouter()` ouvre donc DEUX fils de
fond (jamais un rappel ROS2, piege 1 de plan02.md) : l'un lit les trames audio
en continu, l'autre retranscrit le tampon COMPLET a intervalle regulier et
affiche le texte des qu'il change, en reecrivant la ligne courante. Le fil
appelant attend l'appui sur Entree (lecture clavier bloquante, comme la lecture
du micro), fige alors le texte et le rend. Une transcription vide n'est jamais
publiee par l'appelant.

Pourquoi une interface plutot qu'un appel direct
------------------------------------------------
Les trois rendus etudiants appelaient `sr.Microphone()` au milieu de leur boucle
principale. Leur devoir devient alors impossible a tester, impossible a demontrer
sans micro, et impossible a corriger a distance. Ici, le programme principal ne
connait que `EntreeVocale.ecouter()`.

Panne « parole non comprise » diagnostiquee le 2026-09-19
----------------------------------------------------------
(.sdd/6mig841-ameliorations/diagnostic-micro-report.md). `MicrophoneInput`
acceptait deja `device_index`, mais rien ne permettait de le choisir avant
`voice_input_node` et `devoir2.launch.py` (voir `devoir2.microphone_device_index`
dans ihr_config.json et Devoir2/code/diagnostic_micro.py pour trouver le bon
index). La saturation AGC mesuree ce jour-la sur le micro Intel Smart Sound (voir
provenance devoir2_microphone_seuil) reste un defaut MATERIEL, hors perimetre :
faster-whisper est nettement plus tolerant qu'un moteur en nuage a un signal
ecrete ou bruite, mais rien ne garantit que cela suffise sans le mesurer en
seance.

Panne « transcription locale en echec » diagnostiquee le 2026-09-20
----------------------------------------------------------------------
(.sdd/6mig841-ameliorations/vram-et-transcription-report.md). Sans detection de
fin de parole (design ci-dessus), rien ne bornait la duree d'une ecoute : une
fenetre jamais confirmee (oubliee, ou un processus laisse ouvert plusieurs
heures pendant qu'on travaille sur un autre noeud) fait grandir `donnees` sans
limite, jusqu'a depasser le champ 4 octets non signe du format WAV
(`sr.AudioData.get_wav_data()`, ~4,29 Go, mesure et reproduit hors ROS2 dans le
rapport ci-dessus) : `struct.error: 'L' format requires 0 <= number <=
4294967295`, rattrape par `_texte_depuis_tampon` mais repete a chaque
rafraichissement tant que le tampon reste gigantesque. `microphone_duree_max_ecoute_s`
(ihr_config.json, provenance datee) borne desormais cette accumulation : passe
ce seuil, `_lire_audio` arrete de lire de nouvelles trames et avertit a
l'ecran, sans jamais perdre ni corrompre ce qui a deja ete capte.

VRAM vide au demarrage, diagnostiquee le 2026-09-20
------------------------------------------------------
(.sdd/6mig841-ameliorations/vram-et-transcription-report.md). Le modele se
chargeait deja UNE SEULE FOIS a la construction (ci-dessus), mais ctranslate2
n'alloue les noyaux cuBLAS/cuDNN qu'au PREMIER calcul reel : `nvidia-smi`
mesurait donc une VRAM vide entre le demarrage du noeud et la premiere phrase
captee. `charger_modele_whisper` force desormais ce premier calcul
immediatement apres le chargement (silence numerique, transcrit et jete par
`_prechauffer_modele_whisper`), avant que l'etudiant ne parle.
"""

from __future__ import annotations

import abc
import importlib.util
import contextlib
import io
import os
import sys
import threading
import time
import unicodedata
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# Constante STRUCTURELLE du format WAV/RIFF (jamais une mesure, R0) : le champ
# de taille du bloc RIFF est un entier non signe de 4 octets (struct '<L'),
# donc 2**32 - 1 au maximum ; 36 octets d'en-tete (voir wave.Wave_write, RIFF
# + WAVE + fmt + data) sont retranches par marge plutot que par necessite
# stricte. Voir _texte_depuis_tampon ci-dessous pour la garde qui l'emploie et
# la correction du 2026-09-20 au diagnostic du meme jour.
_LIMITE_RIFF_OCTETS = 2**32 - 1 - 36


class EntreeVocale(abc.ABC):
    """Source de phrases, quelle qu'en soit l'origine."""

    name: str = "abstraite"

    @abc.abstractmethod
    def ecouter(self, invite: str = "") -> str:
        """Rendre la prochaine phrase, ou une chaine vide si rien n'a ete compris."""

    def close(self) -> None:
        """Liberer les ressources. Appelable deux fois sans effet."""

    def __enter__(self) -> "EntreeVocale":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


class ScriptedInput(EntreeVocale):
    """
    Entree deterministe : une file de phrases decidee a l'avance.

    C'est ce qui permet de tester tout le dialogue du Devoir 2 sans micro. La file
    epuisee, elle rend la phrase de sortie configuree, de sorte qu'un test ne puisse
    jamais boucler indefiniment.
    """

    name = "script"

    def __init__(self, phrases: Iterable[str], phrase_de_fin: str = "quitter"):
        self._phrases: deque[str] = deque(phrases)
        self._fin = phrase_de_fin
        self.entendues: list[str] = []
        self.invites: list[str] = []

    def ecouter(self, invite: str = "") -> str:
        self.invites.append(invite)
        phrase = self._phrases.popleft() if self._phrases else self._fin
        self.entendues.append(phrase)
        return phrase

    @property
    def restantes(self) -> int:
        """Nombre de phrases encore en file."""
        return len(self._phrases)


class KeyboardInput(EntreeVocale):
    """Saisie au clavier. Utile sans micro, et pour rejouer un scenario."""

    name = "clavier"

    def ecouter(self, invite: str = "") -> str:
        try:
            return input(f"{invite} > " if invite else "> ").strip()
        except EOFError:
            return ""


def _nom_peripherique_reel(sr_module: Any, device_index: int | None) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Nommer le peripherique d'entree reellement ouvert, pour un message d'echec
        diagnosticable. Mesure du 2026-09-19
        (.sdd/6mig841-ameliorations/diagnostic-micro-report.md) : « parole non
        comprise » ne dit ni quel peripherique a capte le son, ni le seuil d'energie
        en vigueur, les deux chiffres necessaires pour distinguer un mauvais choix de
        peripherique d'une salle bruyante. Ne leve jamais : nommer le peripherique
        est un confort de diagnostic, pas une condition prealable a l'ecoute.

    Inputs:
        sr_module (module): le module speech_recognition deja importe
        device_index (int | None): index explicite, ou None pour le defaut Windows

    Outputs:
        nom (str): description lisible du peripherique
    --------------------------------------------------------------------------
    """
    try:
        noms = sr_module.Microphone.list_microphone_names()
    except Exception:
        noms = []

    if device_index is not None:
        if 0 <= device_index < len(noms):
            return f"{noms[device_index]} (index {device_index})"
        return f"index {device_index} (hors limites, {len(noms)} peripheriques enumeres)"

    try:
        audio = sr_module.Microphone.get_pyaudio().PyAudio()
    except Exception:
        return "peripherique par defaut de Windows (non identifiable)"
    try:
        info = audio.get_default_input_device_info()
        return f"{info['name']} (par defaut de Windows, index {info['index']})"
    except Exception:
        return "peripherique par defaut de Windows (non identifiable)"
    finally:
        audio.terminate()


def _repertoire_cache_whisper() -> str:
    """Repertoire de cache Hugging Face ou faster-whisper telecharge ses modeles."""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE  # noqa: PLC0415

        return str(HF_HUB_CACHE)
    except Exception:
        return "le cache Hugging Face par defaut (HF_HOME ou ~/.cache/huggingface/hub)"


def _ajouter_repertoires_dll_cuda(peripherique: str) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Rendre cuBLAS/cuDNN trouvables par Windows quand faster-whisper tourne
        sur CUDA. Mesure le 2026-09-19 (.sdd/6mig841-ameliorations/
        vram-residence-report.md) : cette machine n'a pas de Toolkit CUDA
        systeme, donc ctranslate2 levait `RuntimeError: Library
        cublas64_12.dll is not found or cannot be loaded` au premier calcul
        reel (pas au chargement du modele). Les paquets pip
        nvidia-cublas-cu12 et nvidia-cudnn-cu12 installent ces DLL sous
        site-packages/nvidia/*/bin, mais Windows ne les cherche pas la sans
        aide : `os.add_dll_directory` (Python >= 3.8) les ajoute a la
        recherche, calcule depuis l'emplacement du paquet installe (jamais un
        chemin ecrit en dur, R1). Ne fait rien sur CPU ni hors Windows. Ne
        leve pas si les paquets sont absents : une machine dotee d'un vrai
        Toolkit CUDA systeme (PATH deja correct) n'en a pas besoin, et
        WhisperModel() ou le premier transcribe() nommeront eux-memes la DLL
        manquante si elle reste introuvable (R8, pas de succes silencieux).

    Inputs:
        peripherique (str): device de ctranslate2 (ex. 'cpu', 'cuda')

    Outputs:
        aucun
    --------------------------------------------------------------------------
    """
    if not peripherique.startswith("cuda") or sys.platform != "win32":
        return
    for paquet in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(paquet)
        except ModuleNotFoundError:
            # Corrige le 2026-09-20 (plan09.md, etape 6, defaut mesure en
            # lancant ros2 launch pour de vrai) : find_spec() d'un nom pointe
            # importe d'abord le paquet PARENT ('nvidia'), et leve
            # ModuleNotFoundError (au lieu de rendre None) quand ce parent est
            # ENTIEREMENT absent, pas seulement le sous-module cible. Sur cette
            # machine, envs/ihr (conda, ROS2) n'a jamais recu nvidia-cublas-cu12
            # ni nvidia-cudnn-cu12 (paquets pip, installes dans .venv/.venv-skills
            # pour un autre usage), donc voice_input mourait avant meme d'ouvrir
            # la fenetre de plan09. Le docstring de cette fonction promettait deja
            # de ne jamais lever ici (R8) : ce cas y manquait.
            continue
        if spec is None or not spec.submodule_search_locations:
            continue
        repertoire_bin = Path(next(iter(spec.submodule_search_locations))) / "bin"
        if not repertoire_bin.is_dir():
            continue
        # os.add_dll_directory ne couvre que les chargements natifs faits via
        # LoadLibraryEx. Le binaire compile de ctranslate2 appelle LoadLibrary
        # (sans Ex) pour cuBLAS/cuDNN charges paresseusement au premier calcul,
        # ce que add_dll_directory seul ne couvre pas (mesure le 2026-09-19 :
        # add_dll_directory seul ne suffisait pas). PATH est donc AUSSI mis a
        # jour : c'est l'ordre de recherche classique de Windows, couvrant
        # LoadLibrary comme LoadLibraryEx.
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(repertoire_bin))
        chemin_actuel = os.environ.get("PATH", "")
        if str(repertoire_bin) not in chemin_actuel.split(os.pathsep):
            os.environ["PATH"] = str(repertoire_bin) + os.pathsep + chemin_actuel


def charger_modele_whisper(taille: str, type_calcul: str, peripherique: str) -> Any:
    """
    --------------------------------------------------------------------------
    Purpose:
        Charger un modele faster-whisper, avec annonce a l'ecran et erreur
        nommee (R3). Fonction PURE et PUBLIQUE (aucun prefixe) : partagee par
        `charger_transcripteur_whisper` (ci-dessous, utilise par
        `MicrophoneInput`) et par la bissection de `diagnostic_micro.py`, pour
        ne jamais dupliquer l'appel a `WhisperModel` (R2 : un seul endroit sait
        comment on charge le modele). Decision de l'enseignant du 2026-09-19
        (.sdd/6mig841-ameliorations/stt-local-report.md) : faster-whisper,
        aucune autre alternative comparee.

        Le premier appel sur un modele absent du cache local le telecharge
        depuis Hugging Face : annonce a l'ecran plutot que silencieux (une
        attente de plusieurs secondes en pleine seance, sans rien dire, se lit
        comme un blocage). Si le modele est absent ET le reseau injoignable,
        l'erreur nomme le modele attendu et le repertoire de cache au lieu d'un
        echec obscur (R3).

        RECHAUFFE le calcul avant de rendre la main (correctif du 2026-09-20,
        .sdd/6mig841-ameliorations/vram-et-transcription-report.md, defaut 2 :
        VRAM mesuree VIDE au demarrage). ctranslate2 charge les POIDS du
        modele des ce constructeur, mais ne compile ni n'alloue les noyaux
        cuBLAS/cuDNN qu'au PREMIER calcul reel (deja note par
        `_ajouter_repertoires_dll_cuda` pour le chargement des DLL
        elles-memes) : sans rechauffement, cette allocation n'a lieu qu'a la
        premiere phrase captee, exactement le decalage mesure par
        l'enseignant. `_prechauffer_modele_whisper` force ce calcul
        immediatement, sur un silence numerique jete.

    Inputs:
        taille (str): taille du modele faster-whisper (ex. 'small')
        type_calcul (str): compute_type de ctranslate2 (ex. 'int8')
        peripherique (str): device de ctranslate2 (ex. 'cpu')

    Outputs:
        modele (faster_whisper.WhisperModel): modele charge et rechauffe, pret
            a transcrire
    --------------------------------------------------------------------------
    """
    _ajouter_repertoires_dll_cuda(peripherique)

    from faster_whisper import WhisperModel  # noqa: PLC0415

    print(f"[whisper] chargement du modele '{taille}' (compute_type={type_calcul}, "
          f"device={peripherique}). Telechargement depuis Hugging Face si absent "
          f"du cache local (premier lancement uniquement).")
    try:
        modele = WhisperModel(taille, device=peripherique, compute_type=type_calcul)
    except Exception as exc:
        raise RuntimeError(
            f"Modele Whisper '{taille}' indisponible : absent du cache local "
            f"({_repertoire_cache_whisper()}) et le telechargement depuis Hugging "
            f"Face a echoue (reseau injoignable ?). Verifier la connexion, "
            f"pre-telecharger le modele sur un poste connecte, ou lancer le devoir "
            f"avec --input clavier. Detail : {exc}"
        ) from exc
    print(f"[whisper] modele '{taille}' charge, rechauffement du calcul...")
    _prechauffer_modele_whisper(modele)
    print(f"[whisper] modele '{taille}' pret.")
    return modele


def _prechauffer_modele_whisper(modele: Any) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Forcer un calcul reel (encodeur puis decodeur) sur le peripherique
        cible, au chargement plutot qu'a la premiere phrase captee. Mesure du
        2026-09-20 (.sdd/6mig841-ameliorations/vram-et-transcription-report.md,
        defaut 2) : ctranslate2 charge les poids au constructeur de
        WhisperModel, mais ne compile ni n'alloue les noyaux cuBLAS/cuDNN
        qu'au PREMIER calcul reel, la meme paresse deja notee par
        `_ajouter_repertoires_dll_cuda` pour le chargement des DLL. Transcrire
        une seconde de silence numerique, une fois, jetee, suffit a
        declencher cette allocation. N'ELEVE JAMAIS (R8 attenue en
        avertissement ici) : un echec de rechauffement ne doit pas empecher
        le noeud de demarrer, la premiere phrase reelle restera correcte,
        seulement plus lente.

    Inputs:
        modele (faster_whisper.WhisperModel): modele deja charge

    Outputs:
        aucun
    --------------------------------------------------------------------------
    """
    import numpy as np  # noqa: PLC0415

    try:
        silence = np.zeros(16000, dtype=np.float32)
        segments, _info = modele.transcribe(silence, language=None)
        for _segment in segments:
            pass
    except Exception as exc:
        print(f"[whisper] rechauffement ignore ({type(exc).__name__}: {exc}), "
              f"la premiere phrase reelle sera plus lente.", file=sys.stderr)


def _normaliser_phrase(texte: str) -> str:
    """Minuscules, sans accent ni ponctuation, pour comparer deux formulations."""
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", texte.lower())
        if not unicodedata.combining(c)
    )
    return " ".join(
        "".join(c if (c.isalnum() or c.isspace()) else " " for c in sans_accent).split()
    )


def est_hallucination(texte: str, phrases: Sequence[str]) -> bool:
    """
    --------------------------------------------------------------------------
    Purpose:
        Dire si une transcription n'est qu'une formule connue que Whisper
        produit sur du silence.

        Le modele a ete entraine sur des sous-titres de videos : sur une plage
        sans parole il rend les formules de fin de generique qu'il a le plus
        vues, « Sous-titres realises par l'Amara.org » ou « Merci d'avoir
        regarde cette video ». Signale par l'enseignant le 2026-09-20, et
        reproduit independamment le meme jour sur deux sinusoides pures.

        La comparaison porte sur la phrase ENTIERE, jamais sur une sous-chaine :
        filtrer un fragment couperait une vraie commande qui le contiendrait par
        hasard. Accents et ponctuation sont replies des deux cotes, la
        transcription etant ponctuee et le catalogue ne l'etant pas forcement.

    Inputs:
        texte (str): transcription a juger
        phrases (Sequence): devoir2.transcription.phrases_hallucinees

    Outputs:
        hallucination (bool): vrai si le texte doit etre jete
    --------------------------------------------------------------------------
    """
    normalise = _normaliser_phrase(texte)
    if not normalise:
        return False
    return any(normalise == _normaliser_phrase(p) for p in phrases)


def transcrire_avec_whisper(modele: Any, audio: Any, langue: str,
                            reglages: dict[str, Any] | None = None) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Transcrire un sr.AudioData avec un modele faster-whisper DEJA charge.
        Fonction pure, partagee par `MicrophoneInput` (ci-dessous) et la
        bissection de `diagnostic_micro.py` (R2 : un seul endroit sait comment
        on transcrit).

        Deux garde-fous contre les hallucinations sur silence, ajoutes le
        2026-09-20 et actifs seulement si `reglages` est fourni (un appelant qui
        n'en passe pas garde exactement l'ancien comportement) :

          - le detecteur d'activite vocale (VAD) ECARTE les plages sans parole
            avant de les soumettre au modele, ce qui supprime la cause ;
          - `conditionner_sur_texte_precedent=false` empeche le modele de se
            nourrir de sa propre sortie, mecanisme par lequel une hallucination
            unique se repete ensuite a chaque rafraichissement ;
          - la liste noire est le filet de securite, en donnees (R6).

    Inputs:
        modele (faster_whisper.WhisperModel): modele deja charge
        audio (Any): sr.AudioData (ou equivalent portant get_wav_data())
        langue (str): code de langue court ('fr'), deja converti depuis
            'fr-FR' par l'appelant
        reglages (dict | None): section devoir2.transcription, ou None

    Outputs:
        texte (str): transcription, chaine vide si rien n'est reconnu ou si la
            transcription n'est qu'une hallucination connue
    --------------------------------------------------------------------------
    """
    reglages = reglages or {}
    options: dict[str, Any] = {"language": langue}
    if reglages:
        options["vad_filter"] = bool(reglages["vad_filtre"])
        options["vad_parameters"] = {
            "min_silence_duration_ms": int(reglages["vad_duree_silence_min_ms"]),
        }
        options["condition_on_previous_text"] = bool(
            reglages["conditionner_sur_texte_precedent"]
        )

    segments, _info = modele.transcribe(io.BytesIO(audio.get_wav_data()), **options)
    texte = " ".join(segment.text.strip() for segment in segments).strip()

    if texte and est_hallucination(texte, reglages.get("phrases_hallucinees", ())):
        return ""
    return texte


def charger_transcripteur_whisper(settings: dict[str, Any]) -> Callable[[Any], str]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Assembler `charger_modele_whisper` et `transcrire_avec_whisper` en une
        fonction de transcription prete a l'emploi (fermeture sur le modele
        charge UNE SEULE FOIS). La taille du modele, le type de calcul et le
        peripherique viennent de la configuration (R7) ; seule la langue est
        deja partagee avec l'ancien moteur (speech_language), convertie au
        format court attendu par faster-whisper ('fr' plutot que 'fr-FR',
        jamais duplique en configuration).

    Inputs:
        settings (dict): section devoir2 de la configuration

    Outputs:
        transcrire (Callable[[Any], str]): rend le texte reconnu (chaine vide
            si rien n'est reconnu) a partir d'un sr.AudioData
    --------------------------------------------------------------------------
    """
    taille = str(settings["speech_model_size"])
    type_calcul = str(settings["speech_compute_type"])
    peripherique = str(settings["speech_device"])
    langue = str(settings["speech_language"]).split("-")[0].lower()

    modele = charger_modele_whisper(taille, type_calcul, peripherique)
    # devoir2.transcription : VAD et liste noire des hallucinations (2026-09-20).
    # `.get` et non `[]` : une configuration anterieure a cette date reste lisible,
    # et transcrire_avec_whisper retombe alors sur son comportement d'origine.
    reglages_transcription = settings.get("transcription", {})

    def transcrire(audio: Any) -> str:
        return transcrire_avec_whisper(modele, audio, langue, reglages_transcription)

    return transcrire


class MicrophoneInput(EntreeVocale):
    """Capture via SpeechRecognition, transcription locale via faster-whisper."""

    name = "microphone"

    def __init__(self, settings: dict[str, Any], device_index: int | None = None,
                 transcripteur: Callable[[Any], str] | None = None,
                 affichage: Any | None = None,
                 on_fermeture: Callable[[], None] | None = None):
        """
        --------------------------------------------------------------------------
        Purpose:
            Ouvrir le micro et charger le transcripteur local (faster-whisper) une
            seule fois. Conception reprise le 2026-09-19 par l'enseignant
            (.sdd/6mig841-ameliorations/stt-local-report.md) : AUCUNE detection de
            fin de parole par seuil d'energie (`energy_threshold`,
            `adjust_for_ambient_noise`, `dynamic_energy_threshold`,
            `listen(timeout=...)`). La machine d'etat le prevoyait depuis
            l'origine : « le micro ecoute et transcrit le texte entendu, l'etudiant
            appuie sur Entree pour envoyer ». C'est donc l'etudiant qui decide de
            la fin de la phrase, jamais une heuristique de silence. Les cles de
            configuration retirees a cette occasion (microphone_energy_threshold,
            microphone_recalibrer_chaque_ecoute, speech_timeout_seconds,
            speech_phrase_limit_seconds) ne reglaient plus rien.

            L'AFFICHAGE (texte courant + saisie d'Entree) est injectable depuis
            plan09.md (2026-09-20) : le defaut construit une vraie
            voice_window.VoiceWindow, corrigeant le defaut mesure le 2026-09-19
            (sous ros2 launch, le stdin n'est pas rattache aux noeuds, donc
            l'ancien input() bloquant n'aboutissait jamais). La fenetre n'est
            ouverte qu'APRES que le microphone soit confirme disponible, pour ne
            jamais laisser une fenetre orpheline si sr.Microphone() echoue.

        Inputs:
            settings (dict): section devoir2 de la configuration, y compris
                microphone_duree_max_ecoute_s (ihr_config.json, provenance
                datee) : duree maximale d'accumulation continue avant que
                _lire_audio ne s'arrete de lire de nouvelles trames (defaut
                mesure le 2026-09-20, vram-et-transcription-report.md :
                aucune borne ne faisait deborder get_wav_data() au-dela
                d'environ 4,29 Go de tampon PCM accumule).
            device_index (int | None): index du peripherique d'entree, ou None pour
                le peripherique par defaut de Windows (comportement historique).
                Valeur par defaut lue par l'appelant dans
                settings['microphone_device_index'] (ihr_config.json).
            transcripteur (Callable[[Any], str] | None): fonction de transcription
                injectee, appelee avec un sr.AudioData et rendant le texte reconnu.
                None (comportement reel) charge faster-whisper via
                `charger_transcripteur_whisper`. Les tests injectent toujours une
                valeur : ils ne doivent jamais charger de modele ni toucher le
                reseau (workflow.md R5).
            affichage (Any | None): interface d'affichage et de saisie d'Entree
                (afficher_texte(str), afficher_ecoute(bool),
                attendre_confirmation() -> str | None, close()). None (chemin de
                production) construit une voice_window.VoiceWindow reelle depuis
                settings['fenetre_voix']. Les tests injectent toujours un faux
                (workflow.md R5) : jamais de vraie fenetre tkinter en test.
            on_fermeture (Callable[[], None] | None): transmis a la VoiceWindow
                construite par defaut (ignore si `affichage` est deja fourni) ;
                voir voice_window.VoiceWindow.

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        import speech_recognition as sr  # noqa: PLC0415

        self._sr = sr
        self._transcrire = (
            transcripteur if transcripteur is not None
            else charger_transcripteur_whisper(settings)
        )
        self._rafraichissement = float(settings["speech_rafraichissement_secondes"])
        self._arret_fil_timeout = float(settings["microphone_arret_fil_timeout_s"])
        self._duree_max_ecoute = float(settings["microphone_duree_max_ecoute_s"])
        self._nom_peripherique = _nom_peripherique_reel(sr, device_index)

        try:
            self._micro = sr.Microphone(device_index=device_index)
        except Exception as exc:
            raise RuntimeError(
                f"Microphone indisponible ({self._nom_peripherique}) : {exc}\n"
                "Verifier le peripherique d'entree de Windows, lister les "
                "peripheriques avec Devoir2/code/diagnostic_micro.py --lister, "
                "ou lancer le devoir avec --input clavier."
            ) from exc

        if affichage is not None:
            self._affichage = affichage
        else:
            from voice_window import VoiceWindow  # noqa: PLC0415

            self._affichage = VoiceWindow(settings["fenetre_voix"], on_fermeture=on_fermeture)

        self._closed = False

    @property
    def nom_peripherique(self) -> str:
        """Nom du peripherique reellement ouvert (index Windows resolu inclus)."""
        return self._nom_peripherique

    @property
    def affichage(self) -> Any:
        """
        Interface d'affichage en service (la vraie fenetre en production, un faux en
        test). Lue par voice_input_node.VoiceInputNode pour refleter la porte
        d'ecoute a l'ecran sans dupliquer la fenetre.
        """
        return self._affichage

    def _texte_depuis_tampon(self, trames: list[bytes], verrou: threading.Lock) -> str:
        """
        --------------------------------------------------------------------------
        Purpose:
            Retranscrire le tampon audio COMPLET accumule jusqu'ici. Jamais un
            fragment isole : Whisper degrade mal sur un extrait coupe au milieu
            d'un mot, donc le texte se corrige de lui-meme a mesure que le
            tampon s'allonge, plutot que d'assembler des fragments transcrits
            separement (decision de l'enseignant, 2026-09-19).

            CORRIGE le 2026-09-20 (defaut mesure a nouveau ce jour, ce rapport
            invalide la conclusion du rapport precedent du meme jour,
            vram-et-transcription-report.md) : ce rapport concluait a un
            DEPASSEMENT (tampon grossissant jusqu'a ~4,29 Go, ~13,5 h a 44100 Hz
            mono 16 bits, reproduit hors ROS2 a l'epoque). Cette conclusion ne
            resiste pas a un examen du code de sr.AudioData.get_wav_data() :
            sr.AudioData.__init__ (speech_recognition/audio.py) REFUSE par
            `assert` tout sample_rate <= 0 et tout sample_width hors [1, 4]
            AVANT que l'objet n'existe, et sr.Microphone fixe SAMPLE_WIDTH a la
            constante pyaudio.get_sample_size(paInt16)=2 (independante du
            peripherique) et SAMPLE_RATE a un entier positif valide par ses
            PROPRES `assert` (Microphone.__init__). Verifie le 2026-09-20 sur
            les deux interpretes reellement utilises par ce depot (.venv et
            l'environnement conda 'ihr', `sys.flags.optimize == 0` sur les
            deux : les `assert` sont actifs, pas de -O qui les desactiverait).
            Un `sample_rate`/`sample_width` invalide ne peut donc PAS atteindre
            wave.py : struct.pack('<L', ...) ne peut y echouer QUE par
            DEPASSEMENT (tampon >= ~4,29 Go), jamais par une valeur negative,
            pour un sr.Microphone reel. Or `microphone_duree_max_ecoute_s=600.0`
            (deja en place) borne desormais tout tampon a environ
            duree_max_ecoute_s * SAMPLE_RATE * SAMPLE_WIDTH octets, tres loin
            sous 4,29 Go pour tout peripherique audio reel (~53 Mo a 44100 Hz,
            ~460 Mo meme a 192000 Hz/32 bits) : ce depassement precis est donc
            deja rendu impossible par le correctif existant. La garde
            ci-dessous rend ce raisonnement EXPLICITE au lieu d'un `assert`
            tiers potentiellement contournable : elle recalcule la meme borne
            physique (le champ RIFF 4 octets non signe du format WAV,
            _LIMITE_RIFF_OCTETS ci-dessous, constante STRUCTURELLE du format,
            jamais une mesure) et rend un texte vide avec un diagnostic clair
            plutot que de laisser wave.py lever un struct.error illisible, si
            jamais cette hypothese se revelait fausse sur une autre machine
            (peripherique au SAMPLE_RATE anormalement eleve, par exemple).

        Inputs:
            trames (list[bytes]): trames PCM accumulees jusqu'ici
            verrou (threading.Lock): protege `trames` contre le fil d'acquisition

        Outputs:
            texte (str): transcription courante, vide si rien d'intelligible
        --------------------------------------------------------------------------
        """
        with verrou:
            donnees = b"".join(trames)
        if not donnees:
            return ""
        if len(donnees) >= _LIMITE_RIFF_OCTETS:
            # Ne devrait plus jamais se produire (microphone_duree_max_ecoute_s
            # borne le tampon tres en-dessous de cette limite), mais un
            # diagnostic clair vaut mieux qu'un struct.error illisible si cette
            # hypothese s'avere fausse ailleurs (voir la note ci-dessus).
            print(
                f"[micro] tampon audio ({len(donnees)} octets) au-dela de la "
                f"limite du format WAV ({_LIMITE_RIFF_OCTETS} octets), "
                "transcription ignoree pour ce cycle.",
                file=sys.stderr,
            )
            return ""
        audio = self._sr.AudioData(donnees, self._micro.SAMPLE_RATE, self._micro.SAMPLE_WIDTH)
        try:
            return self._transcrire(audio)
        except Exception as exc:
            print(
                f"[micro] transcription locale en echec ({len(donnees)} octets, "
                f"SAMPLE_RATE={self._micro.SAMPLE_RATE}, "
                f"SAMPLE_WIDTH={self._micro.SAMPLE_WIDTH}) : {exc}",
                file=sys.stderr,
            )
            return ""

    def ecouter(self, invite: str = "") -> str:
        """
        --------------------------------------------------------------------------
        Purpose:
            Enregistrer aussi longtemps que l'etudiant parle, avec une
            transcription PROGRESSIVE affichee au fur et a mesure (precision de
            l'enseignant, 2026-09-19) : Entree n'enclenche pas la transcription,
            elle FIGE et ENVOIE le texte deja transcrit. Deux fils de fond,
            jamais un rappel ROS2 (piege 1 de plan02.md, qui ne se negocie pas) :
            l'un lit les trames audio en continu sans jamais s'arreter pour
            transcrire (pour ne rien perdre pendant qu'une transcription est en
            cours), l'autre retranscrit le tampon complet toutes les
            `speech_rafraichissement_secondes` et pousse le texte a l'affichage
            SEULEMENT s'il a CHANGE (self._affichage.afficher_texte, reecrit en
            place, jamais empile).

            CORRIGE le 2026-09-20 (plan09.md, defaut mesure le 2026-09-19) :
            l'attente d'Entree se faisait par input(), bloquant INDEFINIMENT
            sous ros2 launch (le stdin n'y est pas rattache aux noeuds).
            Remplace par self._affichage.attendre_confirmation(). Ce fil
            appelant reste celui qui porte l'attente, exactement comme le
            prevoit plan02.md (aucun rappel ROS2 ici), mais NE TOUCHE PLUS
            jamais tkinter directement (correction du 2026-09-20, apres
            l'epreuve reelle de plan09.md etape 6 : tkinter sous Windows leve
            `RuntimeError: main thread is not in main loop` hors du fil
            principal) : attendre_confirmation() ne fait que RELIRE une
            confirmation ou une fermeture deja enregistree par le pompage du
            fil principal (voice_input_node.main(), voir voice_window.py).

            Si la fenetre est fermee pendant l'attente, attendre_confirmation()
            rend None : ce cas se termine comme une ecoute vide, rien n'est
            publie, et c'est voice_input_node qui arrete alors le noeud (rappel
            on_fermeture de VoiceWindow).

            Une transcription vide (rien dit, ou rien d'intelligible) n'est
            jamais publiee par l'appelant : elle est rendue telle quelle et
            affichee une seule fois, sans qu'aucun code n'y reagisse comme a une
            erreur de programme.

        Inputs:
            invite (str): conserve pour compatibilite d'appel (voir
                voice_input_node.py) ; l'invite n'est plus imprimee sur stdout
                depuis plan09.md, la fenetre remplace le journal comme surface
                d'affichage.

        Outputs:
            texte (str): transcription finale, vide si rien d'intelligible n'a
                ete capte ou si la fenetre a ete fermee pendant l'ecoute
        --------------------------------------------------------------------------
        """
        if self._closed:
            raise RuntimeError("Microphone deja ferme.")

        self._affichage.afficher_texte("")

        trames: list[bytes] = []
        verrou = threading.Lock()
        arret = threading.Event()
        dernier_texte_affiche = ""

        def _lire_audio() -> None:
            depart = time.monotonic()
            with self._micro as source:
                while not arret.is_set():
                    if time.monotonic() - depart >= self._duree_max_ecoute:
                        # Garde-fou (defaut mesure le 2026-09-20,
                        # vram-et-transcription-report.md) : sans detection de
                        # fin de parole, rien d'autre ne bornait cette boucle.
                        # Une fenetre jamais confirmee accumulait un tampon
                        # jusqu'a depasser le champ 4 octets non signe du
                        # format WAV (~4,29 Go), et get_wav_data() levait
                        # struct.error a chaque rafraichissement. Le tampon
                        # deja capte reste utilisable ; seule la lecture de
                        # NOUVELLES trames s'arrete.
                        self._affichage.afficher_texte(
                            "(duree maximale d'ecoute atteinte : appuyez sur "
                            "Entree pour envoyer ce qui a ete capte)"
                        )
                        arret.set()
                        break
                    trame = source.stream.read(source.CHUNK)
                    with verrou:
                        trames.append(trame)

        def _rafraichir_periodiquement() -> None:
            nonlocal dernier_texte_affiche
            while not arret.wait(timeout=self._rafraichissement):
                texte = self._texte_depuis_tampon(trames, verrou)
                if texte and texte != dernier_texte_affiche:
                    dernier_texte_affiche = texte
                    self._affichage.afficher_texte(texte)

        fil_audio = threading.Thread(target=_lire_audio, daemon=True)
        fil_rafraichissement = threading.Thread(target=_rafraichir_periodiquement, daemon=True)
        fil_audio.start()
        fil_rafraichissement.start()

        resultat = self._affichage.attendre_confirmation()

        arret.set()
        fil_audio.join(timeout=self._arret_fil_timeout)
        fil_rafraichissement.join(timeout=self._arret_fil_timeout)

        if resultat is None:
            # Fenetre fermee pendant l'attente : rien a publier, voice_input_node
            # arrete le noeud via le rappel on_fermeture de VoiceWindow.
            return ""

        texte_final = self._texte_depuis_tampon(trames, verrou)
        if texte_final:
            self._affichage.afficher_texte(texte_final)
            return texte_final

        self._affichage.afficher_texte("(rien d'intelligible n'a ete capte)")
        return ""

    def close(self) -> None:
        self._closed = True
        self._affichage.close()


class MoteurWinRT:
    """
    --------------------------------------------------------------------------
    Purpose:
        Parler francais avec les voix que Windows possede DEJA mais que SAPI5
        n'expose pas.

        Mesure du 2026-09-20 sur la machine de l'enseignant : SAPI5, par lequel
        passe pyttsx3, n'offre qu'une seule voix, `TTS_MS_EN-US_ZIRA_11.0`
        (en-US). Le francais etait donc prononce par un moteur anglais, d'ou la
        qualite signalee. Or `Speech_OneCore` porte trois voix French (Canada) --
        Microsoft Caroline, Claude et Nathalie -- invisibles pour SAPI5. L'API
        WinRT `Windows.Media.SpeechSynthesis` les atteint sans aucun droit
        administrateur, contrairement a la copie de cles de registre vers SAPI5.

        Mesure de la chaine complete le meme jour : voix par defaut 'Microsoft
        Caroline' (fr-CA), 241486 octets de `audio/wav` pour une phrase de
        confirmation du Devoir 2, entete RIFF/WAVE valide, lecture audible par
        `winsound.PlaySound` (bibliotheque standard, aucune dependance de plus).

        La lecture est BLOQUANTE, comme l'etait `pyttsx3.runAndWait()` : le robot
        finit sa phrase avant que la machine d'etats ne passe a la suite.
    --------------------------------------------------------------------------
    """

    def __init__(self, langue_preferee: str = "fr", voix_preferee: str = ""):
        # Importes ici et non en tete de module : ce sont des paquets optionnels,
        # et leur absence doit degrader vers pyttsx3, pas casser l'import de voice.
        import asyncio  # noqa: PLC0415
        from winrt.windows.media.speechsynthesis import (  # noqa: PLC0415
            SpeechSynthesizer,
        )

        self._asyncio = asyncio
        self._synth = SpeechSynthesizer()
        self._choisir_voix(langue_preferee, voix_preferee)

    def _choisir_voix(self, langue_preferee: str, voix_preferee: str) -> None:
        """
        Retenir une voix explicite si elle est demandee, sinon garder celle du
        systeme quand sa langue convient deja.

        L'enumeration statique des voix n'est pas exposee par cette liaison Python
        (`SpeechSynthesizer` n'a ni `get_all_voices` ni interface `_Statics`,
        mesure le 2026-09-20), donc on ne peut pas parcourir le catalogue : on lit
        la voix courante et on verifie sa langue. C'est suffisant ici, la voix par
        defaut du poste etant deja fr-CA, et c'est dit plutot que suppose.
        """
        self.voix = ""
        self.langue = ""
        courante = getattr(self._synth, "voice", None)
        if courante is not None:
            self.voix = str(getattr(courante, "display_name", ""))
            self.langue = str(getattr(courante, "language", ""))

        if voix_preferee and self.voix != voix_preferee:
            raise RuntimeError(
                f"voix '{voix_preferee}' demandee par "
                f"devoir2.synthese_vocale.voix_preferee, mais WinRT rend "
                f"'{self.voix}' et cette liaison Python n'expose pas "
                f"l'enumeration des voix. Laisser voix_preferee vide pour "
                f"accepter la voix du systeme."
            )
        if langue_preferee and not self.langue.lower().startswith(
                langue_preferee.lower()):
            raise RuntimeError(
                f"la voix par defaut de Windows est '{self.voix}' ({self.langue}), "
                f"or devoir2.synthese_vocale.langue_preferee vaut "
                f"'{langue_preferee}'. Changer la voix par defaut dans les "
                f"parametres de Windows, ou vider langue_preferee pour l'accepter."
            )

    def dire(self, texte: str) -> None:
        """Synthetiser puis jouer, en bloquant jusqu'a la fin de la phrase."""
        import tempfile  # noqa: PLC0415
        import winsound  # noqa: PLC0415
        from winrt.windows.storage.streams import DataReader  # noqa: PLC0415

        async def _synthetiser() -> bytes:
            flux = await self._synth.synthesize_text_to_stream_async(texte)
            taille = int(flux.size)
            lecteur = DataReader(flux.get_input_stream_at(0))
            await lecteur.load_async(taille)
            return bytes(lecteur.read_buffer(taille))

        octets = self._asyncio.run(_synthetiser())
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fichier:
            fichier.write(octets)
            chemin = fichier.name
        try:
            winsound.PlaySound(chemin, winsound.SND_FILENAME)
        finally:
            with contextlib.suppress(OSError):
                Path(chemin).unlink()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._synth.close()


class MoteurPyttsx3:
    """Ancien moteur, conserve comme repli : SAPI5 via pyttsx3."""

    def __init__(self):
        import pyttsx3  # noqa: PLC0415

        self._moteur = pyttsx3.init()
        self.voix = ""
        self.langue = ""
        with contextlib.suppress(Exception):
            courante = self._moteur.getProperty("voice")
            for v in self._moteur.getProperty("voices"):
                if v.id == courante:
                    self.voix = str(v.name)
                    langues = getattr(v, "languages", None) or []
                    self.langue = str(langues[0]) if langues else ""
                    break

    def dire(self, texte: str) -> None:
        self._moteur.say(texte)
        self._moteur.runAndWait()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._moteur.stop()


class SortieVocale:
    """
    Synthese vocale, facultative.

    Le devoir reste entierement utilisable sans elle : si aucun moteur n'est
    disponible, la classe se rabat sur l'affichage texte et LE DIT une fois, au lieu
    de faire croire que le robot parle.

    Trois moteurs, choisis par `devoir2.synthese_vocale.moteur` (R7) :
    'winrt' (voix francaises de Windows, sans droits administrateur), 'pyttsx3'
    (SAPI5, l'ancien chemin), 'texte' (aucune synthese), et 'auto' qui essaie WinRT
    puis pyttsx3. Chaque repli est ANNONCE avec sa raison (R8).
    """

    def __init__(self, actif: bool = True, reglages: dict[str, Any] | None = None):
        self._moteur: Any = None
        self._raison = ""
        if not actif:
            self._raison = "synthese vocale desactivee par l'utilisateur"
            return

        reglages = reglages or {}
        demande = str(reglages.get("moteur", "auto")).lower()
        langue = str(reglages.get("langue_preferee", ""))
        voix = str(reglages.get("voix_preferee", ""))

        if demande == "texte":
            self._raison = "synthese vocale desactivee par configuration (moteur='texte')"
            return

        if demande == "auto":
            ordre = ("winrt", "pyttsx3")
        elif demande in ("winrt", "pyttsx3"):
            ordre = (demande,)
        else:
            self._raison = (
                f"devoir2.synthese_vocale.moteur vaut '{demande}', attendu "
                f"'auto', 'winrt', 'pyttsx3' ou 'texte'"
            )
            return

        echecs: list[str] = []
        for nom in ordre:
            try:
                self._moteur = (MoteurWinRT(langue, voix) if nom == "winrt"
                                else MoteurPyttsx3())
                self._raison = ""
                return
            except Exception as exc:
                echecs.append(f"{nom} ({type(exc).__name__}: {exc})")
        self._raison = "synthese vocale indisponible : " + " ; ".join(echecs)

    @property
    def disponible(self) -> bool:
        return self._moteur is not None

    @property
    def raison(self) -> str:
        """Pourquoi la synthese est indisponible, vide si elle l'est."""
        return self._raison

    @property
    def description(self) -> str:
        """Quelle voix parle reellement, pour que le journal le dise (R9)."""
        if self._moteur is None:
            return self._raison
        voix = getattr(self._moteur, "voix", "")
        langue = getattr(self._moteur, "langue", "")
        nom = type(self._moteur).__name__
        return f"{nom} : {voix} ({langue})" if voix else nom

    def dire(self, texte: str) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Prononcer un texte, et l'afficher dans tous les cas.

        Inputs:
            texte (str): phrase a prononcer

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        print(f"[robot] {texte}")
        if self._moteur is None:
            return
        try:
            self._moteur.dire(texte)
        except Exception as exc:
            self._moteur = None
            self._raison = f"synthese vocale interrompue ({exc}), suite en texte seul"
            print(f"[robot] {self._raison}", file=sys.stderr)

    def close(self) -> None:
        if self._moteur is None:
            return
        with contextlib.suppress(Exception):
            self._moteur.close()
        self._moteur = None


def ouvrir_entree(mode: str,
                  settings: dict[str, Any],
                  phrases: Sequence[str] | None = None,
                  device_index: int | None = None,
                  affichage: Any | None = None,
                  on_fermeture: Callable[[], None] | None = None) -> EntreeVocale:
    """
    --------------------------------------------------------------------------
    Purpose:
        Choisir la source de phrases et DIRE laquelle. En mode 'auto', l'echec du
        micro se rabat sur le clavier avec sa raison, jamais en silence : un
        etudiant qui croit parler a un micro muet perd sa seance.

    Inputs:
        mode (str): 'micro', 'clavier', 'script' ou 'auto'
        settings (dict): section devoir2 de la configuration
        phrases (Sequence | None): phrases du mode 'script'
        device_index (int | None): index du peripherique d'entree a ouvrir. Si
            absent, lu dans settings['microphone_device_index'] (ihr_config.json,
            None = peripherique par defaut de Windows, comportement historique).
            Ajoute le 2026-09-19 (diagnostic-micro-report.md) : avant, aucun appelant
            ne pouvait choisir un autre peripherique que le defaut de Windows.
        affichage (Any | None): transmis a MicrophoneInput (mode 'micro'/'auto'
            reussi) uniquement ; voir voice.MicrophoneInput. Sans effet pour les
            autres modes, qui n'ouvrent pas de fenetre (plan09.md, 2026-09-20).
        on_fermeture (Callable[[], None] | None): transmis a MicrophoneInput,
            meme portee que `affichage`.

    Outputs:
        entree (EntreeVocale): source prete a l'emploi
    --------------------------------------------------------------------------
    """
    mode = (mode or "auto").strip().lower()
    valides = ("micro", "clavier", "script", "auto")
    if mode not in valides:
        raise ValueError(f"Mode d'entree '{mode}' inconnu. Valeurs : {', '.join(valides)}.")

    if mode == "script":
        if phrases is None:
            raise ValueError("Le mode 'script' exige une suite de phrases.")
        return ScriptedInput(phrases)

    if mode == "clavier":
        print("[entree] clavier")
        return KeyboardInput()

    if device_index is None:
        device_index = settings.get("microphone_device_index")

    try:
        entree = MicrophoneInput(settings, device_index=device_index,
                                 affichage=affichage, on_fermeture=on_fermeture)
        print(f"[entree] microphone ({entree.nom_peripherique}), "
              f"reconnaissance vocale locale (faster-whisper), fenetre de saisie")
        return entree
    except Exception as exc:
        if mode == "micro":
            raise
        print(f"[entree] microphone indisponible ({exc}). Repli sur le CLAVIER.",
              file=sys.stderr)
        return KeyboardInput()
