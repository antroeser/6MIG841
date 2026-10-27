"""
llm_interpreter.py - Traduire une phrase francaise en plan de mouvement pour la tortue.

Devoir 2. Ce module parle a Ollama et rend un `Plan` du module `state_machine`, ou
echoue en le disant. Il ne touche ni au micro, ni a la tortue.

Ce que faisaient les rendus etudiants, et pourquoi c'etait fragile
------------------------------------------------------------------
Les trois rendus demandaient au modele DEUX NOMBRES EN TEXTE LIBRE, puis les
repechaient avec `re.findall(r'-?\\d+\\.?\\d*', reponse)`. Trois consequences,
toutes rapportees dans leurs propres rapports :

  1. Le modele repond souvent une phrase entiere. Le rapport Devoir2-1 montre la
     reponse "2 2.0" recuperee la ou "2.0 4.0" etait attendu : le premier nombre
     venait d'ailleurs dans la phrase.
  2. `\\d+\\.?\\d*` accroche n'importe quel chiffre, y compris celui d'un "llama3.2"
     ou d'une annee cite dans la reponse.
  3. Rien ne borne les valeurs. Un modele qui repond "20.0 0.0" envoie la tortue
     dans le mur a dix fois la vitesse prevue.

Le solutionnaire ne demande plus de texte libre. Il impose un SCHEMA JSON a Ollama
(parametre `format`), et il contraint le champ `action` a une enumeration fermee,
construite depuis la table d'actions de la configuration.

Le sens par booleen (plan04, amelioration A)
---------------------------------------------
Defaut mesure le 2026-09-18 : rien ne declarait au modele le sens positif d'une
rotation, qui devinait alors un signe. `distance_m` et `angle_deg` restent des
grandeurs NON SIGNEES dans le schema (minimum impose a zero) ; `is_forward` et
`is_clockwise` portent le sens. `signer()` (state_machine.py) est le SEUL endroit qui
decide un signe : ce module ne fait que transmettre les booleens rendus par le modele
a `action_depuis_config`, qui les borne et les signe.

L'historique (plan04, amelioration B)
---------------------------------------
`interpreter()` accepte un bloc d'historique DEJA FORMATE (voir `history.py`), insere
tel quel dans l'invite. Ce module ne construit ni ne borne cet historique : c'est la
responsabilite de l'appelant (`voice_turtle.boucle`, `dialogue_manager_node`), qui seul
connait la duree de vie d'une conversation.

La sequence (plan04, amelioration C)
--------------------------------------
Quand la capacite de sequence est active (`avec_sequence=True` a la construction),
l'enumeration du schema gagne le membre special 'sequence' et un champ `etapes`,
tableau borne, chacune ayant la meme forme qu'une action simple. Une reponse valant
`action: "sequence"` est lue comme un `Plan` a PLUSIEURS etapes ; toute autre reponse
valide est lue comme un `Plan` a UNE SEULE etape. Le modele CLASSE, il ne calcule pas :
les vitesses ne viennent jamais de sa reponse, seulement de la configuration.

Le catalogue sous-ensemblable (plan04, amelioration D)
---------------------------------------------------------
`LlmInterpreter(settings, client=None, sous_ensemble=None)` filtre l'enumeration
exposee au modele. `sous_ensemble=None` (le defaut) expose le catalogue COMPLET avec
la sequence activee : c'est le comportement de tout appelant existant, inchange par ce
filtrage (controle negatif exige par plan04.md, etape 10). Un nom declare dans
`devoir2.sous_ensembles` restreint l'enumeration a ce sous-ensemble ; un nom absent de
cette table leve `KeyError` nommant les sous-ensembles connus.

La fenetre de contexte, residence VRAM (correctif du 2026-09-19)
------------------------------------------------------------------
`devoir2.llm_num_ctx` est transmis dans `options.num_ctx` a chaque appel
`generate()`. Sans cela, Ollama sert le defaut du demon (OLLAMA_CONTEXT_LENGTH,
mesure a 262144 le 2026-09-19), dont le cache cle-valeur qui en decoule oblige le
demon a repousser la majorite des poids sur le processeur au lieu du GPU. La
valeur retenue (16384) est MESUREE, pas devinee : balayage de
`optimize_ollama.evaluate_rung` (skill loop-engineer) sur le tag reel, plus grand
palier a residence GPU 100% avec une marge laissee pour Whisper (voir
ihr_config.json, entree de provenance `devoir2_vram_residence`, et
`.sdd/6mig841-ameliorations/vram-residence-report.md`). Aucun tag Ollama derive
n'est cree : un parametre de requete suffit et reste lisible pour l'etudiant.

Residence permanente et mise en train (correctif du 2026-09-20)
-------------------------------------------------------------------
`devoir2.llm_keep_alive` (-1, ihr_config.json) est transmis au niveau superieur
de CHAQUE appel `generate()` (jamais dans `options`, l'API Ollama le place a
part) : une valeur negative garde le modele charge indefiniment, ecrasant le
defaut du demon (5 minutes d'inactivite). `LlmInterpreter.demarrer()`, appelee
par `LlmNode.__init__` (llm_node.py), force un premier appel des la
construction du noeud plutot que d'attendre la premiere commande, corrigeant
une VRAM mesuree VIDE au demarrage (defaut 2,
.sdd/6mig841-ameliorations/vram-et-transcription-report.md).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

from state_machine import Action, Plan, action_depuis_config


@dataclass(frozen=True)
class Interpretation:
    """Resultat d'une tentative de traduction."""

    plan: Plan | None
    brut: str
    tentatives: int
    erreur: str = ""

    @property
    def ok(self) -> bool:
        return self.plan is not None


# Requis, pas seulement types, sur les quatre champs de sens/grandeur. Mesure le
# 2026-09-19 sur llama3.2 (real daemon, voir evaluation/resultats) : rendus
# OPTIONNELS, le modele les OMET presque systematiquement pour une commande simple
# ('{"action": "reculer"}' seul, sans is_forward), et se rabat implicitement sur le
# nom de l'action plutot que de declarer le sens qu'on lui demande explicitement de
# porter. Un champ requis force Ollama a emettre une valeur du bon type ; cela ne
# garantit pas qu'elle soit correcte (voir le taux de niveau 2 mesure apres ce
# changement), mais retire la possibilite de se taire sur le sens, qui est
# exactement le defaut structurel que l'amelioration A visait a eliminer.
_REQUIS_ETAPE = ["action", "distance_m", "angle_deg", "is_forward", "is_clockwise"]


def _proprietes_etape(noms: list[str], distance_max: float, angle_max: float) -> dict[str, Any]:
    """Bloc de proprietes JSON Schema partage par une action simple et une etape de sequence."""
    return {
        "action": {"type": "string", "enum": list(noms)},
        "distance_m": {"type": "number", "minimum": 0.0, "maximum": distance_max},
        "angle_deg": {"type": "number", "minimum": 0.0, "maximum": angle_max},
        "is_forward": {"type": "boolean"},
        "is_clockwise": {"type": "boolean"},
    }


def construire_schema(actions_cfg: dict[str, Any], bornes: dict[str, Any],
                       noms_permis: list[str] | None = None,
                       sequence_max_etapes: int | None = None) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire le schema JSON impose au modele. L'enumeration est derivee de
        la configuration (ou du sous-ensemble `noms_permis`), donc ajouter une
        action dans ihr_config.json suffit a la rendre disponible : aucun nom
        d'action n'est ecrit en dur ici. `distance_m` et `angle_deg` portent un
        minimum de zero : le schema n'expose AUCUN champ signe (plan04,
        amelioration A), le sens passant uniquement par `is_forward` et
        `is_clockwise`.

    Inputs:
        actions_cfg (dict): section devoir2.actions de la configuration
        bornes (dict): section devoir2.bornes (distance_m_max, angle_deg_max)
        noms_permis (list[str] | None): sous-ensemble de noms d'action exposes
            au modele ; le catalogue complet si omis
        sequence_max_etapes (int | None): si fourni et positif, active la
            capacite de sequence : l'enumeration gagne 'sequence' et le schema
            gagne un champ `etapes`, tableau borne a cette taille

    Outputs:
        schema (dict): schema JSON au format attendu par Ollama
    --------------------------------------------------------------------------
    """
    noms = sorted(noms_permis) if noms_permis is not None else sorted(actions_cfg)
    if not noms:
        raise ValueError(
            "Aucune action exposee au modele. Sans action declaree, le modele "
            "n'aurait aucun choix valide a faire."
        )

    distance_max = float(bornes["distance_m_max"])
    angle_max = float(bornes["angle_deg_max"])

    proprietes = _proprietes_etape(noms, distance_max, angle_max)

    if sequence_max_etapes:
        proprietes["action"] = {"type": "string", "enum": noms + ["sequence"]}
        proprietes["etapes"] = {
            "type": "array",
            "minItems": 1,
            "maxItems": int(sequence_max_etapes),
            "items": {
                "type": "object",
                "properties": _proprietes_etape(noms, distance_max, angle_max),
                "required": _REQUIS_ETAPE,
            },
        }

    proprietes["justification"] = {"type": "string"}
    return {
        "type": "object",
        "properties": proprietes,
        "required": _REQUIS_ETAPE,
    }


def construire_prompt(commande: str, actions_cfg: dict[str, Any],
                      noms_permis: list[str] | None = None,
                      avec_sequence: bool = False,
                      historique_texte: str = "") -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Composer le prompt. Les exemples viennent de la configuration, de sorte
        que le vocabulaire reconnu se regle sans toucher au code. L'invite
        DECLARE la convention de signe en toutes lettres (plan04, amelioration
        A) : sans cela le modele devine, ce qui est exactement ce qui a rate le
        2026-09-18.

    Inputs:
        commande (str): phrase prononcee par l'utilisateur
        actions_cfg (dict): section devoir2.actions de la configuration
        noms_permis (list[str] | None): sous-ensemble de noms d'action exposes ;
            le catalogue complet si omis
        avec_sequence (bool): si vrai, ajoute l'exemple de sequence a l'invite
        historique_texte (str): bloc d'historique deja formate (history.py),
            insere tel quel ; rien n'est ajoute s'il est vide

    Outputs:
        prompt (str): texte envoye au modele
    --------------------------------------------------------------------------
    """
    noms = sorted(noms_permis) if noms_permis is not None else sorted(actions_cfg)
    lignes = []
    for nom in noms:
        exemples = ", ".join(actions_cfg[nom].get("exemples", []))
        lignes.append(f"- {nom} : {exemples}" if exemples else f"- {nom}")
    catalogue = "\n".join(lignes)

    conventions = (
        "Conventions obligatoires, a respecter strictement :\n"
        "- distance_m et angle_deg sont des grandeurs POSITIVES, jamais negatives.\n"
        "- is_forward vaut vrai pour avancer, faux pour reculer.\n"
        "- is_clockwise vaut vrai pour tourner a DROITE (sens horaire), faux pour "
        "tourner a GAUCHE (sens antihoraire).\n"
    )

    bloc_sequence = ""
    if avec_sequence:
        bloc_sequence = (
            "\nSi la commande enchaine PLUSIEURS mouvements, reponds avec "
            "action=\"sequence\" et un tableau etapes contenant une entree par "
            "mouvement, dans l'ordre. Ignore toute demande hors du catalogue : par "
            "exemple, « tourne de 60 degres a gauche, avance d'un metre, arrete-toi, "
            "et apporte-moi un cafe » rend une sequence de TROIS etapes, la demande "
            "de cafe etant hors catalogue et donc ignoree.\n"
        )

    bloc_historique = f"\n{historique_texte}\n" if historique_texte else ""

    return (
        "Tu classes une commande vocale francaise destinee a un robot tortue.\n"
        f"{conventions}"
        f"{bloc_sequence}"
        "Choisis EXACTEMENT une action parmi la liste, celle dont le sens est le "
        "plus proche de la commande.\n\n"
        f"Actions possibles et exemples de formulation :\n{catalogue}\n"
        f"{bloc_historique}\n"
        f"Commande de l'utilisateur : « {commande} »\n\n"
        "Reponds uniquement par l'objet JSON demande. Le champ action doit valoir "
        "l'un des noms ci-dessus, sans rien ajouter. Le champ justification "
        "contient au plus une phrase courte en francais."
    )


class LlmInterpreter:
    """Traducteur commande -> plan, adosse a Ollama."""

    def __init__(self, settings: dict[str, Any], client: Any | None = None,
                 sous_ensemble: str | None = None):
        """
        --------------------------------------------------------------------------
        Purpose:
            Preparer le traducteur. Le client est injectable pour que les tests
            tournent sans demon Ollama. `sous_ensemble` filtre le catalogue
            expose au modele (plan04, amelioration D) : omis, le catalogue
            complet est expose avec la sequence activee, exactement comme avant
            l'introduction des sous-ensembles (controle negatif).

        Inputs:
            settings (dict): section devoir2 de la configuration
            client (Any | None): client Ollama, cree ici s'il est absent
            sous_ensemble (str | None): nom declare dans devoir2.sous_ensembles,
                ou None pour le catalogue complet

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._cfg = settings
        self._actions = settings["actions"]
        self._bornes = settings["bornes"]
        self._sequence_max = int(self._bornes["sequence_max_etapes"])
        self._modele = str(settings["llm_model"])
        self._max_tentatives = int(settings["llm_max_attempts"])
        self._timeout = float(settings["llm_timeout_seconds"])
        self._num_ctx = int(settings["llm_num_ctx"])
        self._keep_alive = settings["llm_keep_alive"]
        self._erreur_demarrage = ""

        sous_ensembles_cfg = settings.get("sous_ensembles", {})
        if sous_ensemble is None:
            self._noms_permis = sorted(self._actions)
            self._avec_sequence = True
        else:
            if sous_ensemble not in sous_ensembles_cfg:
                raise KeyError(
                    f"Sous-ensemble '{sous_ensemble}' inconnu. Sous-ensembles "
                    f"declares : {sorted(sous_ensembles_cfg)}."
                )
            membres = sous_ensembles_cfg[sous_ensemble]
            self._avec_sequence = "sequence" in membres
            self._noms_permis = sorted(n for n in membres if n != "sequence")

        self._schema = construire_schema(
            self._actions, self._bornes, noms_permis=self._noms_permis,
            sequence_max_etapes=(self._sequence_max if self._avec_sequence else None),
        )

        if self._max_tentatives < 1:
            raise ValueError(
                f"llm_max_attempts vaut {self._max_tentatives}. Il faut au moins une "
                "tentative, sinon le traducteur echoue sans avoir rien demande."
            )

        if client is not None:
            self._client = client
        else:
            import ollama  # noqa: PLC0415

            self._client = ollama.Client(host=str(settings["llm_host"]),
                                         timeout=self._timeout)

    @property
    def schema(self) -> dict[str, Any]:
        """Schema JSON impose au modele."""
        return self._schema

    @property
    def erreur_demarrage(self) -> str:
        """Erreur du dernier prechauffage Ollama, vide si le demarrage a reussi."""
        return self._erreur_demarrage

    def interpreter(self, commande: str, historique: str = "") -> Interpretation:
        """
        --------------------------------------------------------------------------
        Purpose:
            Traduire une phrase en plan, avec un nombre de tentatives BORNE. Les
            rendus etudiants rappelaient le modele dans une boucle sans borne :
            un modele qui ne repond jamais correctement gelait la seance.

        Inputs:
            commande (str): phrase prononcee par l'utilisateur
            historique (str): bloc d'historique deja formate (history.py),
                insere tel quel dans l'invite ; vide par defaut

        Outputs:
            interpretation (Interpretation): plan trouve, ou echec motive
        --------------------------------------------------------------------------
        """
        if not commande or not commande.strip():
            return Interpretation(None, "", 0, "commande vide")

        prompt = construire_prompt(commande, self._actions, self._noms_permis,
                                   self._avec_sequence, historique)
        derniere_erreur = "aucune tentative"
        brut = ""

        for tentative in range(1, self._max_tentatives + 1):
            try:
                reponse = self._client.generate(
                    model=self._modele,
                    prompt=prompt,
                    format=self._schema,
                    options={"temperature": 0.0, "seed": 1, "num_ctx": self._num_ctx},
                    keep_alive=self._keep_alive,
                )
            except Exception as exc:
                derniere_erreur = f"{type(exc).__name__}: {exc}"
                continue

            brut = self._extraire_texte(reponse)
            plan, erreur = self._lire_plan(brut)
            if plan is None:
                derniere_erreur = erreur
                continue

            return Interpretation(plan, brut, tentative)

        return Interpretation(None, brut, self._max_tentatives, derniere_erreur)

    def demarrer(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Charger le modele Ollama en VRAM des la construction du noeud, plutot
            que d'attendre le premier appel a interpreter() (defaut mesure le
            2026-09-20, .sdd/6mig841-ameliorations/vram-et-transcription-report.md,
            defaut 2 : VRAM mesuree VIDE au demarrage). Ollama charge un modele
            PARESSEUSEMENT, au premier /api/generate, et le decharge par defaut
            apres 5 minutes d'inactivite (keep_alive du demon, jamais fixe par ce
            depot) : ce decalage explique la VRAM vide mesuree. Un appel de mise
            en train, prompt vide et sans schema impose (aucun texte n'est attendu
            ni lu), avec le meme options.num_ctx et le meme keep_alive que chaque
            appel reel d'interpreter(), force ce chargement immediatement et le
            rend permanent (keep_alive negatif, convention Ollama). N'eleve JAMAIS
            (R8 attenue en avertissement) : un demon Ollama injoignable au
            demarrage du noeud ne doit pas empecher rclpy.spin, le premier appel
            reel a interpreter() echouera alors normalement et le dira.

        Inputs:
            aucun

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._erreur_demarrage = ""
        try:
            self._client.generate(
                model=self._modele,
                prompt="",
                format=None,
                options={"num_ctx": self._num_ctx},
                keep_alive=self._keep_alive,
            )
        except Exception as exc:
            self._erreur_demarrage = (
                f"{type(exc).__name__}: {exc}. Verifier qu'Ollama est demarre "
                f"et accessible sur {self._cfg['llm_host']}."
            )
            print(f"[llm][ERREUR] Ollama indisponible : {self._erreur_demarrage}",
                  file=sys.stderr)

    @staticmethod
    def _extraire_texte(reponse: Any) -> str:
        """Lire le champ 'response', que le client rende un objet ou un dict."""
        if isinstance(reponse, dict):
            return str(reponse.get("response", "")).strip()
        return str(getattr(reponse, "response", "")).strip()

    def _action_depuis_etape(self, etape: dict[str, Any]) -> Action:
        """Construire une Action a partir d'une etape JSON deja validee comme objet."""
        nom = etape.get("action")
        if not isinstance(nom, str) or nom.strip() not in self._noms_permis:
            raise KeyError(
                f"action '{nom}' hors de l'enumeration {self._noms_permis}"
            )
        return action_depuis_config(nom.strip(), self._actions, params=etape,
                                    bornes=self._bornes)

    def _lire_plan(self, brut: str) -> tuple[Plan | None, str]:
        """
        --------------------------------------------------------------------------
        Purpose:
            Extraire un Plan d'une reponse JSON, et dire precisement ce qui
            cloche sinon. Une reponse dont l'action vaut 'sequence' est lue
            comme un Plan a plusieurs etapes (le champ 'etapes') ; toute autre
            reponse valide est lue comme un Plan a une seule etape.

        Inputs:
            brut (str): texte rendu par le modele

        Outputs:
            plan (Plan | None): plan construit, ou None
            erreur (str): raison de l'echec, vide en cas de succes
        --------------------------------------------------------------------------
        """
        if not brut:
            return None, "reponse vide du modele"
        try:
            charge = json.loads(brut)
        except json.JSONDecodeError as exc:
            return None, f"reponse non JSON ({exc}) : {brut[:120]}"

        if not isinstance(charge, dict):
            return None, f"JSON qui n'est pas un objet : {brut[:120]}"

        nom = charge.get("action")
        if not isinstance(nom, str) or not nom:
            return None, f"champ 'action' absent ou vide : {brut[:120]}"
        nom = nom.strip()

        if nom == "sequence":
            if not self._avec_sequence:
                return None, "sequence rendue alors que la capacite est desactivee"
            etapes_brutes = charge.get("etapes")
            if not isinstance(etapes_brutes, list) or not etapes_brutes:
                return None, f"sequence sans champ 'etapes' exploitable : {brut[:120]}"
            if len(etapes_brutes) > self._sequence_max:
                return None, (f"sequence de {len(etapes_brutes)} etapes depasse la "
                              f"borne sequence_max_etapes={self._sequence_max}")
            actions: list[Action] = []
            for index, etape in enumerate(etapes_brutes):
                if not isinstance(etape, dict):
                    return None, f"etape {index} n'est pas un objet : {brut[:120]}"
                try:
                    actions.append(self._action_depuis_etape(etape))
                except KeyError as exc:
                    return None, f"etape {index} : {exc}"
            try:
                return Plan(tuple(actions)), ""
            except ValueError as exc:
                return None, str(exc)

        if nom not in self._noms_permis:
            return None, (f"action '{nom}' hors de l'enumeration "
                          f"{self._noms_permis}")
        try:
            action = action_depuis_config(nom, self._actions, params=charge,
                                          bornes=self._bornes)
        except KeyError as exc:
            # Le schema interdit ce cas, mais un modele peut renvoyer une casse
            # differente ou un espace. On le signale plutot que de le rattraper
            # en silence.
            return None, str(exc)
        return Plan((action,)), ""
