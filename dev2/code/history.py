"""
history.py - Historique borne des tours de dialogue (Devoir 2, plan04, amelioration B).

Deux tours enchaines : « avance de deux metres » puis « et maintenant tourne a droite ».
Sans historique, « et maintenant » ne nomme aucune action : le modele ne voit que la
seconde phrase, isolee de la premiere. Ce module retient les derniers tours et les met
en forme pour l'invite de `llm_interpreter.construire_prompt`.

Fenetre BORNEE, jamais illimitee
---------------------------------
Un historique qui grandit sans borne fait croitre l'invite a chaque tour, donc la
latence, jusqu'a depasser la fenetre de contexte du modele. Ollama TRONQUE alors le
prompt en silence plutot que de lever une erreur (voir la note sur les limites de
taille dans .claude/rules/code-style.md) : l'instruction la plus probablement perdue
est la DERNIERE, c'est-a-dire la commande de l'utilisateur elle-meme. `Historique` ne
retient donc jamais plus de `tours_max` tours, le plus ancien etant oublie des que la
fenetre deborde.

Ce module est independant de `MachineDialogue.historique` (state_machine.py), qui est
le journal des TRANSITIONS d'etat (from, to, message), un concept different : celui-ci
est le journal des TOURS DE CONVERSATION (commande utilisateur -> action choisie),
destine au modele, pas au diagnostic de la machine d'etat.
"""

from __future__ import annotations

from typing import Sequence


def formater_lignes(lignes: Sequence[str]) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Mettre en forme une suite de tours deja reduite a sa fenetre, en un bloc
        de texte insere dans l'invite. Une suite vide rend une chaine VIDE : un
        en-tete « Historique » suivi de rien coute des jetons pour rien, sans
        rien apporter au modele.

    Inputs:
        lignes (Sequence[str]): tours dans l'ordre du plus ancien au plus
            recent, chaque element deja pret a l'affichage

    Outputs:
        bloc (str): texte pret pour l'invite, chaine vide si `lignes` est vide
    --------------------------------------------------------------------------
    """
    retenues = [ligne for ligne in lignes if ligne]
    if not retenues:
        return ""
    corps = "\n".join(f"- {ligne}" for ligne in retenues)
    return f"Historique recent :\n{corps}"


class Historique:
    """
    Fenetre bornee des derniers tours de dialogue.

    Chaque tour est stocke comme une phrase unique « commande -> resume », prete a
    etre transmise telle quelle dans un champ ROS2 `string[]` (Interpret.srv, plan01) :
    c'est `rendre()` qui expose cette forme brute, et `formater()` qui l'assemble en un
    bloc de texte pour l'invite.
    """

    def __init__(self, tours_max: int) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire un historique vide, borne a `tours_max` tours.

        Inputs:
            tours_max (int): nombre maximal de tours retenus, doit etre >= 1

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        if tours_max <= 0:
            raise ValueError(
                f"tours_max vaut {tours_max}. Un historique de fenetre nulle ou "
                "negative ne pourrait jamais retenir un seul tour, ce qui rendrait "
                "toute anaphore impossible des le premier tour suivant."
            )
        self._tours_max = tours_max
        self._tours: list[str] = []

    def ajouter(self, commande: str, resume: str) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Ajouter un tour, en ne retenant jamais plus de `tours_max` tours : le
            plus ancien est oublie des que la fenetre deborde.

        Inputs:
            commande (str): phrase prononcee par l'utilisateur
            resume (str): ce que le tour a produit (nom d'action, ou sequence de
                noms separes par ' puis ')

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._tours.append(f"{commande} -> {resume}")
        if len(self._tours) > self._tours_max:
            del self._tours[: len(self._tours) - self._tours_max]

    def rendre(self) -> tuple[str, ...]:
        """Tours retenus, du plus ancien au plus recent, forme brute pour Interpret.srv."""
        return tuple(self._tours)

    def formater(self) -> str:
        """Bloc de texte pret pour l'invite ; chaine vide si l'historique est vide."""
        return formater_lignes(self._tours)

    def vider(self) -> None:
        """Oublier tous les tours retenus."""
        self._tours.clear()
