"""
voice_input_node.py - Devoir 2, noeud ROS2 : entree vocale (voice_input).

Publie chaque phrase entendue sur le topic de transcription (section 'topics'
de la configuration). Ce noeud NE DECIDE RIEN : c'est dialogue_manager qui lit
la transcription et pousse les evenements de la machine d'etat (plan02.md,
tableau des responsabilites).

Piege 1 (plan02.md). L'ecoute (voice.EntreeVocale.ecouter) est BLOQUANTE : elle
attend une phrase au microphone, au clavier ou en file de script. Appelee
directement dans le rappel d'une minuterie ROS2, elle affamerait l'executeur du
noeud, qui ne pourrait plus rien traiter, pas meme son propre arret. Le remede
retenu : un FIL separe appelle ecouter() en boucle et pousse chaque phrase dans
une file (queue.Queue), pendant qu'une minuterie ROS2 se contente de VIDER
cette file et de publier ce qu'elle contient. La minuterie, elle, ne bloque
jamais.

Le mode d'entree ('micro', 'clavier', 'script', 'auto') vient du parametre
ROS2 'input_mode', pour que devoir2.launch.py puisse le transmettre via
l'argument de lancement 'input' (plan02.md, etape 9).

Ajoute le 2026-09-19 (diagnostic-micro-report.md) : le parametre ROS2
'microphone_device_index' choisit le peripherique d'entree, par defaut celui de
devoir2.microphone_device_index (ihr_config.json, null = peripherique par defaut
de Windows). ROS2 ne type pas un entier optionnel : -1 est la sentinelle « aucun
index choisi », jamais un vrai index de peripherique.

Fenetre de saisie vocale, plan09.md (2026-09-20). Ce noeud OUVRE la fenetre en
production (mode 'micro'/'auto' reussi) : `ouvrir_entree` lui transmet
`on_fermeture=self._sur_fermeture_fenetre`, et voice.MicrophoneInput construit
alors voice_window.VoiceWindow par defaut. Ce noeud n'ouvre PAS sa propre
fenetre separee : il retrouve celle deja construite via `entree.affichage`
(voice.MicrophoneInput.affichage), pour refleter la porte /ihr/ecoute_active a
l'ecran depuis `_on_porte_ecoute` (un rappel ROS2 : AUCUN appel tkinter direct
ici, seulement `fenetre.afficher_ecoute()`, qui n'enregistre qu'une valeur,
voir voice_window.py) et pour que la croix de la fenetre arrete le noeud
proprement (`_sur_fermeture_fenetre`, invoquee par VoiceWindow pendant
`fenetre.pump()`, elle-meme appelee UNIQUEMENT depuis `main()`, sur le fil
PRINCIPAL du processus : tkinter sous Windows leve
`RuntimeError: main thread is not in main loop` pompee depuis tout autre fil,
y compris le fil de fond qui construit la fenetre. Mesure le 2026-09-20,
plan09.md etape 6 : voir `main()` ci-dessous, qui remplace `rclpy.spin(node)`
par une boucle alternant `rclpy.spin_once()` et `fenetre.pump()`).
"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from std_msgs.msg import Bool, String  # noqa: E402

from ihr_ros import config  # noqa: E402

from voice import EntreeVocale, ouvrir_entree  # noqa: E402


class VoiceInputNode(Node):
    """Fil d'ecoute bloquant + minuterie de publication. Aucune decision."""

    def __init__(self, entree: EntreeVocale | None = None,
                 settings: dict[str, Any] | None = None,
                 topics: dict[str, Any] | None = None,
                 editeur: Any | None = None,
                 context: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire le noeud. L'entree et l'editeur sont injectables pour les
            tests hors ligne : quand une entree est fournie, le fil d'ecoute reel
            n'est JAMAIS demarre, et le test pousse lui-meme dans la file avant
            d'appeler le rappel de minuterie en direct (plan02.md : aucun fil,
            aucun spin, aucun micro dans les tests).

        Inputs:
            entree (EntreeVocale | None): source de phrases ; construite depuis
                le parametre ROS2 'input_mode' si absente (chemin de production)
            settings (dict | None): section 'devoir2' de la configuration
            topics (dict | None): section 'topics' de la configuration
            editeur (Any | None): editeur ROS2 du topic de transcription, un
                vrai `create_publisher` si absent
            context (Any | None): contexte rclpy, celui par defaut si absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        super().__init__("voice_input", context=context)
        self._context = context
        self._settings = settings if settings is not None else config.section("devoir2")
        self._topics = topics if topics is not None else config.section("topics")

        self.declare_parameter("input_mode", str(self._settings["input_mode"]))
        mode = self.get_parameter("input_mode").get_parameter_value().string_value

        index_config = self._settings.get("microphone_device_index")
        index_defaut = int(index_config) if index_config is not None else -1
        self.declare_parameter("microphone_device_index", index_defaut)
        index_parametre = self.get_parameter(
            "microphone_device_index"
        ).get_parameter_value().integer_value
        device_index = index_parametre if index_parametre >= 0 else None

        self._file: "queue.Queue[str]" = queue.Queue()
        self._arret = threading.Event()
        self._entree = entree if entree is not None else ouvrir_entree(
            mode, self._settings, device_index=device_index,
            on_fermeture=self._sur_fermeture_fenetre,
        )
        # Fenetre eventuellement ouverte par MicrophoneInput (plan09.md) : None
        # pour toute autre source (ScriptedInput injecte par les tests,
        # KeyboardInput, echec du micro replie sur le clavier).
        self._fenetre = getattr(self._entree, "affichage", None)

        self._editeur = editeur if editeur is not None else self.create_publisher(
            String, str(self._topics["transcription_topic"]),
            int(self._topics["queue_depth"]),
        )

        self._pause_apres_echec = float(
            self._settings["microphone_pause_apres_echec_s"]
        )
        # Le Devoir 2 est une machine d'etat : on n'ecoute QUE lorsqu'elle attend
        # une phrase. `dialogue_manager` publie cette porte a chaque changement
        # d'etat. Ouverte au depart, sinon un gestionnaire qui demarre apres nous
        # laisserait le micro muet jusqu'a sa premiere transition.
        self._porte_ecoute = threading.Event()
        self._porte_ecoute.set()
        self._sub_ecoute = self.create_subscription(
            Bool, str(self._topics["ecoute_active_topic"]),
            self._on_porte_ecoute, int(self._topics["queue_depth"]),
        )
        self._fil: threading.Thread | None = None
        if entree is None:
            self._fil = threading.Thread(target=self._ecouter_en_boucle, daemon=True)
            self._fil.start()

        periode = float(self._topics["voice_input_timer_period_s"])
        self._minuterie = self.create_timer(periode, self._vider_et_publier)

    @property
    def context(self) -> Any:
        """Contexte rclpy transmis au constructeur (celui par defaut si absent)."""
        return self._context

    @property
    def fenetre(self) -> Any:
        """
        Fenetre de saisie vocale ouverte en production (None en mode
        clavier/script, ou si le micro a echoue et s'est replie sur le
        clavier). Lue par main() pour la pomper depuis le fil principal
        (plan09.md, corrige le 2026-09-20 : voir voice_window.py).
        """
        return self._fenetre

    def _on_porte_ecoute(self, message: Any) -> None:
        """
        Ouvrir ou fermer l'ecoute selon l'etat publie par le gestionnaire, et
        refleter cet etat a l'ecran (plan09.md) si une fenetre est ouverte.
        Rappel ROS2 : `fenetre.afficher_ecoute()` n'enregistre qu'une valeur,
        AUCUN appel tkinter direct ici (voice_window.py, piege 1 de plan02.md).
        """
        if message.data:
            self._porte_ecoute.set()
        else:
            self._porte_ecoute.clear()
        if self._fenetre is not None:
            self._fenetre.afficher_ecoute(bool(message.data))

    def _sur_fermeture_fenetre(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            La croix de la fenetre de saisie vocale a ete cliquee (rappel
            on_fermeture de voice_window.VoiceWindow, appele depuis le fil de
            fond qui pompe deja la fenetre, jamais un rappel ROS2) : arreter le
            fil d'ecoute et demander l'arret du noeud, exactement comme un
            Ctrl+C (main(), meme chemin de nettoyage : node.close(),
            node.destroy_node(), rclpy.shutdown()). Aucun processus orphelin :
            rclpy.spin() sort de sa boucle des que le contexte n'est plus valide
            (executor.context.ok() devient faux), et le fil _ecouter_en_boucle
            sort de la sienne des que self._arret est pose.

        Inputs:
            aucun

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._arret.set()
        if rclpy.ok(context=self._context):
            rclpy.try_shutdown(context=self._context)

    def _ecouter_en_boucle(self) -> None:
        """Fil de fond : ecoute bloquante, jamais executee dans un rappel ROS2."""
        while not self._arret.is_set():
            if not self._porte_ecoute.wait(timeout=self._pause_apres_echec):
                continue
            phrase = self._entree.ecouter("Commande ?")
            if phrase:
                self._file.put(phrase)
                continue
            # Une ecoute vide (rien entendu, ou parole non comprise) ne doit pas
            # relancer l'ecoute immediatement : sans cette pause, un micro muet ou
            # un seuil trop haut produit une boucle serree qui inonde le journal du
            # launch et masque les autres noeuds. Mesure du 2026-09-19.
            self._arret.wait(self._pause_apres_echec)

    def _vider_et_publier(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Rappel de minuterie : vider la file et publier chaque phrase, une par
            une. Ne publie RIEN si la file est vide (controle negatif du tableau
            des tests de plan02.md : une minuterie qui publie du vide inonderait
            le topic).

        Inputs:
            aucun

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        while True:
            try:
                phrase = self._file.get_nowait()
            except queue.Empty:
                return
            message = String()
            message.data = phrase
            self._editeur.publish(message)

    def close(self) -> None:
        """Arreter le fil d'ecoute et fermer l'entree. Rappelable sans effet."""
        self._arret.set()
        self._entree.close()


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree du noeud : initialiser rclpy, tourner jusqu'a l'arret.

        CORRIGE le 2026-09-20 (plan09.md, defaut mesure a l'etape 6, l'epreuve
        reelle) : rclpy.spin(node) est remplace par une boucle manuelle qui
        alterne rclpy.spin_once() et fenetre.pump(), les DEUX sur le fil
        PRINCIPAL du processus. tkinter sous Windows leve
        `RuntimeError: main thread is not in main loop` des qu'un widget est
        touche hors de ce fil, meme depuis le fil de fond qui a construit la
        fenetre (voice.MicrophoneInput.ecouter(), appelee par
        _ecouter_en_boucle) : la premiere version de ce noeud pompait la
        fenetre depuis ce fil de fond, et le processus mourait des la
        premiere image. Quand aucune fenetre n'est ouverte (mode
        clavier/script, ou repli sur le clavier), `timeout_sec=None` rend
        cette boucle strictement equivalente a rclpy.spin(node) : aucune
        attente active, spin_once() bloque jusqu'au prochain evenement.

    Inputs:
        argv (list[str] | None): arguments rclpy, ceux de la ligne de commande
            si absents

    Outputs:
        code (int): code de sortie du processus
    --------------------------------------------------------------------------
    """
    rclpy.init(args=argv)
    node = VoiceInputNode()
    try:
        while rclpy.ok(context=node.context):
            periode = node.fenetre.intervalle_pompe if node.fenetre is not None else None
            rclpy.spin_once(node, timeout_sec=periode)
            if node.fenetre is not None:
                node.fenetre.pump()
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
