"""
extract_libs.py - Inventaire des librairies utilisees par les travaux des annees passees.

Etape 1 du Lab1. Lit tous les rapports PDF et tous les codes sources de
`*/rapport_etudiants/`, en tire la liste des modules Python reellement importes, et
produit :

  - `libraries.json` : rapport lisible par une machine (workflow.md, R17),
  - une table sur la sortie standard, lisible par un humain.

Deux sources sont croisees, volontairement :

  1. les instructions `import` trouvees dans le code source et dans les annexes de
     code recopiees dans les PDF, qui donnent le nom EXACT du module,
  2. les mentions en prose ("nous avons utilise OpenCV et Yolo"), qui rattrapent les
     librairies citees dans un tableau de rapport mais dont le code n'est pas joint.

La correspondance module -> distribution PyPI vit dans `library_markers.json`, en
donnee. Rien n'est devine ici : un module inconnu de la table est rapporte comme
`inconnu` plutot que traduit en un nom PyPI plausible.

Usage :
    python Lab1/code/extract_libs.py
    python Lab1/code/extract_libs.py --root . --json Lab1/code/libraries.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

MARKERS_FILE = "library_markers.json"

# Formes d'import Python. Le code recopie dans un PDF perd ses sauts de ligne, donc
# les motifs ne s'ancrent pas en debut de ligne.
#
# L'ordre compte et le premier motif est CONSOMMATEUR. Mesure le 2026-09-18 : un
# motif `import\s+(\w+)` applique au texte entier capture aussi le nom importe, pas
# seulement le module. `from ollama import Client` produisait alors le faux module
# `client`, et l'inventaire annoncait treize modules inconnus dont onze etaient des
# noms de fonctions et de classes.
_FROM_IMPORT = re.compile(r"\bfrom\s+([A-Za-z_][\w.]*)\s+import\b")
_PLAIN_IMPORT = re.compile(r"\bimport\s+([A-Za-z_][\w.]*)")


def configure_streams() -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Forcer stdout et stderr en utf-8. Les rapports sont en francais et les
        noms de fichiers portent des accents : sur une console cp1252, une
        simple impression leve UnicodeEncodeError et le script meurt avant
        d'avoir rien ecrit.

    Inputs:
        aucun

    Outputs:
        aucun
    --------------------------------------------------------------------------
    """
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


def load_markers(code_dir: Path) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Charger la table module -> distribution PyPI.

    Inputs:
        code_dir (Path): repertoire contenant library_markers.json

    Outputs:
        markers (dict): contenu du fichier
    --------------------------------------------------------------------------
    """
    path = code_dir / MARKERS_FILE
    if not path.is_file():
        raise SystemExit(
            f"ERREUR : {path} introuvable. Sans cette table, l'inventaire serait une "
            "liste de noms devinee plutot qu'une mesure."
        )
    with path.open(encoding="utf-8") as handle:
        markers = json.load(handle)
    if not markers.get("modules"):
        raise SystemExit(f"ERREUR : {path} ne declare aucun module.")
    return markers


def pdf_text(path: Path) -> tuple[str, str]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Extraire le texte d'un PDF avec pypdf.

    Inputs:
        path (Path): chemin du PDF

    Outputs:
        text (str): texte extrait, vide si illisible
        status (str): 'ok', 'vide' (PDF scanne ou image), ou 'illisible: <raison>'
    --------------------------------------------------------------------------
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "illisible: pypdf absent (pip install pypdf)"

    try:
        reader = PdfReader(str(path))
        chunks = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        return "", f"illisible: {type(exc).__name__}: {exc}"

    text = "\n".join(chunks)
    if not text.strip():
        return "", "vide"
    return text, "ok"


def modules_from_imports(text: str) -> set[str]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Relever les modules cites par une instruction import.

    Inputs:
        text (str): texte source ou texte extrait d'un PDF

    Outputs:
        modules (set): noms de module racine, en minuscules
    --------------------------------------------------------------------------
    """
    found: set[str] = set()

    # Les formes `from X import Y` sont relevees PUIS retirees du texte, de sorte que
    # le motif `import Y` qui suit ne puisse plus capturer Y comme s'il etait un module.
    def take_from(match: re.Match[str]) -> str:
        found.add(match.group(1).split(".")[0].lower())
        return " "

    remainder = _FROM_IMPORT.sub(take_from, text)

    for match in _PLAIN_IMPORT.finditer(remainder):
        found.add(match.group(1).split(".")[0].lower())
    return found


def modules_from_prose(text: str, aliases: dict[str, str]) -> set[str]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Relever les librairies citees en prose, via la table d'alias.

    Inputs:
        text (str): texte du rapport
        aliases (dict): alias de prose -> nom de module

    Outputs:
        modules (set): noms de module
    --------------------------------------------------------------------------
    """
    lowered = text.lower()
    found: set[str] = set()
    for alias, module in aliases.items():
        if alias.startswith("_"):
            continue
        if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", lowered):
            found.add(module)
    return found


def scan(root: Path, markers: dict[str, Any]) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Parcourir tous les rapport_etudiants/ et construire l'inventaire.

    Inputs:
        root (Path): racine du depot 6MIG841-Lab
        markers (dict): table chargee depuis library_markers.json

    Outputs:
        report (dict): inventaire complet, serialisable en JSON
    --------------------------------------------------------------------------
    """
    aliases = {k: v for k, v in markers["prose_aliases"].items() if not k.startswith("_")}
    known = markers["modules"]

    per_module_sources: dict[str, set[str]] = defaultdict(set)
    per_module_evidence: dict[str, set[str]] = defaultdict(set)
    documents: list[dict[str, Any]] = []

    targets = sorted(root.glob("*/rapport_etudiants"))
    if not targets:
        raise SystemExit(
            f"ERREUR : aucun repertoire */rapport_etudiants sous {root}. "
            "Lancer le script depuis la racine de 6MIG841-Lab, ou passer --root."
        )

    for reports_dir in targets:
        travail = reports_dir.parent.name
        for path in sorted(reports_dir.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                text, status = pdf_text(path)
                kind = "rapport"
            elif suffix == ".py":
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                    status = "ok"
                except OSError as exc:
                    text, status = "", f"illisible: {exc}"
                kind = "code"
            else:
                continue

            imports = modules_from_imports(text) if text else set()
            prose = modules_from_prose(text, aliases) if text else set()

            for module in imports:
                per_module_sources[module].add(travail)
                per_module_evidence[module].add("import")
            for module in prose:
                per_module_sources[module].add(travail)
                per_module_evidence[module].add("prose")

            documents.append({
                "travail": travail,
                "fichier": str(path.relative_to(root)).replace("\\", "/"),
                "type": kind,
                "statut": status,
                "modules_importes": sorted(imports),
                "modules_en_prose": sorted(prose - imports),
            })

    modules: list[dict[str, Any]] = []
    for module in sorted(per_module_sources):
        entry = known.get(module)
        modules.append({
            "module": module,
            "pypi_name": entry["pypi_name"] if entry else None,
            "role": entry["role"] if entry else "inconnu",
            "note": entry["note"] if entry else
                    "Module absent de library_markers.json. A classer a la main avant installation.",
            "travaux": sorted(per_module_sources[module]),
            "preuve": sorted(per_module_evidence[module]),
        })

    a_installer = sorted({m["pypi_name"] for m in modules if m["pypi_name"]})
    fournis_par_ros2 = sorted({m["module"] for m in modules if m["role"] == "ros2"})
    inconnus = sorted({m["module"] for m in modules if m["role"] == "inconnu"})

    return {
        "genere_par": "Lab1/code/extract_libs.py",
        "racine": str(root),
        "documents_lus": len(documents),
        "documents_illisibles": [d for d in documents if d["statut"] != "ok"],
        "modules": modules,
        "a_installer_par_pip": a_installer,
        "fournis_par_ros2": fournis_par_ros2,
        "modules_inconnus": inconnus,
        "documents": documents,
    }


def print_report(report: dict[str, Any]) -> None:
    """Table lisible par un humain, en complement du JSON."""
    print(f"Documents lus : {report['documents_lus']}")
    illisibles = report["documents_illisibles"]
    if illisibles:
        print(f"Documents illisibles : {len(illisibles)}")
        for doc in illisibles:
            print(f"  - {doc['fichier']} : {doc['statut']}")
    else:
        print("Documents illisibles : aucun")

    print()
    print(f"{'module':<20} {'pypi':<20} {'role':<8} {'preuve':<14} travaux")
    print("-" * 88)
    for entry in report["modules"]:
        pypi = entry["pypi_name"] or "-"
        print(f"{entry['module']:<20} {pypi:<20} {entry['role']:<8} "
              f"{','.join(entry['preuve']):<14} {','.join(entry['travaux'])}")

    print()
    print("A installer par pip :")
    for name in report["a_installer_par_pip"]:
        print(f"  {name}")
    print()
    print("Fournis par l'installation ROS2, jamais par pip :")
    for name in report["fournis_par_ros2"]:
        print(f"  {name}")
    if report["modules_inconnus"]:
        print()
        print("A CLASSER A LA MAIN (absents de library_markers.json) :")
        for name in report["modules_inconnus"]:
            print(f"  {name}")


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    code_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--root", default=str(code_dir.parent.parent),
                        help="racine du depot 6MIG841-Lab")
    parser.add_argument("--json", default=str(code_dir / "libraries.json"),
                        help="chemin du rapport JSON a ecrire")
    parser.add_argument("--quiet", action="store_true",
                        help="n'ecrire que le JSON, sans table sur la sortie standard")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = scan(root, load_markers(code_dir))

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if not args.quiet:
        print_report(report)
        print()
        print(f"Rapport JSON ecrit : {out}")

    return 1 if report["modules_inconnus"] or report["documents_illisibles"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
