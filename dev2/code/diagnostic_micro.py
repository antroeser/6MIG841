"""
diagnostic_micro.py - Devoir 2 : diagnostic outille de la panne "parole non comprise".

Contexte (.sdd/6mig841-ameliorations/diagnostic-micro-report.md, 2026-09-19). Le
symptome signale par l'enseignant venait d'un audio CAPTE et ENVOYE a Google, qui
repondait sans rien reconnaitre.

MODIFIE le 2026-09-19 (.sdd/6mig841-ameliorations/stt-local-report.md) :
`recognize_google` (Google, en nuage) est remplace par faster-whisper (local),
partout dans le solutionnaire. La bissection ci-dessous doit donc eprouver le
MEME chemin que `voice.MicrophoneInput` emprunte reellement : elle appelle
`voice.charger_transcripteur_whisper` (le meme chargeur, jamais un second qui
pourrait diverger, R2), jamais `recognize_google`. Un chemin de reconnaissance
qui n'est plus emprunte par le programme ne certifie plus rien.

Ce script rejoue la bissection qui a diagnostique la panne, sans demander a
personne de parler :

  1. `essayer_bissection` fabrique un WAV synthetique (pyttsx3) et le fait
     transcrire localement. Reconnu : le chemin reconnaissance/langue est sain
     (plus de reseau dans ce chemin depuis le passage a faster-whisper), le
     defaut est dans la CAPTURE. Non reconnu : l'inverse.
  2. `lister_peripheriques` enumere les peripheriques d'entree, index et nom, et
     marque celui que Windows donne par defaut.
  3. `mesurer_amplitude` calibre et mesure l'amplitude crete et la valeur RMS,
     independamment du moteur de reconnaissance. Un peripherique qui rend un
     silence numerique se voit directement sur ce chiffre.

Usage :

    python Devoir2/code/diagnostic_micro.py --lister
    python Devoir2/code/diagnostic_micro.py --device 1
    python Devoir2/code/diagnostic_micro.py --dry-run

Aucune valeur numerique en dur (R7) : duree de mesure, phrase de test et seuil de
silence numerique viennent de devoir2.diagnostic_micro (ihr_config.json), langue
et duree de calibration de devoir2 lui-meme (memes cles que MicrophoneInput,
jamais dupliquees). `--dry-run` n'ouvre aucun peripherique, ne charge aucun
modele et n'ecrit rien (R16). Rapport machine ecrit a cote du texte humain (R17).
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_RACINE_DEPOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(_RACINE_DEPOT / "Lab1" / "code"))

from ihr_ros import config  # noqa: E402
from voice import charger_transcripteur_whisper  # noqa: E402

_RAPPORT_DEFAUT = Path(__file__).resolve().parent.parent / "diagnostic_micro_rapport.json"


class DiagnosticMicroError(RuntimeError):
    """Une dependance attendue (speech_recognition, pyttsx3, PyAudio) est absente."""


def _importer_sr() -> Any:
    """Importer speech_recognition, en nommant la dependance manquante (R8)."""
    try:
        import speech_recognition as sr  # noqa: PLC0415
    except ImportError as exc:
        raise DiagnosticMicroError(
            "speech_recognition est absent de l'environnement actif. "
            "Installer avec le .venv du Devoir 2 (requirements.txt)."
        ) from exc
    return sr


def index_peripherique_par_defaut(sr_module: Any) -> int | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Trouver l'index que PyAudio donne au peripherique par defaut de Windows,
        sans en ouvrir aucun.

    Inputs:
        sr_module (module): speech_recognition deja importe

    Outputs:
        index (int | None): index par defaut, None si indetectable
    --------------------------------------------------------------------------
    """
    try:
        audio = sr_module.Microphone.get_pyaudio().PyAudio()
    except Exception:
        return None
    try:
        return int(audio.get_default_input_device_info()["index"])
    except Exception:
        return None
    finally:
        audio.terminate()


def lister_peripheriques(sr_module: Any) -> list[dict[str, Any]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Enumerer les peripheriques d'entree, avec une marque sur celui que
        Windows donne par defaut.

    Inputs:
        sr_module (module): speech_recognition deja importe

    Outputs:
        peripheriques (list[dict]): un {index, nom, est_defaut} par entree
    --------------------------------------------------------------------------
    """
    noms = sr_module.Microphone.list_microphone_names()
    index_defaut = index_peripherique_par_defaut(sr_module)
    return [
        {"index": i, "nom": nom, "est_defaut": i == index_defaut}
        for i, nom in enumerate(noms)
    ]


def mesurer_amplitude(
    sr_module: Any,
    device_index: int | None,
    duree_s: float,
    calibration_s: float,
) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Ouvrir un peripherique, calibrer le bruit ambiant comme le fait
        `MicrophoneInput.__init__`, puis enregistrer et mesurer l'amplitude
        reelle du signal capte (crete et valeur efficace RMS). Un peripherique
        qui rend un silence numerique se voit sur ce chiffre.

    Inputs:
        sr_module (module): speech_recognition deja importe
        device_index (int | None): index du peripherique, None pour le defaut
        duree_s (float): duree d'enregistrement mesuree, en secondes
        calibration_s (float): duree de calibration ambiante, en secondes

    Outputs:
        mesure (dict): n_echantillons, amplitude_crete, amplitude_rms (0..32767),
            seuil_energie (recognizer.energy_threshold apres calibration)
    --------------------------------------------------------------------------
    """
    recognizer = sr_module.Recognizer()
    micro = sr_module.Microphone(device_index=device_index)
    with micro as source:
        recognizer.adjust_for_ambient_noise(source, duration=calibration_s)
        seuil = float(recognizer.energy_threshold)
        audio = recognizer.record(source, duration=duree_s)

    echantillons = struct.unpack(f"<{len(audio.frame_data) // 2}h", audio.frame_data)
    n = len(echantillons)
    crete = max(abs(x) for x in echantillons) if n else 0
    rms = (sum(x * x for x in echantillons) / n) ** 0.5 if n else 0.0

    return {
        "n_echantillons": n,
        "amplitude_crete": crete,
        "amplitude_rms": round(rms, 3),
        "seuil_energie": round(seuil, 3),
    }


def essayer_bissection(
    sr_module: Any,
    phrase: str,
    transcripteur: Callable[[Any], str],
    chemin_wav: Path,
    createur_moteur_tts: Any = None,
) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Fabriquer de la parole synthetique (pyttsx3) et la faire transcrire par
        le MEME transcripteur local (faster-whisper) que `voice.MicrophoneInput`
        emploie reellement, sans jamais toucher un vrai microphone. La
        bissection du diagnostic : isoler le chemin reconnaissance/langue de la
        capture materielle. MODIFIE le 2026-09-19
        (.sdd/6mig841-ameliorations/stt-local-report.md) : remplace
        `recognize_google` (Google, en nuage), qui n'est plus le chemin
        emprunte par le programme et ne certifiait donc plus rien.

    Inputs:
        sr_module (module): speech_recognition deja importe
        phrase (str): phrase a synthetiser puis a faire reconnaitre
        transcripteur (Callable[[Any], str]): fonction de transcription locale,
            construite par `voice.charger_transcripteur_whisper` (charge une
            seule fois par `construire_rapport`, jamais ici) ou injectee par un
            test hors ligne
        chemin_wav (Path): fichier temporaire ecrit puis relu
        createur_moteur_tts (callable | None): fabrique le moteur pyttsx3 ; le
            vrai `pyttsx3.init` si absent (injectable pour les tests hors ligne)

    Outputs:
        resultat (dict): reconnu (bool), texte ou raison, phrase_envoyee
    --------------------------------------------------------------------------
    """
    if createur_moteur_tts is None:
        import pyttsx3  # noqa: PLC0415

        createur_moteur_tts = pyttsx3.init

    moteur = createur_moteur_tts()
    try:
        moteur.save_to_file(phrase, str(chemin_wav))
        moteur.runAndWait()
    finally:
        try:
            moteur.stop()
        except Exception:
            pass

    # Ecriture asynchrone sur certains pilotes : attendre un fichier non vide
    # plutot que le relire immediatement (mesure 2026-09-19, sinon tronque).
    for _ in range(20):
        if chemin_wav.exists() and chemin_wav.stat().st_size > 44:
            break
        time.sleep(0.1)

    recognizer = sr_module.Recognizer()
    with sr_module.AudioFile(str(chemin_wav)) as source:
        audio = recognizer.record(source)

    try:
        texte = transcripteur(audio)
    except Exception as exc:
        return {"reconnu": False, "raison": f"{type(exc).__name__}: {exc}", "phrase_envoyee": phrase}

    if texte:
        return {"reconnu": True, "texte": texte, "phrase_envoyee": phrase}
    return {"reconnu": False, "raison": "transcription vide", "phrase_envoyee": phrase}


def construire_rapport(
    sr_module: Any,
    device_index: int | None,
    devoir2_cfg: dict[str, Any],
    diag_cfg: dict[str, Any],
    faire_bissection: bool,
    faire_mesure: bool,
    createur_moteur_tts: Any = None,
    transcripteur: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Orchestrer les trois mesures et assembler le rapport machine, sans rien
        decider qu'une des fonctions mesurables n'ait deja etabli.

    Inputs:
        sr_module (module): speech_recognition deja importe
        device_index (int | None): peripherique a mesurer, None pour le defaut
        devoir2_cfg (dict): section 'devoir2' de la configuration
        diag_cfg (dict): section 'devoir2.diagnostic_micro' de la configuration
        faire_bissection (bool): executer l'essai de reconnaissance synthetique
        faire_mesure (bool): executer la mesure d'amplitude
        createur_moteur_tts (callable | None): voir essayer_bissection
        transcripteur (Callable[[Any], str] | None): voir essayer_bissection.
            None (comportement reel) charge faster-whisper via
            `voice.charger_transcripteur_whisper`, UNE SEULE FOIS pour tout le
            rapport, seulement si `faire_bissection` est vrai. Les tests hors
            ligne injectent toujours une valeur (workflow.md R5).

    Outputs:
        rapport (dict): horodatage, peripheriques, mesure, bissection, verdict
    --------------------------------------------------------------------------
    """
    rapport: dict[str, Any] = {
        "horodatage_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "peripheriques": lister_peripheriques(sr_module),
    }

    if faire_bissection:
        if transcripteur is None:
            transcripteur = charger_transcripteur_whisper(devoir2_cfg)
        with tempfile.TemporaryDirectory(prefix="diagnostic_micro_") as dossier:
            rapport["bissection"] = essayer_bissection(
                sr_module,
                str(diag_cfg["phrase_test_defaut"]),
                transcripteur,
                Path(dossier) / "synthese.wav",
                createur_moteur_tts,
            )

    if faire_mesure:
        rapport["mesure_amplitude"] = mesurer_amplitude(
            sr_module,
            device_index,
            float(diag_cfg["duree_mesure_secondes"]),
            float(devoir2_cfg["ambient_noise_seconds"]),
        )
        rms = rapport["mesure_amplitude"]["amplitude_rms"]
        rapport["verdict_silence_numerique"] = rms < float(diag_cfg["seuil_silence_numerique_rms"])

    return rapport


def _imprimer_rapport_humain(rapport: dict[str, Any]) -> None:
    """Texte humain a cote du rapport machine (R17), jamais a sa place."""
    print(f"diagnostic_micro : mesure du {rapport['horodatage_utc']}")

    for peripherique in rapport.get("peripheriques", []):
        marque = " (defaut Windows)" if peripherique["est_defaut"] else ""
        print(f"    [{peripherique['index']}] {peripherique['nom']}{marque}")

    if "bissection" in rapport:
        bissection = rapport["bissection"]
        if bissection["reconnu"]:
            print(f"  bissection : RECONNU ('{bissection['texte']}') -> chemin "
                  "reconnaissance/langue sain (faster-whisper, local), la panne "
                  "est dans la CAPTURE.")
        else:
            print(f"  bissection : NON RECONNU ({bissection['raison']}) -> le "
                  "chemin de reconnaissance est en cause, le micro est hors de cause.")

    if "mesure_amplitude" in rapport:
        mesure = rapport["mesure_amplitude"]
        print(f"  amplitude mesuree : crete={mesure['amplitude_crete']} "
              f"rms={mesure['amplitude_rms']} (max possible 32767), "
              f"seuil d'energie={mesure['seuil_energie']}")
        if rapport.get("verdict_silence_numerique"):
            print("  VERDICT : silence numerique sur ce peripherique. Choisir un "
                  "autre index avec devoir2.microphone_device_index (voir --lister).")


def _construire_analyseur() -> argparse.ArgumentParser:
    """Arguments CLI, separes de main() pour rester lisibles (R17 : --rapport)."""
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--lister", action="store_true",
                           help="enumerer les peripheriques et quitter, sans mesurer")
    analyseur.add_argument("--device", type=int, default=None, metavar="INDEX",
                           help="index du peripherique a mesurer (par defaut : Windows)")
    analyseur.add_argument("--sans-bissection", action="store_true",
                           help="ne pas fabriquer de parole synthetique (saute le reseau)")
    analyseur.add_argument("--sans-mesure", action="store_true",
                           help="ne pas mesurer l'amplitude du peripherique")
    analyseur.add_argument("--rapport", type=Path, default=_RAPPORT_DEFAUT,
                           help=f"chemin du rapport machine (defaut : {_RAPPORT_DEFAUT})")
    analyseur.add_argument("--dry-run", action="store_true",
                           help="n'ouvre rien, n'appelle aucun reseau, n'ecrit rien (R16)")
    return analyseur


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree CLI : parser les arguments, executer les mesures
        demandees, imprimer le rapport humain, ecrire le rapport machine.

    Inputs:
        argv (list[str] | None): arguments CLI, ceux du processus si absents

    Outputs:
        code (int): 0 si les mesures demandees ont pu s'executer, 1 sinon
    --------------------------------------------------------------------------
    """
    args = _construire_analyseur().parse_args(argv)

    try:
        sr_module = _importer_sr()
        devoir2_cfg = config.section("devoir2")
        diag_cfg = devoir2_cfg["diagnostic_micro"]
    except (DiagnosticMicroError, config.ConfigError) as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("diagnostic_micro : essai a blanc (--dry-run), rien n'est touche.")
        if not args.sans_bissection:
            print(f"  bissection prevue : phrase '{diag_cfg['phrase_test_defaut']}', "
                  f"langue {devoir2_cfg['speech_language']} (aucun modele charge, "
                  f"aucun reseau touche)")
        if not args.sans_mesure:
            print(f"  mesure prevue : peripherique {args.device!r}, "
                  f"{diag_cfg['duree_mesure_secondes']} s (aucun micro ouvert)")
        print(f"  rapport qui aurait ete ecrit : {args.rapport}")
        return 0

    if args.lister:
        for peripherique in lister_peripheriques(sr_module):
            marque = " (defaut Windows)" if peripherique["est_defaut"] else ""
            print(f"[{peripherique['index']}] {peripherique['nom']}{marque}")
        return 0

    try:
        rapport = construire_rapport(
            sr_module, args.device, devoir2_cfg, diag_cfg,
            faire_bissection=not args.sans_bissection,
            faire_mesure=not args.sans_mesure,
        )
    except Exception as exc:
        print(f"ERREUR pendant la mesure : {exc}", file=sys.stderr)
        return 1

    _imprimer_rapport_humain(rapport)
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    args.rapport.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  rapport machine ecrit : {args.rapport}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
