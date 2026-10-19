"""
check_env.py - Etat de l'environnement du laboratoire 6MIG841.

Etape de verification du Lab1, et premier reflexe quand un devoir refuse de demarrer.
Repond a cinq questions, sans rien installer et sans rien modifier :

  1. quel interpreteur Python tourne, et est-ce bien celui du .venv,
  2. quelles librairies sont presentes, et dans quelle version,
  3. ROS2 est-il importable, et quelle dorsale sera donc choisie,
  4. la camera repond-elle,
  5. le demon Ollama repond-il, et quels modeles porte-t-il.

Sortie humaine par defaut, JSON avec `--json` (workflow.md R17). Le code de retour
vaut 0 si tout ce qui est INDISPENSABLE est present, 1 sinon. La camera, le micro,
Ollama et ROS2 ne sont pas indispensables : leur absence est rapportee, avec ce
qu'elle empeche, sans faire echouer la verification.

Usage :
    python Lab1/code/check_env.py
    python Lab1/code/check_env.py --json
    python Lab1/code/check_env.py --camera        (ouvre reellement la camera)
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

# Modules sans lesquels aucun travail ne demarre.
REQUIRED = ("cv2", "mediapipe", "numpy", "ihr_ros")

# Modules dont l'absence n'empeche qu'une partie du laboratoire.
OPTIONAL = {
    "ultralytics": "Projet : detection d'objets YOLO",
    "speech_recognition": "Devoir 2 : capture audio brute (sr.Microphone)",
    "pyaudio": "Devoir 2 : acces au microphone",
    "faster_whisper": "Devoir 2 : transcription vocale locale (remplace recognize_google)",
    "pyttsx3": "Devoir 2 : synthese vocale",
    "ollama": "Devoir 2 : client du LLM local",
    "matplotlib": "Lab 1 : figures de comparaison des planificateurs",
    "pytest": "les trois travaux : suite de tests",
}

_DIST_NAME = {
    "cv2": "opencv-python",
    "speech_recognition": "SpeechRecognition",
    "pyaudio": "PyAudio",
    "ihr_ros": "ihr-ros",
    "faster_whisper": "faster-whisper",
}

# Paquets pip que Devoir2/code/voice.py::_ajouter_repertoires_dll_cuda cherche par
# importlib.util.find_spec (jamais un 'import' litteral) quand
# devoir2.speech_device commence par 'cuda'. Nommes ICI une seule fois :
# Lab1/code/requirements-cuda.txt et Lab1/test/test_dependances_completes.py sont
# tous deux verifies contre cette table plutot que de la recopier (R2).
CUDA_DLL_PACKAGES = {
    "nvidia.cublas": "nvidia-cublas-cu12",
    "nvidia.cudnn": "nvidia-cudnn-cu12",
    "nvidia.cuda_nvrtc": "nvidia-cuda-nvrtc-cu12",
}


def configure_streams() -> None:
    """Forcer utf-8 sur stdout et stderr, sans jamais lever (console cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def module_state(name: str) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Dire si un module s'importe et dans quelle version.

    Inputs:
        name (str): nom du module a importer

    Outputs:
        state (dict): cles present, version, erreur
    --------------------------------------------------------------------------
    """
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return {"present": False, "version": None, "erreur": f"{type(exc).__name__}: {exc}"}

    version = getattr(module, "__version__", None)
    if version is None:
        try:
            version = metadata.version(_DIST_NAME.get(name, name))
        except Exception:
            version = "inconnue"
    return {"present": True, "version": str(version), "erreur": None}


def interpreter_state(repo_root: Path) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Reconnaitre l'interpreteur courant parmi les DEUX interpreteurs legitimes
        du laboratoire : le `.venv` (Lab1, Devoir1, tests hors ligne) et
        l'environnement conda ROS2 (Devoir2, Projet, tout ce qui touche ROS2).
        Avant plan01, une seule appartenance etait reconnue et toute sortie du
        `.venv` declenchait une alerte : ce jugement etait faux la moitie du
        temps, puisque conda est le second interpreteur legitime, pas une erreur.

    Inputs:
        repo_root (Path): racine du depot 6MIG841-Lab

    Outputs:
        state (dict): version, chemin, role a trois valeurs ("venv", "conda",
            "inconnu"), et conseil non vide seulement pour "inconnu"
    --------------------------------------------------------------------------
    """
    expected_venv = (repo_root / ".venv").resolve()
    # Chemin derive de USERPROFILE, jamais un nom de compte ecrit en dur (R1),
    # comme dans Lab1/code/ros2_env.ps1.
    conda_envs = (Path(os.environ.get("USERPROFILE", "")) /
                  "scoop" / "apps" / "miniforge3" / "current" / "envs").resolve()
    current = Path(sys.executable).resolve()

    if expected_venv in current.parents:
        role = "venv"
    elif conda_envs in current.parents:
        role = "conda"
    else:
        role = "inconnu"

    conseil = ""
    if role == "inconnu":
        conseil = (
            f"Interpreteur non reconnu : ni le .venv ({expected_venv}) ni "
            f"l'environnement conda ROS2 ({conda_envs}). Lancer avec "
            f"{expected_venv / 'Scripts' / 'python.exe'} pour Lab1/Devoir1, ou "
            "Lab1/code/ros2_env.ps1 pour Devoir2/Projet."
        )

    return {
        "version": sys.version.split()[0],
        "executable": str(current),
        "venv_attendu": str(expected_venv),
        "conda_envs_attendu": str(conda_envs),
        "role": role,
        "conseil": conseil,
    }


def ros2_variables_state() -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Rapporter les deux variables ROS2 obligatoires (Lab1/code/ros2_env.ps1,
        ihr_config.json section "ros2"). Leur absence est la cause la plus
        probable d'un probleme de pare-feu (Fast DDS emet en multicast) ou d'une
        tortue pilotee par un autre poste de la salle, mesure le 2026-09-18.

    Inputs:
        aucun (lit os.environ)

    Outputs:
        state (dict): valeurs lues, et avertissement si l'une des deux manque
    --------------------------------------------------------------------------
    """
    localhost_only = os.environ.get("ROS_LOCALHOST_ONLY")
    domain_id = os.environ.get("ROS_DOMAIN_ID")
    manquantes = [nom for nom, val in
                  (("ROS_LOCALHOST_ONLY", localhost_only), ("ROS_DOMAIN_ID", domain_id))
                  if not val]
    return {
        "ROS_LOCALHOST_ONLY": localhost_only,
        "ROS_DOMAIN_ID": domain_id,
        "manquantes": manquantes,
        "avertissement": (
            "Variable(s) absente(s) : " + ", ".join(manquantes) +
            ". Lancer Lab1/code/ros2_env.ps1 avant tout programme ROS2, "
            "sinon le pare-feu peut reclamer les droits administrateur et "
            "DDS peut decouvrir un autre poste de la salle."
        ) if manquantes else "",
    }


def camera_state(index: int, open_it: bool) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Verifier la camera. L'ouverture reelle est optionnelle car elle allume le
        voyant de la webcam et prend une seconde.

    Inputs:
        index (int): index de camera OpenCV
        open_it (bool): tenter l'ouverture reelle

    Outputs:
        state (dict): teste, ouverte, dimensions de la trame lue, erreur
    --------------------------------------------------------------------------
    """
    if not open_it:
        return {"teste": False, "ouverte": None,
                "note": "Non teste. Relancer avec --camera pour ouvrir reellement."}
    try:
        import cv2
    except Exception as exc:
        return {"teste": True, "ouverte": False, "erreur": f"cv2 absent : {exc}"}

    capture = cv2.VideoCapture(index)
    try:
        if not capture.isOpened():
            return {"teste": True, "ouverte": False,
                    "erreur": f"Aucune camera a l'index {index}."}
        ok, frame = capture.read()
        if not ok or frame is None:
            return {"teste": True, "ouverte": True, "trame": False,
                    "erreur": "Camera ouverte mais aucune trame lue."}
        height, width = frame.shape[:2]
        return {"teste": True, "ouverte": True, "trame": True,
                "largeur": int(width), "hauteur": int(height), "erreur": None}
    finally:
        capture.release()


def ollama_state(host: str, timeout_seconds: float) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Verifier que le demon Ollama ecoute et lister ses modeles.

    Inputs:
        host (str): URL du demon, par exemple http://127.0.0.1:11434
        timeout_seconds (float): delai maximal de connexion

    Outputs:
        state (dict): joignable, modeles, erreur
    --------------------------------------------------------------------------
    """
    from urllib.parse import urlparse

    parsed = urlparse(host)
    hostname = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434

    try:
        with socket.create_connection((hostname, port), timeout=timeout_seconds):
            pass
    except OSError as exc:
        return {"joignable": False, "modeles": [],
                "erreur": f"{hostname}:{port} injoignable ({exc}). Lancer `ollama serve`."}

    try:
        import ollama
        listing = ollama.Client(host=host).list()
        models = sorted(
            getattr(m, "model", None) or m.get("model", "?")
            for m in getattr(listing, "models", None) or listing.get("models", [])
        )
        return {"joignable": True, "modeles": models, "erreur": None}
    except Exception as exc:
        return {"joignable": True, "modeles": [],
                "erreur": f"Demon joignable mais liste des modeles illisible : {exc}"}


def gpu_state(timeout_seconds: float) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Dire si un GPU NVIDIA est utilisable et si les bibliotheques CUDA dont
        Devoir2/code/voice.py a besoin en mode devoir2.speech_device="cuda"
        (Lab1/code/ihr_config.json) sont trouvables. Mesure le 2026-09-19 sur
        cette machine : l'environnement conda 'ihr' avait faster-whisper et
        ctranslate2 installes SANS nvidia-cublas-cu12 ni nvidia-cudnn-cu12, ce
        qui leve `RuntimeError: Library cublas64_12.dll is not found` au
        PREMIER CALCUL REEL de ctranslate2, pas au chargement du modele : une
        panne qui n'apparaissait qu'en pleine transcription, jamais ici.

        Ni le GPU ni les bibliotheques CUDA ne sont INDISPENSABLES (REQUIRED) :
        une machine sans GPU NVIDIA execute le Devoir 2 en mettant
        devoir2.speech_device a 'cpu' dans ihr_config.json (mode d'origine du
        solutionnaire).

    Inputs:
        timeout_seconds (float): delai maximal pour l'appel a nvidia-smi (R10)

    Outputs:
        state (dict): gpu_detecte, nom, vram_totale_mio, vram_libre_mio,
            bibliotheques_cuda (dict paquet -> present), erreur
    --------------------------------------------------------------------------
    """
    state: dict[str, Any] = {
        "gpu_detecte": False,
        "nom": None,
        "vram_totale_mio": None,
        "vram_libre_mio": None,
        "bibliotheques_cuda": {
            paquet: importlib.util.find_spec(module) is not None
            for module, paquet in CUDA_DLL_PACKAGES.items()
        },
        "erreur": None,
    }

    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        state["erreur"] = ("nvidia-smi introuvable : pas de pilote NVIDIA installe, ou "
                           "aucun GPU NVIDIA sur cette machine.")
        return state

    try:
        sortie = subprocess.run(
            [nvidia_smi, "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout_seconds, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        state["erreur"] = f"nvidia-smi a echoue : {type(exc).__name__}: {exc}"
        return state

    premiere_ligne = next((l for l in sortie.stdout.splitlines() if l.strip()), "")
    morceaux = [m.strip() for m in premiere_ligne.split(",")]
    if len(morceaux) != 3:
        state["erreur"] = f"sortie nvidia-smi inattendue : {premiere_ligne!r}"
        return state

    state["gpu_detecte"] = True
    state["nom"] = morceaux[0]
    try:
        state["vram_totale_mio"] = int(morceaux[1])
        state["vram_libre_mio"] = int(morceaux[2])
    except ValueError:
        state["erreur"] = f"valeurs de VRAM illisibles dans la sortie nvidia-smi : {premiere_ligne!r}"
    return state


def collect(repo_root: Path, open_camera: bool) -> dict[str, Any]:
    """Assembler l'etat complet de l'environnement."""
    from ihr_ros import config as ihr_config
    from ihr_ros.turtle_io import describe_environment

    report: dict[str, Any] = {
        "interpreteur": interpreter_state(repo_root),
        "requis": {name: module_state(name) for name in REQUIRED},
        "optionnels": {name: module_state(name) for name in OPTIONAL},
        "ros2": describe_environment(),
        "ros2_variables": ros2_variables_state(),
    }

    try:
        camera_cfg = ihr_config.section("camera")
        report["camera"] = camera_state(int(camera_cfg["index"]), open_camera)
    except Exception as exc:
        report["camera"] = {"teste": False, "erreur": f"Configuration camera illisible : {exc}"}

    try:
        devoir2 = ihr_config.section("devoir2")
        report["ollama"] = ollama_state(str(devoir2["llm_host"]), 2.0)
    except Exception as exc:
        report["ollama"] = {"joignable": False, "modeles": [],
                            "erreur": f"Configuration ollama illisible : {exc}"}

    try:
        timeout_gpu = float(ihr_config.section("check_env")["nvidia_smi_timeout_seconds"])
    except Exception:
        timeout_gpu = 3.0  # secours seulement si la section a disparu (R3 : jamais silencieux)
        report.setdefault("avertissements", []).append(
            "Section 'check_env' absente ou illisible dans ihr_config.json : "
            "delai nvidia-smi de secours (3.0 s) utilise."
        )
    report["gpu"] = gpu_state(timeout_gpu)
    try:
        speech_device = str(ihr_config.section("devoir2")["speech_device"])
    except Exception:
        speech_device = "inconnu"
    report["gpu"]["cuda_requis_par_devoir2"] = speech_device.startswith("cuda")

    manquants = [n for n, s in report["requis"].items() if not s["present"]]
    report["manquants_indispensables"] = manquants
    report["pret"] = not manquants and report["interpreteur"]["role"] != "inconnu"
    return report


def render(report: dict[str, Any]) -> None:
    """Rapport lisible par un humain."""
    interp = report["interpreteur"]
    marque = "ATT " if interp["role"] == "inconnu" else "OK  "
    print("=" * 74)
    print(" 6MIG841 - etat de l'environnement")
    print("=" * 74)
    print(f"{marque} Python {interp['version']}  (role : {interp['role']})")
    print(f"     {interp['executable']}")
    if interp["conseil"]:
        print(f"     {interp['conseil']}")

    print()
    print("-- Librairies indispensables " + "-" * 45)
    for name, state in report["requis"].items():
        flag = "OK  " if state["present"] else "MANQ"
        detail = state["version"] if state["present"] else state["erreur"]
        print(f"{flag} {name:<20} {detail}")

    print()
    print("-- Librairies optionnelles " + "-" * 47)
    for name, state in report["optionnels"].items():
        flag = "OK  " if state["present"] else "abs "
        detail = state["version"] if state["present"] else OPTIONAL[name]
        print(f"{flag} {name:<20} {detail}")

    print()
    print("-- ROS2 et dorsale " + "-" * 55)
    ros = report["ros2"]
    print(f"{'OK  ' if ros['ros2_available'] else 'abs '} ROS2 importable : {ros['ros2_available']}")
    if not ros["ros2_available"]:
        print(f"     {ros['ros2_reason']}")
    print(f"     dorsale retenue : {ros['backend_selected']}")
    print(f"     {ros['backend_reason']}")

    print()
    print("-- Variables ROS2 obligatoires " + "-" * 43)
    rv = report["ros2_variables"]
    if rv["manquantes"]:
        print(f"ATT  {rv['avertissement']}")
    else:
        print(f"OK   ROS_LOCALHOST_ONLY={rv['ROS_LOCALHOST_ONLY']}  ROS_DOMAIN_ID={rv['ROS_DOMAIN_ID']}")

    print()
    print("-- Camera " + "-" * 64)
    cam = report["camera"]
    if not cam.get("teste"):
        print(f"     {cam.get('note') or cam.get('erreur')}")
    elif cam.get("trame"):
        print(f"OK   trame {cam['largeur']}x{cam['hauteur']} lue a l'index configure")
    else:
        print(f"abs  {cam.get('erreur')}")

    print()
    print("-- Ollama " + "-" * 64)
    oll = report["ollama"]
    if oll["joignable"]:
        print(f"OK   demon joignable, modeles : {', '.join(oll['modeles']) or 'aucun'}")
        if oll["erreur"]:
            print(f"     {oll['erreur']}")
    else:
        print(f"abs  {oll['erreur']}")

    print()
    print("-- GPU et bibliotheques CUDA (Devoir 2, mode 'cuda') " + "-" * 21)
    gpu = report["gpu"]
    if gpu["gpu_detecte"]:
        print(f"OK   GPU : {gpu['nom']}  VRAM libre {gpu['vram_libre_mio']} / "
              f"{gpu['vram_totale_mio']} Mio")
    else:
        print(f"abs  {gpu['erreur']}")
    for paquet, present in gpu["bibliotheques_cuda"].items():
        print(f"{'OK  ' if present else 'abs '} {paquet}")
    if gpu["cuda_requis_par_devoir2"]:
        manque_cuda = (not gpu["gpu_detecte"]) or not all(gpu["bibliotheques_cuda"].values())
        if manque_cuda:
            print("ATT  devoir2.speech_device='cuda' dans ihr_config.json, mais le GPU ou les")
            print("     bibliotheques CUDA manquent : la transcription echouera au premier")
            print("     calcul reel. Installer -Cuda (install_lab1.ps1) ou repasser")
            print("     speech_device a 'cpu'.")

    print()
    print("=" * 74)
    if report["pret"]:
        print(" PRET : les librairies indispensables sont en place.")
    else:
        if report["manquants_indispensables"]:
            print(" PAS PRET : " + ", ".join(report["manquants_indispensables"]))
        if report["interpreteur"]["role"] == "inconnu":
            print(" PAS PRET : interpreteur non reconnu (ni .venv, ni conda ROS2).")
            print(" Relancer Lab1/code/install_lab1.ps1, ou utiliser Lab1/code/ros2_env.ps1.")
        else:
            print(" Relancer Lab1/code/install_lab1.ps1.")
    print("=" * 74)


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    repo_root = Path(__file__).resolve().parent.parent.parent

    parser = argparse.ArgumentParser(description="Etat de l'environnement 6MIG841.")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--camera", action="store_true",
                        help="ouvrir reellement la camera pour la tester")
    args = parser.parse_args(argv)

    report = collect(repo_root, args.camera)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        render(report)

    return 0 if report["pret"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
