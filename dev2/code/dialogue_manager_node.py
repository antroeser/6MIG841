"""
dialogue_manager_node.py - Devoir 2, noeud ROS2 : chef d'orchestre du dialogue.

Porte la machine d'etat (state_machine.MachineDialogue, reutilisee SANS
MODIFICATION), appelle le service Interpret et commande l'action ExecutePlan
(plan02.md, tableau des responsabilites). Ce noeud NE PARLE PAS au microphone :
il recoit la transcription par topic et publie ce qu'il faut dire par un autre
topic.

Piege 2 (plan02.md). Un appel de service SYNCHRONE (spin_until_future_complete)
depuis un rappel se bloque DEFINITIVEMENT : la reponse arrive sur le meme
executeur, deja occupe a executer ce rappel. Cette faute ne produit AUCUN
message, le noeud se tait, et on la cherche ailleurs. Le remede, applique
PARTOUT dans ce fichier : `call_async` / `send_goal_async`, chacun suivi d'un
rappel pose sur le futur avec `add_done_callback`. Aucune attente bloquante
sur un futur n'apparait ici (verifie par lecture de la source, plan02.md,
tableau des tests).

Le sens par booleen, applique (plan04, amelioration A). `Step.msg` est FIGE et NON
SIGNE : le sens passe par `is_forward` / `is_clockwise`. Jusqu'a plan04, ce noeud les
DERIVAIT du nom de l'action, lu dans le catalogue a cinq entrees de la configuration
(devoir2.actions) ; ce n'etait plus possible une fois `tourner_gauche` et
`tourner_droite` fusionnes en une seule entree `tourner`, puisque le nom seul ne
distingue plus la direction. `step_depuis_action` lit desormais ces deux booleens
DIRECTEMENT sur l'`Action` recue (le champ que `state_machine.Action` porte depuis
plan04), jamais redevines depuis un nom ou une valeur numerique de configuration.

L'historique (plan04, amelioration B). Le noeud tient un `history.Historique` borne
(devoir2.historique_tours) et transmet sa forme brute au champ `historique` du service
`Interpret` (`string[]`, fige depuis plan01), pour que llm_node le mette en forme dans
l'invite.

La sequence (plan04, amelioration C). `MachineDialogue.action` est devenu
`MachineDialogue.plan` ; ce noeud reconstruit desormais un `Plan` a partir de TOUTES les
etapes de `Interpret.Response.etapes`, pas seulement la premiere, et envoie un but
`ExecutePlan` portant une `Step` par etape du plan.

Un arbitre, ou aucun (plan07.md, « Qui commande la tortue, et pourquoi un seul »).
Dans le Projet, `arbiter_node` devient le SEUL client de l'action ExecutePlan : ce
noeud ne commande plus directement la tortue, il PUBLIE son intention sur le topic
`topics.voice_intent_topic`, et l'arbitre decide. C'est un changement du noeud PRIS
COMME UNITE (ruling de l'orchestrateur, plan07.md), jamais une reecriture de la
machine d'etat ni du catalogue d'actions, tous deux repris SANS MODIFICATION.

Le parametre ROS2 booleen `avec_arbitre` (faux par defaut) decide la branche, un SEUL
if dans `_demarrer_execution` : faux, le Devoir 2 lance SEUL garde le chemin direct
existant (send_goal_async), sans quoi il cesserait de bouger ; vrai (pose par
`projet.launch.py`), ce noeud publie et laisse l'arbitre executer. Ce n'est PAS un
reglage de securite : la priorite de l'arret d'urgence n'est jamais dans ce
parametre, elle vit entierement dans `arbiter.Arbitre` (PRIORITE_ARRET_URGENCE),
inchangee par ce plan.

Simplification assumee et documentee (R8) : `arbiter.Commande` ne porte qu'une seule
consigne de vitesse a la fois, la ou un `Plan` confirme peut porter PLUSIEURS etapes
(plan04, amelioration C). En mode avec_arbitre, seule la PREMIERE etape du plan est
donc publiee comme intention ; c'est fidele au cas le plus frequent (une commande
vocale simple) mais une sequence vocale composee n'est, dans ce mode, honoree que
pour sa premiere etape. Documente ici plutot que traite en silence.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rclpy  # noqa: E402
from rclpy.action import ActionClient  # noqa: E402
from rclpy.node import Node  # noqa: E402
from std_msgs.msg import Bool, String  # noqa: E402

from ihr_6mig841_interfaces.action import ExecutePlan  # noqa: E402
from ihr_6mig841_interfaces.msg import Commande, Step  # noqa: E402
from ihr_6mig841_interfaces.srv import Interpret  # noqa: E402

from ihr_ros import config  # noqa: E402

from history import Historique  # noqa: E402
from state_machine import Action, Etat, MachineDialogue, Plan, action_depuis_config  # noqa: E402


def step_depuis_action(action: Action, actions_cfg: dict[str, Any]) -> Any:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire un Step ROS2 a partir d'une Action de state_machine. Depuis
        plan04, `is_forward` et `is_clockwise` sont LUS DIRECTEMENT sur
        l'Action recue : le catalogue fusionne (devoir2.actions) ne distingue
        plus 'tourner a gauche' de 'tourner a droite' par le nom, donc la seule
        source fiable du sens est desormais le booleen que la machine d'etat
        porte deja, jamais une redevination depuis un nom ou une valeur
        numerique de configuration.

        distance_m et angle_deg restent a 0.0 : la cinematique reelle (profil
        de vitesse, distance parcourue) est le sujet de plan05, qui n'est pas
        anticipe ici. motion_node continue de retrouver la vitesse et la
        duree de l'etape par son nom, via action_depuis_config.

    Inputs:
        action (Action): action confirmee par l'utilisateur
        actions_cfg (dict): section devoir2.actions de la configuration

    Outputs:
        step (Step): message ROS2 pret a etre envoye a motion_node
    --------------------------------------------------------------------------
    """
    if action.nom not in actions_cfg:
        raise KeyError(
            f"Action '{action.nom}' absente du catalogue devoir2.actions : "
            f"{sorted(actions_cfg)}."
        )
    step = Step()
    step.nom_action = action.nom
    step.distance_m = 0.0
    step.angle_deg = 0.0
    step.is_forward = bool(action.is_forward)
    step.is_clockwise = bool(action.is_clockwise)
    return step


class DialogueManagerNode(Node):
    """Chef d'orchestre : machine d'etat, service Interpret, action ExecutePlan."""

    def __init__(self, settings: dict[str, Any] | None = None,
                 topics: dict[str, Any] | None = None,
                 client_interpret: Any | None = None,
                 client_execute: Any | None = None,
                 pub_speak: Any | None = None,
                 avec_arbitre: bool | None = None,
                 pub_intention: Any | None = None,
                 horloge: Any = time.monotonic,
                 context: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire le noeud. Les clients de service et d'action, l'editeur
            de parole et l'editeur d'intention sont injectables pour les tests
            hors ligne : aucun serveur Interpret ni ExecutePlan reel, et aucun
            arbiter_node reel, n'est requis pour prouver le branchement de la
            machine d'etat sur une transcription.

        Inputs:
            settings (dict | None): section 'devoir2' de la configuration
            topics (dict | None): section 'topics' de la configuration
            client_interpret (Any | None): client du service Interpret
            client_execute (Any | None): client de l'action ExecutePlan (chemin
                direct, utilise seulement si avec_arbitre est faux)
            pub_speak (Any | None): editeur du topic 'speak'
            avec_arbitre (bool | None): force la branche (tests) ; lu sur le
                parametre ROS2 'avec_arbitre' si absent (chemin de production,
                pose par projet.launch.py, faux par defaut : plan07.md)
            pub_intention (Any | None): editeur du topic 'voice_intent_topic',
                utilise seulement si avec_arbitre est vrai
            horloge (callable): source de temps pour l'instant de l'intention
                publiee, injectee pour les tests (workflow.md, determinisme)
            context (Any | None): contexte rclpy, celui par defaut si absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        super().__init__("dialogue_manager", context=context)
        self._settings = settings if settings is not None else config.section("devoir2")
        self._topics = topics if topics is not None else config.section("topics")
        self._actions_cfg = self._settings["actions"]
        self._bornes_cfg = self._settings.get("bornes")
        self._historique = Historique(int(self._settings["historique_tours"]))
        self._horloge = horloge

        self._machine = MachineDialogue(
            mots_accord=self._settings["affirmative_words"],
            mots_refus=self._settings["negative_words"],
            mots_sortie=self._settings["quit_words"],
        )
        self._dernier_etat_affiche: Etat | None = None

        profondeur = int(self._topics["queue_depth"])
        self._sub_transcription = self.create_subscription(
            String, str(self._topics["transcription_topic"]),
            self._on_transcription, profondeur,
        )
        self._pub_speak = pub_speak if pub_speak is not None else self.create_publisher(
            String, str(self._topics["speak_topic"]), profondeur,
        )
        self._client_interpret = (
            client_interpret if client_interpret is not None
            else self.create_client(Interpret, str(self._topics["interpret_service"]))
        )
        self._client_execute = (
            client_execute if client_execute is not None
            else ActionClient(self, ExecutePlan, str(self._topics["execute_action"]))
        )

        self.declare_parameter("avec_arbitre", False)
        self._avec_arbitre = (
            bool(avec_arbitre) if avec_arbitre is not None
            else bool(self.get_parameter("avec_arbitre").get_parameter_value().bool_value)
        )
        self._pub_intention = (
            pub_intention if pub_intention is not None
            else self.create_publisher(
                Commande, str(self._topics["voice_intent_topic"]), profondeur,
            )
        )

        self._pub_ecoute = self.create_publisher(
            Bool, str(self._topics["ecoute_active_topic"]), profondeur,
        )
        self._publier_porte_ecoute()

    def _publier_porte_ecoute(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Dire si le dialogue ATTEND une phrase. Le micro n'ecoute que dans les
            trois etats qui en attendent une ; pendant INTERPRETATION et EXECUTION
            il se tait, sans quoi il redemande 'Commande ?' pendant que la tortue
            bouge. C'est la machine d'etat qui commande l'ecoute, pas l'inverse.

        Inputs:
            aucun

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        ouverte = self._machine.etat in (
            Etat.ECOUTE, Etat.CONFIRMATION_COMMANDE, Etat.CONFIRMATION_ACTION,
        )
        message = Bool()
        message.data = bool(ouverte)
        self._pub_ecoute.publish(message)

    @property
    def machine(self) -> MachineDialogue:
        """Etat courant du dialogue, lu par les tests et par le diagnostic."""
        return self._machine

    # ------------------------------------------------------------- transcription

    def _on_transcription(self, message: Any) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Pousser l'evenement qui correspond a l'etat courant : 'entendu' en
            ECOUTE, 'repondu' dans les deux etats de confirmation. Une
            transcription recue hors de ces etats (par exemple pendant
            INTERPRETATION, en attente de la reponse du service) est IGNOREE :
            la machine ne l'attend pas encore.

        Inputs:
            message (std_msgs.msg.String): phrase transcrite

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        texte = message.data
        etat = self._machine.etat

        if etat is Etat.ECOUTE:
            transition = self._machine.entendu(texte)
        elif etat in (Etat.CONFIRMATION_COMMANDE, Etat.CONFIRMATION_ACTION):
            transition = self._machine.repondu(texte)
        else:
            return

        self._annoncer(transition)

        self._publier_porte_ecoute()

        if self._machine.etat is Etat.INTERPRETATION:
            self._demarrer_interpretation()
        elif self._machine.etat is Etat.EXECUTION:
            self._demarrer_execution()

    # ------------------------------------------------------------- interpretation (piege 2)

    def _demarrer_interpretation(self) -> None:
        """
        Appel ASYNCHRONE du service Interpret. Aucune attente bloquante ici.

        L'historique transmis (plan04, amelioration B) est la forme BRUTE que
        `Historique.rendre()` expose, prete pour le champ `string[]` du service ;
        c'est llm_node qui la met en forme dans l'invite (history.formater_lignes).
        """
        requete = Interpret.Request()
        requete.commande = self._machine.commande
        requete.historique = list(self._historique.rendre())
        futur = self._client_interpret.call_async(requete)
        futur.add_done_callback(self._sur_reponse_interpretation)

    def _sur_reponse_interpretation(self, futur: Any) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Traiter la reponse du service, arrivee de facon asynchrone (le
            futur est deja complete quand ce rappel est appele). Reconstruit un
            Plan a partir de TOUTES les etapes rendues (plan04, amelioration C :
            une commande composee en rend plusieurs), en lisant sur chaque Step
            les grandeurs et les booleens de sens deja decides par llm_node,
            jamais redevines ici. Pousse 'interprete' si le plan est valide,
            sinon 'echec_interpretation'.

        Inputs:
            futur (rclpy.task.Future): futur du service, deja complete

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        reponse = futur.result()
        if not reponse.succes or not reponse.etapes:
            transition = self._machine.echec_interpretation(
                reponse.erreur or "aucune etape rendue"
            )
            self._annoncer(transition)
            self._publier_porte_ecoute()
            return

        commande_traitee = self._machine.commande
        try:
            etapes = tuple(
                action_depuis_config(
                    step.nom_action, self._actions_cfg,
                    params={
                        "distance_m": step.distance_m,
                        "angle_deg": step.angle_deg,
                        "is_forward": step.is_forward,
                        "is_clockwise": step.is_clockwise,
                    },
                    bornes=self._bornes_cfg,
                )
                for step in reponse.etapes
            )
            plan = Plan(etapes)
        except (KeyError, ValueError) as exc:
            transition = self._machine.echec_interpretation(str(exc))
            self._annoncer(transition)
            self._publier_porte_ecoute()
            return

        self._historique.ajouter(commande_traitee,
                                 " puis ".join(etape.nom for etape in plan.etapes))
        transition = self._machine.interprete(plan)
        self._annoncer(transition)
        # La confirmation du plan est une nouvelle phase d'ecoute : le micro
        # etait ferme pendant l'appel LLM et doit etre rouvert pour recevoir oui/non.
        self._publier_porte_ecoute()

    # ------------------------------------------------------------- execution (piege 2)

    def _demarrer_execution(self) -> None:
        """
        Un seul branchement (plan07.md, « Qui commande la tortue ») : avec un
        arbitre present, PUBLIER l'intention et rendre la main tout de suite ;
        sans arbitre, garder le chemin direct existant (envoi ASYNCHRONE du but
        ExecutePlan, aucune attente bloquante ici).

        Une Step par etape du Plan confirme (plan04, amelioration C) : une commande
        composee envoie donc plusieurs etapes dans le meme but, motion_node les
        executant dans l'ordre avec un arret franc entre deux (plan02.md, etape 8).
        """
        if self._avec_arbitre:
            self._publier_intention()
            transition = self._machine.execute()
            self._annoncer(transition)
            return

        but = ExecutePlan.Goal()
        but.etapes = [step_depuis_action(etape, self._actions_cfg)
                     for etape in self._machine.plan.etapes]
        futur = self._client_execute.send_goal_async(but)
        futur.add_done_callback(self._sur_acceptation_but)

    def _publier_intention(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Publier l'intention vocale confirmee pour que l'arbitre du Projet
            decide (plan07.md). Ce noeud ne sait pas, et n'a pas a savoir, si
            l'arbitre retiendra cette intention : une modalite plus prioritaire
            et fraiche (le geste) peut l'ecarter, exactement comme geste et objet
            peuvent l'ecarter l'un l'autre (arbiter.Arbitre, inchange).

            Simplification assumee (voir en-tete du module) : seule la PREMIERE
            etape du plan confirme est publiee, arbiter.Commande ne portant
            qu'une seule consigne de vitesse a la fois.

        Inputs:
            aucun (lit self._machine.plan, deja confirme par l'appelant)

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        premiere = self._machine.plan.etapes[0]
        message = Commande()
        message.modalite = "voix"
        message.linear_x = float(premiere.linear)
        message.angular_z = float(premiere.angular)
        message.instant = float(self._horloge())
        message.motif = f"commande vocale « {premiere.nom} »"
        message.urgence = False
        self._pub_intention.publish(message)

    def _sur_acceptation_but(self, futur: Any) -> None:
        """Le serveur d'action a accepte ou refuse le but. Aucune attente bloquante ici."""
        goal_handle = futur.result()
        if goal_handle is None or not getattr(goal_handle, "accepted", True):
            transition = self._machine.echec_execution("but ExecutePlan refuse")
            self._annoncer(transition)
            self._publier_porte_ecoute()
            return
        futur_resultat = goal_handle.get_result_async()
        futur_resultat.add_done_callback(self._sur_resultat_execution)

    def _sur_resultat_execution(self, futur: Any) -> None:
        """Le mouvement est termine (ou annule). Aucune attente bloquante ici."""
        resultat = futur.result().result
        transition = self._machine.execute()
        self._publier_porte_ecoute()
        if resultat.succes:
            self._annoncer(transition)
        else:
            # `raison_arret` est technique et non accentue -- par exemple
            # « collision prevue a t=0.52s, position=(5.55, 6.57) ». Prononce, cela
            # donne une suite de chiffres et de parentheses. Il part donc au journal,
            # et l'oreille recoit une phrase francaise (defaut signale par
            # l'enseignant le 2026-09-20).
            self._annoncer(Transition(
                transition.etat,
                "Mouvement interrompu avant la fin. Commande suivante.",
                detail=str(resultat.raison_arret),
            ))

    # ------------------------------------------------------------------- parole

    def _annoncer(self, transition: Any) -> None:
        """
        Prononcer le message d'une transition, et JOURNALISER son detail technique.

        Separation introduite le 2026-09-20 : `Transition.message` est ecrit pour
        l'oreille, en francais accentue ; `Transition.detail` porte la cause exacte,
        qui contient souvent la reponse brute du modele (du JSON) et ne s'ecoute pas.
        """
        if transition.etat is not self._dernier_etat_affiche:
            self.get_logger().info(f"[etat] {transition.etat.value}")
            self._dernier_etat_affiche = transition.etat
        self._parler(transition.message, detail=getattr(transition, "detail", ""))

    def _parler(self, texte: str, detail: str = "") -> None:
        """Publier un message a dire, ou rien si le message est vide."""
        if detail:
            self.get_logger().info(f"[dialogue] detail : {detail}")
        if not texte:
            return
        message = String()
        message.data = texte
        self._pub_speak.publish(message)


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree du noeud.

    Inputs:
        argv (list[str] | None): arguments rclpy, ceux de la ligne de commande
            si absents

    Outputs:
        code (int): code de sortie du processus
    --------------------------------------------------------------------------
    """
    rclpy.init(args=argv)
    node = DialogueManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
