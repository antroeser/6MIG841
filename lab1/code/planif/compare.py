"""
planif.compare - Banc de comparaison des trois planificateurs sur la meme grille.

Fait tourner A*, Theta* et D*-Lite sur la grille de planif_config.json, puis ajoute
l'obstacle_replanification et rejoue chacun pour mesurer le cout d'une replanification
complete (A*, Theta*) face a une replanification incrementale (D*-Lite). C'est le banc qui
remplit le tableau mesure de l'etape 6 du plan (docs/superpowers/plans/6mig841-ameliorations/
plan06.md) : trois lignes, trois colonnes, des valeurs reelles.

Script d'etat (workflow.md R16, R17) : `--dry-run` n'ecrit rien et affiche ce qui serait
ecrit, et un rapport JSON est toujours emis a cote du texte humain.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import astar, thetastar, world
from .dstarlite import DStarLite
from .world import World

_RAPPORT_PAR_DEFAUT = Path(__file__).resolve().parent / "rapport_comparaison.json"


def executer_comparaison(monde: World | None = None) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Comparer A*, Theta* et D*-Lite sur la meme grille : longueur et points de
        passage du chemin initial, puis cellules reexaminees lors d'une replanification
        apres l'ajout de l'obstacle de replanification.

    Inputs:
        monde (World | None): grille a utiliser ; None charge planif_config.json

    Outputs:
        rapport (dict): grille/depart/but partages, puis un enregistrement par
            planificateur (longueur, points_de_passage, cellules_reexaminees)
    --------------------------------------------------------------------------
    """
    monde = monde if monde is not None else World()
    depart = monde.depart
    but = monde.but
    if depart is None or but is None:
        raise ValueError(
            "La configuration de planification doit fournir 'depart' et 'but' pour comparer."
        )

    # Les trois planificateurs tournent sur LE MEME objet World : le banc ne compare
    # jamais des mondes differents.
    resultat_astar_initial = astar.planifier(monde, depart, but)
    resultat_theta_initial = thetastar.planifier(monde, depart, but)
    planificateur_dstar = DStarLite(monde, depart, but)
    resultat_dstar_initial = planificateur_dstar.planifier()

    rectangle = world.load_config().get("obstacle_replanification")
    cellules_ajoutees = world.rectangle_vers_cellules(rectangle) if rectangle else set()

    if cellules_ajoutees:
        # D*-Lite applique le changement lui-meme (il doit le savoir pour reutiliser son
        # calcul precedent) ; A* et Theta* relisent ensuite le meme monde, deja modifie,
        # sans jamais l'avoir su a l'avance (replanification complete).
        resultat_dstar_replan = planificateur_dstar.mettre_a_jour_obstacle(cellules_ajoutees, True)
        resultat_astar_replan = astar.planifier(monde, depart, but)
        resultat_theta_replan = thetastar.planifier(monde, depart, but)
    else:
        resultat_dstar_replan = planificateur_dstar.planifier()
        resultat_astar_replan = resultat_astar_initial
        resultat_theta_replan = resultat_theta_initial

    return {
        "grille": {
            "largeur_cellules": monde.largeur_cellules,
            "hauteur_cellules": monde.hauteur_cellules,
        },
        "depart": list(depart),
        "but": list(but),
        "planificateurs": {
            "astar": _ligne(resultat_astar_initial, resultat_astar_replan.cellules_examinees),
            "thetastar": _ligne(resultat_theta_initial, resultat_theta_replan.cellules_examinees),
            "dstarlite": _ligne(resultat_dstar_initial, resultat_dstar_replan.cellules_reexaminees),
        },
    }


def _ligne(resultat_initial: Any, cellules_reexaminees_replan: int) -> dict[str, Any]:
    """Assemble les trois grandeurs d'une ligne du tableau compare."""
    chemin = resultat_initial.chemin
    return {
        "longueur": resultat_initial.longueur,
        "points_de_passage": len(chemin) if chemin else 0,
        "cellules_reexaminees": cellules_reexaminees_replan,
    }


def formater_texte(rapport: dict[str, Any]) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Mettre le rapport en un tableau texte lisible (trois lignes, trois colonnes).

    Inputs:
        rapport (dict): sortie de executer_comparaison()

    Outputs:
        texte (str): tableau pret a etre copie dans le tutoriel
    --------------------------------------------------------------------------
    """
    entetes = ("planificateur", "longueur", "points_de_passage", "cellules_reexaminees")
    lignes = [entetes]
    for nom, valeurs in rapport["planificateurs"].items():
        lignes.append((
            nom,
            f"{valeurs['longueur']:.3f}",
            str(valeurs["points_de_passage"]),
            str(valeurs["cellules_reexaminees"]),
        ))
    largeurs = [max(len(ligne[i]) for ligne in lignes) for i in range(len(entetes))]
    return "\n".join(
        "  ".join(cellule.ljust(largeur) for cellule, largeur in zip(ligne, largeurs))
        for ligne in lignes
    )


def main(argv: list[str] | None = None) -> int:
    """Point d'entree CLI : execute la comparaison, affiche le tableau, ecrit le JSON."""
    analyseur = argparse.ArgumentParser(
        description="Compare A*, Theta* et D*-Lite sur la grille de planif_config.json."
    )
    analyseur.add_argument(
        "--sortie",
        type=Path,
        default=_RAPPORT_PAR_DEFAUT,
        help="Chemin du rapport JSON a ecrire (defaut : rapport_comparaison.json a cote de ce module).",
    )
    analyseur.add_argument(
        "--dry-run",
        action="store_true",
        help="N'ecrit rien ; affiche le rapport qui serait ecrit.",
    )
    arguments = analyseur.parse_args(argv)

    rapport = executer_comparaison()
    texte = formater_texte(rapport)
    print(texte)

    contenu_json = json.dumps(rapport, indent=2, ensure_ascii=False)
    if arguments.dry_run:
        print(f"\n[dry-run] N'ecrit rien. Rapport qui serait ecrit dans {arguments.sortie} :")
        print(contenu_json)
        return 0

    arguments.sortie.write_text(contenu_json, encoding="utf-8")
    print(f"\nRapport JSON ecrit dans {arguments.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
