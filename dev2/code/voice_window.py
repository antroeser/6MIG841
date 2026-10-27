"""
voice_window.py - Devoir 2 : fenetre de saisie vocale (affichage + Entree).

Corrige un defaut mesure le 2026-09-19 (plan09.md) : sous `ros2 launch`, les
noeuds partagent un terminal dont le stdin ne leur est PAS rattache.
`voice.MicrophoneInput.ecouter()` attendait Entree via `input()`, qui
bloquait donc INDEFINIMENT. Et le journal entrelace de six noeuds ne peut de
toute facon pas afficher un texte qui se reecrit, alors que l'enonce exige
que la transcription apparaisse au fur et a mesure. Cette fenetre tkinter
remplace les deux : elle affiche le texte courant (reecrit en place, jamais
empile) et capte Entree elle-meme, sans jamais toucher a stdin.

tkinter est dans la bibliotheque standard, deja une dependance de fait du
solutionnaire (ihr_ros.backends.sim._TkView, meme technique de fenetre
optionnelle pompee par un fil de fond). Aucune dependance nouvelle (decision
arretee de plan09.md). Deux autres voies ont ete ecartees et ne sont pas
reprises ici : une console dediee par Node(prefix=...) se detache sous
Windows et casse l'arret propre de ros2 launch ; sortir voice_input du
launch ferait perdre le lancement unique.

Piege 1 de plan02.md, applique ici aussi, mais CORRIGE le 2026-09-20 apres
l'epreuve reelle de l'etape 6 : tkinter sous Windows leve
`RuntimeError: main thread is not in main loop` des qu'un widget est touche
depuis un fil AUTRE que le fil principal du processus, meme un fil qui a
lui-meme cree la fenetre. `_ecouter_en_boucle` (voice_input_node.py) est un
`threading.Thread`, jamais le fil principal (qui execute `rclpy.spin`) : y
pomper la fenetre y crashait a chaque tour. TOUS les appels tkinter reels
(creation des widgets, .config(), .update()) se produisent donc UNIQUEMENT a
l'interieur de `pump()`, appelee UNIQUEMENT depuis le fil principal du
processus (la boucle de voice_input_node.main(), qui alterne
`rclpy.spin_once()` et `fenetre.pump()`), jamais depuis un rappel ROS2 et
jamais depuis le fil de fond qui porte la capture et l'ecoute.
`afficher_texte()` et `afficher_ecoute()` restent appelables depuis
N'IMPORTE QUEL fil (respectivement le fil de rafraichissement de
voice.MicrophoneInput et le rappel ROS2 de la porte d'ecoute,
voice_input_node.VoiceInputNode._on_porte_ecoute) : ils n'enregistrent qu'une
valeur, sans jamais appeler tkinter directement. `attendre_confirmation()`,
appelee depuis voice.MicrophoneInput.ecouter() (donc depuis le fil de fond
qui porte la capture), ne pompe PLUS elle-meme : elle attend, en sommeillant,
qu'une confirmation ou une fermeture soit deja enregistree par le PROCHAIN
`pump()` du fil principal.

La fenetre n'est PAS la machine d'etat (plan09.md, decisions arretees) :
elle affiche et elle saisit Entree, rien d'autre. C'est dialogue_manager qui
decide.

Provenance des valeurs de configuration (titre, taille, police, intervalle
de pompe) : section devoir2.fenetre_voix de ihr_config.json, datee
2026-09-20 (R7, R4).
"""

from __future__ import annotations

import time
from typing import Any, Callable


class VoiceWindow:
    """Fenetre tkinter : affichage du texte courant, saisie d'Entree, rien de plus."""

    def __init__(self, settings: dict[str, Any],
                 on_fermeture: Callable[[], None] | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Ouvrir la fenetre. Si tkinter ne peut pas ouvrir de fenetre (pas
            d'affichage disponible), lever une erreur explicite nommant la
            cause, jamais un blocage muet (R3, exigence de plan09.md).

        Inputs:
            settings (dict): section devoir2.fenetre_voix de la configuration
                (titre, largeur_pixels, hauteur_pixels, police_nom,
                police_taille, intervalle_pompe_s)
            on_fermeture (Callable[[], None] | None): rappel invoque quand la
                croix de la fenetre est cliquee, APRES que la fenetre soit
                deja marquee fermee et detruite. Sert a voice_input_node.py
                pour arreter le noeud proprement (pas de processus orphelin).

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        import tkinter  # noqa: PLC0415

        self._on_fermeture = on_fermeture
        self._texte_courant = ""
        self._ecoute_active = True
        self._dernier_texte_applique: str | None = None
        self._dernier_etat_applique: bool | None = None
        self._confirmation_en_attente: str | None = None
        self._fermee = False
        self._intervalle_pompe = float(settings["intervalle_pompe_s"])

        titre = str(settings["titre"])
        largeur = int(settings["largeur_pixels"])
        hauteur = int(settings["hauteur_pixels"])
        police = (str(settings["police_nom"]), int(settings["police_taille"]))

        try:
            self._root = tkinter.Tk()
        except Exception as exc:
            raise RuntimeError(
                f"Impossible d'ouvrir la fenetre de saisie vocale (tkinter) : "
                f"{exc}. Verifier qu'un affichage est disponible (session "
                f"sans tete ?), ou lancer le devoir avec input:=clavier."
            ) from exc

        self._root.title(titre)
        self._root.geometry(f"{largeur}x{hauteur}")
        self._label_ecoute = tkinter.Label(
            self._root, text="ecoute active",
            font=(police[0], max(police[1] - 4, 8)),
        )
        self._label_ecoute.pack(anchor="w", padx=10, pady=(10, 0))
        self._label_texte = tkinter.Label(
            self._root, text="Parlez, puis appuyez sur Entree pour envoyer.",
            font=police, wraplength=max(largeur - 20, 40),
            justify="left", anchor="nw",
        )
        self._label_texte.pack(fill="both", expand=True, padx=10, pady=10)

        self._root.bind("<Return>", self._on_entree)
        self._root.protocol("WM_DELETE_WINDOW", self._on_fermeture_clic)

    # ------------------------------------------------------------- appelable de tout fil

    def afficher_texte(self, texte: str) -> None:
        """Remplacer le texte courant (jamais empile). Aucun appel tkinter ici."""
        self._texte_courant = texte

    def afficher_ecoute(self, active: bool) -> None:
        """Refleter l'etat de la porte /ihr/ecoute_active. Aucun appel tkinter ici."""
        self._ecoute_active = active

    @property
    def fermee(self) -> bool:
        """Vrai des que la croix de la fenetre a ete cliquee (ou close() appele)."""
        return self._fermee

    @property
    def intervalle_pompe(self) -> float:
        """
        Intervalle de pompage configure (fenetre_voix.intervalle_pompe_s), pour
        que l'appelant (voice_input_node.main(), fil principal) cadence sa
        propre boucle sans dupliquer cette valeur (R2).
        """
        return self._intervalle_pompe

    # ------------------------------------------------------------- fil principal seulement

    def pump(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Appliquer aux VRAIS widgets le texte et l'etat de la porte en
            attente, puis traiter les evenements Tk (clavier, croix de
            fermeture). A appeler UNIQUEMENT depuis le fil PRINCIPAL du
            processus (voice_input_node.main(), en alternance avec
            rclpy.spin_once()) : tkinter sous Windows leve
            `RuntimeError: main thread is not in main loop` depuis tout autre
            fil, y compris celui qui a construit la fenetre (mesure le
            2026-09-20, plan09.md etape 6). Jamais depuis un rappel ROS2 non
            plus (piege 1 de plan02.md).

        Inputs:
            aucun

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        if self._fermee:
            return
        if self._texte_courant != self._dernier_texte_applique:
            self._label_texte.config(
                text=self._texte_courant
                or "Parlez, puis appuyez sur Entree pour envoyer."
            )
            self._dernier_texte_applique = self._texte_courant
        if self._ecoute_active != self._dernier_etat_applique:
            self._label_ecoute.config(
                text="ecoute active" if self._ecoute_active
                else "ecoute en pause (execution en cours)",
            )
            self._dernier_etat_applique = self._ecoute_active
        try:
            self._root.update_idletasks()
            self._root.update()
        except Exception:
            # Fenetre detruite par le systeme de fenetrage sans passer par la
            # croix (rare) : ne jamais faire tomber le fil principal pour cela.
            self._fermee = True

    def attendre_confirmation(self) -> str | None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Bloquer, en sommeillant regulierement (JAMAIS input(), dont le
            stdin n'est pas rattache sous ros2 launch, et JAMAIS tkinter
            directement : voir l'en-tete du module, corrige le 2026-09-20),
            jusqu'a ce que l'etudiant confirme un texte non vide par Entree
            (porte d'ecoute ouverte) ou que la fenetre soit fermee. Ces deux
            evenements sont enregistres par `pump()`, appelee ailleurs par le
            fil PRINCIPAL du processus : cette methode se contente de les
            RELIRE. C'est le remplacement direct de l'ancien input() bloquant
            de voice.MicrophoneInput.ecouter(), appele depuis le meme fil de
            fond qui portait deja cette attente.

        Inputs:
            aucun

        Outputs:
            texte (str | None): texte confirme (jamais vide), ou None si la
                fenetre a ete fermee entre-temps (l'appelant doit alors
                arreter proprement, sans rien publier)
        --------------------------------------------------------------------------
        """
        while True:
            if self._fermee:
                return None
            if self._confirmation_en_attente is not None:
                texte = self._confirmation_en_attente
                self._confirmation_en_attente = None
                return texte
            time.sleep(self._intervalle_pompe)

    def close(self) -> None:
        """Fermer la fenetre. Rappelable deux fois sans effet (meme contrat que EntreeVocale.close())."""
        if self._fermee:
            return
        self._fermee = True
        self._detruire()

    # ------------------------------------------------------------- gestionnaires tkinter

    def _on_entree(self, event: Any = None) -> None:
        """
        Gestionnaire tkinter (appele par Tk lui-meme pendant pump(), donc
        deja dans le bon fil). Ignore Entree si la porte d'ecoute est
        fermee (le micro se tait pendant l'execution) ou si rien n'a encore
        ete transcrit (une transcription vide n'est jamais publiee,
        controle negatif de plan09.md).
        """
        if not self._ecoute_active:
            return
        if not self._texte_courant:
            return
        self._confirmation_en_attente = self._texte_courant

    def _on_fermeture_clic(self) -> None:
        """La croix de la fenetre a ete cliquee : se marquer fermee, se detruire, avertir l'appelant."""
        self._fermee = True
        self._detruire()
        if self._on_fermeture is not None:
            self._on_fermeture()

    def _detruire(self) -> None:
        try:
            self._root.destroy()
        except Exception:
            pass
