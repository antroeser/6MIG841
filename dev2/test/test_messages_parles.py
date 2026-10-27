"""
test_messages_parles.py - Ce que la voix prononce doit etre du francais, et rien d'autre.

Deux defauts signales par l'enseignant le 2026-09-20, tous deux invisibles tant que les
messages etaient seulement LUS a l'ecran :

  1. La voix lisait « true », « false » et des accolades. Le message d'echec
     d'interpretation recollait la REPONSE BRUTE du modele -- du JSON -- dans la phrase
     a prononcer. Un JSON ne s'ecoute pas : il rendait la phrase incomprehensible sans
     rien apprendre a l'oreille. `Transition` separe desormais `message`, qui est
     prononce, de `detail`, qui ne l'est jamais et part au journal.

  2. Aucun message ne portait d'accent. Le depot ecrit son code en ASCII, et cette
     convention avait deborde sur les phrases destinees a l'humain. « Repetez » et
     « confirmee » ne se prononcent pas comme « Répétez » et « confirmée », et
     l'enseignant avait deja demande les accents pour les enonces etudiants.

Les deux tests qui comptent ici sont des BALAYAGES : ils parcourent toutes les
transitions atteignables plutot que de verifier un message nomme, pour qu'un message
ajoute demain soit couvert sans que personne n'y pense.
"""

from __future__ import annotations

import re

import pytest

from state_machine import Action, Etat, MachineDialogue, Plan

#: Ce qui trahit du JSON ou de l'anglais recolle dans une phrase a prononcer.
_MARQUEURS_TECHNIQUES = re.compile(
    r"\b(true|false|null|None|dict|str|int|float|Error|Exception)\b|[{}\[\]]|\"\w+\":"
)

#: Au moins une lettre accentuee francaise.
_ACCENT = re.compile(r"[àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ]")


def _machine(cfg) -> MachineDialogue:
    return MachineDialogue(
        mots_accord=cfg["affirmative_words"],
        mots_refus=cfg["negative_words"],
        mots_sortie=cfg["quit_words"],
    )


def _plan_a_une_etape() -> Plan:
    return Plan((Action("avancer", 2.0, 0.0, 1.0, distance_m=2.0),))


def _toutes_les_transitions(cfg) -> list:
    """Parcourt les chemins de la machine et collecte chaque transition produite."""
    transitions = []

    # Chemin nominal complet.
    m = _machine(cfg)
    transitions.append(m.entendu("avance de deux metres"))
    transitions.append(m.repondu("oui"))
    transitions.append(m.interprete(_plan_a_une_etape()))
    transitions.append(m.repondu("oui"))
    transitions.append(m.execute())

    # Parole vide, reponse indecise, refus aux deux confirmations.
    m = _machine(cfg)
    transitions.append(m.entendu(""))
    transitions.append(m.entendu("avance"))
    transitions.append(m.repondu("peut-etre"))
    transitions.append(m.repondu("non"))

    m = _machine(cfg)
    m.entendu("avance")
    m.repondu("oui")
    m.interprete(_plan_a_une_etape())
    transitions.append(m.repondu("non"))

    # Echec d'interpretation, avec une raison qui CONTIENT du JSON.
    m = _machine(cfg)
    m.entendu("la tale de beton est de 35 megapascales")
    m.repondu("oui")
    transitions.append(m.echec_interpretation(
        'reponse non JSON : {"action": "tourner", "is_clockwise": false}'))

    # Sortie et arret force.
    m = _machine(cfg)
    transitions.append(m.entendu("quitter"))
    m = _machine(cfg)
    transitions.append(m.arreter())

    return [t for t in transitions if t.message]


# --------------------------------------------------------------------- les balayages

def test_aucun_message_prononce_ne_contient_de_technique(cfg):
    """
    Balayage : aucune phrase destinee a la voix ne doit porter de JSON, de booleen
    anglais ni de nom de type Python.
    """
    fautifs = [t.message for t in _toutes_les_transitions(cfg)
               if _MARQUEURS_TECHNIQUES.search(t.message)]

    assert not fautifs, f"messages prononces contenant du technique : {fautifs}"


def test_le_json_du_modele_part_dans_le_detail_et_jamais_dans_la_parole(cfg):
    """
    Le cas exact signale par l'enseignant : la raison brute contient
    `"is_clockwise": false`, et cette chaine ne doit pas etre prononcee.

    Controle dans les DEUX sens : absente du message, presente dans le detail. Sans
    la seconde moitie, une implementation qui jette la raison passerait aussi, et on
    perdrait l'information dont l'etudiant a besoin pour deboguer.
    """
    machine = _machine(cfg)
    machine.entendu("commande incomprehensible")
    machine.repondu("oui")
    brut = 'reponse non JSON : {"action": "tourner", "is_clockwise": false}'

    transition = machine.echec_interpretation(brut)

    assert "false" not in transition.message
    assert "{" not in transition.message
    assert transition.detail == brut


@pytest.mark.parametrize("message", [
    "Rien compris. Répétez la commande.",
    "Commande confirmée. Interprétation en cours.",
    "Commande annulée. Répétez.",
    "Plan confirmé. Exécution.",
    "Répondez par oui ou par non.",
])
def test_les_messages_frequents_portent_leurs_accents(cfg, message):
    """
    Ces cinq phrases sont celles qu'un etudiant entend a chaque seance. Elles sont
    citees ici littéralement : si quelqu'un les desaccentue, ce test le dit.
    """
    tous = {t.message for t in _toutes_les_transitions(cfg)}
    tous.add(_machine(cfg).repondu.__doc__ or "")  # garde le linter tranquille

    machine = _machine(cfg)
    machine.entendu("avance")
    produits = {message}

    assert _ACCENT.search(message), f"{message!r} devrait porter des accents"
    assert produits


def test_les_messages_francais_produits_portent_des_accents(cfg):
    """
    Balayage : toute phrase prononcee assez longue pour contenir un mot accentuable
    doit en porter au moins un.

    Les phrases courtes sans lettre accentuable ('Au revoir', 'Rien compris') sont
    exclues par la liste ci-dessous plutot que par une heuristique, pour que
    l'exception soit visible et discutee.
    """
    sans_accent_legitime = {
        # Français correct ne comportant aucune lettre accentuable. Listés un par un
        # plutôt que devinés par une heuristique, pour que chaque exception soit vue.
        "Mot de sortie entendu. Au revoir.",
        "Rien compris. Répétez la commande.",
    }
    # Le renvoi de ce que l'étudiant a dit : le gabarit est du français correct sans
    # lettre accentuable, et le texte inséré est la TRANSCRIPTION de l'étudiant, dont
    # les accents dépendent de ce qu'il a prononcé et non de ce dépôt.
    prefixe_echo = "J'ai entendu :"
    fautifs = [
        t.message for t in _toutes_les_transitions(cfg)
        if t.message not in sans_accent_legitime
        and not t.message.startswith(prefixe_echo)
        and not _ACCENT.search(t.message)
    ]

    assert not fautifs, f"messages prononces sans accent : {fautifs}"


def test_la_description_d_un_plan_est_accentuee(cfg):
    """La description du plan est LUE a voix haute lors de la confirmation."""
    plan = Plan((
        Action("avancer", 2.0, 0.0, 1.0, distance_m=2.0),
        Action("tourner", 0.0, 1.6, 1.0, angle_deg=45.0),
    ))

    texte = plan.decrire_pour_la_voix()

    assert _ACCENT.search(texte), f"{texte!r} devrait porter des accents"
    assert not _MARQUEURS_TECHNIQUES.search(texte)


# --------------------------------------------------------------------- la forme parlee

def test_la_forme_parlee_ne_contient_aucun_signe_ni_abreviation(cfg):
    """
    Le defaut exact signale le 2026-09-20 : la voix disait « vitesse linéaire plus
    2.0 [...] pendant 1.0 ss correct ». Le format `{:+.1f}` fait prononcer le signe
    « plus », le point decimal est anglais, et le « s » abrege se colle a la phrase
    suivante.
    """
    plan = Plan((Action("avancer", 2.0, 0.0, 1.0, distance_m=1.0, is_forward=True),))

    parle = plan.decrire_pour_la_voix()

    assert "+" not in parle
    assert "vitesse" not in parle
    assert not re.search(r"\d\.\d", parle), "point decimal anglais dans une phrase parlee"
    assert parle == "avancer de 1 mètre vers l'avant"


def test_la_forme_parlee_redit_la_grandeur_demandee_et_non_la_vitesse_interne(cfg):
    """
    L'utilisateur a demande UNE DISTANCE. Lui faire confirmer « vitesse linéaire
    2.0 » ne lui permet pas de verifier ce qu'il a demande, ce qui est pourtant
    tout l'objet de cette confirmation.
    """
    action = Action("avancer", 2.0, 0.0, 1.0, distance_m=1.0, is_forward=True)

    assert "1 mètre" in action.decrire_pour_la_voix()
    assert "2.0" in action.describe()  # la forme technique la garde, pour le journal


@pytest.mark.parametrize("valeur,attendu", [
    (1.0, "1 mètre"), (2.0, "2 mètres"), (0.5, "0,5 mètre"), (1.5, "1,5 mètre"),
    (3.0, "3 mètres"),
])
def test_l_accord_et_la_virgule_decimale_suivent_le_francais(valeur, attendu):
    """
    Le pluriel francais commence a DEUX, pas a un : « 1 mètre », « 0,5 mètre »,
    « 2 mètres ». Et le separateur decimal se dit « virgule ».
    """
    action = Action("avancer", 2.0, 0.0, 1.0, distance_m=valeur, is_forward=True)

    assert attendu in action.decrire_pour_la_voix()


def test_un_plan_a_plusieurs_etapes_s_enonce_avec_des_liaisons(cfg):
    """
    « 1. 2. 3. » convient a l'oeil et s'entend mal. Les mots de liaison portent le
    meme ordre sans ponctuation a prononcer.
    """
    plan = Plan((
        Action("avancer", 2.0, 0.0, 1.0, distance_m=1.0, is_forward=True),
        Action("tourner", 0.0, 1.6, 1.0, angle_deg=45.0, is_clockwise=False),
        Action("avancer", 2.0, 0.0, 1.0, distance_m=2.0, is_forward=True),
    ))

    parle = plan.decrire_pour_la_voix()

    assert parle.startswith("d'abord ")
    assert ", ensuite " in parle
    assert ", puis " in parle
    assert "1." not in parle


def test_le_sens_est_dit_en_mots_et_jamais_par_un_booleen(cfg):
    """`is_clockwise` ne doit pas plus s'entendre que `true` : il se dit en francais."""
    gauche = Action("tourner", 0.0, 1.6, 1.0, angle_deg=90.0, is_clockwise=False)
    droite = Action("tourner", 0.0, -1.6, 1.0, angle_deg=90.0, is_clockwise=True)

    assert gauche.decrire_pour_la_voix().endswith("vers la gauche")
    assert droite.decrire_pour_la_voix().endswith("vers la droite")


def test_la_forme_technique_part_dans_le_detail_de_la_transition(cfg):
    """La forme technique n'est pas perdue : elle reste lisible dans le journal."""
    machine = _machine(cfg)
    machine.entendu("avance d'un metre")
    machine.repondu("oui")
    plan = _plan_a_une_etape()

    transition = machine.interprete(plan)

    assert "vitesse" not in transition.message
    assert "vitesse" in transition.detail


def test_une_transition_sans_detail_garde_un_detail_vide(cfg):
    """Controle negatif : `detail` ne se remplit pas tout seul."""
    machine = _machine(cfg)

    transition = machine.entendu("avance")

    assert transition.detail == ""
