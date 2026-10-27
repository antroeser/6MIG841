"""
faux_ollama.py - Faux clients Ollama pour les tests du Devoir 2.

`LlmInterpreter` n'appelle jamais qu'une seule methode de son client :
`.generate(model, prompt, format, options, keep_alive)`. C'est donc la seule methode que
ces faux clients doivent fournir pour se substituer completement a `ollama.Client()` :
AUCUN demon Ollama n'est jamais contacte pendant les tests (workflow.md R5).

`keep_alive` ajoute le 2026-09-20 (.sdd/6mig841-ameliorations/vram-et-transcription-report.md,
defaut 2 : VRAM vide au demarrage) : `LlmInterpreter.interpreter()` et
`LlmInterpreter.demarrer()` transmettent desormais ce parametre a CHAQUE appel
`generate()`, jamais seulement dans `options` (l'API reelle d'Ollama le porte au niveau
superieur de la requete, pas dans `options`). `format` et `keep_alive` portent un defaut
pour rester utilisables par `demarrer()`, qui n'impose pas de schema.

Ce fichier n'est PAS un module de test : aucune fonction ni classe ne s'appelle
`test_*`, pytest ne le collecte donc pas comme suite. Il est importe par les modules
de test qui en ont besoin (`import faux_ollama` ou `from faux_ollama import ...`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class Appel:
    """
    Un appel enregistre a `.generate()`.

    Conserve exactement ce que LlmInterpreter a envoye, pour que les tests puissent
    verifier non seulement CE QUI a ete recu, mais aussi CE QUI A ETE EXPEDIE (modele,
    prompt, schema JSON impose).
    """

    model: str
    prompt: str
    format: Any
    options: dict[str, Any]
    keep_alive: Any = None


class FauxOllama:
    """
    Faux client qui rend des reponses connues d'avance, dans l'ordre de la file.

    La DERNIERE reponse de la file est repetee indefiniment une fois celle-ci vide,
    exactement comme `ScriptedInput` (voice.py) repete sa phrase de fin : un test qui
    appelle `.generate()` plus de fois que de reponses fournies ne doit jamais lever
    IndexError, il doit plutot echouer sur une ASSERTION explicite (par exemple sur le
    nombre d'appels attendu). C'est ce qui permet de fournir une seule reponse-poubelle
    pour verifier que le nombre de tentatives est borne, sans devoir la dupliquer
    `llm_max_attempts` fois.
    """

    def __init__(self, reponses: list[str]) -> None:
        if not reponses:
            raise ValueError("FauxOllama exige au moins une reponse en file.")
        self._reponses: deque[str] = deque(reponses)
        self._derniere_reponse = reponses[-1]
        self.appels: list[Appel] = []

    def generate(self, model: str, prompt: str, format: Any = None,
                 options: dict[str, Any] | None = None,
                 keep_alive: Any = None) -> dict[str, Any]:
        """Rendre la prochaine reponse en file (ou la derniere, la file une fois vide)."""
        self.appels.append(Appel(model=model, prompt=prompt, format=format,
                                 options=options or {}, keep_alive=keep_alive))
        texte = self._reponses.popleft() if self._reponses else self._derniere_reponse
        return {"response": texte}

    @property
    def nb_appels(self) -> int:
        """Nombre de fois ou `.generate()` a ete appelee, pour verifier une borne de tentatives."""
        return len(self.appels)


class OllamaQuiEchoue:
    """
    Faux client qui leve une exception a chaque appel.

    Sert a prouver que `LlmInterpreter.interpreter()` RATTRAPE l'exception et la
    rapporte dans `Interpretation.erreur`, plutot que de la laisser se propager et
    faire planter tout le programme du Devoir 2.
    """

    def __init__(self, exception: BaseException | None = None) -> None:
        self._exception = exception if exception is not None else RuntimeError(
            "Ollama injoignable (faux client, aucun demon reel contacte)"
        )
        self.appels = 0

    def generate(self, model: str, prompt: str, format: Any = None,
                 options: dict[str, Any] | None = None,
                 keep_alive: Any = None) -> dict[str, Any]:
        self.appels += 1
        raise self._exception


class OllamaLent(OllamaQuiEchoue):
    """
    Faux client qui simule un depassement de delai, sans jamais reellement attendre.

    Meme comportement que OllamaQuiEchoue (il leve a chaque appel), mais avec une
    exception qui ressemble a un vrai timeout reseau plutot qu'a un refus de service.
    """

    def __init__(self) -> None:
        super().__init__(TimeoutError(
            "Ollama ne repond pas dans le delai imparti (faux client, aucune attente reelle)"
        ))
