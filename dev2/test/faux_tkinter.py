"""
faux_tkinter.py - Faux module tkinter pour test_voice_window.py.

Aucune fenetre reelle n'est jamais ouverte par les tests qui l'utilisent (workflow.md
R5). Le faux Tk enregistre les gestionnaires poses par bind()/protocol() sans jamais
rien dessiner ; declencher_entree()/declencher_fermeture() les invoquent directement,
exactement comme le ferait tkinter lui-meme au prochain passage d'evenements.
FauxLabel.config() enregistre le dernier texte configure, pour verification.

Ce fichier n'est PAS un module de test : aucune fonction ni classe ne s'appelle `test_*`.
"""

from __future__ import annotations

from typing import Any, Callable


class FauxLabel:
    """Faux tkinter.Label : enregistre le dernier texte configure, ne dessine rien."""

    def __init__(self, root: "FauxTk", **kwargs: Any) -> None:
        self.root = root
        self.text = kwargs.get("text", "")

    def pack(self, **kwargs: Any) -> None:
        pass

    def config(self, **kwargs: Any) -> None:
        if "text" in kwargs:
            self.text = kwargs["text"]


class FauxTk:
    """Faux tkinter.Tk : enregistre les gestionnaires, ne cree aucune fenetre reelle."""

    def __init__(self) -> None:
        self.titre = ""
        self.geometrie = ""
        self.gestionnaires: dict[str, Callable[..., Any]] = {}
        self.gestionnaire_fermeture: Callable[[], None] | None = None
        self.detruite = False
        self.appels_update = 0

    def title(self, titre: str) -> None:
        self.titre = titre

    def geometry(self, geometrie: str) -> None:
        self.geometrie = geometrie

    def bind(self, sequence: str, gestionnaire: Callable[..., Any]) -> None:
        self.gestionnaires[sequence] = gestionnaire

    def protocol(self, nom: str, gestionnaire: Callable[[], None]) -> None:
        self.gestionnaire_fermeture = gestionnaire

    def update_idletasks(self) -> None:
        self.appels_update += 1

    def update(self) -> None:
        self.appels_update += 1

    def destroy(self) -> None:
        self.detruite = True

    def declencher_entree(self) -> None:
        """Simule l'appui sur Entree : appelle le gestionnaire pose par bind('<Return>', ...)."""
        gestionnaire = self.gestionnaires.get("<Return>")
        if gestionnaire is not None:
            gestionnaire(None)

    def declencher_fermeture(self) -> None:
        """Simule un clic sur la croix de la fenetre (WM_DELETE_WINDOW)."""
        if self.gestionnaire_fermeture is not None:
            self.gestionnaire_fermeture()


def construire_faux_module() -> Any:
    """
    --------------------------------------------------------------------------
    Purpose:
        Assembler un faux module tkinter complet, utilisable partout ou
        voice_window.VoiceWindow attend `tkinter`.

    Inputs:
        aucun

    Outputs:
        module (types.SimpleNamespace): objet portant Tk et Label, comme le
            vrai module tkinter
    --------------------------------------------------------------------------
    """
    import types

    module = types.SimpleNamespace()
    module.Tk = FauxTk
    module.Label = FauxLabel
    return module
