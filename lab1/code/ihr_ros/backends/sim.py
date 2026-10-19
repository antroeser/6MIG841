"""
ihr_ros.backends.sim - Substitut de turtlesim, en Python pur.

Raison d'etre, mesuree le 2026-09-18 sur la machine de l'enseignant : WSL2 refuse de
demarrer la moindre machine virtuelle pour ce compte
(`Wsl/Service/CreateInstance/CreateVm/HCS/0x80070569`, y compris sur la distribution
docker-desktop deja enregistree), donc ni WSL2, ni Docker, ni turtlesim ne peuvent
tourner ici sans intervention de l'administration. Le developpement et les tests
devaient malgre tout avancer.

Ce module n'est PAS la solution livree. Il reproduit le modele cinematique et les
bornes de turtlesim assez fidelement pour que le meme code de commande fonctionne des
que ROS2 est disponible, et il annonce dans sa sortie qu'il n'est pas ROS2
(`is_real_ros2 = False`).

Fidelite au turtlesim reel :
  - modele unicycle, integration d'Euler,
  - canevas borne, la tortue s'arrete au mur au lieu de le traverser,
  - consigne oubliee apres `sim.cmd_timeout_seconds`, comme le fait turtlesim.

L'affichage tkinter est facultatif. Sans lui, la dorsale tourne sans fenetre, ce qui
est la forme utilisee par la suite de tests.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Callable

from .. import config
from .base import Pose, TurtleBackend, Twist


def integrate(pose: Pose,
              twist: Twist,
              dt_seconds: float,
              canvas_width: float,
              canvas_height: float) -> Pose:
    """
    --------------------------------------------------------------------------
    Purpose:
        Avancer la pose d'un pas de temps selon le modele unicycle de turtlesim,
        en bornant au canevas. Fonction pure : aucune horloge, aucun etat global,
        donc reproductible et testable (workflow.md R5).

    Inputs:
        pose (Pose): pose courante
        twist (Twist): consigne de vitesse appliquee pendant le pas
        dt_seconds (float): duree du pas, en secondes
        canvas_width (float): largeur du canevas, unites turtlesim
        canvas_height (float): hauteur du canevas, unites turtlesim

    Outputs:
        pose (Pose): nouvelle pose, bornee au canevas
    --------------------------------------------------------------------------
    """
    theta = pose.theta + twist.angular_z * dt_seconds
    theta = math.atan2(math.sin(theta), math.cos(theta))

    x = pose.x + twist.linear_x * math.cos(theta) * dt_seconds
    y = pose.y + twist.linear_x * math.sin(theta) * dt_seconds

    x = max(0.0, min(canvas_width, x))
    y = max(0.0, min(canvas_height, y))

    return Pose(
        x=x,
        y=y,
        theta=theta,
        linear_velocity=twist.linear_x,
        angular_velocity=twist.angular_z,
    )


class SimBackend(TurtleBackend):
    """Dorsale de substitution, sans ROS2."""

    name = "simulateur (substitut, PAS ROS2)"
    is_real_ros2 = False

    def __init__(self, with_window: bool = False, clock: Callable[[], float] | None = None):
        """
        --------------------------------------------------------------------------
        Purpose:
            Preparer le substitut et, si demande, sa fenetre d'affichage.

        Inputs:
            with_window (bool): ouvrir une fenetre tkinter de visualisation
            clock (callable | None): source de temps, injectee pour les tests

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        turtle_cfg = config.section("turtlesim")
        sim_cfg = config.section("sim")

        self._canvas_width = float(turtle_cfg["canvas_width"])
        self._canvas_height = float(turtle_cfg["canvas_height"])
        self._tick = float(sim_cfg["tick_seconds"])
        self._cmd_timeout = float(sim_cfg["cmd_timeout_seconds"])
        self._window_pixels = int(sim_cfg["window_pixels"])
        self._trail_max = int(sim_cfg["trail_max_points"])
        self._premieres_passes = int(sim_cfg["premieres_passes_fenetre"])

        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._pose = Pose(
            x=float(turtle_cfg["start_x"]),
            y=float(turtle_cfg["start_y"]),
            theta=float(turtle_cfg["start_theta"]),
        )
        self._twist = Twist()
        self._last_command_at = self._clock()
        self._trail: list[tuple[float, float]] = [(self._pose.x, self._pose.y)]

        self._closed = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._view = None

        if with_window:
            self._view = _TkView(self, self._window_pixels,
                                 self._canvas_width, self._canvas_height)
            # La fenetre doit s'ouvrir DES LE DEBUT. Sans ces premieres passes, Tk
            # cree la fenetre sans la mapper a l'ecran, et rien n'apparait jusqu'au
            # premier spin_once. Mesure le 2026-09-18 : winfo_ismapped() rendait 0
            # apres trois secondes d'attente, puis 1 apres le premier pump. Or la
            # boucle du Devoir 2 n'appelle spin_once que pendant l'EXECUTION, donc
            # l'utilisateur ne voyait aucune tortue tant qu'il n'avait pas reussi a
            # faire executer une commande.
            for _ in range(self._premieres_passes):
                self._view.pump()

        self._thread = threading.Thread(target=self._run, name="ihr-sim", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ contrat

    def publish(self, twist: Twist) -> None:
        with self._lock:
            self._twist = twist
            self._last_command_at = self._clock()

    def pose(self) -> Pose:
        with self._lock:
            return self._pose

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        if self._view is not None:
            self._view.pump()
        if timeout_seconds > 0.0:
            time.sleep(timeout_seconds)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._tick * 10)
        if self._view is not None:
            self._view.close()

    # ------------------------------------------------------------------ interne

    def _run(self) -> None:
        previous = self._clock()
        while not self._stop_event.wait(self._tick):
            now = self._clock()
            dt = now - previous
            previous = now
            self.step(dt, now)

    def step(self, dt_seconds: float, now: float | None = None) -> Pose:
        """
        --------------------------------------------------------------------------
        Purpose:
            Appliquer un pas de simulation. Publique pour que les tests avancent le
            simulateur sans dependre du temps reel.

        Inputs:
            dt_seconds (float): duree du pas
            now (float | None): instant courant, pris a l'horloge si absent

        Outputs:
            pose (Pose): pose apres le pas
        --------------------------------------------------------------------------
        """
        instant = self._clock() if now is None else now
        with self._lock:
            if instant - self._last_command_at > self._cmd_timeout:
                self._twist = Twist()
            self._pose = integrate(self._pose, self._twist, dt_seconds,
                                   self._canvas_width, self._canvas_height)
            self._trail.append((self._pose.x, self._pose.y))
            if len(self._trail) > self._trail_max:
                del self._trail[: len(self._trail) - self._trail_max]
            return self._pose

    def trail(self) -> list[tuple[float, float]]:
        """Copie de la trace laissee par la tortue, pour l'affichage."""
        with self._lock:
            return list(self._trail)


class _TkView:
    """Fenetre de visualisation minimale. Absente des tests."""

    def __init__(self, backend: SimBackend, pixels: int,
                 canvas_width: float, canvas_height: float):
        import tkinter

        self._tk = tkinter
        self._pixels = pixels
        self._canvas_width = canvas_width
        self._canvas_height = canvas_height
        self._backend = backend

        self._root = tkinter.Tk()
        self._root.title("ihr_ros - SUBSTITUT de turtlesim (pas ROS2)")
        self._canvas = tkinter.Canvas(self._root, width=pixels, height=pixels,
                                      bg="#4556aa", highlightthickness=0)
        self._canvas.pack()
        self._closed = False
        self._root.protocol("WM_DELETE_WINDOW", self.close)

    def _to_pixels(self, x: float, y: float) -> tuple[float, float]:
        return (x / self._canvas_width * self._pixels,
                self._pixels - (y / self._canvas_height * self._pixels))

    def pump(self) -> None:
        if self._closed:
            return
        try:
            self._canvas.delete("all")
            trail = self._backend.trail()
            if len(trail) > 1:
                flat: list[float] = []
                for point in trail:
                    flat.extend(self._to_pixels(*point))
                self._canvas.create_line(*flat, fill="#ffffff", width=2)
            pose = self._backend.pose()
            px, py = self._to_pixels(pose.x, pose.y)
            nose = self._to_pixels(pose.x + math.cos(pose.theta) * 0.6,
                                   pose.y + math.sin(pose.theta) * 0.6)
            self._canvas.create_oval(px - 9, py - 9, px + 9, py + 9,
                                     fill="#3ddc84", outline="")
            self._canvas.create_line(px, py, nose[0], nose[1], fill="#0b2b16", width=3)
            self._canvas.create_text(8, 10, anchor="nw", fill="#ffd166",
                                     text="SUBSTITUT - pas ROS2",
                                     font=("Consolas", 10, "bold"))
            self._canvas.create_text(8, self._pixels - 12, anchor="sw", fill="#ffffff",
                                     text=f"x={pose.x:5.2f}  y={pose.y:5.2f}  "
                                          f"theta={pose.theta:6.3f}",
                                     font=("Consolas", 10))
            self._root.update_idletasks()
            self._root.update()
        except Exception:
            # Une fenetre fermee par l'utilisateur ne doit pas faire tomber la boucle
            # de commande : le programme continue sans affichage.
            self._closed = True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._root.destroy()
        except Exception:
            pass
