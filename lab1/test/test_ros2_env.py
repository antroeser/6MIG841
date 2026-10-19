"""
test_ros2_env.py - Tests de Lab1/code/ros2_env.ps1.

Un script PowerShell qui pose des variables d'environnement ROS2 ne s'eprouve pas hors
ligne sur son chemin NOMINAL (workflow.md R5, aucun test ne depend de ROS2) : les quatre
premiers tests inspectent donc son CONTENU plutot que de l'executer, pour les quatre
points exiges par plan01.md, section "Les tests exiges".

1. Les deux variables obligatoires (ROS_LOCALHOST_ONLY, ROS_DOMAIN_ID) sont posees.
   Leur absence cause deux pannes mesurees le 2026-09-18 : le pare-feu Windows qui
   reclame les droits administrateur (Fast DDS emet en multicast), et, dans une salle
   de classe, une tortue qui bouge toute seule parce que DDS a decouvert un autre
   etudiant sur le sous-reseau.
2. AMENT_PREFIX_PATH est pose : sans elle, la CLI `ros2` echoue meme si `rclpy`
   s'importe.
3. Le code de sortie 2 est present : un environnement conda absent est un refus par
   conception (R12), jamais un repli silencieux sur le `.venv`.
4. Controle negatif : aucun nom de compte n'est ecrit en dur, le chemin passe par
   la variable d'environnement USERPROFILE.

Correction de la ronde 1 (relecture) : le point 3 n'etait affirme que textuellement,
donc `exit 2` n'etait jamais reellement exerce et une regression future passerait
inapercue. Le motif du hors-ligne ("du PowerShell qui pose des variables ne s'eprouve
pas hors ligne") est vrai du chemin nominal et FAUX du chemin de refus : ce dernier ne
pose aucune variable, ne touche ni ROS2 ni le reseau, et s'arrete avant toute ecriture
d'environnement. Le cinquieme test ci-dessous execute donc REELLEMENT le script, avec un
nom d'environnement conda qui n'existe pas, et reste hors ligne au sens fort. Il se saute
proprement si ni `pwsh` ni `powershell` n'est trouve sur le PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "code" / "ros2_env.ps1"
_DELAI_MAX_SECONDES = 30.0  # R10 : tout appel de sous-processus porte un delai borne.


def _lire_script() -> str:
    """Lire le contenu texte du script, en echouant si le fichier n'existe pas encore."""
    return _SCRIPT.read_text(encoding="utf-8")


def test_les_deux_variables_obligatoires_sont_posees():
    """
    ROS_LOCALHOST_ONLY et ROS_DOMAIN_ID doivent tous les deux etre assignes, et leur
    valeur doit venir de la configuration plutot que d'un litteral en dur dans le
    script (R7). ihr_config.json, section "ros2", porte les deux valeurs reelles.
    """
    contenu = _lire_script()
    assert "$env:ROS_LOCALHOST_ONLY" in contenu
    assert "$env:ROS_DOMAIN_ID" in contenu
    assert "ros_localhost_only" in contenu
    assert "ros_domain_id_default" in contenu

    config = json.loads((_SCRIPT.parent.parent / "code" / "ihr_config.json").read_text(encoding="utf-8"))
    ros2_cfg = config["ros2"]
    assert int(ros2_cfg["ros_localhost_only"]) == 1
    assert isinstance(ros2_cfg["ros_domain_id_default"], int)


def test_ament_prefix_path_est_pose():
    """AMENT_PREFIX_PATH doit etre assigne, sinon la CLI ros2 echoue sans le dire."""
    contenu = _lire_script()
    assert "$env:AMENT_PREFIX_PATH" in contenu


def test_exit_2_present_pour_environnement_absent():
    """Un environnement conda introuvable est un refus par conception (R12), code 2."""
    contenu = _lire_script()
    assert "exit 2" in contenu


def test_aucun_nom_de_compte_ecrit_en_dur():
    """
    Controle negatif : le chemin de l'environnement passe par $env:USERPROFILE,
    jamais par le nom de compte reel de cette machine ecrit en dur dans le script.
    """
    contenu = _lire_script()
    assert "$env:USERPROFILE" in contenu

    nom_de_compte = os.environ.get("USERNAME", "")
    assert nom_de_compte, "USERNAME absent de l'environnement de test, controle impossible."
    assert nom_de_compte.lower() not in contenu.lower()


def _executable_powershell() -> str | None:
    """Chercher pwsh puis powershell sur le PATH, sans en exiger un des deux."""
    for candidat in ("pwsh", "powershell"):
        trouve = shutil.which(candidat)
        if trouve:
            return trouve
    return None


def test_environnement_conda_absent_rend_le_code_2_et_nomme_le_chemin():
    """
    Chemin de refus (R12), reellement execute plutot qu'affirme sur le texte seul
    (correction ronde 1). Un nom d'environnement conda qui n'existe pas fait echouer
    le Test-Path sur python.exe AVANT toute ecriture de variable ROS2 : ce test reste
    donc hors ligne au sens fort (aucune variable posee, ni ROS2 ni reseau touches).
    Saute proprement si ni pwsh ni powershell n'est sur le PATH de cette machine.
    """
    executable = _executable_powershell()
    if executable is None:
        pytest.skip("Ni pwsh ni powershell trouve sur le PATH : chemin de refus non exercable ici.")

    nom_environnement_absent = "environnement_de_test_qui_n_existe_pas_6mig841"
    resultat = subprocess.run(
        [
            executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(_SCRIPT),
            "-CondaEnvName", nom_environnement_absent,
        ],
        capture_output=True,
        text=True,
        timeout=_DELAI_MAX_SECONDES,
    )

    assert resultat.returncode == 2
    sortie = resultat.stdout + resultat.stderr
    assert nom_environnement_absent in sortie
    assert "python.exe" in sortie
