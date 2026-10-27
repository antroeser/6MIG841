"""
voice_turtle.py - Devoir 2 : ANCIENNE FORME, un seul programme (plan02.md).

Depuis plan02, le Devoir 2 se lance par `stDev2.bat`, qui invoque
`devoir2.launch.py` et demarre SIX noeuds ROS2 independants (voice_input,
llm_node, dialogue_manager, voice_output, motion_node, turtlesim), relies par
les trois modes de communication de ROS2 (topic, service, action). Ce fichier
n'est PLUS le chemin de lancement du devoir : il reste pour deux raisons
seulement.

  1. Ses tests hors ligne (Devoir2/test/test_boucle.py, 48 cas au total avec
     les autres suites du Devoir 2) prouvent la logique de dialogue que les
     cinq noeuds ROS2 REUTILISENT SANS MODIFICATION (state_machine.py,
     llm_interpreter.py, voice.py). Les faire disparaitre ferait disparaitre
     cette preuve.
  2. Il documente, en un seul fichier lineaire, la meme boucle que les noeuds
     executent maintenant repartie entre plusieurs processus : LIRE L'ETAT,
     faire l'entree-sortie qui correspond, POUSSER L'EVENEMENT.

Assemble les quatre morceaux du devoir :

    voice.py          -> ce que l'utilisateur dit
    state_machine.py  -> ou en est le dialogue
    llm_interpreter.py-> ce que la phrase veut dire
    ihr_ros.turtle_io -> ce que la tortue fait

Aucune decision n'est prise ici, elles sont toutes dans `state_machine`, ce qui
rend le dialogue entierement testable sans micro, sans Ollama et sans ROS2.

Usage (tests et demonstration hors ligne uniquement ; pour le devoir, utiliser
stDev2.bat) :
    python Devoir2/code/voice_turtle.py
    python Devoir2/code/voice_turtle.py --input clavier
    python Devoir2/code/voice_turtle.py --input script --phrases "avance" "oui" "oui" "quitter"
    python Devoir2/code/voice_turtle.py --backend sim --no-window --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ihr_ros import config  # noqa: E402
from ihr_ros.turtle_io import open_turtle  # noqa: E402

from history import Historique  # noqa: E402
from llm_interpreter import LlmInterpreter  # noqa: E402
from state_machine import Etat, MachineDialogue  # noqa: E402
from voice import SortieVocale, ouvrir_entree  # noqa: E402


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


def executer_action(turtle, action, settings: dict[str, Any],
                    sleep=time.sleep) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Envoyer l'action a la tortue pendant toute sa duree, puis l'immobiliser.

        C'est le correctif le plus visible par rapport aux rendus etudiants. Ils
        publiaient UN SEUL message Twist et passaient a la suite. Or turtlesim
        oublie sa derniere consigne au bout d'une seconde sans nouveau message :
        la tortue avancait donc un instant puis s'arretait seule, ce que plusieurs
        rapports decrivent comme un mouvement "trop court". Ici, la consigne est
        republiee a `command_period_s` pendant `duree_s`, puis une consigne nulle
        est envoyee pour arreter proprement.

    Inputs:
        turtle (TurtleClient): facade de commande
        action (Action): mouvement a executer
        settings (dict): section devoir2 de la configuration
        sleep (callable): fonction d'attente, injectee pour les tests

    Outputs:
        messages (int): nombre de messages Twist publies, arret compris
    --------------------------------------------------------------------------
    """
    periode = float(settings["command_period_s"])
    if periode <= 0:
        raise ValueError(
            f"command_period_s vaut {periode}. Une periode nulle ou negative "
            "publierait indefiniment sans jamais avancer dans le temps."
        )

    publies = 0
    ecoule = 0.0
    while ecoule < action.duree_s:
        turtle.drive(linear=action.linear, angular=action.angular)
        turtle.spin_once(0.0)
        publies += 1
        sleep(periode)
        ecoule += periode

    turtle.stop()
    turtle.spin_once(0.0)
    return publies + 1


def boucle(machine: MachineDialogue,
           entree,
           voix: SortieVocale,
           interprete: LlmInterpreter,
           turtle,
           settings: dict[str, Any],
           max_tours: int = 0,
           sleep=time.sleep) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Derouler le dialogue jusqu'a l'arret. Lire l'etat, faire l'entree-sortie,
        pousser l'evenement.

    Inputs:
        machine (MachineDialogue): machine d'etat du dialogue
        entree (EntreeVocale): source des phrases
        voix (SortieVocale): sortie parlee et affichee
        interprete (LlmInterpreter): traducteur phrase -> action
        turtle (TurtleClient): facade de commande de la tortue
        settings (dict): section devoir2 de la configuration
        max_tours (int): borne de securite, 0 pour illimite
        sleep (callable): fonction d'attente, injectee pour les tests

    Outputs:
        resume (dict): tours effectues, actions executees, etat final
    --------------------------------------------------------------------------
    """
    tours = 0
    executees: list[str] = []
    echecs: list[str] = []
    historique = Historique(int(settings["historique_tours"]))

    while machine.etat is not Etat.ARRET:
        tours += 1
        if max_tours and tours > max_tours:
            machine.arreter("Limite de sécurité atteinte. Arrêt de la session.")
            break

        # Rafraichir la fenetre du substitut a chaque tour. Sans cela, elle
        # n'est dessinee que pendant l'EXECUTION, puisque c'est le seul etat
        # qui appelle spin_once, et l'utilisateur ne voit aucune tortue tant
        # qu'il n'a pas reussi a faire executer une commande.
        turtle.spin_once(0.0)

        etat = machine.etat

        if etat is Etat.ECOUTE:
            transition = machine.entendu(entree.ecouter("Commande ?"))

        elif etat in (Etat.CONFIRMATION_COMMANDE, Etat.CONFIRMATION_ACTION):
            transition = machine.repondu(entree.ecouter("oui ou non ?"))

        elif etat is Etat.INTERPRETATION:
            commande_courante = machine.commande
            resultat = interprete.interpreter(commande_courante,
                                              historique=historique.formater())
            if resultat.ok:
                noms_plan = " puis ".join(a.nom for a in resultat.plan.etapes)
                historique.ajouter(commande_courante, noms_plan)
                transition = machine.interprete(resultat.plan)
            else:
                echecs.append(resultat.erreur)
                transition = machine.echec_interpretation(resultat.erreur)

        elif etat is Etat.EXECUTION:
            plan = machine.plan
            total_publies = 0
            for action in plan.etapes:
                total_publies += executer_action(turtle, action, settings, sleep=sleep)
                executees.append(action.nom)
            noms_executes = " puis ".join(a.nom for a in plan.etapes)
            voix.dire(f"{noms_executes} envoyee(s), {total_publies} messages publies.")
            transition = machine.execute()

        else:  # pragma: no cover - ARRET est la condition de sortie de la boucle
            break

        if transition.message:
            voix.dire(transition.message)

    return {
        "tours": tours,
        "actions_executees": executees,
        "echecs_interpretation": echecs,
        "etat_final": machine.etat.value,
        "historique": [(a.value, b.value, m) for a, b, m in machine.historique],
    }


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    parser = argparse.ArgumentParser(
        description="Devoir 2 - commander la tortue a la voix via une LLM."
    )
    parser.add_argument("--input", default=None,
                        choices=["micro", "clavier", "script", "auto"],
                        help="source des phrases (defaut : celle de ihr_config.json)")
    parser.add_argument("--phrases", nargs="*", default=None,
                        help="phrases du mode script, dans l'ordre")
    parser.add_argument("--backend", default=None, choices=["ros2", "sim", "auto"],
                        help="dorsale de commande de la tortue")
    parser.add_argument("--no-window", action="store_true",
                        help="ne pas ouvrir la fenetre du substitut")
    parser.add_argument("--no-voice", action="store_true",
                        help="desactiver la synthese vocale")
    parser.add_argument("--max-tours", type=int, default=0,
                        help="borne de securite sur le nombre de tours (0 = illimite)")
    parser.add_argument("--json", action="store_true",
                        help="imprimer le resume final en JSON")
    args = parser.parse_args(argv)

    settings = config.section("devoir2")
    mode = args.input or str(settings.get("input_mode", "auto"))

    print("=" * 62)
    print(" Devoir 2 - commande vocale de la tortue via une LLM")
    print("=" * 62)

    entree = ouvrir_entree(mode, settings, args.phrases)
    voix = SortieVocale(actif=not args.no_voice,
                        reglages=settings.get("synthese_vocale", {}))
    if not voix.disponible and voix.raison:
        print(f"[robot] {voix.raison}", file=sys.stderr)
    elif voix.disponible:
        print(f"[robot] voix : {voix.description}")

    interprete = LlmInterpreter(settings)
    machine = MachineDialogue(
        mots_accord=settings["affirmative_words"],
        mots_refus=settings["negative_words"],
        mots_sortie=settings["quit_words"],
    )

    turtle = open_turtle(args.backend, node_name="devoir2_voice_turtle",
                         with_window=not args.no_window)
    print(f"Modele LLM : {settings['llm_model']}   entree : {entree.name}")
    print("Dites une commande, puis confirmez. Dites « quitter » pour sortir.\n")

    try:
        resume = boucle(machine, entree, voix, interprete, turtle,
                        settings, max_tours=args.max_tours)
    finally:
        turtle.close()
        entree.close()
        voix.close()

    if args.json:
        print(json.dumps(resume, indent=2, ensure_ascii=False))
    else:
        print(f"\n{resume['tours']} tours, actions executees : "
              f"{', '.join(resume['actions_executees']) or 'aucune'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
