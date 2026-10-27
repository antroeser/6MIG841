"""
test_boucle.py - Tests d'integration de la boucle principale du Devoir 2 (voice_turtle.py).

Integration complete (machine d'etat + traducteur LLM + entree + tortue) mais toujours
entierement hors-ligne : `ScriptedInput` remplace le micro, `FauxOllama` remplace le
demon Ollama, `SortieVocale(actif=False)` n'appelle aucun moteur, et la tortue est soit
un enregistreur minimal soit la dorsale substitut ('sim'), jamais ROS2 ni turtlesim
reel (workflow.md R5).

Aucun `time.sleep` reel n'est jamais attendu : `executer_action` et `boucle` recoivent
`sleep=lambda _: None`, et la seule source de mouvement reel (le thread de fond de
`SimBackend`, qui boucle sur du temps REEL) est neutralisee en gonflant
`sim.tick_seconds` a 3600 s dans la fixture `config_isolee`, exactement comme le fait
`Lab1/test/test_sim_backend.py`. La physique est avancee a la main via
`backend.step(dt, now)`, jamais en attendant le thread.
"""

from __future__ import annotations

import json

import pytest

from ihr_ros import config
from ihr_ros.turtle_io import open_turtle

from faux_ollama import FauxOllama
from llm_interpreter import LlmInterpreter
from state_machine import Etat, MachineDialogue, action_depuis_config
from voice import ScriptedInput, SortieVocale
from voice_turtle import boucle, executer_action


class _TortueFactice:
    """
    Tortue minimale qui n'enregistre que les consignes recues, sans aucune physique.

    Utilisee la ou seul le NOMBRE et la NATURE des messages Twist publies importent,
    pas la pose reelle : plus simple et plus rapide qu'une SimBackend reelle, et ne
    depend d'aucun thread de fond ni d'aucune configuration.
    """

    def __init__(self) -> None:
        self.consignes: list[tuple[float, float]] = []
        self.spins = 0

    def drive(self, linear: float = 0.0, angular: float = 0.0) -> None:
        self.consignes.append((linear, angular))

    def stop(self) -> None:
        self.consignes.append((0.0, 0.0))

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        self.spins += 1


@pytest.fixture
def config_isolee(tmp_path, monkeypatch):
    """
    Copie ihr_config.json en gonflant sim.tick_seconds a 3600 s, pour que le thread de
    fond de SimBackend (`_run`, qui boucle sur du temps REEL via `Event.wait`) ne
    puisse jamais interferer avec les pas de simulation explicites pris par un test
    (meme piege que Lab1/test/test_sim_backend.py, decrit dans son en-tete de module).
    """
    chemin_reel = config.config_path()
    donnees = json.loads(chemin_reel.read_text(encoding="utf-8"))
    donnees["sim"]["tick_seconds"] = 3600.0
    chemin_test = tmp_path / "config_boucle_test.json"
    chemin_test.write_text(json.dumps(donnees), encoding="utf-8")
    monkeypatch.setenv("IHR_CONFIG", str(chemin_test))
    config.load(force_reload=True)
    return donnees


def _nouvelle_machine(cfg) -> MachineDialogue:
    return MachineDialogue(
        mots_accord=cfg["affirmative_words"],
        mots_refus=cfg["negative_words"],
        mots_sortie=cfg["quit_words"],
    )


# --------------------------------------------------------------------- scenario nominal complet

def test_scenario_nominal_avance_oui_oui_quitter_finit_en_arret_avec_une_action(cfg):
    """Le scenario 'avance/oui/oui/quitter' finit en ARRET, apres exactement une action executee."""
    machine = _nouvelle_machine(cfg)
    entree = ScriptedInput(["avance", "oui", "oui"], phrase_de_fin="quitter")
    voix = SortieVocale(actif=False)
    interprete = LlmInterpreter(cfg, client=FauxOllama(['{"action": "avancer"}']))
    turtle = open_turtle("sim", with_window=False, announce=None)

    try:
        resume = boucle(machine, entree, voix, interprete, turtle, cfg,
                        max_tours=20, sleep=lambda _: None)
    finally:
        turtle.close()

    assert resume["etat_final"] == Etat.ARRET.value
    assert resume["actions_executees"] == ["avancer"]
    assert len(resume["actions_executees"]) == 1
    # 6 = ECOUTE->CONFIRMATION_COMMANDE->INTERPRETATION->CONFIRMATION_ACTION->EXECUTION->ECOUTE->ARRET.
    # Le max_tours=20 n'est qu'un filet de securite : s'il avait ete declenche a la
    # place d'une fin naturelle, ce compte de tours le revelerait (21, pas 6).
    assert resume["tours"] == 6
    assert resume["echecs_interpretation"] == []


# --------------------------------------------------------------------- executer_action() : messages Twist

def test_executer_action_publie_plus_d_un_message_twist(cfg):
    """
    Le rendu etudiant publiait UN SEUL Twist, or turtlesim oublie sa derniere consigne
    au bout d'une seconde : la tortue avancait un instant puis s'arretait seule.
    Ici, la consigne est republiee a command_period_s pendant toute la duree, puis une
    consigne nulle est envoyee. Pour l'action 'avancer' (duree_s=1.0) avec
    command_period_s=0.2 : duree_s/command_period_s + 1 = 1.0/0.2 + 1 = 6.0 messages
    (5 pendant le mouvement, republies toutes les 0.2 s, plus 1 pour l'arret final) ;
    verifie a la main dans le module (pas de derive flottante sur ces valeurs precises).
    """
    action = action_depuis_config("avancer", cfg["actions"])
    turtle = _TortueFactice()

    publies = executer_action(turtle, action, cfg, sleep=lambda _: None)

    attendu = int(round(action.duree_s / cfg["command_period_s"])) + 1
    assert publies == attendu
    assert publies > 1
    assert len(turtle.consignes) == publies
    # La toute derniere consigne publiee est bien l'arret (vitesse nulle).
    assert turtle.consignes[-1] == (0.0, 0.0)


@pytest.mark.parametrize("periode_invalide", [0.0, -0.2], ids=["nulle", "negative"])
def test_executer_action_command_period_non_positif_leve_valueerror(cfg, periode_invalide):
    """command_period_s <= 0 leve ValueError : une periode nulle ou negative publierait sans jamais avancer dans le temps."""
    parametres = dict(cfg)
    parametres["command_period_s"] = periode_invalide
    action = action_depuis_config("avancer", cfg["actions"])
    turtle = _TortueFactice()

    with pytest.raises(ValueError):
        executer_action(turtle, action, parametres, sleep=lambda _: None)


# --------------------------------------------------------------------- executer_action() : tortue immobilisee

def test_executer_action_laisse_la_tortue_immobile_apres_coup(cfg, config_isolee):
    """
    Apres executer_action(), la derniere consigne envoyee est nulle : faire avancer la
    tortue a la main pour prouver que la simulation PEUT bouger, puis appeler
    executer_action() doit laisser sa pose STABLE aux pas de simulation suivants
    (turtle.stop() est le dernier message publie).
    """
    turtle = open_turtle("sim", with_window=False, announce=None)
    try:
        backend = turtle.backend

        # La tortue avance : preuve que la simulation bouge quand on lui donne une consigne.
        turtle.drive(linear=2.0, angular=0.0)
        pose_en_mouvement = backend.step(1.0, now=1.0)
        assert pose_en_mouvement.x > config_isolee["turtlesim"]["start_x"]

        action = action_depuis_config("avancer", cfg["actions"])
        executer_action(turtle, action, cfg, sleep=lambda _: None)

        # La derniere consigne publiee par executer_action est nulle (turtle.stop()) :
        # deux pas de simulation supplementaires ne doivent plus deplacer la tortue.
        pose_apres_1 = backend.step(1.0, now=2.0)
        pose_apres_2 = backend.step(1.0, now=3.0)

        assert pose_apres_1.linear_velocity == pytest.approx(0.0)
        assert pose_apres_1.angular_velocity == pytest.approx(0.0)
        assert pose_apres_2.x == pytest.approx(pose_apres_1.x)
        assert pose_apres_2.y == pytest.approx(pose_apres_1.y)
        assert pose_apres_2.theta == pytest.approx(pose_apres_1.theta)
    finally:
        turtle.close()


# --------------------------------------------------------------------- max_tours borne une boucle sans fin

def test_max_tours_borne_une_boucle_qui_ne_convergerait_jamais(cfg):
    """
    Une reponse toujours INDECIS ('peut-etre', qui n'est ni un accord ni un refus ni
    une sortie) ne fait jamais progresser la machine hors de CONFIRMATION_COMMANDE :
    sans max_tours, boucle() tournerait indefiniment. La borne de securite doit
    l'arreter et laisser un etat final ARRET.
    """
    machine = _nouvelle_machine(cfg)
    entree = ScriptedInput([], phrase_de_fin="peut-etre")
    voix = SortieVocale(actif=False)
    interprete = LlmInterpreter(cfg, client=FauxOllama(["ne devrait jamais servir"]))
    turtle = _TortueFactice()

    resume = boucle(machine, entree, voix, interprete, turtle, cfg,
                    max_tours=5, sleep=lambda _: None)

    assert resume["etat_final"] == Etat.ARRET.value
    assert resume["tours"] == 6  # 5 tours autorises + 1 pour detecter le depassement
    # Message reformule le 2026-09-20 : il est PRONONCE par la synthese vocale, donc
    # ecrit en francais accentue et sans jargon (« borne de securite (5 tours) »
    # s'entendait mal). Le compte de tours reste verifie par l'assertion ci-dessus.
    assert "Limite de sécurité atteinte" in resume["historique"][-1][2]
    assert resume["actions_executees"] == []  # la machine n'a jamais atteint EXECUTION
