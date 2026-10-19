"""
test_lanceurs.py - Tests des trois lanceurs a la racine (stDev1.bat, stDev2.bat, stProjet.bat).

Bogue corrige : stDev2.bat testait `$LASTEXITCODE -ne 0` juste apres avoir appele
Lab1\\code\\ros2_env.ps1 par l'operateur `&`. Dans une session `powershell -Command` neuve,
$LASTEXITCODE est indefini ($null) tant qu'aucun executable natif n'a tourne, et un script
.ps1 qui rend normalement (sans `exit` explicite, ce que fait ros2_env.ps1 sur son chemin de
succes) ne le fixe pas. `$null -ne 0` est vrai, donc le lanceur prenait la branche de refus
et rendait `exit $null`, c'est-a-dire 0 : le .bat sortait en silence, code de succes, sans
jamais atteindre `ros2 launch`. Mesure le 2026-09-19, voir
.sdd/6mig841-ameliorations/lanceur-stdev2-report.md.

Le correctif teste plutot le CONTENU de $py : le contrat documente de ros2_env.ps1 (ecrit le
chemin de l'interpreteur sur la sortie standard en cas de succes, ou se tait sur cette meme
sortie et rend 2 en cas de refus). Les quatre premiers tests inspectent le TEXTE des trois
.bat (workflow.md R2, sur le modele de test_ros2_env.py) :

  1. Les trois lanceurs existent.
  2. stDev1.bat et stProjet.bat gardent leur garde deja saine (existence testee reellement,
     message ERREUR explicite, code de sortie non nul) : verifie plutot qu'affirme, pour
     qu'une regression future soit vue.
  3. Le motif fautif exact de stDev2.bat est absent.
  4. La garde corrigee teste $py et, en cas de refus, l'affiche et rend un code non nul.

Un texte syntaxiquement correct ne prouve rien de semantique : le bogue diagnostique ne se
serait jamais vu a l'inspection seule. Les deux derniers tests sont donc COMPORTEMENTAUX, sur
le modele du cinquieme cas de test_ros2_env.py. Ils copient le VRAI stDev2.bat et le VRAI
ros2_env.ps1 (aucune reimplantation) dans un arbre temporaire qui reproduit la structure
relative dont stDev2.bat depend, les font tourner reellement, et affirment l'effet plutot que
le seul code de retour (R9) :

  - environnement conda absent (configuration de fixture pointant un nom qui n'existe pas) :
    le refus doit etre VISIBLE et le code de retour NE DOIT PAS etre 0 ;
  - controle negatif exige par la tache : environnement conda PRESENT (racine USERPROFILE de
    fixture, hermetique, sans dependre d'une vraie installation conda) : la garde NE DOIT PAS
    se declencher. Sans ce controle, une garde qui refuse toujours passerait le premier test
    par accident.

Les deux tests comportementaux restent hors ligne au sens fort de workflow.md R5 : aucune
variable ROS2 n'est jamais posee sur une vraie installation, ROS2 n'est jamais requis sur le
PATH, et le second monte un environnement conda entierement factice. Ils se sautent proprement
si ni pwsh ni powershell n'est trouve sur le PATH, et portent un delai borne (R10).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_RACINE_DEPOT = Path(__file__).resolve().parent.parent.parent
_STDEV1 = _RACINE_DEPOT / "stDev1.bat"
_STDEV2 = _RACINE_DEPOT / "stDev2.bat"
_STPROJET = _RACINE_DEPOT / "stProjet.bat"
_ROS2_ENV_PS1 = _RACINE_DEPOT / "Lab1" / "code" / "ros2_env.ps1"

_DELAI_MAX_SECONDES = 30.0  # R10 : tout appel de sous-processus porte un delai borne.
_NOM_ENV_CONDA_ABSENT = "environnement_de_test_lanceur_qui_n_existe_pas_6mig841"
_NOM_ENV_CONDA_FIXTURE = "sonde_env_present_6mig841"


def _lire(chemin: Path) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Lire le contenu texte d'un fichier, en echouant si le fichier n'existe
        pas encore (le test qui l'appelle porte alors l'echec, jamais un skip).

    Inputs:
        chemin (Path): fichier a lire.

    Outputs:
        str: contenu texte decode en UTF-8.
    --------------------------------------------------------------------------
    """
    return chemin.read_text(encoding="utf-8")


def _executable_powershell() -> str | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Chercher pwsh puis powershell sur le PATH, sans en exiger un des deux.
        Duplique de test_ros2_env.py pour que ce fichier reste autosuffisant.

    Inputs:
        Aucune.

    Outputs:
        str | None: chemin de l'executable trouve, ou None si aucun des deux.
    --------------------------------------------------------------------------
    """
    for candidat in ("pwsh", "powershell"):
        trouve = shutil.which(candidat)
        if trouve:
            return trouve
    return None


def _ecrire_config_minimal(dossier_code: Path, nom_env_conda: str, complet: bool) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Ecrire un ihr_config.json de fixture, section "ros2" seulement, dans un
        arbre temporaire qui imite Lab1/code.

    Inputs:
        dossier_code (Path): dossier de fixture qui joue le role de Lab1/code.
        nom_env_conda (str): valeur ecrite pour ros2.conda_env_name.
        complet (bool): si vrai, ajoute aussi les cles lues APRES le test
            d'existence de python.exe (ros_localhost_only, ros_distro,
            ros_version, rmw_implementation), necessaires quand le montage
            attend que le script aille plus loin (environnement present).

    Outputs:
        Aucune : ecrit ihr_config.json dans dossier_code.
    --------------------------------------------------------------------------
    """
    ros2_config = {
        "ros_domain_id_default": 1,
        "conda_env_name": nom_env_conda,
    }
    if complet:
        ros2_config.update(
            {
                "ros_localhost_only": 1,
                "ros_distro": "humble",
                "ros_version": 2,
                "rmw_implementation": "rmw_fastrtps_cpp",
            }
        )
    dossier_code.mkdir(parents=True, exist_ok=True)
    (dossier_code / "ihr_config.json").write_text(
        json.dumps({"ros2": ros2_config}), encoding="utf-8"
    )


def _preparer_arbre_lanceur(tmp_path: Path) -> Path:
    """
    --------------------------------------------------------------------------
    Purpose:
        Copier le VRAI stDev2.bat et le VRAI ros2_env.ps1 (contenu de
        production, jamais reimplante) dans un arbre temporaire qui reproduit
        la structure relative dont stDev2.bat depend
        (%~dp0Lab1\\code\\ros2_env.ps1).

    Inputs:
        tmp_path (Path): racine temporaire fournie par pytest.

    Outputs:
        Path: chemin du stDev2.bat copie, pret a etre execute.
    --------------------------------------------------------------------------
    """
    dossier_code = tmp_path / "Lab1" / "code"
    dossier_code.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_ROS2_ENV_PS1, dossier_code / "ros2_env.ps1")
    stdev2_copie = tmp_path / "stDev2.bat"
    shutil.copy2(_STDEV2, stdev2_copie)
    return stdev2_copie


def test_les_trois_lanceurs_existent():
    """Les trois .bat attendus a la racine du depot sont bien presents."""
    assert _STDEV1.is_file()
    assert _STDEV2.is_file()
    assert _STPROJET.is_file()


def test_stdev1_et_stprojet_gardent_une_garde_deja_saine():
    """
    Controle de non-regression (point 3 de la tache) : stDev1.bat et stProjet.bat ne
    portent pas le motif fautif de stDev2.bat. Leur garde teste l'existence d'un fichier
    reel (`if not exist`), affiche un message ERREUR explicite nommant le chemin attendu,
    et rend un code de sortie non nul (`exit /b 1`) : rien de silencieux ici, verifie
    plutot qu'affirme.
    """
    for chemin in (_STDEV1, _STPROJET):
        contenu = _lire(chemin)
        assert contenu.count("if not exist") >= 2, chemin
        assert "echo ERREUR" in contenu, chemin
        assert "exit /b 1" in contenu, chemin
        # Negatif : ces deux lanceurs n'invoquent pas powershell et ne portent donc
        # aucune garde fondee sur $LASTEXITCODE.
        assert "LASTEXITCODE" not in contenu, chemin


def test_stdev2_le_motif_fautif_est_absent():
    """
    Le motif exact diagnostique (`if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }` juste
    apres l'appel a ros2_env.ps1) doit avoir disparu. Ecrit AVANT le correctif : ce test
    echoue sur le stDev2.bat fautif, ou le motif est present verbatim, et passe une fois
    le correctif applique.
    """
    contenu = _lire(_STDEV2)
    assert "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" not in contenu


def test_stdev2_la_garde_corrigee_teste_py_et_nomme_le_refus():
    """
    La garde corrigee doit tester le contenu de $py (le contrat documente de
    ros2_env.ps1), afficher un message qui nomme le refus, et propager un code de
    sortie non nul plutot que de se taire.
    """
    contenu = _lire(_STDEV2)
    assert "$py = &" in contenu
    assert "IsNullOrWhiteSpace($py)" in contenu
    assert "Write-Host" in contenu
    assert "refuse" in contenu.lower()
    assert "exit 2" in contenu


def test_stdev2_refuse_visiblement_quand_l_environnement_conda_est_absent(tmp_path):
    """
    Test comportemental central (point 4 de la tache) : execute REELLEMENT le vrai
    stDev2.bat, dans une configuration ou l'environnement conda declare par la
    configuration n'existe pas. Avant le correctif, ce montage rendait 0 en silence
    (le bogue diagnostique) ; le correctif doit rendre un code non nul et afficher le
    refus. Reste hors ligne au sens fort : le Test-Path sur python.exe echoue avant
    l'ecriture d'aucune variable d'environnement ROS2.
    """
    executable = _executable_powershell()
    if executable is None:
        pytest.skip("Ni pwsh ni powershell trouve sur le PATH : lanceur non executable ici.")

    stdev2_copie = _preparer_arbre_lanceur(tmp_path)
    _ecrire_config_minimal(tmp_path / "Lab1" / "code", _NOM_ENV_CONDA_ABSENT, complet=False)

    resultat = subprocess.run(
        ["cmd", "/c", str(stdev2_copie), "domain_id:=1"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=_DELAI_MAX_SECONDES,
    )

    sortie = resultat.stdout + resultat.stderr
    assert resultat.returncode != 0, sortie
    assert _NOM_ENV_CONDA_ABSENT in sortie, sortie
    assert "introuvable" in sortie, sortie
    assert "refuse" in sortie.lower(), sortie


def test_stdev2_ne_refuse_pas_quand_l_environnement_conda_existe(tmp_path):
    """
    Controle negatif exige par la tache : dans un montage ou l'environnement conda
    EXISTE, la garde ne doit pas se declencher. Sans ce controle, une garde qui refuse
    toujours passerait le test precedent par accident. USERPROFILE est redirige vers
    une fixture hermetique (aucune dependance a une vraie installation conda) : un
    python.exe vide suffit, ros2_env.ps1 se contente d'un Test-Path dessus, jamais ne
    l'execute.
    """
    executable = _executable_powershell()
    if executable is None:
        pytest.skip("Ni pwsh ni powershell trouve sur le PATH : lanceur non executable ici.")

    stdev2_copie = _preparer_arbre_lanceur(tmp_path)
    _ecrire_config_minimal(tmp_path / "Lab1" / "code", _NOM_ENV_CONDA_FIXTURE, complet=True)

    faux_userprofile = tmp_path / "faux_userprofile"
    faux_python = (
        faux_userprofile
        / "scoop"
        / "apps"
        / "miniforge3"
        / "current"
        / "envs"
        / _NOM_ENV_CONDA_FIXTURE
        / "python.exe"
    )
    faux_python.parent.mkdir(parents=True, exist_ok=True)
    faux_python.write_bytes(b"")

    environnement = dict(os.environ)
    environnement["USERPROFILE"] = str(faux_userprofile)

    resultat = subprocess.run(
        ["cmd", "/c", str(stdev2_copie), "domain_id:=1"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=_DELAI_MAX_SECONDES,
        env=environnement,
    )

    sortie = resultat.stdout + resultat.stderr
    assert "ros2_env.ps1 a refuse" not in sortie, sortie
    assert "introuvable" not in sortie, sortie
    # Preuve directe que la ligne `ros2 launch` a ete ATTEINTE (R9 : l'effet, pas le seul
    # code de retour) : ros2 n'existe pas dans cette fixture, donc PowerShell rend
    # CommandNotFoundException des qu'il tente reellement de l'executer. Sur le .bat
    # fautif, la garde sortait AVANT cette ligne (exit $null == 0, en silence) et ce
    # marqueur n'apparaissait jamais : c'est precisement ce que ce test distingue, la
    # ou le seul code de retour (0 dans les deux cas) ne distingue rien.
    assert "CommandNotFoundException" in sortie, sortie
