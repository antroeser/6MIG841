"""
test_state_machine.py - Tests de la machine de dialogue du Devoir 2 (state_machine.py).

Aucune entree-sortie ici : la machine ne parle ni au micro, ni a Ollama, ni a la
tortue, donc toute sa logique se teste sans rien de materiel (workflow.md R5). Le
coeur du devoir tient dans la difference entre les DEUX confirmations
(CONFIRMATION_COMMANDE : la parole a-t-elle ete bien ENTENDUE ? CONFIRMATION_ACTION :
la LLM a-t-elle bien TRADUIT ?), et c'est ce que les rendus etudiants confondaient.

Depuis plan04 (amelioration A), le sens d'un mouvement passe par un BOOLEEN
(`is_forward`, `is_clockwise`) plutot que par le signe d'un nombre rendu par le
modele : `signer()` est le seul endroit qui decide ce signe, et les six tests de la
section « le sens par booleen » ci-dessous en sont la preuve, en quatre paires
opposees (un signe constant passerait un test unilateral). Depuis plan04
(amelioration C), une commande simple rend un `Plan` a une seule etape, exactement
comme une commande composee en rend un a plusieurs : `MachineDialogue.interprete()`
prend donc desormais un `Plan`, jamais une `Action` nue.
"""

from __future__ import annotations

import pytest

from state_machine import (
    Action,
    Etat,
    Plan,
    Reponse,
    action_depuis_config,
    interpreter_reponse,
    signer,
    MachineDialogue,
)


def _nouvelle_machine(cfg) -> MachineDialogue:
    """Fabrique une machine fraiche avec les listes de mots de la configuration reelle."""
    return MachineDialogue(
        mots_accord=cfg["affirmative_words"],
        mots_refus=cfg["negative_words"],
        mots_sortie=cfg["quit_words"],
    )


def _plan_avancer(cfg) -> Plan:
    """Un Plan a une seule etape, l'action 'avancer' construite depuis la config reelle."""
    return Plan((action_depuis_config("avancer", cfg["actions"]),))


# --------------------------------------------------------------------- chemin nominal

def test_chemin_nominal_visite_les_cinq_etats_dans_l_ordre_et_revient_a_ecoute(cfg):
    """Le chemin nominal complet visite ECOUTE->CONFIRMATION_COMMANDE->INTERPRETATION->CONFIRMATION_ACTION->EXECUTION->ECOUTE."""
    machine = _nouvelle_machine(cfg)
    assert machine.etat is Etat.ECOUTE

    machine.entendu("avance")
    assert machine.etat is Etat.CONFIRMATION_COMMANDE

    machine.repondu("oui")
    assert machine.etat is Etat.INTERPRETATION

    plan = _plan_avancer(cfg)
    machine.interprete(plan)
    assert machine.etat is Etat.CONFIRMATION_ACTION

    machine.repondu("oui")
    assert machine.etat is Etat.EXECUTION

    machine.execute()
    assert machine.etat is Etat.ECOUTE


# ------------------------------------------------ la claim qui compte : deux refus, deux destinations

def test_refus_en_confirmation_commande_renvoie_a_ecoute_jamais_a_interpretation(cfg):
    """
    Garde contre le defaut du rendu Devoir2-2 : il renvoyait TOUJOURS a
    INTERPRETATION, y compris quand la phrase elle-meme avait ete mal entendue, ce qui
    bouclait indefiniment sur une phrase erronee. Un refus a CONFIRMATION_COMMANDE
    doit renvoyer ECOUTER (on redemande la phrase), jamais INTERPRETER une phrase que
    l'utilisateur vient de desavouer.
    """
    machine = _nouvelle_machine(cfg)
    machine.entendu("avance")
    assert machine.etat is Etat.CONFIRMATION_COMMANDE

    transition = machine.repondu("non")

    assert machine.etat is Etat.ECOUTE
    assert machine.etat is not Etat.INTERPRETATION
    assert transition.etat is Etat.ECOUTE
    assert machine.commande == ""  # la phrase mal entendue est oubliee


def test_refus_en_confirmation_action_renvoie_a_interpretation_jamais_a_ecoute(cfg):
    """
    Garde contre le defaut du rendu Devoir2-3 : il renvoyait TOUJOURS a ECOUTE, y
    compris quand la phrase avait ete bien comprise et que seule la TRADUCTION de la
    LLM etait fausse, ce qui faisait reparler l'utilisateur pour rien. Un refus a
    CONFIRMATION_ACTION doit renvoyer INTERPRETER la MEME phrase, jamais reecouter.
    """
    machine = _nouvelle_machine(cfg)
    machine.entendu("avance")
    machine.repondu("oui")
    plan = _plan_avancer(cfg)
    machine.interprete(plan)
    assert machine.etat is Etat.CONFIRMATION_ACTION
    commande_avant_refus = machine.commande

    transition = machine.repondu("non")

    assert machine.etat is Etat.INTERPRETATION
    assert machine.etat is not Etat.ECOUTE
    assert transition.etat is Etat.INTERPRETATION
    assert machine.commande == commande_avant_refus  # la phrase survit au refus
    assert machine.plan is None  # seul le plan refuse est oublie


# --------------------------------------------------------------------- interpreter_reponse()

def test_interpreter_reponse_oui_seul_est_un_accord(cfg):
    """'oui' seul est classe ACCORD."""
    resultat = interpreter_reponse("oui", cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])
    assert resultat is Reponse.ACCORD


def test_interpreter_reponse_oui_c_est_correct_est_un_accord(cfg):
    """
    'oui c'est correct' est ACCORD : le rendu etudiant testait l'EGALITE stricte avec
    la chaine "oui" (`if reponse != "oui"`), ce qui aurait classe cette phrase pourtant
    naturelle a l'oral comme un REFUS. Ici, on cherche la PRESENCE du mot dans la
    phrase, jamais l'egalite de la phrase entiere.
    """
    resultat = interpreter_reponse("oui c'est correct", cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])
    assert resultat is Reponse.ACCORD


def test_interpreter_reponse_non_seul_est_un_refus(cfg):
    """'non' seul est classe REFUS."""
    resultat = interpreter_reponse("non", cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])
    assert resultat is Reponse.REFUS


def test_interpreter_reponse_quitter_seul_est_une_sortie(cfg):
    """'quitter' seul est classe SORTIE."""
    resultat = interpreter_reponse("quitter", cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])
    assert resultat is Reponse.SORTIE


def test_interpreter_reponse_non_quitter_est_une_sortie_la_sortie_gagne_sur_le_refus(cfg):
    """
    'non, quitter' est SORTIE et non REFUS : claim d'ORDONNANCEMENT explicite, la
    sortie est testee avant l'accord et le refus dans interpreter_reponse.
    """
    resultat = interpreter_reponse("non, quitter", cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])
    assert resultat is Reponse.SORTIE


def test_interpreter_reponse_accord_et_refus_dans_la_meme_phrase_est_indecis(cfg):
    """Une phrase portant a la fois un mot d'accord ('oui') et un mot de refus ('non') est INDECIS."""
    resultat = interpreter_reponse("oui mais non", cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])
    assert resultat is Reponse.INDECIS


def test_interpreter_reponse_texte_vide_est_indecis(cfg):
    """Une transcription vide est INDECIS, jamais une erreur ni un refus par defaut."""
    resultat = interpreter_reponse("", cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])
    assert resultat is Reponse.INDECIS


def test_interpreter_reponse_phrase_hors_sujet_est_indecis(cfg):
    """Une phrase ne portant aucun mot connu (ni accord, ni refus, ni sortie) est INDECIS."""
    resultat = interpreter_reponse("il fait beau aujourd'hui", cfg["affirmative_words"],
                                   cfg["negative_words"], cfg["quit_words"])
    assert resultat is Reponse.INDECIS


# --------------------------------------------------------------------- INDECIS et sortie directe

def test_indecis_en_confirmation_commande_ne_change_pas_l_etat_et_repose_la_question(cfg):
    """Une reponse INDECIS en CONFIRMATION_COMMANDE laisse l'etat inchange et produit un message a redire."""
    machine = _nouvelle_machine(cfg)
    machine.entendu("avance")
    assert machine.etat is Etat.CONFIRMATION_COMMANDE

    transition = machine.repondu("peut-etre")

    assert machine.etat is Etat.CONFIRMATION_COMMANDE
    assert transition.etat is Etat.CONFIRMATION_COMMANDE
    assert transition.message  # une question est reposee, pas de reponse muette


def test_mot_de_sortie_prononce_en_ecoute_va_directement_a_arret(cfg):
    """Un mot de sortie prononce en ECOUTE va directement a ARRET, sans passer par une confirmation."""
    machine = _nouvelle_machine(cfg)
    transition = machine.entendu("quitter")
    assert machine.etat is Etat.ARRET
    assert transition.etat is Etat.ARRET


# --------------------------------------------------------------------- echec d'interpretation

def test_echec_interpretation_vide_la_commande_et_revient_a_ecoute(cfg):
    """echec_interpretation() (toutes les tentatives LLM epuisees) revient a ECOUTE et vide la commande."""
    machine = _nouvelle_machine(cfg)
    machine.entendu("avance")
    machine.repondu("oui")
    assert machine.etat is Etat.INTERPRETATION

    transition = machine.echec_interpretation("le modele n'a jamais rendu de JSON valide")

    assert machine.etat is Etat.ECOUTE
    assert transition.etat is Etat.ECOUTE
    assert machine.commande == ""


# --------------------------------------------------------------------- chemins d'echec : mauvais etat

def test_evenement_interprete_dans_le_mauvais_etat_leve_runtimeerror_nommant_les_etats(cfg):
    """.interprete() appele en ECOUTE (etat attendu : interpretation) leve RuntimeError nommant les deux etats."""
    machine = _nouvelle_machine(cfg)
    plan = _plan_avancer(cfg)

    with pytest.raises(RuntimeError) as exc_info:
        machine.interprete(plan)

    message = str(exc_info.value)
    assert Etat.ECOUTE.value in message
    assert Etat.INTERPRETATION.value in message


def test_evenement_repondu_dans_le_mauvais_etat_leve_runtimeerror_nommant_les_etats(cfg):
    """.repondu() appele en ECOUTE (etats attendus : les deux confirmations) leve RuntimeError nommant les trois etats."""
    machine = _nouvelle_machine(cfg)

    with pytest.raises(RuntimeError) as exc_info:
        machine.repondu("oui")

    message = str(exc_info.value)
    assert Etat.ECOUTE.value in message
    assert Etat.CONFIRMATION_COMMANDE.value in message
    assert Etat.CONFIRMATION_ACTION.value in message


def test_evenement_execute_dans_le_mauvais_etat_leve_runtimeerror_nommant_les_etats(cfg):
    """.execute() appele en ECOUTE (etat attendu : execution) leve RuntimeError nommant les deux etats."""
    machine = _nouvelle_machine(cfg)

    with pytest.raises(RuntimeError) as exc_info:
        machine.execute()

    message = str(exc_info.value)
    assert Etat.ECOUTE.value in message
    assert Etat.EXECUTION.value in message


# --------------------------------------------------------------------- action_depuis_config()

def test_action_depuis_config_nom_inconnu_leve_keyerror_listant_les_noms_connus(cfg):
    """Un nom d'action absent de la configuration leve KeyError qui liste les noms d'actions connus."""
    with pytest.raises(KeyError) as exc_info:
        action_depuis_config("voler", cfg["actions"])

    message = str(exc_info.value)
    for nom in cfg["actions"]:
        assert nom in message


def test_action_depuis_config_lit_les_vitesses_de_la_configuration(cfg):
    """action_depuis_config() construit une Action dont linear_speed/angular_speed/duree_s viennent de la config, pas d'ailleurs."""
    action = action_depuis_config("tourner", cfg["actions"])
    attendu = cfg["actions"]["tourner"]
    assert abs(action.linear) == pytest.approx(attendu["linear_speed"])
    assert abs(action.angular) == pytest.approx(attendu["angular_speed"])
    assert action.duree_s == pytest.approx(attendu["duree_s"])


# --------------------------------------------------------------------- historique (transitions)

def test_historique_enregistre_chaque_transition_comme_from_to_message(cfg):
    """Chaque evenement pousse ajoute a l'historique un triplet (etat_source, etat_cible, message)."""
    machine = _nouvelle_machine(cfg)

    t1 = machine.entendu("avance")
    t2 = machine.repondu("oui")
    plan = _plan_avancer(cfg)
    t3 = machine.interprete(plan)

    assert len(machine.historique) == 3
    assert machine.historique[0] == (Etat.ECOUTE, Etat.CONFIRMATION_COMMANDE, t1.message)
    assert machine.historique[1] == (Etat.CONFIRMATION_COMMANDE, Etat.INTERPRETATION, t2.message)
    assert machine.historique[2] == (Etat.INTERPRETATION, Etat.CONFIRMATION_ACTION, t3.message)


# --------------------------------------------------------------------- le sens par booleen (plan04, amelioration A)
#
# Quatre paires OPPOSEES : un signe constant (par exemple angular toujours negatif)
# passerait un test unilateral. C'est exactement le defaut mesure le 2026-09-18 (le
# modele rendait +90 pour "a droite" ET pour "a gauche"), donc chaque paire compare
# les deux sens plutot que d'affirmer un seul cas.

def test_signer_is_forward_vrai_rend_une_vitesse_lineaire_positive():
    """is_forward vrai -> vitesse lineaire positive."""
    linear, _ = signer(2.0, 0.0, is_forward=True, is_clockwise=False)
    assert linear > 0.0


def test_signer_is_forward_faux_rend_une_vitesse_lineaire_negative():
    """is_forward faux -> vitesse lineaire negative. Paire opposee au test precedent."""
    linear, _ = signer(2.0, 0.0, is_forward=False, is_clockwise=False)
    assert linear < 0.0


def test_signer_is_clockwise_vrai_rend_une_vitesse_angulaire_negative():
    """
    is_clockwise vrai (tourner a droite) -> vitesse angulaire NEGATIVE, convention
    REP-103 (axe z vers le haut, antihoraire positif, horaire negatif).
    """
    _, angular = signer(0.0, 1.6, is_forward=True, is_clockwise=True)
    assert angular < 0.0


def test_signer_is_clockwise_faux_rend_une_vitesse_angulaire_positive():
    """is_clockwise faux (tourner a gauche) -> vitesse angulaire positive. Paire opposee."""
    _, angular = signer(0.0, 1.6, is_forward=True, is_clockwise=False)
    assert angular > 0.0


def test_action_depuis_config_distance_hors_borne_est_ramenee_au_maximum(cfg):
    """
    distance_m demandee a 999 est ramenee a bornes.distance_m_max : le schema JSON
    borne deja cote modele, le code borne A NOUVEAU (R9), sans faire confiance a un
    appelant direct (un test, par exemple) qui ne passerait pas par ce schema.
    """
    action = action_depuis_config("avancer", cfg["actions"],
                                  params={"distance_m": 999.0}, bornes=cfg["bornes"])
    assert action.distance_m == pytest.approx(cfg["bornes"]["distance_m_max"])


def test_action_depuis_config_reculer_sans_parametre_rend_une_vitesse_lineaire_negative(cfg):
    """
    Regression mesuree le 2026-09-19 : la LLM omet systematiquement is_forward pour
    une commande simple, se fiant au nom de l'action. 'reculer' declare donc
    is_forward_defaut=false dans la configuration : sans lui, un defaut global
    unique (vrai) donnait une vitesse lineaire POSITIVE pour reculer.
    """
    action = action_depuis_config("reculer", cfg["actions"])
    assert action.is_forward is False
    assert action.linear < 0.0


def test_action_depuis_config_sans_parametre_applique_les_valeurs_par_defaut_de_la_config(cfg):
    """Aucun parametre fourni -> les valeurs par defaut de la configuration s'appliquent (is_forward vrai, is_clockwise faux, distance_m/angle_deg de l'entree)."""
    action = action_depuis_config("tourner", cfg["actions"])
    attendu = cfg["actions"]["tourner"]
    assert action.is_forward is True
    assert action.is_clockwise is False
    assert action.distance_m == pytest.approx(attendu["distance_m"])
    assert action.angle_deg == pytest.approx(attendu["angle_deg"])


# --------------------------------------------------------------------- Plan (plan04, amelioration C)

def test_plan_vide_leve_valueerror():
    """Un Plan sans aucune etape leve ValueError des sa construction : il n'y aurait rien a confirmer."""
    with pytest.raises(ValueError):
        Plan(())


def test_plan_a_une_etape_describe_rend_la_description_de_l_unique_action(cfg):
    """describe() d'un Plan a une seule etape rend exactement la description de cette action, sans numerotation."""
    action = action_depuis_config("avancer", cfg["actions"])
    plan = Plan((action,))
    assert plan.describe() == action.describe()


def test_plan_a_plusieurs_etapes_describe_les_numerote(cfg):
    """describe() d'un Plan a plusieurs etapes numerote chaque action, dans l'ordre."""
    a1 = action_depuis_config("avancer", cfg["actions"])
    a2 = action_depuis_config("tourner", cfg["actions"], params={"is_clockwise": True})
    plan = Plan((a1, a2))
    description = plan.describe()
    assert "1." in description
    assert "2." in description
    assert len(plan) == 2
