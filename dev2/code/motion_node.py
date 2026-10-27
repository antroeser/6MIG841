"""
motion_node.py - Devoir 2, noeud ROS2 : serveur d'action ExecutePlan.

Execute un plan de mouvement (Step[]) en pilotant la tortue via
`ihr_ros.turtle_io` (le SEUL chemin vers le robot, enonce.md). N'INTERPRETE
RIEN (plan02.md, tableau des responsabilites) : le nom de chaque etape est
cherche tel quel dans le catalogue devoir2.actions de la configuration
(state_machine.action_depuis_config, reutilise SANS MODIFICATION) pour
retrouver sa vitesse et sa duree.

Cinematique (plan05.md). `dialogue_manager_node.step_depuis_action` remet
toujours `distance_m`/`angle_deg` a 0.0 sur le `Step` envoye (limite non
touchee par ce plan, qui ne modifie pas ce fichier) : la grandeur reellement
parcourue par chaque etape reste donc celle que `action_depuis_config` retrouve
par le NOM de l'action dans `devoir2.actions` (sa colonne `distance_m` /
`angle_deg`, la grandeur PAR DEFAUT de cette action). C'est cette grandeur,
combinee a `action.duree_s` et a la section `cinematique` de la configuration
(acceleration_max, vitesse_lineaire_max, vitesse_angulaire_max), que
`construire_profils` transforme en deux profils trapezoidaux simultanes
(trajectory.calculer_profil) : la consigne CONSTANTE d'avant plan05 disparait,
remplacee par une consigne qui rampe, evaluee a l'instant courant a chaque
periode de publication (`cinematique.periode_publication_s`).

La lecon du plan (plan05.md) : le Lab 1 prouve qu'un SEGMENT est libre, mais
l'ARC reellement parcouru par ces deux profils simultanes peut entrer dans un
obstacle que ce segment evitait. `verifier_etape_libre` echantillonne cet arc
(arcs.echantillonner_arc) et gele l'execution de l'etape des qu'une collision
est trouvee, plutot que d'executer un mouvement dont on sait deja qu'il
heurte. `obstacle` est injecte au constructeur, jamais lu d'un etat global
(arcs.py).

Obstacle de production (decision de l'enseignant, 2026-09-19,
.sdd/6mig841-ameliorations/obstacle-devoir2-report.md) : jusqu'ici le Devoir 2
n'en declarait aucun (ni devoir2.launch.py, ni ihr_config.json), si bien que ce
mecanisme n'etait jamais exerce qu'en test. `main()` lit desormais
devoir2.obstacle et le convertit via `obstacle_config.obstacle_depuis_config`
(cellule de la grille de planification du Lab 1, convertie en unites turtlesim
par Lab1/code/planif/world.py) avant de construire le noeud : la tortue refuse
donc reellement une trajectoire qui heurte cet obstacle fixe, une seconde
tortue immobile engendree par devoir2.launch.py a la meme position. `obstacle`
reste injectable au constructeur pour les tests (ce chemin n'a pas change).

Piege 3 (plan02.md). Annuler un but n'arrete PAS la tortue toute seule :
l'annulation fait sortir le serveur de sa boucle, mais turtlesim garde sa
derniere consigne une seconde de plus. Le remede, dans `executer_etape` : une
consigne NULLE est TOUJOURS publiee avant de rendre la main, que l'etape se
soit terminee normalement ou par annulation.

Arret franc entre deux etapes (plan02.md, etape 8). Sans lui, enchainer une
avance et une rotation decrit un ARC plutot que les deux mouvements demandes,
la vitesse lineaire et la vitesse angulaire restant simultanement non nulles
pendant la transition. Une consigne nulle est donc publiee ENTRE deux etapes
du plan, jamais seulement a la toute fin.
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rclpy  # noqa: E402
from rclpy.action import ActionServer, CancelResponse, GoalResponse  # noqa: E402
from rclpy.callback_groups import ReentrantCallbackGroup  # noqa: E402
from rclpy.executors import MultiThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402

from ihr_6mig841_interfaces.action import ExecutePlan  # noqa: E402

from ihr_ros import config  # noqa: E402
from ihr_ros.turtle_io import open_turtle  # noqa: E402

import arcs  # noqa: E402
import trajectory  # noqa: E402
from obstacle_config import obstacle_depuis_config  # noqa: E402
from state_machine import Action, action_depuis_config, signer  # noqa: E402


def construire_profils(action: Action,
                       cinematique: dict[str, Any]) -> tuple[trajectory.ProfilTrapeze,
                                                              trajectory.ProfilTrapeze]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire les profils trapezoidaux lineaire et angulaire d'une
        etape : la magnitude (non signee) vient de `action.distance_m` /
        `action.angle_deg` (converti en radians), le temps alloue de
        `action.duree_s`, et les bornes physiques de la section 'cinematique'
        de la configuration. Vitesse et acceleration en sont les RESULTATS
        (plan05.md), jamais des entrees choisies ici.

    Inputs:
        action (Action): etape a executer
        cinematique (dict): section 'cinematique' de la configuration

    Outputs:
        (profil_lineaire, profil_angulaire) (tuple[ProfilTrapeze, ProfilTrapeze]):
            un profil par axe, magnitudes non signees
    --------------------------------------------------------------------------
    """
    acceleration_max = float(cinematique["acceleration_max"])
    distance = abs(float(action.distance_m))
    angle_rad = abs(math.radians(float(action.angle_deg)))

    profil_lineaire = trajectory.calculer_profil(
        distance, action.duree_s, acceleration_max,
        float(cinematique["vitesse_lineaire_max"]),
    )
    profil_angulaire = trajectory.calculer_profil(
        angle_rad, action.duree_s, acceleration_max,
        float(cinematique["vitesse_angulaire_max"]),
    )
    return profil_lineaire, profil_angulaire


def _params_depuis_step(step: Any) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire le `params` de `action_depuis_config` a partir d'un `Step`
        ROS2 reellement recu, plutot que de le jeter (defaut critique mesure
        le 2026-09-19 : `_executer` appelait `action_depuis_config` sans
        `params`, si bien que seul le NOM de l'action survivait et que 'tourne
        a droite' comme 'tourne a gauche' executaient le meme mouvement).
        `is_forward` et `is_clockwise` sont TOUJOURS transmis : ce sont des
        booleens reels, jamais un signal d'absence. `distance_m` et
        `angle_deg` ne le sont que s'ils sont NON NULS : `Step.msg` n'a pas de
        valeur « absente », et `dialogue_manager_node.step_depuis_action`
        pose actuellement 0.0 pour dire « aucune grandeur precisee, utiliser
        celle du catalogue » (voir l'en-tete de ce module) ; transmettre 0.0
        comme une vraie valeur ramenerait chaque 'avancer'/'tourner' de
        production a un deplacement nul des que ce noeud tourne en
        production, ce qui serait un defaut pire que celui corrige ici.

    Inputs:
        step (Any): Step.msg recu (nom_action, distance_m, angle_deg,
            is_forward, is_clockwise)

    Outputs:
        params (dict): pret pour `action_depuis_config(..., params=params)`
    --------------------------------------------------------------------------
    """
    params: dict[str, Any] = {
        "is_forward": bool(step.is_forward),
        "is_clockwise": bool(step.is_clockwise),
    }
    if step.distance_m:
        params["distance_m"] = step.distance_m
    if step.angle_deg:
        params["angle_deg"] = step.angle_deg
    return params


def verifier_etape_libre(pose_depart: tuple[float, float, float], action: Action,
                         cinematique: dict[str, Any],
                         obstacle: arcs.Obstacle | None = None) -> arcs.ResultatArc:
    """
    --------------------------------------------------------------------------
    Purpose:
        Echantillonner l'arc reellement parcouru par `action` depuis
        `pose_depart` et signaler la PREMIERE collision avec `obstacle` s'il y
        en a une (plan05.md, « la lecon que ce plan porte ») : le SEGMENT que
        Theta* validerait peut etre libre alors que l'ARC, lui, heurte.
        `obstacle` est toujours un argument, jamais un etat global (arcs.py).

    Inputs:
        pose_depart (tuple): (x, y, theta) de la tortue au debut de l'etape
        action (Action): etape a verifier
        cinematique (dict): section 'cinematique' de la configuration
        obstacle (arcs.Obstacle | None): obstacle a tester, aucune collision
            possible si absent (le Devoir 2 en declare desormais un par defaut
            en production, voir devoir2.obstacle et obstacle_config.py ; None
            reste la valeur qui desactive le mecanisme, pour les tests)

    Outputs:
        resultat (arcs.ResultatArc): echantillons et premiere collision eventuelle
    --------------------------------------------------------------------------
    """
    profil_lineaire, profil_angulaire = construire_profils(action, cinematique)
    sens_lineaire, sens_angulaire = signer(1.0, 1.0, action.is_forward, action.is_clockwise)

    return arcs.echantillonner_arc(
        pose_depart=pose_depart,
        profil_lineaire=profil_lineaire, sens_lineaire=sens_lineaire,
        profil_angulaire=profil_angulaire, sens_angulaire=sens_angulaire,
        duree_etape=action.duree_s,
        resolution_s=float(cinematique["resolution_echantillonnage_s"]),
        obstacle=obstacle, tolerance_collision=float(cinematique["tolerance_collision"]),
    )


def executer_etape(turtle: Any, action: Action, cinematique: dict[str, Any] | None = None,
                    doit_annuler: Callable[[], bool] = lambda: False,
                    sur_avancement: Callable[[float], None] | None = None,
                    sleep: Callable[[float], None] = time.sleep) -> tuple[int, bool]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Executer une etape en republiant, a periode_publication_s, la
        consigne de vitesse evaluee a l'instant courant sur les deux profils
        trapezoidaux de l'etape (construire_profils), puis publier une
        consigne nulle. La consigne CONSTANTE d'avant plan05 a disparu : le
        depart et l'arret sont desormais progressifs. S'arrete PLUS TOT si
        doit_annuler() devient vrai a un tour de boucle, sans jamais omettre
        la consigne nulle finale (piege 3, inchange par plan05).

        Fonction volontairement PURE dans ses dependances (turtle, sleep,
        doit_annuler, sur_avancement sont tous injectes), pour rester testable
        hors ligne sans ActionServer ni goal_handle reels : c'est exactement
        ce que demandent les tests « plus d'un Twist par etape » et
        « l'annulation arrete la tortue » (plan02.md, tableau des tests),
        remis a niveau par plan05 pour la nouvelle signature.

    Inputs:
        turtle (TurtleClient): facade de commande de la tortue (drive/stop/spin_once)
        action (Action): mouvement a executer
        cinematique (dict | None): section 'cinematique' de la configuration,
            relue depuis ihr_ros.config si absente
        doit_annuler (callable): rendu vrai des qu'une annulation est demandee
        sur_avancement (callable | None): appele avec le temps ECOULE dans
            cette etape (secondes), apres chaque consigne de mouvement
            publiee (pas apres la consigne d'arret finale)
        sleep (callable): fonction d'attente, injectee pour les tests

    Outputs:
        publies (int): nombre de messages Twist publies, arret final compris
        annulee (bool): vrai si l'etape a ete interrompue par une annulation
    --------------------------------------------------------------------------
    """
    if cinematique is None:
        cinematique = config.section("cinematique")

    periode = float(cinematique["periode_publication_s"])
    if periode <= 0:
        raise ValueError(
            f"periode_publication_s vaut {periode}. Une periode nulle ou "
            "negative publierait indefiniment sans jamais avancer dans le temps."
        )

    profil_lineaire, profil_angulaire = construire_profils(action, cinematique)
    sens_lineaire, sens_angulaire = signer(1.0, 1.0, action.is_forward, action.is_clockwise)

    publies = 0
    ecoule = 0.0
    annulee = False
    while ecoule < action.duree_s:
        if doit_annuler():
            annulee = True
            break
        linear = sens_lineaire * trajectory.evaluer(profil_lineaire, ecoule).vitesse
        angular = sens_angulaire * trajectory.evaluer(profil_angulaire, ecoule).vitesse
        turtle.drive(linear=linear, angular=angular)
        turtle.spin_once(0.0)
        publies += 1
        ecoule += periode
        if sur_avancement is not None:
            sur_avancement(min(ecoule, action.duree_s))
        sleep(periode)

    # Consigne nulle TOUJOURS publiee : arret normal ou annulation (piege 3).
    turtle.stop()
    turtle.spin_once(0.0)
    return publies + 1, annulee


class MotionNode(Node):
    """Serveur de l'action ExecutePlan."""

    def __init__(self, turtle: Any | None = None,
                 settings: dict[str, Any] | None = None,
                 topics: dict[str, Any] | None = None,
                 cinematique: dict[str, Any] | None = None,
                 obstacle: arcs.Obstacle | None = None,
                 context: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire le noeud et son serveur d'action. La tortue est
            injectable pour les tests hors ligne (aucun turtlesim reel requis).

        Inputs:
            turtle (Any | None): facade de commande, ouverte via turtle_io si
                absente (chemin de production)
            settings (dict | None): section 'devoir2' de la configuration
            topics (dict | None): section 'topics' de la configuration
            cinematique (dict | None): section 'cinematique' de la
                configuration (plan05.md), relue depuis ihr_ros.config si absente
            obstacle (arcs.Obstacle | None): obstacle injecte pour la
                verification de collision (verifier_etape_libre) ; None par
                defaut a la construction directe (chemin des tests), mais
                main() lui passe toujours l'obstacle de production lu de la
                configuration (obstacle_config.obstacle_depuis_config)
            context (Any | None): contexte rclpy, celui par defaut si absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        super().__init__("motion_node", context=context)
        self._settings = settings if settings is not None else config.section("devoir2")
        self._topics = topics if topics is not None else config.section("topics")
        self._cinematique = cinematique if cinematique is not None else config.section("cinematique")
        self._obstacle = obstacle
        self._actions_cfg = self._settings["actions"]
        self._bornes_cfg = self._settings.get("bornes")
        self._turtle = turtle if turtle is not None else open_turtle(
            node_name="motion_node_turtle", announce=self.get_logger().info,
        )

        groupe = ReentrantCallbackGroup()
        self._serveur = ActionServer(
            self, ExecutePlan, str(self._topics["execute_action"]),
            execute_callback=self._executer,
            goal_callback=self._sur_but,
            cancel_callback=self._sur_annulation,
            callback_group=groupe,
        )

    @staticmethod
    def _sur_but(goal_request: Any) -> Any:
        """Accepter tout but : la validation du contenu vient de action_depuis_config."""
        return GoalResponse.ACCEPT

    @staticmethod
    def _sur_annulation(goal_handle: Any) -> Any:
        """Accepter toute demande d'annulation (piege 3 : voir executer_etape)."""
        return CancelResponse.ACCEPT

    def _executer(self, goal_handle: Any) -> Any:
        """
        --------------------------------------------------------------------------
        Purpose:
            Executer chaque etape du but, publier l'avancement, et honorer
            l'annulation. Une consigne nulle est publiee ENTRE deux etapes
            (arret franc, plan02.md etape 8) en plus de celle, garantie, de
            `executer_etape`. Avant chaque etape (plan05.md, etape 8) :
            l'arc qu'elle decrirait est verifie (verifier_etape_libre) et,
            en cas de collision prevue, l'etape n'est PAS executee, le but
            est refuse et la raison nomme l'instant et la position. La
            progression rendue par l'action est desormais la fraction du
            temps ECOULE sur la duree totale du plan (plan05.md, etape 7),
            pas un simple compteur d'etapes.

            Correctif critique (2026-09-19) : chaque `Step` porte reellement
            `distance_m`, `angle_deg`, `is_forward` et `is_clockwise` (Step.msg,
            plan01 ; le sens par booleen, plan04), et ce noeud les jetait en
            appelant `action_depuis_config` sans `params` ni `bornes` -- seul le
            NOM de l'action survivait, et 'tourne a droite' comme 'tourne a
            gauche' executaient le meme mouvement (defaut mesure le
            2026-09-18, exactement celui que Step.msg et plan04 existent pour
            empecher). `_params_depuis_step` porte desormais les quatre champs
            du `Step` recu vers `action_depuis_config`, et `bornes`
            (devoir2.bornes) re-borne cote code (R9 : le schema JSON borne
            deja la LLM, mais rien ne garantit qu'un appelant direct, comme un
            test, le respecte). Aucune logique de signe recopiee ici :
            `signer()`, appele par `action_depuis_config`, reste le seul
            endroit du solutionnaire qui decide un signe.

        Inputs:
            goal_handle (ServerGoalHandle): but ExecutePlan en cours

        Outputs:
            resultat (ExecutePlan.Result): succes, messages publies, raison d'arret
        --------------------------------------------------------------------------
        """
        etapes = list(goal_handle.request.etapes)
        total = len(etapes)
        messages = 0
        annulee = False

        actions = [
            action_depuis_config(
                step.nom_action, self._actions_cfg,
                params=_params_depuis_step(step), bornes=self._bornes_cfg,
            )
            for step in etapes
        ]
        duree_totale_plan = sum(action.duree_s for action in actions)
        cumul_avant: list[float] = []
        acc = 0.0
        for action in actions:
            cumul_avant.append(acc)
            acc += action.duree_s

        for index, action in enumerate(actions):
            if goal_handle.is_cancel_requested:
                annulee = True
                break

            pose = self._turtle.pose()
            resultat_arc = verifier_etape_libre(
                (pose.x, pose.y, pose.theta), action, self._cinematique,
                obstacle=self._obstacle,
            )
            if resultat_arc.collision is not None:
                self._turtle.stop()
                self._turtle.spin_once(0.0)
                collision = resultat_arc.collision
                self.get_logger().error(
                    f"etape '{action.nom}' refusee : collision prevue a "
                    f"t={collision.instant:.2f} s, position=({collision.x:.2f}, "
                    f"{collision.y:.2f})"
                )
                goal_handle.abort()
                resultat = ExecutePlan.Result()
                resultat.succes = False
                resultat.messages_publies = messages
                resultat.raison_arret = (
                    f"collision prevue a t={collision.instant:.2f}s, "
                    f"position=({collision.x:.2f}, {collision.y:.2f})"
                )
                return resultat

            duree_avant = cumul_avant[index]

            def _avancement(ecoule_etape: float, index: int = index,
                            duree_avant: float = duree_avant) -> None:
                retour = ExecutePlan.Feedback()
                retour.etape_courante = index
                retour.total = total
                temps_ecoule = duree_avant + ecoule_etape
                retour.progression = (
                    min(1.0, temps_ecoule / duree_totale_plan) if duree_totale_plan > 0 else 1.0
                )
                goal_handle.publish_feedback(retour)

            publies, annulee_ici = executer_etape(
                self._turtle, action, self._cinematique,
                doit_annuler=lambda: goal_handle.is_cancel_requested,
                sur_avancement=_avancement,
            )
            messages += publies

            # Arret franc entre deux etapes (voir docstring du module).
            self._turtle.stop()
            self._turtle.spin_once(0.0)

            if annulee_ici:
                annulee = True
                break

        if annulee:
            self._turtle.stop()
            self._turtle.spin_once(0.0)
            goal_handle.canceled()
            resultat = ExecutePlan.Result()
            resultat.succes = False
            resultat.messages_publies = messages
            resultat.raison_arret = "annulee"
            return resultat

        goal_handle.succeed()
        resultat = ExecutePlan.Result()
        resultat.succes = True
        resultat.messages_publies = messages
        resultat.raison_arret = ""
        return resultat

    def close(self) -> None:
        """Fermer la tortue. Rappelable sans effet si la facade le permet."""
        self._turtle.close()


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree du noeud : executeur multifil, groupe reentrant, pour
        que l'action reste annulable pendant son execution. L'obstacle de
        production (devoir2.obstacle) est lu ICI, via
        obstacle_config.obstacle_depuis_config, et passe au constructeur :
        c'est ce qui ferme l'ecart mesure le 2026-09-19 (rien en production ne
        passait d'obstacle a MotionNode, le mecanisme de plan05 n'etait donc
        jamais exerce que par les tests).

    Inputs:
        argv (list[str] | None): arguments rclpy, ceux de la ligne de commande
            si absents

    Outputs:
        code (int): code de sortie du processus
    --------------------------------------------------------------------------
    """
    rclpy.init(args=argv)
    devoir2_cfg = config.section("devoir2")
    obstacle = obstacle_depuis_config(devoir2_cfg)
    node = MotionNode(settings=devoir2_cfg, obstacle=obstacle)
    executeur = MultiThreadedExecutor()
    executeur.add_node(node)
    try:
        executeur.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
