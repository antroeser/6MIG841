"""
state_machine.py - Machine d'etat du Devoir 2, sans aucune entree-sortie.

Le Devoir 2 demande une machine d'etat autour d'une LLM. Ce module EST cette machine :
il ne parle ni au microphone, ni a Ollama, ni a la tortue. Il recoit des evenements et
rend des transitions. C'est ce qui permet de tester toute la logique du devoir sans
micro, sans demon LLM et sans ROS2 (workflow.md R5).

Les cinq etats
--------------

    ECOUTE ──(parole comprise)──> CONFIRMATION_COMMANDE
      ^                                  │
      │                    (refus)       │ (accord)
      ├──────────────────────────────────┤
      │                                  v
      │                          INTERPRETATION ──(echec LLM)──> ECOUTE
      │                                  │
      │                        (plan propose)
      │                                  v
      ├──(refus)────────────── CONFIRMATION_ACTION
      │                                  │ (accord)
      │                                  v
      └──────────────────────────── EXECUTION ──> ECOUTE

    n'importe quel etat ──(mot de sortie)──> ARRET

Pourquoi DEUX confirmations
---------------------------
Les rendus etudiants en avaient deux aussi, mais implicitement et de facon incoherente.
Elles repondent a deux questions differentes, et les confondre coute une seance :

  - CONFIRMATION_COMMANDE : "ai-je bien ENTENDU ce que vous avez dit ?" La
    reconnaissance vocale se trompe, surtout en francais sur un micro d'ordinateur
    portable.
  - CONFIRMATION_ACTION : "la LLM a-t-elle bien TRADUIT votre phrase en mouvement ?"
    C'est une erreur d'un tout autre ordre, et c'est celle que les trois groupes ont
    rapportee comme la plus frequente.

Un refus a la premiere renvoie ecouter. Un refus a la seconde renvoie interpreter, pas
ecouter : la phrase etait bonne, c'est la traduction qui etait fausse. Le rendu
Devoir2-2 renvoyait toujours a l'interpretation, ce qui bouclait indefiniment sur une
phrase mal entendue ; le rendu Devoir2-3 renvoyait toujours a l'ecoute, ce qui faisait
reparler l'utilisateur alors que sa phrase etait correcte.

Le sens par booleen (plan04, amelioration A)
---------------------------------------------
Defaut mesure le 2026-09-18 : une LLM contrainte par schema a rendu +90 pour "tourne de
90 degres a droite" ET pour la meme commande a gauche. Le modele etait coherent avec
lui-meme : rien dans le schema ni dans l'invite ne declarait le sens positif, alors la
LLM devinait un signe. L'ontologie de ROSGPT ne signe pas les nombres, elle declare le
sens par un booleen : `move.is_forward`, `rotate.is_clockwise`. Un booleen ne peut pas
avoir le mauvais signe, c'est la seule correction structurelle possible.

`signer()` est desormais le SEUL endroit du solutionnaire qui decide un signe. La LLM,
et tout code appelant, ne fait jamais que porter `is_forward` / `is_clockwise` ;
`action_depuis_config()` borne les grandeurs recues (R9 : le schema borne, le code
borne a nouveau) puis delegue le signe a `signer()`.

La sequence (plan04, amelioration C)
--------------------------------------
`Plan` porte une ou plusieurs `Action`, dans l'ordre d'execution. Une commande simple
("avance") rend desormais un Plan a UNE etape, exactement comme une commande composee
("avance puis tourne a droite") en rend un a plusieurs : un seul mecanisme de
confirmation pour les deux cas, plutot qu'un chemin special pour le cas simple.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


class Etat(str, Enum):
    """Les cinq etats de la machine."""

    ECOUTE = "ecoute"
    CONFIRMATION_COMMANDE = "confirmation_commande"
    INTERPRETATION = "interpretation"
    CONFIRMATION_ACTION = "confirmation_action"
    EXECUTION = "execution"
    ARRET = "arret"


class Reponse(str, Enum):
    """Ce qu'une reponse de l'utilisateur veut dire."""

    ACCORD = "accord"
    REFUS = "refus"
    SORTIE = "sortie"
    INDECIS = "indecis"


def _nombre_parle(valeur: float) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Ecrire un nombre comme le francais le dit : virgule decimale, et pas de
        partie decimale inutile.

        Une synthese vocale francaise lit « 2.0 » comme « deux point zero » et
        « 1.0 » comme « un point zero ». Elle lit « 2 » comme « deux » et « 0,5 »
        comme « zéro virgule cinq », ce qui est ce qu'un humain dirait.

    Inputs:
        valeur (float): grandeur a enoncer

    Outputs:
        texte (str): '2', '0,5', '1,5'
    --------------------------------------------------------------------------
    """
    if float(valeur).is_integer():
        return str(int(valeur))
    return f"{valeur:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _accorder(unite: str, valeur: float) -> str:
    """
    Mettre l'unite au pluriel seulement a partir de deux.

    Le francais ecrit « 1 mètre », « 0,5 mètre » et « 2 mètres » : le pluriel
    commence a 2, pas a 1, contrairement a l'anglais qui pluralise des que la
    valeur differe de un. Sans cet accord la voix disait « 1 mètres ».
    """
    return unite if abs(valeur) < 2.0 else f"{unite}s"


@dataclass(frozen=True)
class Action:
    """
    Un mouvement a envoyer a la tortue.

    `linear` et `angular` sont les vitesses SIGNEES envoyees a la tortue (m/s, rad/s) :
    c'est ce que consomme `ihr_ros.turtle_io`. `distance_m` et `angle_deg` sont les
    grandeurs NON SIGNEES demandees par l'utilisateur (Step.msg du paquet
    d'interfaces porte exactement cette meme paire, non signee, gele au plan01).
    `is_forward` et `is_clockwise` sont les booleens qui ont decide le signe : ils sont
    portes par l'Action elle-meme (et non redecidee ailleurs) pour que tout appelant en
    aval -- dialogue_manager_node en particulier -- lise le sens au lieu de le
    redevine depuis un nom d'action ou une valeur numerique.
    """

    nom: str
    linear: float
    angular: float
    duree_s: float
    distance_m: float = 0.0
    angle_deg: float = 0.0
    is_forward: bool = True
    is_clockwise: bool = False

    def describe(self) -> str:
        """
        Forme TECHNIQUE, pour le journal et les tests : vitesses signees envoyees a
        la tortue. Elle n'est plus prononcee depuis le 2026-09-20 -- voir
        `decrire_pour_la_voix`.
        """
        return (f"{self.nom} : vitesse linéaire {self.linear:+.1f}, "
                f"vitesse angulaire {self.angular:+.1f}, pendant {self.duree_s:.1f} s")

    def decrire_pour_la_voix(self) -> str:
        """
        --------------------------------------------------------------------------
        Purpose:
            Dire l'action comme on la dirait a quelqu'un, pas comme on la debogue.

            Defaut signale par l'enseignant le 2026-09-20 : la synthese prononcait
            « avancé vitesse linéaire plus 2.0 vitesse angulaire plus 0.0 pendant
            1.0 ss correct ». Trois causes dans la seule forme technique :
            le format `{:+.1f}` fait lire le signe « plus », le point decimal est
            anglais alors que le francais dit « virgule », et le « s » abrege colle
            a la phrase suivante.

            Plus important : cette forme decrit les VITESSES INTERNES envoyees a la
            tortue, alors que l'utilisateur a demande une DISTANCE ou un ANGLE.
            Confirmer « vitesse lineaire 2.0 » quand on a dit « avance d'un metre »
            ne permet pas de verifier ce qu'on a demande, qui est tout l'objet de
            cette confirmation. On redit donc les grandeurs de l'utilisateur,
            `distance_m` et `angle_deg`, et le sens porte par les booleens.

    Inputs:
            aucun

        Outputs:
            phrase (str): francais accentue, sans signe ni abreviation
        --------------------------------------------------------------------------
        """
        if self.angle_deg > 0.0:
            sens = "vers la droite" if self.is_clockwise else "vers la gauche"
            return (f"tourner de {_nombre_parle(self.angle_deg)} "
                    f"{_accorder('degré', self.angle_deg)} {sens}")
        if self.distance_m > 0.0:
            sens = "vers l'avant" if self.is_forward else "vers l'arrière"
            return (f"avancer de {_nombre_parle(self.distance_m)} "
                    f"{_accorder('mètre', self.distance_m)} {sens}")
        return self.nom


@dataclass(frozen=True)
class Plan:
    """
    Sequence d'une ou plusieurs Action, dans l'ordre d'execution.

    Une commande simple rend un Plan a une seule etape ; une commande composee en rend
    un a plusieurs (plan04, amelioration C). Un plan vide leve ValueError des sa
    construction : il ferait confirmer le vide a l'utilisateur, ce qui n'a pas de sens,
    mieux vaut echouer ici plutot que plus loin dans la confirmation.
    """

    etapes: tuple[Action, ...]

    def __post_init__(self) -> None:
        if not self.etapes:
            raise ValueError(
                "Un plan sans aucune etape ne peut pas etre confirme par l'utilisateur : "
                "il n'y a rien a confirmer. Un plan vide est une erreur de construction, "
                "jamais un resultat valide."
            )

    def __len__(self) -> int:
        return len(self.etapes)

    def describe(self) -> str:
        """
        Phrase soumise a la confirmation de l'utilisateur : la description de l'unique
        action pour un plan a une etape, une liste numerotee pour un plan a plusieurs
        etapes -- c'est un meilleur exercice d'interaction que de ne jamais confirmer
        qu'un mouvement isole.
        """
        if len(self.etapes) == 1:
            return self.etapes[0].describe()
        lignes = [f"{i}. {etape.describe()}" for i, etape in enumerate(self.etapes, start=1)]
        return f"plan à {len(self.etapes)} étapes :\n" + "\n".join(lignes)

    def decrire_pour_la_voix(self) -> str:
        """
        Enoncer le plan a voix haute : une phrase pour une etape, une enumeration
        parlee ('d'abord ..., ensuite ..., puis ...') au-dela.

        Les numeros « 1. 2. 3. » de `describe` conviennent a l'oeil et s'entendent
        mal ; les mots de liaison disent la meme chose sans ponctuation a prononcer.
        """
        if len(self.etapes) == 1:
            return self.etapes[0].decrire_pour_la_voix()

        liaisons = ["d'abord", "ensuite"] + ["puis"] * (len(self.etapes) - 2)
        morceaux = [f"{liaison} {etape.decrire_pour_la_voix()}"
                    for liaison, etape in zip(liaisons, self.etapes)]
        return ", ".join(morceaux)


@dataclass
class Transition:
    """
    Resultat d'un evenement : l'etat atteint et ce qu'il faut dire a l'utilisateur.

    `message` est PRONONCE : il est ecrit en francais accentue et ne contient jamais
    de detail technique. `detail` ne l'est jamais : il porte la cause exacte, pour le
    journal et pour l'etudiant qui debogue.

    La separation date du 2026-09-20 et vient d'un defaut signale par l'enseignant :
    la synthese vocale francaise lisait « true », « false » et des accolades. Le
    message d'echec d'interpretation recollait la REPONSE BRUTE du modele, donc du
    JSON, dans la phrase a prononcer. Fondre les deux rendait la voix incomprehensible
    sans rien apprendre a l'oreille, puisqu'un JSON ne s'ecoute pas.
    """

    etat: Etat
    message: str = ""
    plan: Plan | None = None
    detail: str = ""


def _normaliser_pour_comparaison(texte: str) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Ramener une transcription et un mot du catalogue a une forme comparable,
        puis l'encadrer d'espaces pour que la recherche porte sur un MOT ENTIER.

        Corrige deux defauts mesures le 2026-09-20 sur les enregistrements de
        l'enseignant (CommandeAccepte.m4a), tous deux invisibles tant qu'on tapait
        les reponses au clavier :

        1. LA PONCTUATION. L'ancienne version cherchait " oui " dans
           " {texte} ". Or faster-whisper PONCTUE toujours : quelqu'un qui dit
           « oui » est transcrit « Oui. », donc " oui. ", ou " oui " ne se trouve
           pas. La reponse tombait en INDECIS et la question etait reposee
           indefiniment. C'est une cause, independante du microphone, des boucles
           signalees par l'enseignant.

        2. L'APOSTROPHE. « J'accepte. » ne peut s'ecrire comme un mot du
           catalogue sans que l'apostrophe soit traitee comme une frontiere de
           mot. Elle devient donc une espace, ce qui fait aussi de « d'accord »,
           deja au catalogue, une entree reconnue quand elle est prononcee.

        Les accents sont replies par la meme occasion : le catalogue ecrit
        « arreter le programme » sans accent, alors qu'une transcription reelle
        rend « arrêter ».

        Le MOT du catalogue passe par la MEME normalisation que le texte, sans
        quoi une entree accentuee ou apostrophee du catalogue ne se retrouverait
        jamais dans un texte normalise.

    Inputs:
        texte (str): transcription, ou mot du catalogue

    Outputs:
        normalise (str): minuscules, sans accent, ponctuation remplacee par des
            espaces, espaces multiples reduits, le tout encadre d'une espace
    --------------------------------------------------------------------------
    """
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", texte.lower())
        if not unicodedata.combining(c)
    )
    mots = "".join(
        c if (c.isalnum() or c.isspace()) else " "
        for c in sans_accent
    ).split()
    return f" {' '.join(mots)} "


def interpreter_reponse(texte: str,
                        mots_accord: Sequence[str],
                        mots_refus: Sequence[str],
                        mots_sortie: Sequence[str]) -> Reponse:
    """
    --------------------------------------------------------------------------
    Purpose:
        Classer une reponse parlee en accord, refus, sortie ou indecis.

        Les rendus etudiants testaient l'EGALITE stricte avec la chaine "oui"
        (`if reponse != "oui"`), si bien que "oui c'est correct", que l'on prononce
        naturellement, etait compris comme un refus. Le rapport Devoir2-1 note
        d'ailleurs que leur commande reelle etait "correct oui" et que seul le mot
        oui comptait. On cherche donc ici la PRESENCE d'un mot, pas l'egalite.

        La sortie est testee en premier : "non, quitter" doit quitter, pas refuser.
        Une phrase portant a la fois un accord et un refus est INDECIS et fait
        reposer la question, ce qu'aucun rendu etudiant ne faisait.

    Inputs:
        texte (str): transcription de la reponse
        mots_accord (Sequence): mots valant accord
        mots_refus (Sequence): mots valant refus
        mots_sortie (Sequence): mots valant demande de sortie

    Outputs:
        reponse (Reponse): classe de la reponse
    --------------------------------------------------------------------------
    """
    if not texte or not texte.strip():
        return Reponse.INDECIS

    normalise = _normaliser_pour_comparaison(texte)

    def contient(mots: Sequence[str]) -> bool:
        return any(_normaliser_pour_comparaison(mot).strip() and
                   _normaliser_pour_comparaison(mot) in normalise
                   for mot in mots)

    if contient(mots_sortie):
        return Reponse.SORTIE

    accord = contient(mots_accord)
    refus = contient(mots_refus)
    if accord and refus:
        return Reponse.INDECIS
    if accord:
        return Reponse.ACCORD
    if refus:
        return Reponse.REFUS
    return Reponse.INDECIS


@dataclass
class MachineDialogue:
    """
    Machine d'etat du dialogue. Aucun effet de bord : elle ne fait que transiter.

    L'appelant lui pousse des evenements (`entendu`, `repondu`, `interprete`,
    `echec_interpretation`, `execute`) et lit l'etat courant. Toute la boucle du
    Devoir 2 se reduit alors a : lire l'etat, faire l'entree-sortie correspondante,
    pousser l'evenement.

    `plan` (autrefois `action`, plan04) porte le Plan propose par l'interpretation en
    attente de confirmation, puis d'execution.
    """

    mots_accord: Sequence[str]
    mots_refus: Sequence[str]
    mots_sortie: Sequence[str]
    etat: Etat = Etat.ECOUTE
    commande: str = ""
    plan: Plan | None = None
    historique: list[tuple[Etat, Etat, str]] = field(default_factory=list)

    def _aller(self, etat: Etat, message: str = "", plan: Plan | None = None,
               detail: str = "") -> Transition:
        self.historique.append((self.etat, etat, message))
        self.etat = etat
        if plan is not None:
            self.plan = plan
        return Transition(etat, message, plan if plan is not None else self.plan,
                          detail)

    # ------------------------------------------------------------- evenements

    def entendu(self, texte: str) -> Transition:
        """
        --------------------------------------------------------------------------
        Purpose:
            Evenement : une phrase a ete transcrite en etat ECOUTE.

        Inputs:
            texte (str): transcription, vide si rien n'a ete compris

        Outputs:
            transition (Transition): etat atteint et message a dire
        --------------------------------------------------------------------------
        """
        self._exiger(Etat.ECOUTE)

        if not texte or not texte.strip():
            return self._aller(Etat.ECOUTE, "Rien compris. Répétez la commande.")

        if interpreter_reponse(texte, (), (), self.mots_sortie) is Reponse.SORTIE:
            return self._aller(Etat.ARRET, "Mot de sortie entendu. Au revoir.")

        self.commande = texte.strip()
        return self._aller(
            Etat.CONFIRMATION_COMMANDE,
            f"J'ai entendu : « {self.commande} ». Est-ce bien cela ?",
        )

    def repondu(self, texte: str) -> Transition:
        """
        --------------------------------------------------------------------------
        Purpose:
            Evenement : l'utilisateur a repondu a une question de confirmation.
            Le meme evenement sert aux deux confirmations, et c'est l'ETAT COURANT
            qui decide ou mene un refus.

        Inputs:
            texte (str): transcription de la reponse

        Outputs:
            transition (Transition): etat atteint et message a dire
        --------------------------------------------------------------------------
        """
        self._exiger(Etat.CONFIRMATION_COMMANDE, Etat.CONFIRMATION_ACTION)
        # Indice : l'etat courant decide ou mene un refus ; SORTIE et INDECIS d'abord
        # Tests : test_refus_en_confirmation_commande_renvoie_a_ecoute_jamais_a_interpretation, test_refus_en_confirmation_action_renvoie_a_interpretation_jamais_a_ecoute
        raise NotImplementedError(
            "fonction 'Transitions.repondu' a implementer (voir l'enonce et les tests cites)"
        )

    def interprete(self, plan: Plan) -> Transition:
        """
        --------------------------------------------------------------------------
        Purpose:
            Evenement : la LLM a propose un plan (une ou plusieurs etapes).

        Inputs:
            plan (Plan): plan de mouvement propose

        Outputs:
            transition (Transition): etat atteint et message a dire
        --------------------------------------------------------------------------
        """
        self._exiger(Etat.INTERPRETATION)
        return self._aller(
            Etat.CONFIRMATION_ACTION,
            # `decrire_pour_la_voix` et non `describe` depuis le 2026-09-20 : la
            # forme technique enoncait « vitesse linéaire plus 2.0 [...] 1.0 s »,
            # ou le signe se lit « plus », le point decimal est anglais et le « s »
            # abrege se colle a la phrase suivante. La forme parlee redit en outre
            # la DISTANCE demandee plutot que la vitesse interne, seule facon pour
            # l'utilisateur de verifier ce qu'il a demande. La forme technique reste
            # dans `detail`, pour le journal.
            f"Plan proposé : {plan.decrire_pour_la_voix()}. Est-ce correct ?",
            plan=plan,
            detail=plan.describe(),
        )

    def echec_interpretation(self, raison: str) -> Transition:
        """
        --------------------------------------------------------------------------
        Purpose:
            Evenement : la LLM n'a pas produit de plan exploitable, apres toutes
            ses tentatives. La machine revient ECOUTER plutot que de reessayer
            indefiniment, ce que faisait le rendu Devoir2-2.

        Inputs:
            raison (str): pourquoi l'interpretation a echoue

        Outputs:
            transition (Transition): etat atteint et message a dire
        --------------------------------------------------------------------------
        """
        self._exiger(Etat.INTERPRETATION)
        self.commande = ""
        self.plan = None
        # Le message PRONONCE ne porte jamais la raison technique : celle-ci contient
        # la reponse brute du modele, donc du JSON, et la voix lisait « true »,
        # « false » et des accolades (defaut signale par l'enseignant le 2026-09-20).
        # La raison part dans `detail`, pour le journal et pour l'etudiant qui debogue.
        return self._aller(
            Etat.ECOUTE,
            "Je n'ai pas réussi à traduire cette commande. Répétez, s'il vous plaît.",
            detail=raison,
        )

    def execute(self) -> Transition:
        """
        --------------------------------------------------------------------------
        Purpose:
            Evenement : le plan a ete envoye a la tortue.

        Inputs:
            aucun

        Outputs:
            transition (Transition): retour a l'ecoute
        --------------------------------------------------------------------------
        """
        self._exiger(Etat.EXECUTION)
        noms = " puis ".join(etape.nom for etape in self.plan.etapes) if self.plan else "plan"
        self.commande = ""
        self.plan = None
        return self._aller(Etat.ECOUTE, f"{noms} exécutée(s). Commande suivante.")

    def echec_execution(self, raison: str) -> Transition:
        """
        --------------------------------------------------------------------------
        Purpose:
            Revenir a l'ecoute quand le serveur d'action refuse ou interrompt un
            plan apres la confirmation de l'utilisateur.

        Inputs:
            raison (str): cause technique conservee dans le detail de transition

        Outputs:
            transition (Transition): etat ECOUTE et message vocal d'echec
        --------------------------------------------------------------------------
        """
        self._exiger(Etat.EXECUTION)
        self.commande = ""
        self.plan = None
        return self._aller(
            Etat.ECOUTE,
            "Le mouvement n'a pas pu être exécuté. Commande suivante.",
            detail=raison,
        )

    def arreter(self, raison: str = "Arrêt demandé.") -> Transition:
        """
        Forcer l'arret depuis n'importe quel etat.

        `raison` est PRONONCEE : elle est donc ecrite en francais accentue, comme
        tout `Transition.message` (2026-09-20). Un appelant qui passe une raison
        technique doit la mettre dans le journal, pas ici.
        """
        return self._aller(Etat.ARRET, raison)

    # ------------------------------------------------------------------ garde

    def _exiger(self, *etats: Etat) -> None:
        if self.etat not in etats:
            attendus = ", ".join(e.value for e in etats)
            raise RuntimeError(
                f"Evenement recu dans l'etat '{self.etat.value}', attendu parmi "
                f"[{attendus}]. Une machine d'etat qui accepte n'importe quel "
                "evenement dans n'importe quel etat n'est pas une machine d'etat."
            )


def signer(linear_speed: float, angular_speed: float,
           is_forward: bool, is_clockwise: bool) -> tuple[float, float]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Decider le signe des vitesses lineaire et angulaire. SEUL endroit du
        solutionnaire ou un signe est decide (plan04, amelioration A) : le modele
        n'y participe jamais, il ne fait que porter le sens par un booleen, comme
        les actions `move`/`rotate` de l'ontologie ROSGPT (`is_forward`,
        `is_clockwise`) plutot que par le signe d'un nombre qu'il rendrait.

        Convention REP-103 : l'axe z pointe vers le haut, donc le sens antihoraire
        (vers la gauche) est positif et le sens horaire (vers la droite) est
        negatif.

    Inputs:
        linear_speed (float): grandeur NON SIGNEE (m/s)
        angular_speed (float): grandeur NON SIGNEE (rad/s)
        is_forward (bool): vrai pour avancer, faux pour reculer
        is_clockwise (bool): vrai pour tourner a droite (horaire), faux pour
            tourner a gauche (antihoraire)

    Outputs:
        (linear, angular) (tuple[float, float]): vitesses SIGNEES
    --------------------------------------------------------------------------
    """
    # Indice : convention REP-103 : antihoraire positif, horaire negatif
    # Tests : test_signer_is_forward_vrai_rend_une_vitesse_lineaire_positive, test_signer_is_clockwise_vrai_rend_une_vitesse_angulaire_negative
    raise NotImplementedError(
        "fonction 'signer' a implementer (voir l'enonce et les tests cites)"
    )


def _borner(valeur: float, maximum: float | None) -> float:
    """Ramener une grandeur non signee dans [0, maximum] (R9 : le code borne a nouveau)."""
    valeur = max(0.0, float(valeur))
    if maximum is not None:
        valeur = min(valeur, float(maximum))
    return valeur


def action_depuis_config(nom: str, actions_cfg: dict[str, Any],
                         params: dict[str, Any] | None = None,
                         bornes: dict[str, Any] | None = None) -> Action:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire une Action a partir de la table d'actions de la configuration.
        Un nom absent est une erreur qui liste les noms connus, jamais un
        mouvement par defaut : une tortue qui avance parce que le nom d'action
        n'a pas ete reconnu est exactement ce qu'il ne faut pas.

        `params` porte ce que la LLM (ou l'appelant) a fourni : `is_forward`,
        `is_clockwise`, `distance_m`, `angle_deg`. Toute cle absente retombe sur
        le defaut de CETTE action dans la configuration (`is_forward_defaut`,
        `is_clockwise_defaut`), et seulement si l'entree ne le precise pas, sur
        vrai / faux. Mesure le 2026-09-19 (plan04) : un defaut global unique
        (`is_forward` toujours vrai) donnait une vitesse lineaire POSITIVE pour
        'reculer' des que la LLM omettait le champ, ce qu'un modele de 3 B fait
        systematiquement pour une commande simple, se fiant au nom de l'action
        plutot que de repeter un sens deja porte par ce nom. `reculer` declare
        donc `is_forward_defaut: false` dans ihr_config.json ; les autres actions
        n'ont pas besoin de le declarer, le defaut vrai/faux leur convenant deja.
        `bornes` re-borne `distance_m` et `angle_deg` (R9 : le schema borne, le
        code borne a nouveau) : le schema JSON impose deja un minimum et un
        maximum a la LLM, mais rien ne garantit qu'un appelant direct (les tests,
        par exemple) les respecte.

    Inputs:
        nom (str): nom de l'action
        actions_cfg (dict): section devoir2.actions de la configuration
        params (dict | None): is_forward / is_clockwise / distance_m / angle_deg,
            valeurs par defaut de la configuration si omis
        bornes (dict | None): section devoir2.bornes, aucun bornage si omise

    Outputs:
        action (Action): action entierement construite et signee
    --------------------------------------------------------------------------
    """
    if nom not in actions_cfg:
        raise KeyError(
            f"Action '{nom}' inconnue. Actions declarees : {sorted(actions_cfg)}."
        )

    entree = actions_cfg[nom]
    linear_speed_cfg = float(entree["linear_speed"])
    angular_speed_cfg = float(entree["angular_speed"])
    duree_s = float(entree["duree_s"])
    distance_defaut = float(entree.get("distance_m", 0.0))
    angle_defaut = float(entree.get("angle_deg", 0.0))

    p = params or {}
    is_forward_defaut = bool(entree.get("is_forward_defaut", True))
    is_clockwise_defaut = bool(entree.get("is_clockwise_defaut", False))
    is_forward = bool(p.get("is_forward", is_forward_defaut))
    is_clockwise = bool(p.get("is_clockwise", is_clockwise_defaut))
    distance_m = float(p.get("distance_m", distance_defaut))
    angle_deg = float(p.get("angle_deg", angle_defaut))

    distance_max = float(bornes["distance_m_max"]) if bornes else None
    angle_max = float(bornes["angle_deg_max"]) if bornes else None
    linear_max = float(bornes["linear_speed_max"]) if bornes else None
    angular_max = float(bornes["angular_speed_max"]) if bornes else None

    distance_m = _borner(distance_m, distance_max)
    angle_deg = _borner(angle_deg, angle_max)
    linear_speed = _borner(linear_speed_cfg, linear_max)
    angular_speed = _borner(angular_speed_cfg, angular_max)

    linear, angular = signer(linear_speed, angular_speed, is_forward, is_clockwise)

    return Action(nom=nom, linear=linear, angular=angular, duree_s=duree_s,
                 distance_m=distance_m, angle_deg=angle_deg,
                 is_forward=is_forward, is_clockwise=is_clockwise)
