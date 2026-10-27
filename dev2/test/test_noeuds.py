"""
test_noeuds.py - Devoir 2, plan02 : les neuf tests exiges des cinq noeuds ROS2.

Hors ligne AU SENS FORT (plan02.md, tableau des tests) : le contexte rclpy est
initialise SANS GRAPHE (aucun autre processus ROS2, aucun `spin()`), les
noeuds sont instancies et leurs rappels appeles EN DIRECT, et tous les
collaborateurs externes (client Ollama, tortue, voix, editeurs ROS2) sont des
faux injectes au constructeur, fournis par conftest.py. Aucun microphone,
aucun demon Ollama, aucun turtlesim reel.

Chaque test utilise son PROPRE contexte rclpy (fixture `contexte_rclpy`) pour
qu'aucun etat ne fuie d'un test a l'autre : c'est le meme principe que
`_restaurer_environnement_ihr` dans conftest.py, applique au graphe ROS2
plutot qu'aux variables d'environnement.

Saute proprement dans le .venv, ou rclpy et le paquet d'interfaces genere par
`colcon build` sont absents (workflow.md R5) : c'est un SAUT ANNONCE, jamais
un echec.
"""

from __future__ import annotations

import ast
import inspect
import math
from typing import Any

import pytest

rclpy = pytest.importorskip(
    "rclpy",
    reason="ROS2 (rclpy) absent : suite des noeuds ROS2 sautee dans le .venv (workflow.md R5).",
)
pytest.importorskip(
    "ihr_6mig841_interfaces.msg",
    reason="paquet ihr_6mig841_interfaces non construit (colcon build requis, plan01.md).",
)

from std_msgs.msg import String  # noqa: E402

from ihr_6mig841_interfaces.msg import Commande, Step  # noqa: E402
from ihr_6mig841_interfaces.srv import Interpret  # noqa: E402

from ihr_ros import config  # noqa: E402

import arcs  # noqa: E402
import dialogue_manager_node  # noqa: E402
import motion_node  # noqa: E402
import obstacle_config  # noqa: E402
from dialogue_manager_node import DialogueManagerNode  # noqa: E402
from llm_interpreter import LlmInterpreter  # noqa: E402
from llm_node import LlmNode  # noqa: E402
from motion_node import MotionNode, executer_etape  # noqa: E402
from state_machine import Etat, Plan, Transition, action_depuis_config  # noqa: E402
from voice import ScriptedInput  # noqa: E402
from voice_input_node import VoiceInputNode  # noqa: E402
from voice_output_node import VoiceOutputNode  # noqa: E402


@pytest.fixture
def contexte_rclpy():
    """Contexte rclpy isole par test : aucun graphe partage entre deux tests."""
    contexte = rclpy.Context()
    rclpy.init(context=contexte)
    yield contexte
    rclpy.shutdown(context=contexte)


class _EditeurFactice:
    """Faux editeur ROS2 : n'enregistre que les messages publies, aucune DDS reelle."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def publish(self, message: String) -> None:
        self.messages.append(message.data)


class _FauxGoalHandle:
    """
    But ExecutePlan factice : juste assez pour piloter MotionNode._executer EN
    DIRECT (meme principe que les autres tests de ce fichier), sans ActionServer
    ni executeur rclpy reels.
    """

    def __init__(self, etapes: list[Step]) -> None:
        self.request = type("RequeteFactice", (), {"etapes": etapes})()
        self.is_cancel_requested = False
        self.feedbacks: list[Any] = []
        self.issue: str | None = None

    def publish_feedback(self, feedback: Any) -> None:
        self.feedbacks.append(feedback)

    def succeed(self) -> None:
        self.issue = "succes"

    def canceled(self) -> None:
        self.issue = "annulee"

    def abort(self) -> None:
        self.issue = "refusee"


# --------------------------------------------------------------------- voice_input : piege 1

def test_voice_input_la_file_videe_publie(contexte_rclpy, cfg, topics):
    """La minuterie vide la file et publie chaque phrase : la lecture bloquante est bien hors du rappel."""
    entree = ScriptedInput([], phrase_de_fin="quitter")
    editeur = _EditeurFactice()
    node = VoiceInputNode(entree=entree, settings=cfg, topics=topics,
                          editeur=editeur, context=contexte_rclpy)
    try:
        node._file.put("avance")
        node._file.put("oui")
        node._vider_et_publier()
        assert editeur.messages == ["avance", "oui"]
    finally:
        node.close()
        node.destroy_node()


def test_voice_input_file_vide_ne_publie_rien(contexte_rclpy, cfg, topics):
    """Controle negatif : une file vide ne publie rien (une minuterie qui publie du vide inonderait le topic)."""
    entree = ScriptedInput([], phrase_de_fin="quitter")
    editeur = _EditeurFactice()
    node = VoiceInputNode(entree=entree, settings=cfg, topics=topics,
                          editeur=editeur, context=contexte_rclpy)
    try:
        node._vider_et_publier()
        assert editeur.messages == []
    finally:
        node.close()
        node.destroy_node()


# --------------------------------------------------------------------- llm_node : le service

def test_llm_node_le_service_rend_des_etapes(contexte_rclpy, cfg, topics, faux_ollama):
    """L'interpretation traverse le service : une commande valide rend un Step nomme."""
    interprete = LlmInterpreter(cfg, client=faux_ollama)
    node = LlmNode(interprete=interprete, settings=cfg, topics=topics, context=contexte_rclpy)
    try:
        requete = Interpret.Request(commande="avance", historique=[])
        reponse = Interpret.Response()
        resultat = node._on_interpret(requete, reponse)
        assert resultat.succes is True
        assert len(resultat.etapes) == 1
        assert resultat.etapes[0].nom_action == "avancer"
    finally:
        node.destroy_node()


def test_llm_node_rapporte_l_erreur_sans_lever(contexte_rclpy, cfg, topics, faux_ollama_casse):
    """Un client Ollama qui leve ne fait PAS lever le service : l'erreur est rapportee dans la reponse."""
    interprete = LlmInterpreter(cfg, client=faux_ollama_casse)
    node = LlmNode(interprete=interprete, settings=cfg, topics=topics, context=contexte_rclpy)
    try:
        requete = Interpret.Request(commande="avance", historique=[])
        reponse = Interpret.Response()
        resultat = node._on_interpret(requete, reponse)  # ne doit lever aucune exception
        assert resultat.succes is False
        assert list(resultat.etapes) == []
        assert resultat.erreur != ""
    finally:
        node.destroy_node()


# --------------------------------------------------------------------- dialogue_manager

def test_dialogue_manager_une_transcription_fait_avancer_l_etat(contexte_rclpy, cfg, topics):
    """Le gestionnaire est bien branche : une transcription en ECOUTE mene a CONFIRMATION_COMMANDE."""
    node = DialogueManagerNode(
        settings=cfg, topics=topics,
        client_interpret=object(), client_execute=object(),
        pub_speak=_EditeurFactice(), context=contexte_rclpy,
    )
    try:
        assert node.machine.etat is Etat.ECOUTE
        node._on_transcription(String(data="avance"))
        assert node.machine.etat is Etat.CONFIRMATION_COMMANDE
    finally:
        node.destroy_node()


def test_dialogue_manager_aucun_appel_synchrone_au_service():
    """
    Lu dans la SOURCE (plan02.md, tableau des tests) : le piege 2 ne laisse pas
    de trace a l'execution, donc c'est en lisant le fichier qu'on verifie que
    l'appel au service et a l'action sont ASYNCHRONES, et qu'aucune attente
    bloquante (spin_until_future_complete) n'y figure dans le CODE.

    Analyse par ast plutot que par une recherche de sous-chaine dans le texte
    brut : le docstring du module NOMME volontairement
    'spin_until_future_complete' pour expliquer le piege a eviter (piege 2,
    plan02.md), et une recherche naive se declencherait sur sa propre
    documentation plutot que sur du code reellement bloquant.
    """
    source = inspect.getsource(dialogue_manager_node)
    arbre = ast.parse(source)
    appels_bloquants = [
        noeud.func.attr
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Call)
        and isinstance(noeud.func, ast.Attribute)
        and noeud.func.attr == "spin_until_future_complete"
    ]
    assert appels_bloquants == []
    assert "call_async" in source
    assert "send_goal_async" in source
    assert "add_done_callback" in source


# --------------------------------------------- dialogue_manager : avec/sans arbitre (plan07)

class _EditeurCommandeFactice:
    """Faux editeur du topic d'intention : enregistre les messages Commande publies."""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    def publish(self, message: Any) -> None:
        self.messages.append(message)


class _FuturFactice:
    """Faux futur rclpy : n'appelle jamais son rappel, suffisant pour verifier un ENVOI."""

    def add_done_callback(self, callback: Any) -> None:
        pass


class _ClientExecuteEspion:
    """Faux client de l'action ExecutePlan : enregistre les buts envoyes."""

    def __init__(self) -> None:
        self.buts: list[Any] = []

    def send_goal_async(self, but: Any) -> _FuturFactice:
        self.buts.append(but)
        return _FuturFactice()


class _FuturResultatAction:
    """Faux futur rclpy contenant le resultat final d'ExecutePlan."""

    def __init__(self, succes: bool, raison: str = "") -> None:
        self._resultat = type(
            "ResultatAction",
            (),
            {"result": type("Resultat", (), {
                "succes": succes,
                "raison_arret": raison,
            })()},
        )()

    def result(self) -> Any:
        return self._resultat


class _FuturInterpretation:
    """Faux futur contenant une reponse du service Interpret."""

    def __init__(self, succes: bool, erreur: str = "", etapes: list[Step] | None = None) -> None:
        self._reponse = Interpret.Response()
        self._reponse.succes = succes
        self._reponse.erreur = erreur
        self._reponse.etapes = etapes or []

    def result(self) -> Any:
        return self._reponse


class _GoalRefuse:
    """Faux handle signalant le rejet d'un but ExecutePlan."""

    accepted = False


class _JournalEtat:
    """Faux logger limité aux messages d'état."""

    def __init__(self) -> None:
        self.etats: list[str] = []

    def info(self, message: str) -> None:
        self.etats.append(message)


def _machine_prete_a_executer(node: DialogueManagerNode, nom_action: str, cfg: dict) -> None:
    """Piloter la machine d'etat JUSQU'A EXECUTION, sans passer par le service reel."""
    node.machine.entendu(nom_action)
    node.machine.repondu("oui")  # ECOUTE -> ... -> INTERPRETATION
    action = action_depuis_config(nom_action, cfg["actions"])
    node.machine.interprete(Plan((action,)))  # -> CONFIRMATION_ACTION
    node.machine.repondu("oui")  # -> EXECUTION


def test_avec_arbitre_publie_lintention_et_nappelle_pas_laction(contexte_rclpy, cfg, topics):
    """
    plan07.md, « Qui commande la tortue » : avec un arbitre present, ce noeud ne
    commande plus directement. Il publie une seule Commande (modalite='voix') et
    laisse le client de l'action INTACT (jamais appele), puis revient a l'ecoute.
    """
    editeur_intention = _EditeurCommandeFactice()
    client_execute = _ClientExecuteEspion()
    node = DialogueManagerNode(
        settings=cfg, topics=topics, client_interpret=object(),
        client_execute=client_execute, pub_speak=_EditeurFactice(),
        avec_arbitre=True, pub_intention=editeur_intention,
        horloge=lambda: 42.0, context=contexte_rclpy,
    )
    try:
        _machine_prete_a_executer(node, "avancer", cfg)
        assert node.machine.etat is Etat.EXECUTION

        node._demarrer_execution()

        assert len(editeur_intention.messages) == 1
        message = editeur_intention.messages[0]
        assert isinstance(message, Commande)
        assert message.modalite == "voix"
        assert message.linear_x > 0.0
        assert message.angular_z == 0.0
        assert message.instant == 42.0
        assert "avancer" in message.motif
        assert client_execute.buts == []  # jamais appele : c'est l'arbitre qui decide
        assert node.machine.etat is Etat.ECOUTE  # rendu la main, sans attendre l'arbitre
    finally:
        node.destroy_node()


def test_sans_arbitre_garde_le_chemin_direct_de_laction(contexte_rclpy, cfg, topics):
    """
    Controle negatif (plan07.md, « garde le chemin direct quand aucun arbitre
    n'est present ») : avec_arbitre=False (le defaut), ce noeud appelle TOUJOURS
    l'action directement, exactement comme avant ce plan, sans jamais publier
    d'intention.
    """
    editeur_intention = _EditeurCommandeFactice()
    client_execute = _ClientExecuteEspion()
    node = DialogueManagerNode(
        settings=cfg, topics=topics, client_interpret=object(),
        client_execute=client_execute, pub_speak=_EditeurFactice(),
        avec_arbitre=False, pub_intention=editeur_intention, context=contexte_rclpy,
    )
    try:
        _machine_prete_a_executer(node, "avancer", cfg)

        node._demarrer_execution()

        assert len(client_execute.buts) == 1
        assert editeur_intention.messages == []
    finally:
        node.destroy_node()


def test_resultat_action_reouvre_ecoute(contexte_rclpy, cfg, topics):
    """Une action terminee remet la porte d'ecoute a True pour la commande suivante."""
    node = DialogueManagerNode(
        settings=cfg, topics=topics, client_interpret=object(),
        client_execute=_ClientExecuteEspion(), pub_speak=_EditeurFactice(),
        context=contexte_rclpy,
    )
    porte = _EditeurFactice()
    node._pub_ecoute = porte
    try:
        _machine_prete_a_executer(node, "avancer", cfg)
        node._sur_resultat_execution(_FuturResultatAction(True))
        assert node.machine.etat is Etat.ECOUTE
        assert porte.messages[-1] is True
    finally:
        node.destroy_node()


def test_but_refuse_reouvre_ecoute_sans_exception(contexte_rclpy, cfg, topics):
    """Un but refuse depuis EXECUTION revient proprement a l'ecoute."""
    node = DialogueManagerNode(
        settings=cfg, topics=topics, client_interpret=object(),
        client_execute=_ClientExecuteEspion(), pub_speak=_EditeurFactice(),
        context=contexte_rclpy,
    )
    porte = _EditeurFactice()
    node._pub_ecoute = porte
    try:
        _machine_prete_a_executer(node, "avancer", cfg)
        node._sur_acceptation_but(type("Futur", (), {"result": lambda _self: _GoalRefuse()})())
        assert node.machine.etat is Etat.ECOUTE
        assert porte.messages[-1] is True
    finally:
        node.destroy_node()


def test_echec_llm_reouvre_ecoute_pour_la_commande_suivante(contexte_rclpy, cfg, topics):
    """Une reponse LLM invalide ferme puis rouvre la porte d'ecoute."""
    node = DialogueManagerNode(
        settings=cfg, topics=topics, client_interpret=object(),
        client_execute=object(), pub_speak=_EditeurFactice(),
        context=contexte_rclpy,
    )
    porte = _EditeurFactice()
    node._pub_ecoute = porte
    try:
        _machine_prete_a_executer(node, "avancer", cfg)
        node.machine.etat = Etat.INTERPRETATION
        node.machine.commande = "avance"
        node._sur_reponse_interpretation(
            _FuturInterpretation(False, "JSON invalide")
        )
        assert node.machine.etat is Etat.ECOUTE
        assert porte.messages[-1] is True
    finally:
        node.destroy_node()


def test_plan_interprete_rouvre_ecoute_pour_confirmation(contexte_rclpy, cfg, topics, monkeypatch):
    """Un plan valide rouvrre le micro afin de recevoir la confirmation finale."""
    node = DialogueManagerNode(
        settings=cfg, topics=topics, client_interpret=object(),
        client_execute=object(), pub_speak=_EditeurFactice(),
        context=contexte_rclpy,
    )
    porte = _EditeurFactice()
    node._pub_ecoute = porte
    journal = _JournalEtat()
    monkeypatch.setattr(node, "get_logger", lambda: journal)
    try:
        node.machine.etat = Etat.INTERPRETATION
        node.machine.commande = "avance"
        step = Step()
        step.nom_action = "avancer"
        step.distance_m = 1.0
        step.angle_deg = 0.0
        step.is_forward = True
        step.is_clockwise = False
        node._sur_reponse_interpretation(
            _FuturInterpretation(True, etapes=[step])
        )
        assert node.machine.etat is Etat.CONFIRMATION_ACTION
        assert porte.messages[-1] is True
        assert "[etat] confirmation_action" in journal.etats
    finally:
        node.destroy_node()


def test_affichage_etat_une_seule_fois_si_etat_maintenu(contexte_rclpy, cfg, topics, monkeypatch):
    """Un etat conserve n'est journalise qu'au premier affichage."""
    node = DialogueManagerNode(
        settings=cfg, topics=topics, client_interpret=object(),
        client_execute=object(), pub_speak=_EditeurFactice(),
        context=contexte_rclpy,
    )
    journal = _JournalEtat()
    monkeypatch.setattr(node, "get_logger", lambda: journal)
    try:
        transition = Transition(Etat.ECOUTE, "")
        node._annoncer(transition)
        node._annoncer(transition)
        assert journal.etats == ["[etat] ecoute"]
    finally:
        node.destroy_node()


# --------------------------------------------------------------------- motion_node : pieges 1(bis) / 3

def test_motion_node_plus_d_un_twist_par_etape(cfg, cinematique, fausse_tortue):
    """
    Turtlesim oublie sa consigne au bout d'une seconde : une etape republie plus
    d'un Twist. Depuis plan05, la republication se fait au rythme de
    cinematique.periode_publication_s (consigne qui rampe), et non plus de
    devoir2.command_period_s (consigne constante).
    """
    action = action_depuis_config("avancer", cfg["actions"])

    publies, annulee = executer_etape(fausse_tortue, action, cinematique, sleep=lambda _: None)

    attendu = int(round(action.duree_s / cinematique["periode_publication_s"])) + 1
    assert publies == attendu
    assert publies > 1
    assert annulee is False
    assert len(fausse_tortue.consignes) == publies
    assert fausse_tortue.consignes[-1] == (0.0, 0.0)


def test_motion_node_l_annulation_arrete_la_tortue(cfg, cinematique, fausse_tortue):
    """Une annulation immediate publie quand meme une consigne nulle : l'arret d'urgence est reel, pas fictif."""
    action = action_depuis_config("avancer", cfg["actions"])

    publies, annulee = executer_etape(
        fausse_tortue, action, cinematique, doit_annuler=lambda: True, sleep=lambda _: None,
    )

    assert annulee is True
    assert publies == 1  # aucune consigne de mouvement, seulement l'arret final
    assert fausse_tortue.consignes == [(0.0, 0.0)]


def test_motion_node_refuse_une_etape_en_collision(contexte_rclpy, cfg, topics, cinematique,
                                                    fausse_tortue):
    """
    plan05.md, etape 8, le test qui prouve le branchement : quand l'arc d'une
    etape heurte un obstacle, motion_node NE L'EXECUTE PAS, refuse le but et
    nomme l'instant et la position dans la raison d'arret, plutot que
    d'executer un mouvement dont il sait deja qu'il heurte.
    """
    obstacle = arcs.Obstacle(x=1.0, y=0.0, rayon=0.5)
    node = MotionNode(turtle=fausse_tortue, settings=cfg, topics=topics,
                      cinematique=cinematique, obstacle=obstacle, context=contexte_rclpy)
    try:
        etape = Step(nom_action="avancer", distance_m=0.0, angle_deg=0.0,
                    is_forward=True, is_clockwise=False)
        goal_handle = _FauxGoalHandle([etape])

        resultat = node._executer(goal_handle)

        assert resultat.succes is False
        assert resultat.messages_publies == 0
        assert "collision" in resultat.raison_arret
        assert fausse_tortue.consignes == [(0.0, 0.0)]  # arret publie, aucun mouvement execute
        assert goal_handle.issue == "refusee"
    finally:
        node.close()
        node.destroy_node()


# --------------------------------------------------------------------- motion_node : params et bornes reellement transmis (2026-09-19)

def test_motion_node_step_is_clockwise_inverse_le_signe_angulaire(
        contexte_rclpy, cfg, topics, cinematique, fausse_tortue):
    """
    Defaut critique corrige le 2026-09-19 : `_executer` appelait
    `action_depuis_config` SANS `params`, si bien que seul le NOM de l'action
    survivait et que 'tourne a droite' (is_clockwise=True) et 'tourne a
    gauche' (is_clockwise=False) executaient LE MEME mouvement -- exactement
    le defaut que Step.msg (plan01) et le sens par booleen (plan04) existent
    pour empecher. Preuve en PAIRE, comme l'exige le defaut mesure : un test
    unilateral passerait avec un signe constant. Une seconde fausse tortue,
    de la meme classe que celle de la fixture (`type(fausse_tortue)`), est
    construite pour chaque branche : les deux executions doivent rester
    independantes l'une de l'autre.
    """
    def vitesse_angulaire_publiee(is_clockwise: bool) -> float:
        tortue = type(fausse_tortue)()
        node = MotionNode(turtle=tortue, settings=cfg, topics=topics,
                          cinematique=cinematique, obstacle=None, context=contexte_rclpy)
        try:
            etape = Step(nom_action="tourner", distance_m=0.0, angle_deg=0.0,
                        is_forward=True, is_clockwise=is_clockwise)
            resultat = node._executer(_FauxGoalHandle([etape]))
            assert resultat.succes is True
            angulaires = [angular for (_lin, angular) in tortue.consignes if angular != 0.0]
            assert angulaires, "aucune consigne angulaire non nulle publiee"
            return angulaires[0]
        finally:
            node.close()
            node.destroy_node()

    horaire = vitesse_angulaire_publiee(True)
    antihoraire = vitesse_angulaire_publiee(False)

    assert horaire < 0.0
    assert antihoraire > 0.0


def test_motion_node_step_is_forward_faux_donne_une_vitesse_lineaire_negative(
        contexte_rclpy, cfg, topics, cinematique, fausse_tortue):
    """Un Step portant is_forward=False doit produire une vitesse lineaire NEGATIVE, jamais celle par defaut."""
    node = MotionNode(turtle=fausse_tortue, settings=cfg, topics=topics,
                      cinematique=cinematique, obstacle=None, context=contexte_rclpy)
    try:
        etape = Step(nom_action="avancer", distance_m=0.0, angle_deg=0.0,
                    is_forward=False, is_clockwise=False)
        resultat = node._executer(_FauxGoalHandle([etape]))

        assert resultat.succes is True
        lineaires = [linear for (linear, _ang) in fausse_tortue.consignes if linear != 0.0]
        assert lineaires, "aucune consigne lineaire non nulle publiee"
        assert all(v < 0.0 for v in lineaires)
    finally:
        node.close()
        node.destroy_node()


def test_motion_node_step_distance_m_explicite_change_la_distance_parcourue(cfg):
    """
    Un Step portant une distance_m explicite differente de celle du catalogue
    doit changer la distance parcourue (donc le profil trapezoidal construit
    par construire_profils), sinon le champ est encore ignore.
    """
    step_catalogue = Step(nom_action="avancer", distance_m=0.0, angle_deg=0.0,
                          is_forward=True, is_clockwise=False)
    step_explicite = Step(nom_action="avancer", distance_m=3.5, angle_deg=0.0,
                          is_forward=True, is_clockwise=False)

    action_catalogue = action_depuis_config(
        step_catalogue.nom_action, cfg["actions"],
        params=motion_node._params_depuis_step(step_catalogue), bornes=cfg["bornes"],
    )
    action_explicite = action_depuis_config(
        step_explicite.nom_action, cfg["actions"],
        params=motion_node._params_depuis_step(step_explicite), bornes=cfg["bornes"],
    )

    assert action_catalogue.distance_m == pytest.approx(2.0)  # valeur du catalogue, inchangee
    assert action_explicite.distance_m == pytest.approx(3.5)
    assert action_explicite.distance_m != action_catalogue.distance_m


def test_motion_node_step_grandeur_absurde_est_ramenee_a_la_borne(cfg):
    """Un Step portant une grandeur absurde (distance_m=999) est ramene a la borne (R9, second bornage cote code)."""
    step_absurde = Step(nom_action="avancer", distance_m=999.0, angle_deg=0.0,
                        is_forward=True, is_clockwise=False)

    action = action_depuis_config(
        step_absurde.nom_action, cfg["actions"],
        params=motion_node._params_depuis_step(step_absurde), bornes=cfg["bornes"],
    )

    assert action.distance_m == pytest.approx(float(cfg["bornes"]["distance_m_max"]))


# --------------------------------------------------------------------- motion_node : obstacle de production (2026-09-19)

def test_motion_node_main_lit_et_transmet_l_obstacle_de_production():
    """
    Verification structurelle (meme methode que
    test_dialogue_manager_aucun_appel_bloquant, plus haut) : jusqu'ici rien en
    production ne passait d'obstacle a MotionNode (obstacle valait None par
    defaut et le restait). Cette suite prouve que main() appelle desormais
    obstacle_config.obstacle_depuis_config ET passe son resultat a
    MotionNode(obstacle=...), plutot que de laisser le defaut d'injection de
    test s'appliquer aussi en production.
    """
    source = inspect.getsource(motion_node)
    assert "obstacle_depuis_config" in source

    arbre = ast.parse(source)
    fonction_main = next(
        noeud for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.FunctionDef) and noeud.name == "main"
    )
    appels = [n for n in ast.walk(fonction_main) if isinstance(n, ast.Call)]

    appelle_la_lecture = any(
        isinstance(appel.func, ast.Name) and appel.func.id == "obstacle_depuis_config"
        for appel in appels
    )
    assert appelle_la_lecture, "main() n'appelle pas obstacle_depuis_config"

    construction = next(
        appel for appel in appels
        if isinstance(appel.func, ast.Name) and appel.func.id == "MotionNode"
    )
    mots_cles = {mc.arg for mc in construction.keywords}
    assert "obstacle" in mots_cles, "MotionNode() n'est pas construit avec obstacle= dans main()"


def test_motion_node_refuse_avec_l_obstacle_reellement_declare_en_configuration(
        contexte_rclpy, cfg, topics, cinematique, fausse_tortue):
    """
    Preuve comportementale, sans injection d'une valeur inventee par ce test :
    l'obstacle lu depuis la configuration REELLE (cfg), par le meme chemin que
    main() (obstacle_config.obstacle_depuis_config), refuse effectivement
    l'etape 'avancer' executee apres une rotation de 90 degres antihoraire --
    exactement la sequence verifiee par calcul dans
    .sdd/6mig841-ameliorations/obstacle-devoir2-report.md. Le test existant
    (test_motion_node_refuse_une_etape_en_collision) ne prouve que le
    MECANISME avec un obstacle choisi par le test ; celui-ci prouve que la
    VALEUR DE PRODUCTION, une fois lue, produit le meme effet.
    """
    obstacle_production = obstacle_config.obstacle_depuis_config(cfg)
    assert obstacle_production is not None

    turtlesim_cfg = config.section("turtlesim")
    fausse_tortue.pose_actuelle.x = float(turtlesim_cfg["start_x"])
    fausse_tortue.pose_actuelle.y = float(turtlesim_cfg["start_y"])
    fausse_tortue.pose_actuelle.theta = math.pi / 2.0  # deja tournee de 90 deg antihoraire

    node = MotionNode(turtle=fausse_tortue, settings=cfg, topics=topics,
                      cinematique=cinematique, obstacle=obstacle_production,
                      context=contexte_rclpy)
    try:
        etape = Step(nom_action="avancer", distance_m=0.0, angle_deg=0.0,
                    is_forward=True, is_clockwise=False)
        goal_handle = _FauxGoalHandle([etape])

        resultat = node._executer(goal_handle)

        assert resultat.succes is False
        assert "collision" in resultat.raison_arret
        assert goal_handle.issue == "refusee"
    finally:
        node.close()
        node.destroy_node()


def test_motion_node_sans_section_obstacle_fonctionne_comme_avant(
        contexte_rclpy, cfg, topics, cinematique, fausse_tortue):
    """
    Controle negatif : une configuration devoir2 SANS section 'obstacle' (le
    Devoir 2 tel qu'avant ce plan) laisse motion_node executer une etape
    normalement, sans jamais lever ni refuser pour un motif de collision.
    """
    cfg_sans_obstacle = {cle: valeur for cle, valeur in cfg.items() if cle != "obstacle"}
    obstacle_absent = obstacle_config.obstacle_depuis_config(cfg_sans_obstacle)
    assert obstacle_absent is None

    node = MotionNode(turtle=fausse_tortue, settings=cfg_sans_obstacle, topics=topics,
                      cinematique=cinematique, obstacle=obstacle_absent,
                      context=contexte_rclpy)
    try:
        etape = Step(nom_action="avancer", distance_m=0.0, angle_deg=0.0,
                    is_forward=True, is_clockwise=False)
        goal_handle = _FauxGoalHandle([etape])

        resultat = node._executer(goal_handle)

        assert resultat.succes is True
        assert goal_handle.issue == "succes"
    finally:
        node.close()
        node.destroy_node()


# --------------------------------------------------------------------- voice_output

def test_voice_output_prononce_ce_qu_elle_recoit(contexte_rclpy, topics, fausse_voix):
    """Le noeud de sortie ne decide rien : il prononce exactement ce qu'il recoit."""
    node = VoiceOutputNode(voix=fausse_voix, topics=topics, context=contexte_rclpy)
    try:
        node._on_speak(String(data="avancer envoyee"))
        assert fausse_voix.dites == ["avancer envoyee"]
    finally:
        node.close()
        node.destroy_node()
