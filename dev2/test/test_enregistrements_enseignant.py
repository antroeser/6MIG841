"""
test_enregistrements_enseignant.py - La machine d'etats eprouvee sur de VRAIS
enregistrements vocaux, ceux que l'enseignant a dictes le 2026-09-20 pour ce test.

Trois fichiers, a la racine du depot :

  CommandeVocale.m4a   19,50 s  une commande valide, en SEQUENCE de trois etapes
  CommandeAccepte.m4a   2,11 s  la confirmation de l'usager
  CommandeFausse.m4a    3,90 s  une phrase hors domaine, pour eprouver la boucle d'essais

Ces tests sont organises en DEUX etages, et c'est volontaire.

L'etage HORS LIGNE (la quasi-totalite du fichier) ne lit aucun fichier audio et ne
charge aucun modele : il part des transcriptions MESUREES ci-dessous, figees en
constantes. Il tourne donc dans la suite par defaut, sans micro, sans GPU, sans Ollama
et sans ROS2 (workflow.md R5).

L'etage MATERIEL (une seule fonction, marquee @pytest.mark.hardware, hors suite par
defaut) retranscrit les trois .m4a avec le moteur reel et verifie que les constantes
ci-dessous disent encore la verite. Sans lui, les constantes deriveraient en silence le
jour ou le modele, sa taille ou sa langue changeraient, et l'etage hors ligne
continuerait de passer en testant une fiction.

DEUX DEFAUTS REELS ont ete trouves EN ECRIVANT ces tests, tous deux invisibles tant que
les reponses etaient tapees au clavier plutot que dictees :

  1. « J'accepte. » tombait en INDECIS : le mot 'accepte' manquait a
     devoir2.affirmative_words.
  2. Plus grave, « oui. » tombait AUSSI en INDECIS. interpreter_reponse cherchait
     ' oui ' encadre d'espaces dans le texte brut, or faster-whisper PONCTUE toujours.
     Toute confirmation dictee etait donc refusee et la question reposee sans fin. Le
     test test_une_simple_ponctuation_ne_casse_plus_la_confirmation garde cette porte
     fermee.

Voir la provenance devoir2_mots_confirmation dans Lab1/code/ihr_config.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ihr_ros.turtle_io import open_turtle

from faux_ollama import FauxOllama
from llm_interpreter import LlmInterpreter
from state_machine import Etat, MachineDialogue, Reponse, interpreter_reponse
from voice import ScriptedInput, SortieVocale
from voice_turtle import boucle

# --------------------------------------------------------------------- les enregistrements

_RACINE_DEPOT = Path(__file__).resolve().parent.parent.parent

#: Transcriptions MESUREES le 2026-09-20, faster-whisper 'small', compute_type float16,
#: device cuda, langue 'fr' -- c'est-a-dire exactement la configuration devoir2 du
#: depot a cette date. Elles sont figees ici pour que l'etage hors ligne n'ait besoin
#: ni des fichiers ni du modele ; le test marque 'hardware' les reverifie.
COMMANDE_VOCALE = (
    "Le robot avance de 1 mètre à 1 mètre par seconde et tourne de 45 degrés "
    "à 0.5 grades par seconde, ensuite avance de 2 mètre à 2 mètre par seconde."
)
CONFIRMATION = "J'accepte."
COMMANDE_FAUSSE = "La tale de béton est de 35 mégapascales."

ENREGISTREMENTS = {
    "CommandeVocale.m4a": COMMANDE_VOCALE,
    "CommandeAccepte.m4a": CONFIRMATION,
    "CommandeFausse.m4a": COMMANDE_FAUSSE,
}

#: Le plan que le LLM doit rendre pour COMMANDE_VOCALE : la commande dictee enchaine
#: bien TROIS mouvements, donc une 'sequence' et non une action simple.
PLAN_ATTENDU = json.dumps({
    "action": "sequence",
    "etapes": [
        {"action": "avancer", "distance_m": 1.0, "linear_speed": 1.0},
        {"action": "tourner", "angle_deg": 45.0, "angular_speed": 0.5,
         "is_clockwise": False},
        {"action": "avancer", "distance_m": 2.0, "linear_speed": 2.0},
    ],
})


def _nouvelle_machine(cfg) -> MachineDialogue:
    return MachineDialogue(
        mots_accord=cfg["affirmative_words"],
        mots_refus=cfg["negative_words"],
        mots_sortie=cfg["quit_words"],
    )


# --------------------------------------------------------------------- la confirmation dictee

def test_la_confirmation_dictee_j_accepte_est_comprise_comme_un_accord(cfg):
    """« J'accepte. », telle que l'enseignant l'a dictee, vaut ACCORD."""
    resultat = interpreter_reponse(CONFIRMATION, cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])

    assert resultat is Reponse.ACCORD


@pytest.mark.parametrize("dictee", ["oui.", "Oui.", "Oui !", "D'accord.", "oui, c'est correct."])
def test_une_simple_ponctuation_ne_casse_plus_la_confirmation(cfg, dictee):
    """
    Garde le defaut du 2026-09-20 ferme : faster-whisper ponctue TOUJOURS, donc
    « oui » dicte arrive comme « Oui. ». L'ancienne comparaison, qui cherchait
    ' oui ' encadre d'espaces dans le texte brut, rendait INDECIS et faisait
    reposer la question sans fin.
    """
    resultat = interpreter_reponse(dictee, cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])

    assert resultat is Reponse.ACCORD, f"{dictee!r} doit valoir un accord"


def test_la_commande_fausse_dictee_n_est_ni_un_accord_ni_un_refus(cfg):
    """Une phrase hors domaine reste INDECIS : elle ne doit jamais valider par accident."""
    resultat = interpreter_reponse(COMMANDE_FAUSSE, cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])

    assert resultat is Reponse.INDECIS


# --------------------------------------------------------------------- le parcours complet

def test_la_commande_dictee_traverse_la_machine_jusqu_a_l_execution(cfg):
    """
    Le scenario que l'enseignant decrit : l'usager dicte sa commande, le systeme lui
    redit ce qu'il a compris, l'usager confirme, et la commande part vers le robot.

    Les deux confirmations sont la MEME phrase dictee (CommandeAccepte.m4a) : une
    pour valider la transcription, une pour valider le plan interprete.
    """
    machine = _nouvelle_machine(cfg)
    entree = ScriptedInput([COMMANDE_VOCALE, CONFIRMATION, CONFIRMATION],
                           phrase_de_fin="Quitter.")
    voix = SortieVocale(actif=False)
    interprete = LlmInterpreter(cfg, client=FauxOllama([PLAN_ATTENDU]))
    turtle = open_turtle("sim", with_window=False, announce=None)

    try:
        resume = boucle(machine, entree, voix, interprete, turtle, cfg,
                        max_tours=20, sleep=lambda _: None)
    finally:
        turtle.close()

    assert resume["etat_final"] == Etat.ARRET.value
    assert resume["echecs_interpretation"] == []
    # La commande dictee enchaine TROIS mouvements, et `actions_executees` nomme
    # chaque etape reellement envoyee a la tortue, jamais le mot 'sequence' qui
    # n'est que l'enveloppe rendue par le modele. Mesure le 2026-09-20 : l'ordre
    # compte autant que le compte, car c'est lui qui prouve que la phrase dictee
    # a ete lue dans le bon sens (avance, PUIS tourne, PUIS avance).
    assert resume["actions_executees"] == ["avancer", "tourner", "avancer"]


def test_la_commande_dictee_est_lue_comme_une_sequence_de_trois_etapes(cfg):
    """La phrase dictee enchaine trois mouvements, donc le Plan en porte trois."""
    interprete = LlmInterpreter(cfg, client=FauxOllama([PLAN_ATTENDU]))

    resultat = interprete.interpreter(COMMANDE_VOCALE)

    assert resultat.ok is True
    assert len(resultat.plan) == 3


# --------------------------------------------------------------------- la boucle d'essais

def test_la_commande_fausse_epuise_les_trois_essais_sans_jamais_produire_de_plan(cfg):
    """
    « La tale de béton est de 35 mégapascales. » n'est pas une commande de robot.

    Le modele est interroge llm_max_attempts fois, jamais plus, puis l'interpretation
    echoue en NOMMANT la raison (R8 : jamais de succes silencieux). C'est la boucle de
    trois essais que l'enseignant voulait eprouver avec cet enregistrement.
    """
    essais = int(cfg["llm_max_attempts"])
    client = FauxOllama(['{"action": "couler du beton"}'] * essais)
    interprete = LlmInterpreter(cfg, client=client)

    resultat = interprete.interpreter(COMMANDE_FAUSSE)

    assert resultat.ok is False
    assert resultat.tentatives == essais
    assert client.nb_appels == essais
    assert resultat.erreur


def test_apres_trois_essais_rates_la_machine_revient_ecouter_et_n_execute_rien(cfg):
    """
    Une interpretation ratee ne doit ni bloquer la machine ni faire bouger le robot :
    elle ramene a l'ecoute, et la session peut se terminer normalement.
    """
    essais = int(cfg["llm_max_attempts"])
    machine = _nouvelle_machine(cfg)
    entree = ScriptedInput([COMMANDE_FAUSSE, CONFIRMATION], phrase_de_fin="Quitter.")
    voix = SortieVocale(actif=False)
    interprete = LlmInterpreter(
        cfg, client=FauxOllama(['{"action": "couler du beton"}'] * essais))
    turtle = open_turtle("sim", with_window=False, announce=None)

    try:
        resume = boucle(machine, entree, voix, interprete, turtle, cfg,
                        max_tours=20, sleep=lambda _: None)
    finally:
        turtle.close()

    assert resume["etat_final"] == Etat.ARRET.value
    assert resume["actions_executees"] == []
    assert len(resume["echecs_interpretation"]) == 1


# --------------------------------------------------------------------- l'etage materiel

@pytest.mark.hardware
@pytest.mark.parametrize("nom,attendu", sorted(ENREGISTREMENTS.items()))
def test_les_transcriptions_figees_disent_encore_la_verite(cfg, nom, attendu):
    """
    Retranscrit le vrai fichier avec le vrai moteur et le compare a la constante.

    Hors suite par defaut (workflow.md R5) : ce test charge un modele de plusieurs
    centaines de Mo sur le GPU. Il existe pour que les constantes de ce fichier ne
    puissent pas deriver en silence si le modele, sa taille ou sa langue changent.

    Il doit tourner sous l'interprete conda, seul a porter ROS2 et les paquets CUDA
    (.claude/rules/ros2.md). Or pytest y refuse de demarrer : les greffons
    `launch_testing` et `launch_testing_ros` de ROS2 Humble declarent des hooks
    qu'une version recente de pluggy rejette (`PluginValidationError: unknown hook
    'pytest_launch_collect_makemodule'`). Defaut d'environnement, sans rapport avec
    ce depot, et `-p no:<nom>` ne suffit pas car les deux se chargent par point
    d'entree. La commande qui marche, mesuree le 2026-09-20, coupe le chargement
    automatique des greffons tiers :

        $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
        & $py -m pytest Devoir2/test/test_enregistrements_enseignant.py -m hardware -q

    ou $py est l'interprete conda rendu par Lab1/code/ros2_env.ps1. Resultat mesure
    ce jour-la : 3 passed, 11 deselected, en 7,61 s.
    """
    chemin = _RACINE_DEPOT / nom
    if not chemin.is_file():
        pytest.skip(f"{nom} absent de {_RACINE_DEPOT}")

    from voice import _ajouter_repertoires_dll_cuda, charger_modele_whisper

    peripherique = cfg["speech_device"]
    _ajouter_repertoires_dll_cuda(peripherique)
    modele = charger_modele_whisper(cfg["speech_model_size"],
                                    cfg["speech_compute_type"], peripherique)

    segments, _ = modele.transcribe(str(chemin),
                                    language=str(cfg["speech_language"]).split("-")[0])
    obtenu = " ".join(s.text for s in segments).strip()

    assert obtenu == attendu, (
        f"{nom} se transcrit desormais {obtenu!r} et non plus {attendu!r}. "
        "Mettre a jour la constante de ce fichier, et verifier que les tests hors "
        "ligne qui s'en servent disent toujours ce qu'ils pretendent."
    )
