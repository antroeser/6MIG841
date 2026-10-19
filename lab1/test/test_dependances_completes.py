"""
test_dependances_completes.py - Verifie, dans UN SEUL SENS, que toute dependance
tierce reellement importee par le CODE DES QUATRE TRAVAUX (Lab1, Devoir1, Devoir2,
Projet) est declaree dans les fichiers du Lab 1 : library_markers.json et
requirements.txt / requirements-cuda.txt.

C'est le test qui manquait le 2026-09-19 : faster-whisper, huggingface_hub,
matplotlib et les paquets CUDA etaient tous reellement importes par du code des
travaux sans etre tous declares, decouvert seulement en lisant le code a la main
(pyttsx3 avait le meme defaut depuis l'origine). Une liste recopiee ici referait
la meme erreur des la prochaine dependance ajoutee au code sans etre installee.
Ce fichier scanne donc les VRAIS fichiers .py (via
extract_libs.modules_from_imports, deja teste par test_extract_libs.py) plutot
que de recopier quoi que ce soit, et porte un controle negatif prouvant que le
scan sait echouer.

Precision de l'enseignant le 2026-09-19, apres un premier essai trop large : le
sens INVERSE (un paquet installe que rien n'importe) N'EST PAS une erreur a
corriger ici. Lab1/code/extract_libs.py importe reellement pypdf (lecture des
PDF de rapport_etudiants), mais c'est de l'outillage d'ENSEIGNANT pour AUDITER
les rapports des annees passees, jamais du code que l'etudiant execute pour
faire un des quatre travaux ; SOLUTION_DIRS l'exclut donc explicitement, de meme
que dictee/code et evaluation/code (generation des enonces troues, benchmark du
choix de modele : outillage d'enseignant, jamais execute par l'etudiant). Un
paquet installe sur la machine de l'enseignant sans etre importe par le code des
travaux n'a pas sa place dans requirements.txt du seul fait qu'il est present :
seul est ici verifie le sens qui protege l'etudiant.

N'ouvre aucun fichier hors du depot, ne charge aucun modele, ne touche ni le GPU
ni le reseau (workflow.md R5) : uniquement de la lecture de texte et des
expressions regulieres deja testees ailleurs.

Distinct de test_extract_libs.py : celui-ci couvre le scanner
(modules_from_imports, load_markers, scan) sur des rapports HISTORIQUES
(*/rapport_etudiants/) ou des fixtures ; ce fichier-ci l'applique au code
REELLEMENT EXECUTE par l'etudiant pour faire les quatre travaux.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from extract_libs import load_markers, modules_from_imports

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CODE_DIR = Path(__file__).resolve().parent.parent / "code"

# extract_libs.modules_from_imports() est deliberement TOLERANT aux sauts de ligne
# (son propre en-tete : "le code recopie dans un PDF perd ses sauts de ligne"), ce qui
# est correct sur du texte de PDF mais fabrique de faux modules applique tel quel a du
# vrai code source richement commente en francais : 'import' termine une ligne de
# docstring/commentaire et le premier mot de la phrase suivante ('volontairement',
# 'tardif', 'cellule', ...) est alors capture comme un faux module. Mesure le
# 2026-09-19 en ecrivant ce test : 16 faux modules au premier essai sur Devoir2/code et
# Lab1/code/ihr_ros. Les trois filtres ci-dessous, appliques LIGNE PAR LIGNE (jamais au
# texte entier), eliminent cette classe de faux positifs sans toucher a
# modules_from_imports() lui-meme, partage avec le scan historique des rapports ou
# cette tolerance reste correcte :
#   1. un commentaire '#...' est retire avant tout (ex. '# ... (import volontairement
#      apres l'ajustement de sys.path)' ne doit rien capturer d'autre que le vrai
#      import qui le precede sur la meme ligne) ;
#   2. seule une ligne dont le premier mot (apres indentation) est 'import' ou 'from'
#      est examinee, ce qui exclut toute prose ('l'import de ce module', 'a l'import du
#      module') sans exclure un import differe indente dans une fonction ;
#   3. un import RELATIF ('from .x import Y' ou 'from . import Y') est ignore en bloc :
#      modules_from_imports() ne sait consommer que 'from X import' ou X commence par
#      une lettre, donc un 'from .turtle_io import BackendError, ...' laisse
#      'import BackendError' intact pour le motif d'import simple, qui capture alors le
#      premier nom importe ('backenderror') comme un faux module. Un import relatif
#      designe toujours du code du MEME paquet, jamais une dependance tierce.
_COMMENTAIRE = re.compile(r"#.*$")
_DEBUT_IMPORT = re.compile(r"^\s*(import|from)\s")
_IMPORT_RELATIF = re.compile(r"^\s*from\s+\.")


def _modules_importes_dans_code_source(texte: str) -> set[str]:
    """Applique modules_from_imports() ligne par ligne a du vrai code source .py
    (voir le commentaire ci-dessus pour la raison des trois filtres)."""
    modules: set[str] = set()
    for ligne in texte.splitlines():
        sans_commentaire = _COMMENTAIRE.sub("", ligne)
        if _IMPORT_RELATIF.match(sans_commentaire):
            continue
        if _DEBUT_IMPORT.match(sans_commentaire):
            modules |= modules_from_imports(sans_commentaire)
    return modules

# Repertoires portant le code que l'ETUDIANT execute pour faire un des quatre
# travaux. Ni rapport_etudiants/ (historique, deja couvert par
# test_extract_libs.py), ni etudiant/ (copie trouee du meme code pour la
# remise : memes dependances, la scanner deux fois n'apprendrait rien de plus),
# ni dictee/code ou evaluation/code (outillage d'ENSEIGNANT : generation des
# enonces troues, anti-divulgation, benchmark du choix de modele LLM -
# l'etudiant ne les execute jamais pour faire un travail, precision de
# l'enseignant du 2026-09-19).
SOLUTION_DIRS = (
    "Lab1/code",
    "Devoir1/code",
    "Devoir2/code",
    "Projet/code",
)

# Fichiers a exclure meme sous un des SOLUTION_DIRS ci-dessus : outillage
# d'ENSEIGNANT au meme titre que dictee/code et evaluation/code, simplement
# situe dans un repertoire par ailleurs correct. extract_libs.py "extrait des
# rapports des annees precedentes" (son propre en-tete) pour AUDITER le contenu
# de rapport_etudiants/, jamais du code que l'etudiant execute pour faire le
# Lab 1 lui-meme (verifie le 2026-09-19 : il importe pypdf, absent de
# requirements.txt par choix, precision de l'enseignant).
_FICHIERS_OUTILLAGE_ENSEIGNANT = {"extract_libs.py"}

# Sous-repertoires a ignorer meme sous un des SOLUTION_DIRS ci-dessus.
_IGNORER = {"__pycache__", "models", "ihr_ros.egg-info"}


def _fichiers_py(root: Path) -> list[Path]:
    """Tous les .py sous SOLUTION_DIRS, hors caches, modeles binaires et
    outillage d'enseignant (_FICHIERS_OUTILLAGE_ENSEIGNANT)."""
    fichiers: list[Path] = []
    for dossier in SOLUTION_DIRS:
        base = root / dossier
        if not base.is_dir():
            continue
        for chemin in base.rglob("*.py"):
            if any(part in _IGNORER for part in chemin.parts):
                continue
            if chemin.name in _FICHIERS_OUTILLAGE_ENSEIGNANT:
                continue
            fichiers.append(chemin)
    return fichiers


def _modules_locaux(root: Path) -> set[str]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Noms de module que le depot fournit lui-meme, deduits du disque plutot
        que devines (R6/R7) : le nom (sans extension) de chaque fichier .py
        sous SOLUTION_DIRS, et le nom de tout sous-repertoire immediat portant
        un __init__.py (paquet local, ex. 'planif', 'ihr_ros'). Ces modules ne
        sont jamais des dependances a installer : ce sont des fichiers voisins
        importes par leur nom (ex. 'from history import Historique').

    Inputs:
        root (Path): racine sous laquelle chercher SOLUTION_DIRS

    Outputs:
        locaux (set): noms de module locaux
    --------------------------------------------------------------------------
    """
    fichiers = _fichiers_py(root)
    locaux = {f.stem for f in fichiers}
    for dossier in SOLUTION_DIRS:
        base = root / dossier
        if not base.is_dir():
            continue
        for enfant in base.iterdir():
            if enfant.is_dir() and (enfant / "__init__.py").is_file():
                locaux.add(enfant.name)
    return locaux


def _modules_tiers_importes(root: Path, markers: dict) -> tuple[set[str], set[str]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Scanner reellement le code sous SOLUTION_DIRS et classer chaque module
        importe : fournisseur PyPI requis (via library_markers.json), ou
        inconnu (absent de la table, jamais traduit en un nom devine, meme
        principe que extract_libs.scan).

    Inputs:
        root (Path): racine du depot (ou d'une fixture temporaire)
        markers (dict): table chargee par load_markers()

    Outputs:
        (pypi_requis, inconnus) (tuple[set, set])
    --------------------------------------------------------------------------
    """
    fichiers = _fichiers_py(root)
    locaux = _modules_locaux(root)
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    connus = markers["modules"]

    importes: set[str] = set()
    for fichier in fichiers:
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        importes |= _modules_importes_dans_code_source(texte)

    tiers = importes - locaux - stdlib

    pypi_requis: set[str] = set()
    inconnus: set[str] = set()
    for module in tiers:
        entree = connus.get(module)
        if entree is None:
            inconnus.add(module)
        elif entree["pypi_name"]:
            pypi_requis.add(entree["pypi_name"])
    return pypi_requis, inconnus


def _paquets_declares(chemin_requirements: Path) -> set[str]:
    """Noms de paquet declares (avant '=='), normalises minuscule et '_'->'-'."""
    paquets: set[str] = set()
    for ligne in chemin_requirements.read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#", 1)[0].strip()
        if not ligne:
            continue
        nom = ligne.split("==")[0].strip()
        if nom:
            paquets.add(nom.lower().replace("_", "-"))
    return paquets


@pytest.fixture(scope="module")
def markers() -> dict:
    return load_markers(CODE_DIR)


@pytest.fixture(scope="module")
def paquets_requirements() -> set[str]:
    return _paquets_declares(CODE_DIR / "requirements.txt")


# ------------------------------------------------------------------ le test qui compte

def test_toute_dependance_tierce_reellement_importee_est_declaree(markers, paquets_requirements):
    """
    Chaque module tiers reellement importe par le code du solutionnaire doit avoir
    son paquet PyPI dans Lab1/code/requirements.txt, et chaque module tiers doit
    figurer dans Lab1/code/library_markers.json (sinon 'inconnu'). Une dependance
    ajoutee au code sans etre installee fait desormais echouer CE test plutot que
    de casser un devoir en salle (le scenario mesure le 2026-09-19 pour
    faster-whisper, huggingface_hub et matplotlib).
    """
    pypi_requis, inconnus = _modules_tiers_importes(REPO_ROOT, markers)

    manquants = {p for p in pypi_requis if p.lower().replace("_", "-") not in paquets_requirements}
    assert not manquants, (
        f"Paquet(s) reellement importe(s) par le code mais absent(s) de "
        f"Lab1/code/requirements.txt : {sorted(manquants)}"
    )
    assert not inconnus, (
        f"Module(s) reellement importe(s) par le code mais absent(s) de "
        f"Lab1/code/library_markers.json : {sorted(inconnus)}"
    )


def test_controle_negatif_une_dependance_plantee_non_declaree_est_rapportee(tmp_path, markers):
    """
    Controle negatif exige par la tache : sans lui, un test qui ne trouve jamais
    rien a redire ne prouve rien. Un fichier .py plante sous une racine temporaire,
    important un module absent de library_markers.json, doit ressortir en
    'inconnu' plutot que d'etre silencieusement ignore.
    """
    dossier = tmp_path / "Devoir1" / "code"
    dossier.mkdir(parents=True)
    (dossier / "espion.py").write_text(
        "import une_dependance_plantee_non_declaree_du_tout\n", encoding="utf-8"
    )

    _, inconnus = _modules_tiers_importes(tmp_path, markers)

    assert "une_dependance_plantee_non_declaree_du_tout" in inconnus


def test_controle_negatif_un_module_local_voisin_n_est_pas_signale_inconnu(tmp_path, markers):
    """
    Symetrique du controle precedent : un fichier qui importe un VOISIN local
    (meme repertoire, jamais installe par pip) ne doit jamais etre signale, sans
    quoi le test du dessus deviendrait inutilisable au premier fichier ajoute.
    """
    dossier = tmp_path / "Devoir2" / "code"
    dossier.mkdir(parents=True)
    (dossier / "voisin.py").write_text("VALEUR = 1\n", encoding="utf-8")
    (dossier / "utilise_le_voisin.py").write_text("import voisin\n", encoding="utf-8")

    _, inconnus = _modules_tiers_importes(tmp_path, markers)

    assert "voisin" not in inconnus


# ------------------------------------------------------------------ CUDA optionnel

# Paquets CUDA que Devoir2/code/voice.py::_ajouter_repertoires_dll_cuda cherche par
# importlib.util.find_spec (jamais un 'import' litteral, donc invisible au scan
# ci-dessus) quand devoir2.speech_device commence par 'cuda'. Nommes UNE SEULE FOIS
# ici : requirements-cuda.txt et check_env.py (CUDA_DLL_PACKAGES) en sont tous deux
# verifies, jamais recopies l'un depuis l'autre en silence.
_PAQUETS_CUDA_ATTENDUS = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-nvrtc-cu12")


def test_requirements_cuda_declare_les_paquets_que_check_env_verifie():
    """
    Lab1/code/requirements-cuda.txt (installation optionnelle, -Cuda) doit declarer
    exactement les paquets que check_env.py sait detecter (CUDA_DLL_PACKAGES),
    sinon un etudiant qui installe -Cuda resterait signale comme n'ayant pas les
    bibliotheques, ou l'inverse.
    """
    from check_env import CUDA_DLL_PACKAGES

    declares = _paquets_declares(CODE_DIR / "requirements-cuda.txt")
    verifies = set(CUDA_DLL_PACKAGES.values())

    assert verifies == set(_PAQUETS_CUDA_ATTENDUS), (
        "check_env.CUDA_DLL_PACKAGES a change sans mise a jour du controle ci-dessus."
    )
    assert declares == verifies, (
        f"requirements-cuda.txt ({sorted(declares)}) et check_env.CUDA_DLL_PACKAGES "
        f"({sorted(verifies)}) doivent declarer exactement les memes paquets."
    )
