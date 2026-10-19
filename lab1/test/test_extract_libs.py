"""
test_extract_libs.py - Tests de l'inventaire des librairies (Lab1/code/extract_libs.py).

Couvre la regression mesuree le 2026-09-18 (voir l'en-tete de extract_libs.py) : un motif
`import\\s+(\\w+)` applique au texte entier capturait aussi le nom importe d'un
`from X import Y`, produisant le faux module 'client' pour `from ollama import Client` et
treize faux "modules inconnus" dans l'inventaire reel. Couvre aussi les deux sorties
SystemExit exigees par le script : library_markers.json absent, et une racine sans aucun
`*/rapport_etudiants`.
"""

from __future__ import annotations

import json

import pytest

from extract_libs import load_markers, modules_from_imports, modules_from_prose, scan


# ------------------------------------------------------- modules_from_imports (regression)

def test_from_import_ne_capture_pas_le_nom_importe_controle_de_regression():
    """
    Regression du 2026-09-18 : 'from ollama import Client' doit donner exactement
    {'ollama'}, jamais le faux module 'client' capture par le motif `import\\s+(\\w+)`
    applique apres coup sur le nom importe. Les deux directions sont verifiees.
    """
    modules = modules_from_imports("from ollama import Client")
    assert modules == {"ollama"}
    assert "client" not in modules


def test_import_mixte_avec_alias_et_from_import_ne_capture_ni_l_alias_ni_le_nom_importe():
    """Un fichier melangeant 'import X', 'import X as Y' et 'from X.Y import Z' est reduit
    a ses modules racine seulement : ni l'alias 'mp' ni le nom importe 'Twist' n'apparaissent."""
    texte = "import cv2\nimport mediapipe as mp\nfrom geometry_msgs.msg import Twist\n"
    modules = modules_from_imports(texte)
    assert modules == {"cv2", "mediapipe", "geometry_msgs"}
    assert "mp" not in modules
    assert "twist" not in modules


def test_texte_sans_instruction_import_ne_retourne_aucun_module():
    """Un texte de rapport sans code colle ne produit aucun module, sans lever d'exception."""
    assert modules_from_imports("ceci est un rapport sans code colle") == set()


# ------------------------------------------------------- modules_from_prose

def test_modules_from_prose_reconnait_une_librairie_citee_via_son_alias():
    """Une librairie citee en prose ('OpenCV') est retrouvee via la table d'alias fournie."""
    modules = modules_from_prose(
        "Nous avons utilise OpenCV pour la detection.",
        {"opencv": "cv2"},
    )
    assert modules == {"cv2"}


def test_modules_from_prose_ignore_les_alias_prefixes_d_un_tiret_bas():
    """Un alias prefixe par '_' (metadonnee) n'est jamais traite comme un alias de librairie."""
    modules = modules_from_prose(
        "Ceci mentionne opencv dans le texte.",
        {"_commentaire": "ignorer_ceci_aussi", "opencv": "cv2"},
    )
    assert modules == {"cv2"}


# ------------------------------------------------------- load_markers (chemins d'echec)

def test_load_markers_fichier_absent_leve_systemexit(tmp_path):
    """Sans library_markers.json a cote du script, load_markers() leve SystemExit (pas un crash brut)."""
    with pytest.raises(SystemExit, match="introuvable"):
        load_markers(tmp_path)


def test_load_markers_sans_module_declare_leve_systemexit(tmp_path):
    """Un library_markers.json present mais qui ne declare aucun module leve aussi SystemExit."""
    (tmp_path / "library_markers.json").write_text(json.dumps({"modules": {}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="aucun module"):
        load_markers(tmp_path)


def test_load_markers_valide_retourne_la_table_telle_quelle(tmp_path):
    """Un library_markers.json bien forme est charge tel quel, sans transformation."""
    contenu = {"modules": {"cv2": {"pypi_name": "opencv-python", "role": "vision", "note": "n"}}}
    (tmp_path / "library_markers.json").write_text(json.dumps(contenu), encoding="utf-8")
    markers = load_markers(tmp_path)
    assert markers["modules"]["cv2"]["pypi_name"] == "opencv-python"


# ------------------------------------------------------- scan (chemins d'echec + bout en bout)

@pytest.fixture
def markers_minimaux() -> dict:
    """Table module -> distribution minimale, suffisante pour les tests de scan()."""
    return {
        "modules": {
            "cv2": {"pypi_name": "opencv-python", "role": "vision", "note": "test"},
            "ollama": {"pypi_name": "ollama", "role": "llm", "note": "test"},
        },
        "prose_aliases": {},
    }


def test_scan_racine_sans_rapport_etudiants_leve_systemexit(tmp_path, markers_minimaux):
    """Une racine ne contenant aucun */rapport_etudiants leve SystemExit plutot qu'un rapport vide."""
    with pytest.raises(SystemExit, match="rapport_etudiants"):
        scan(tmp_path, markers_minimaux)


def test_scan_construit_l_inventaire_et_evite_le_faux_module_client(tmp_path, markers_minimaux):
    """
    Bout en bout : un code source contenant 'from ollama import Client' est scanne sans
    faire apparaitre 'client' dans les modules trouves (meme regression que ci-dessus,
    verifiee ici au niveau de l'API publique scan(), pas seulement de modules_from_imports).
    """
    dossier = tmp_path / "Devoir1" / "rapport_etudiants"
    dossier.mkdir(parents=True)
    (dossier / "code.py").write_text("import cv2\nfrom ollama import Client\n", encoding="utf-8")

    rapport = scan(tmp_path, markers_minimaux)

    assert rapport["documents_lus"] == 1
    noms_modules = {m["module"] for m in rapport["modules"]}
    assert noms_modules == {"cv2", "ollama"}
    assert "client" not in noms_modules
    assert rapport["a_installer_par_pip"] == ["ollama", "opencv-python"]
    assert rapport["modules_inconnus"] == []


def test_scan_module_absent_de_la_table_est_signale_inconnu_sans_etre_devine(tmp_path):
    """Un module absent de library_markers.json est classe 'inconnu', jamais traduit en un nom PyPI devine."""
    markers = {"modules": {}, "prose_aliases": {}}
    dossier = tmp_path / "Devoir2" / "rapport_etudiants"
    dossier.mkdir(parents=True)
    (dossier / "code.py").write_text("import une_lib_pas_dans_la_table\n", encoding="utf-8")

    rapport = scan(tmp_path, markers)

    assert "une_lib_pas_dans_la_table" in rapport["modules_inconnus"]
