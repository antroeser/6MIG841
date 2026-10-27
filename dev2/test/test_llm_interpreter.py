"""
test_llm_interpreter.py - Tests du traducteur commande -> plan (llm_interpreter.py).

Aucun demon Ollama reel n'est jamais contacte : `LlmInterpreter` recoit un faux client
(`faux_ollama.FauxOllama` et consorts), qui n'implemente que `.generate(...)` et
enregistre chaque appel (workflow.md R5). Le coeur du devoir tient dans deux idees que
les rendus etudiants n'appliquaient pas : la LLM ne rend qu'un NOM D'ACTION contraint
par une enumeration (jamais des vitesses en texte libre), et le nombre de tentatives
est BORNE.

Depuis plan04, quatre idees supplementaires sont eprouvees ici : le sens par booleen
(amelioration A, schema sans champ signe et invite qui declare la convention),
l'historique transmis dans l'invite (amelioration B), la sequence a plusieurs etapes
(amelioration C), et le catalogue sous-ensemblable (amelioration D).
"""

from __future__ import annotations

import copy

import pytest

from faux_ollama import FauxOllama, OllamaLent, OllamaQuiEchoue
from llm_interpreter import LlmInterpreter, construire_prompt, construire_schema


# --------------------------------------------------------------------- construire_schema()

def test_construire_schema_derive_l_enum_des_noms_d_action_de_la_config(cfg):
    """L'enumeration du schema est exactement les noms d'actions de la config, tries."""
    schema = construire_schema(cfg["actions"], cfg["bornes"])
    assert schema["properties"]["action"]["enum"] == sorted(cfg["actions"])
    assert schema["required"] == ["action", "distance_m", "angle_deg",
                                  "is_forward", "is_clockwise"]


def test_construire_schema_n_est_pas_code_en_dur_ajouter_une_action_grandit_l_enum(cfg):
    """
    Ajouter une action a une COPIE de la config fait grandir l'enum d'autant : la
    liste n'est donc PAS ecrite en dur dans llm_interpreter.py, elle est bien derivee
    de la configuration a chaque appel.
    """
    actions_augmentees = copy.deepcopy(cfg["actions"])
    schema_avant = construire_schema(actions_augmentees, cfg["bornes"])

    actions_augmentees["danser"] = {"linear_speed": 0.0, "angular_speed": 0.0,
                                    "duree_s": 1.0}
    schema_apres = construire_schema(actions_augmentees, cfg["bornes"])

    assert len(schema_apres["properties"]["action"]["enum"]) == \
        len(schema_avant["properties"]["action"]["enum"]) + 1
    assert "danser" in schema_apres["properties"]["action"]["enum"]
    assert "danser" not in schema_avant["properties"]["action"]["enum"]
    # La config reelle du fixture n'a pas ete touchee (copie profonde).
    assert "danser" not in cfg["actions"]


def test_construire_schema_table_vide_leve_valueerror(cfg):
    """Une table d'actions vide leve ValueError : sans action declaree, la LLM n'aurait aucun choix valide."""
    with pytest.raises(ValueError):
        construire_schema({}, cfg["bornes"])


# --------------------------------------------------------------------- le sens par booleen (plan04, amelioration A)

def test_construire_schema_n_expose_aucun_champ_signe(cfg):
    """distance_m et angle_deg ont un minimum de zero, is_forward/is_clockwise sont booleens : aucun champ signe n'est expose au modele."""
    schema = construire_schema(cfg["actions"], cfg["bornes"])
    proprietes = schema["properties"]
    assert proprietes["distance_m"]["minimum"] == 0.0
    assert proprietes["angle_deg"]["minimum"] == 0.0
    assert proprietes["is_forward"]["type"] == "boolean"
    assert proprietes["is_clockwise"]["type"] == "boolean"


def test_construire_prompt_declare_la_convention_de_sens(cfg):
    """
    L'invite DECLARE la convention de signe en toutes lettres : sans cela le modele
    devine, ce qui est exactement ce qui a rate le 2026-09-18 (rotation_deg identique
    a droite et a gauche).
    """
    prompt = construire_prompt("tourne a droite", cfg["actions"])
    assert "is_clockwise" in prompt
    assert "droite" in prompt


# --------------------------------------------------------------------- interpretation reussie

def test_interpreter_action_valide_lit_les_vitesses_dans_la_config_pas_dans_la_reponse(cfg):
    """
    Le modele ne rend qu'un NOM d'action ('avancer'), jamais de vitesse. linear/angular
    proviennent de la configuration, pas de la reponse du modele (qui n'en contient
    d'ailleurs aucune ici).
    """
    client = FauxOllama(['{"action": "avancer"}'])
    interp = LlmInterpreter(cfg, client=client)

    resultat = interp.interpreter("avance tout droit")

    assert resultat.ok
    assert resultat.tentatives == 1
    assert len(resultat.plan) == 1
    action = resultat.plan.etapes[0]
    assert action.nom == "avancer"
    assert action.linear == pytest.approx(cfg["actions"]["avancer"]["linear_speed"])
    assert action.angular == pytest.approx(cfg["actions"]["avancer"]["angular_speed"])
    assert action.duree_s == pytest.approx(cfg["actions"]["avancer"]["duree_s"])

    # Ce qui a ete EXPEDIE au modele est aussi verifiable : le nom du modele configure,
    # la commande de l'utilisateur dans le prompt, et le schema a enumeration fermee.
    assert client.nb_appels == 1
    appel = client.appels[0]
    assert appel.model == cfg["llm_model"]
    assert "avance tout droit" in appel.prompt
    assert appel.format == interp.schema
    noms_attendus = sorted(cfg["actions"]) + ["sequence"]
    assert appel.format["properties"]["action"]["enum"] == noms_attendus


# --------------------------------------------------------------------- residence VRAM (correctif 2026-09-19)

def test_interpreter_transmet_num_ctx_depuis_la_config(cfg):
    """
    options.num_ctx doit porter exactement devoir2.llm_num_ctx de la configuration,
    sans quoi Ollama retombe sur le defaut du demon (mesure a 262144 le 2026-09-19,
    voir ihr_config.json/_provenance/devoir2_vram_residence) et le cache cle-valeur
    qui en decoule repousse le modele sur le processeur.
    """
    client = FauxOllama(['{"action": "avancer"}'])
    interp = LlmInterpreter(cfg, client=client)

    interp.interpreter("avance")

    assert client.appels[0].options["num_ctx"] == cfg["llm_num_ctx"]


def test_interpreter_transmet_keep_alive_depuis_la_config(cfg):
    """
    keep_alive doit porter exactement devoir2.llm_keep_alive (au niveau superieur de la
    requete, jamais dans options), sans quoi Ollama retombe sur le keep_alive par defaut
    du demon (5 minutes) et decharge le modele entre deux commandes d'une meme seance
    (defaut mesure le 2026-09-20, .sdd/6mig841-ameliorations/vram-et-transcription-report.md).
    """
    client = FauxOllama(['{"action": "avancer"}'])
    interp = LlmInterpreter(cfg, client=client)

    interp.interpreter("avance")

    assert client.appels[0].keep_alive == cfg["llm_keep_alive"]


# --------------------------------------------------------------------- mise en train (defaut 2026-09-20)

def test_demarrer_charge_le_modele_avec_le_keep_alive_et_le_num_ctx_configures(cfg):
    """
    demarrer() force un appel de mise en train des la construction du noeud (VRAM
    mesuree VIDE au demarrage, defaut 2), avec le meme modele, le meme keep_alive et le
    meme num_ctx que chaque appel reel, jamais un prompt vide configure differemment.
    """
    client = FauxOllama(['{"action": "avancer"}'])
    interp = LlmInterpreter(cfg, client=client)

    interp.demarrer()

    assert client.nb_appels == 1
    appel = client.appels[0]
    assert appel.model == cfg["llm_model"]
    assert appel.keep_alive == cfg["llm_keep_alive"]
    assert appel.options["num_ctx"] == cfg["llm_num_ctx"]


def test_demarrer_n_eleve_pas_si_le_client_echoue(cfg):
    """
    Un demon Ollama injoignable au demarrage du noeud ne doit pas empecher rclpy.spin
    (R8 attenue en avertissement) : le premier appel reel echouera alors normalement,
    demarrer() ne doit jamais lever.
    """
    interp = LlmInterpreter(cfg, client=OllamaQuiEchoue())

    interp.demarrer()  # ne doit pas lever
    assert "Ollama injoignable" in interp.erreur_demarrage


# --------------------------------------------------------------------- chemins d'echec, un par cause

def test_interpreter_reponse_non_json_est_un_echec_qui_nomme_le_probleme(cfg):
    """Une reponse qui n'est pas du JSON produit ok=False et une erreur qui mentionne le JSON."""
    interp = LlmInterpreter(cfg, client=FauxOllama(["ceci n'est pas du JSON du tout"]))

    resultat = interp.interpreter("avance")

    assert resultat.ok is False
    assert "JSON" in resultat.erreur


def test_interpreter_json_qui_n_est_pas_un_objet_est_un_echec_qui_nomme_le_probleme(cfg):
    """Un JSON valide mais qui n'est pas un objet (une liste) produit ok=False et le dit."""
    interp = LlmInterpreter(cfg, client=FauxOllama(["[1, 2]"]))

    resultat = interp.interpreter("avance")

    assert resultat.ok is False
    assert "objet" in resultat.erreur


def test_interpreter_json_sans_champ_action_est_un_echec_qui_nomme_le_probleme(cfg):
    """Un objet JSON sans champ 'action' produit ok=False et l'erreur nomme le champ manquant."""
    interp = LlmInterpreter(cfg, client=FauxOllama(['{"justification": "je ne sais pas"}']))

    resultat = interp.interpreter("avance")

    assert resultat.ok is False
    assert "action" in resultat.erreur


def test_interpreter_action_hors_enumeration_est_un_echec_qui_nomme_le_probleme(cfg):
    """Une valeur 'action' hors de l'enumeration declaree produit ok=False et nomme la valeur en cause."""
    interp = LlmInterpreter(cfg, client=FauxOllama(['{"action": "voler"}']))

    resultat = interp.interpreter("avance")

    assert resultat.ok is False
    assert "voler" in resultat.erreur
    assert "enumeration" in resultat.erreur


# --------------------------------------------------------------------- tentatives bornees

def test_interpreter_borne_les_tentatives_et_ne_bloque_jamais(cfg):
    """
    Un modele qui ne renvoie jamais de JSON exploitable ne fait PAS boucler
    interpreter() indefiniment : elle rend la main apres exactement
    llm_max_attempts appels, jamais plus, jamais moins.
    """
    client = FauxOllama(["toujours la meme reponse-poubelle"])

    interp = LlmInterpreter(cfg, client=client)
    resultat = interp.interpreter("avance")

    assert resultat.ok is False
    assert client.nb_appels == cfg["llm_max_attempts"]
    assert resultat.tentatives == cfg["llm_max_attempts"]


@pytest.mark.parametrize("client_qui_leve", [OllamaQuiEchoue(), OllamaLent()],
                        ids=["exception_generique", "timeout"])
def test_client_qui_leve_est_rattrape_et_rapporte_sans_se_propager(cfg, client_qui_leve):
    """Une exception levee par le client (panne ou timeout) est rattrapee et rapportee, jamais propagee."""
    interp = LlmInterpreter(cfg, client=client_qui_leve)

    resultat = interp.interpreter("avance")  # ne doit pas lever

    assert resultat.ok is False
    assert resultat.erreur  # la cause est rapportee, pas juste "echec"
    assert client_qui_leve.appels == cfg["llm_max_attempts"]  # bornee, meme sous exception


def test_garbage_puis_bonne_reponse_reussit_a_la_deuxieme_tentative(cfg):
    """Une premiere reponse-poubelle suivie d'un JSON valide reussit, et tentatives vaut exactement 2."""
    client = FauxOllama(["pas du JSON", '{"action": "tourner", "is_clockwise": false}'])
    interp = LlmInterpreter(cfg, client=client)

    resultat = interp.interpreter("tourne a gauche")

    assert resultat.ok
    assert resultat.tentatives == 2
    assert resultat.plan.etapes[0].nom == "tourner"
    assert client.nb_appels == 2


# --------------------------------------------------------------------- controle negatif

def test_commande_vide_echoue_sans_appeler_le_client_du_tout(cfg):
    """
    Une commande vide echoue immediatement SANS appeler le client Ollama : controle
    negatif, le nombre d'appels doit rester a zero.
    """
    client = FauxOllama(["peu importe, ne devrait jamais servir"])
    interp = LlmInterpreter(cfg, client=client)

    resultat = interp.interpreter("")

    assert resultat.ok is False
    assert client.nb_appels == 0


def test_commande_uniquement_des_espaces_echoue_sans_appeler_le_client(cfg):
    """Une commande faite uniquement d'espaces est traitee comme vide : aucun appel au client."""
    client = FauxOllama(["peu importe, ne devrait jamais servir"])
    interp = LlmInterpreter(cfg, client=client)

    resultat = interp.interpreter("   ")

    assert resultat.ok is False
    assert client.nb_appels == 0


# --------------------------------------------------------------------- l'historique (plan04, amelioration B)

def test_interpreter_transmet_l_historique_forme_dans_l_invite(cfg):
    """Un historique non vide passe a interpreter() se retrouve tel quel dans le prompt envoye au modele."""
    client = FauxOllama(['{"action": "tourner", "is_clockwise": true}'])
    interp = LlmInterpreter(cfg, client=client)

    interp.interpreter("et maintenant tourne a droite",
                       historique="Historique recent :\n- avance de deux metres -> avancer")

    assert "avance de deux metres -> avancer" in client.appels[0].prompt


def test_interpreter_sans_historique_ne_pollue_pas_le_prompt(cfg):
    """Controle negatif : historique omis (defaut ''), aucun bloc 'Historique recent' n'apparait dans le prompt."""
    client = FauxOllama(['{"action": "avancer"}'])
    interp = LlmInterpreter(cfg, client=client)

    interp.interpreter("avance")

    assert "Historique recent" not in client.appels[0].prompt


# --------------------------------------------------------------------- la sequence (plan04, amelioration C)

def test_interpreter_sequence_rend_un_plan_a_plusieurs_etapes(cfg):
    """Une reponse action='sequence' avec un champ etapes rend un Plan a autant d'etapes."""
    reponse = (
        '{"action": "sequence", "etapes": ['
        '{"action": "avancer"}, {"action": "tourner", "is_clockwise": false}]}'
    )
    client = FauxOllama([reponse])
    interp = LlmInterpreter(cfg, client=client)

    resultat = interp.interpreter("avance puis tourne a gauche")

    assert resultat.ok
    assert len(resultat.plan) == 2
    assert [a.nom for a in resultat.plan.etapes] == ["avancer", "tourner"]


def test_interpreter_sequence_sans_champ_etapes_est_un_echec_qui_nomme_le_probleme(cfg):
    """action='sequence' sans champ 'etapes' exploitable est un echec motive, jamais un plan vide accepte."""
    client = FauxOllama(['{"action": "sequence"}'])
    interp = LlmInterpreter(cfg, client=client)

    resultat = interp.interpreter("fais quelque chose")

    assert resultat.ok is False
    assert "etapes" in resultat.erreur


def test_interpreter_sequence_trop_longue_est_un_echec_qui_nomme_la_borne(cfg):
    """Une sequence de plus de sequence_max_etapes etapes est refusee, motif nommant la borne."""
    borne = int(cfg["bornes"]["sequence_max_etapes"])
    etapes_brutes = ", ".join('{"action": "avancer"}' for _ in range(borne + 1))
    client = FauxOllama([f'{{"action": "sequence", "etapes": [{etapes_brutes}]}}'])
    interp = LlmInterpreter(cfg, client=client)

    resultat = interp.interpreter("enchaine beaucoup de mouvements")

    assert resultat.ok is False
    assert str(borne) in resultat.erreur


# --------------------------------------------------------------------- le catalogue sous-ensemblable (plan04, amelioration D)

def test_sous_ensemble_reduit_reduit_l_enumeration_exposee(cfg):
    """Un sous-ensemble declare reduit l'enumeration du schema a ses seuls membres."""
    interp = LlmInterpreter(cfg, client=FauxOllama(['{"action": "avancer"}']),
                            sous_ensemble="minimal")

    assert interp.schema["properties"]["action"]["enum"] == sorted(cfg["sous_ensembles"]["minimal"])


def test_sans_sous_ensemble_rien_ne_change_pour_les_appelants_existants(cfg):
    """
    Controle negatif : omettre sous_ensemble expose le catalogue COMPLET avec la
    sequence activee, exactement le comportement d'avant l'introduction des
    sous-ensembles.
    """
    interp = LlmInterpreter(cfg, client=FauxOllama(['{"action": "avancer"}']))

    enum_attendue = sorted(cfg["actions"]) + ["sequence"]
    assert interp.schema["properties"]["action"]["enum"] == enum_attendue
    assert "etapes" in interp.schema["properties"]


def test_sous_ensemble_inconnu_leve_keyerror_listant_les_noms_declares(cfg):
    """Un nom de sous-ensemble absent de devoir2.sous_ensembles leve KeyError qui liste les noms declares."""
    with pytest.raises(KeyError) as exc_info:
        LlmInterpreter(cfg, client=FauxOllama(['{"action": "avancer"}']),
                       sous_ensemble="inexistant")

    message = str(exc_info.value)
    for nom in cfg["sous_ensembles"]:
        assert nom in message
