"""
grille_view.py - Le quadrillage 64x64 du Lab 1, avec la tortue du Devoir 2 reportee dessus.

POURQUOI UNE FENETRE A COTE ET NON DANS TURTLESIM. Inventaire complet de turtlesim mesure
le 2026-09-20 sur l'installation ROS2 Humble de ce depot : ses services sont `Kill`,
`SetPen`, `Spawn`, `TeleportAbsolute`, `TeleportRelative`, plus `/clear` et `/reset` ; ses
parametres sont `background_r`, `background_g`, `background_b`, les `qos_overrides.*` et
`use_sim_time` ; ses topics sont `cmd_vel`, `color_sensor` et `pose` par tortue, et il ne
publie AUCUN `/tf`. Il n'a donc aucune API de dessin, et son fond n'accepte qu'une couleur
unie : le crayon d'une tortue est le SEUL mecanisme qui allume un pixel dans sa fenetre.
Afficher le quadrillage sans faire dessiner une tortue exige donc une seconde fenetre.

CE QUI EST TRACE. Le quadrillage est celui du Lab 1, importe et non recopie : `planif.vue`
est le module partage, et `planif.world.World` fournit la grille, l'obstacle du
planificateur, le depart et le but lus dans planif_config.json. La fenetre montre donc le
vrai quadrillage 64x64 aligne sur la solution de reference en lecture seule
`C:\\Users\\m3otis\\solution_robot_dimension`, et non une imitation.

LE CHANGEMENT DE REPERE. turtlesim et la grille du Lab 1 decrivent le meme monde dans deux
unites differentes. Le facteur est DERIVE a l'execution, jamais ecrit en dur :

    echelle = turtlesim.canvas_width / grille.largeur_cellules

soit 11.088 / 64 = 0.17325 unite turtlesim par cellule avec la configuration du 2026-09-20.
Une position turtlesim se ramene donc a la grille par `x_grille = x_turtlesim / echelle`,
et la pose de depart (5.544, 5.544) tombe exactement au centre (32.0, 32.0), ce qui est le
controle le plus simple que la conversion est juste.

Ce module est PUR : il ne connait ni rclpy ni turtlesim, il recoit des nombres. Aucune
fenetre ne s'ouvre a l'import, seul `construire()` cree la figure (R5).
"""

from __future__ import annotations

import math
from typing import Any

from planif import vue
from planif.world import World


def echelle_turtlesim_par_cellule(turtlesim_cfg: dict[str, Any], monde: World) -> float:
    """
    --------------------------------------------------------------------------
    Purpose:
        Rendre le nombre d'unites turtlesim que vaut UNE cellule de la grille du
        Lab 1, derive des deux configurations plutot que duplique (R2 : un seul
        proprietaire par valeur).

        `devoir2.obstacle.echelle_grille_vers_turtlesim` porte une valeur figee de
        0.924, calculee le 2026-09-19 pour la grille de 12 cellules de large qui a
        ete remplacee le 2026-09-20 par une grille de 64. Cette cle est donc
        PERIMEE et n'est deliberement pas lue ici : la deriver est la seule facon
        qu'elle reste juste quand la grille change.

    Inputs:
        turtlesim_cfg (dict): section 'turtlesim' de ihr_config.json
        monde (World): grille du Lab 1

    Outputs:
        echelle (float): unites turtlesim par cellule, strictement positive
    --------------------------------------------------------------------------
    """
    largeur_canevas = float(turtlesim_cfg["canvas_width"])
    if largeur_canevas <= 0.0:
        raise ValueError(
            "turtlesim.canvas_width doit etre strictement positif dans ihr_config.json, "
            f"valeur lue : {largeur_canevas!r}."
        )
    if monde.largeur_cellules <= 0:
        raise ValueError(
            "grille.largeur_cellules doit etre strictement positif dans "
            f"planif_config.json, valeur lue : {monde.largeur_cellules!r}."
        )
    return largeur_canevas / monde.largeur_cellules


def occupation_disque(monde: World, centre_x: float, centre_y: float, rayon: float,
                      echantillons_par_cote: int) -> Any:
    """
    --------------------------------------------------------------------------
    Purpose:
        Rendre la PROBABILITE D'OCCUPATION de chaque cellule par un obstacle
        circulaire, en coordonnees de grille.

        Un quadrillage n'est pas un fond de plan sur lequel on poserait un dessin :
        c'est une grille d'occupation, et chaque case porte la probabilite que
        l'obstacle y soit present. Noir vaut 1, blanc vaut 0. Dessiner le disque
        par-dessus les cases, comme le faisait la premiere version du 2026-09-20,
        montrait une forme que le planificateur ne voit pas : lui ne raisonne que
        sur des cases. C'est la remarque de l'enseignant, et elle porte sur le sens
        de la representation, pas sur son esthetique.

        La fraction couverte est estimee par ECHANTILLONNAGE REGULIER de chaque
        cellule : `echantillons_par_cote` au carre points par case, comptes dans ou
        hors du disque. L'aire exacte d'une intersection disque-carre demande une
        integration par cas (le disque coupe un coin, un cote, deux cotes...), donc
        bien plus de code pour une precision dont l'affichage n'a pas besoin.
        L'erreur est bornee par la taille d'un sous-echantillon, et la methode est
        deterministe : aucun tirage aleatoire, donc le meme resultat a chaque appel
        (R19).

    Inputs:
        monde (World): grille de reference
        centre_x (float): abscisse du centre, en unites de grille
        centre_y (float): ordonnee du centre, en unites de grille
        rayon (float): rayon de l'obstacle, en unites de grille
        echantillons_par_cote (int): points d'echantillonnage par cote de cellule

    Outputs:
        occupation (numpy.ndarray): tableau (hauteur_cellules, largeur_cellules) de
            fractions entre 0.0 et 1.0, indice [ligne, colonne]
    --------------------------------------------------------------------------
    """
    import numpy as np  # noqa: PLC0415

    if echantillons_par_cote < 1:
        raise ValueError(
            "devoir2.grille.echantillons_par_cellule doit valoir au moins 1, "
            f"valeur lue : {echantillons_par_cote!r}."
        )

    largeur = monde.largeur_cellules
    hauteur = monde.hauteur_cellules
    taille = monde.taille_cellule
    occupation = np.zeros((hauteur, largeur), dtype=float)
    if rayon <= 0.0:
        return occupation

    # Decalages des sous-echantillons DANS une cellule, centres sur leurs
    # sous-carres : (i + 0.5) / n, jamais sur les bords, sinon un disque tangent a
    # une frontiere compterait deux fois ou pas du tout.
    pas = taille / echantillons_par_cote
    decalages = (np.arange(echantillons_par_cote) + 0.5) * pas

    colonnes = monde.origine_x + np.arange(largeur) * taille
    lignes = monde.origine_y + np.arange(hauteur) * taille

    # Grille complete des points d'echantillonnage, puis test d'appartenance au
    # disque, puis moyenne par cellule.
    xs = (colonnes[:, None] + decalages[None, :]).ravel()
    ys = (lignes[:, None] + decalages[None, :]).ravel()
    dx = xs - centre_x
    dy = ys - centre_y
    dedans_x = dx[None, :] ** 2
    dedans_y = dy[:, None] ** 2
    dans_le_disque = (dedans_x + dedans_y) <= rayon ** 2

    n = echantillons_par_cote
    par_cellule = dans_le_disque.reshape(hauteur, n, largeur, n)
    return par_cellule.mean(axis=(1, 3))


def turtlesim_vers_grille(x: float, y: float, echelle: float) -> tuple[float, float]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Convertir une position turtlesim en coordonnees de la grille du Lab 1.

    Inputs:
        x (float): abscisse turtlesim
        y (float): ordonnee turtlesim
        echelle (float): unites turtlesim par cellule

    Outputs:
        position (tuple): (x_grille, y_grille) en unites de grille
    --------------------------------------------------------------------------
    """
    if echelle <= 0.0:
        raise ValueError(f"echelle doit etre strictement positive, recue : {echelle!r}.")
    return x / echelle, y / echelle


class VueGrilleDevoir2:
    """
    Fenetre matplotlib du Devoir 2 : le quadrillage du Lab 1, la tortue commandee, et
    la tortue-obstacle, toutes deux reportees en coordonnees de grille.

    Aucune figure n'est creee tant que `construire()` n'a pas ete appelee, pour
    qu'importer ce module pendant la suite de tests n'ouvre aucune fenetre (R5).
    """

    def __init__(self, monde: World, affichage: dict[str, Any],
                 turtlesim_cfg: dict[str, Any], grille_cfg: dict[str, Any],
                 obstacle_cfg: dict[str, Any] | None = None):
        self.monde = monde
        self.affichage = affichage
        self.turtlesim_cfg = turtlesim_cfg
        self.grille_cfg = grille_cfg
        self.obstacle_cfg = obstacle_cfg or {}
        self.echelle = echelle_turtlesim_par_cellule(turtlesim_cfg, monde)

        # Le rayon de l'obstacle est une grandeur du MONDE, mesuree en unites
        # turtlesim (devoir2.obstacle.rayon = 0.5, derive de la taille de l'image
        # de la tortue). Le dessiner a sa vraie taille est ce qui rend visible la
        # marge d'evitement : un point sans dimension ne dit rien de la collision.
        rayon_turtlesim = float(self.obstacle_cfg.get("rayon", 0.0))
        self.rayon_obstacle_grille = rayon_turtlesim / self.echelle

        self.figure: Any = None
        self.ax: Any = None
        self._point_tortue: Any = None
        self._image_occupation: Any = None
        # L'occupation existe DES LA CONSTRUCTION, avant toute figure : un test
        # peut ainsi l'interroger sans ouvrir de fenetre (R5).
        self._occupation: Any = None
        self._trace_x: list[float] = []
        self._trace_y: list[float] = []
        self._ligne_trace: Any = None

    # ---------------------------------------------------------------------- construction

    def construire(self) -> None:
        """Cree la figure, trace le quadrillage du Lab 1 et prepare les artistes mobiles."""
        import matplotlib.pyplot as plt  # noqa: PLC0415  (aucune fenetre a l'import)

        self.figure, self.ax = plt.subplots(
            figsize=(self.affichage["largeur_figure"], self.affichage["hauteur_figure"]),
            dpi=self.affichage["dpi_figure"],
        )
        self.figure.canvas.manager.set_window_title(str(self.grille_cfg["titre_fenetre"]))

        # La GRILLE vient du Lab 1 ; les OBJETS sont ceux du Devoir 2. On ne trace
        # donc NI l'obstacle du planificateur, NI ses cellules de depart et de but :
        # ils appartiennent a l'exercice du Lab 1 et n'existent pas dans turtlesim.
        # Les afficher mettait deux obstacles differents dans la meme image, et
        # comme la pose de depart turtlesim tombe au centre exact de la grille, le
        # robot etait dessine A L'INTERIEUR de l'obstacle du planificateur --
        # pendant qu'on annoncait un evitement de collision (defaut signale par
        # l'enseignant le 2026-09-20). Le seul obstacle reel est la tortue
        # 'obstacle', tracee plus bas a son vrai rayon.
        vue.cadrer_axes(self.ax, self.monde)
        vue.tracer_grille(self.ax, self.monde, self.affichage, avec_obstacle=False)

        (self._ligne_trace,) = self.ax.plot(
            [], [], "-",
            linewidth=float(self.grille_cfg["epaisseur_trace"]),
            color=str(self.grille_cfg["couleur_trace"]),
            zorder=2,
        )
        self._point_tortue = self.ax.scatter(
            [], [], marker="^",
            s=float(self.grille_cfg["aire_marqueur_tortue"]),
            color=str(self.grille_cfg["couleur_tortue"]),
            zorder=4,
        )
        # L'obstacle est une OCCUPATION DE CASES, jamais une forme posee par-dessus
        # le quadrillage : chaque cellule porte la probabilite que l'obstacle y soit
        # present, noir pour 1 et blanc pour 0. C'est ce que le planificateur voit,
        # et c'est la seule representation qui ait un sens sur une grille
        # (remarque de l'enseignant, 2026-09-21).
        #
        # `zorder` la place SOUS les lignes de grille : les cases restent lisibles
        # a travers l'occupation, et l'on voit quelles cellules sont concernees.
        # `interpolation='nearest'` interdit a matplotlib de lisser entre cases, ce
        # qui inventerait des valeurs intermediaires que le calcul n'a pas produites.
        import numpy as np  # noqa: PLC0415

        self._occupation = np.zeros(
            (self.monde.hauteur_cellules, self.monde.largeur_cellules), dtype=float)
        self._image_occupation = self.ax.imshow(
            self._occupation,
            origin="lower",
            extent=(
                self.monde.origine_x,
                self.monde.origine_x + self.monde.largeur_cellules * self.monde.taille_cellule,
                self.monde.origine_y,
                self.monde.origine_y + self.monde.hauteur_cellules * self.monde.taille_cellule,
            ),
            cmap="gray_r",
            vmin=0.0,
            vmax=1.0,
            interpolation="nearest",
            zorder=0,
        )

        # SANS CECI, AUCUNE FENETRE N'APPARAIT. Defaut mesure le 2026-09-20 : le
        # noeud demarrait, journalisait « quadrillage affiche » et restait vivant,
        # mais rien ne s'ouvrait a l'ecran. `plt.subplots()` CREE la figure ; il ne
        # la MONTRE pas. Hors mode interactif -- et `matplotlib.is_interactive()`
        # rend False sous l'interprete conda de ce depot, backend TkAgg -- il faut
        # le demander explicitement. `block=False` rend la main immediatement, pour
        # que rclpy continue de tourner : c'est `pomper()` qui fait ensuite vivre la
        # fenetre, appele depuis le fil PRINCIPAL par grille_node.main().
        plt.show(block=False)

    # ---------------------------------------------------------------------- mise a jour

    def maj_tortue(self, x: float, y: float, theta: float = 0.0) -> tuple[float, float]:
        """
        --------------------------------------------------------------------------
        Purpose:
            Reporter la pose turtlesim de la tortue commandee sur la grille, et
            allonger sa trace.

        Inputs:
            x (float): abscisse turtlesim
            y (float): ordonnee turtlesim
            theta (float): cap en radians, conserve pour la lisibilite du journal

        Outputs:
            position (tuple): (x_grille, y_grille) effectivement affichee
        --------------------------------------------------------------------------
        """
        xg, yg = turtlesim_vers_grille(x, y, self.echelle)
        self._trace_x.append(xg)
        self._trace_y.append(yg)
        borne = int(self.grille_cfg["trace_max_points"])
        if len(self._trace_x) > borne:
            # R10 : aucune accumulation non bornee. Une session longue ne doit pas
            # faire grossir cette liste indefiniment.
            del self._trace_x[:-borne]
            del self._trace_y[:-borne]
        if self._point_tortue is not None:
            self._point_tortue.set_offsets([[xg, yg]])
            self._ligne_trace.set_data(self._trace_x, self._trace_y)
        return xg, yg

    def maj_obstacle(self, x: float, y: float) -> tuple[float, float]:
        """
        --------------------------------------------------------------------------
        Purpose:
            Reporter la tortue-obstacle sur la grille en RECALCULANT l'occupation
            de chaque cellule, et non en deplacant une forme.

        Inputs:
            x (float): abscisse turtlesim du centre de l'obstacle
            y (float): ordonnee turtlesim

        Outputs:
            position (tuple): (x_grille, y_grille) du centre
        --------------------------------------------------------------------------
        """
        xg, yg = turtlesim_vers_grille(x, y, self.echelle)
        self._occupation = occupation_disque(
            self.monde, xg, yg, self.rayon_obstacle_grille,
            int(self.grille_cfg["echantillons_par_cellule"]),
        )
        if self._image_occupation is not None:
            self._image_occupation.set_data(self._occupation)
        return xg, yg

    def occupation(self) -> Any:
        """Le tableau d'occupation courant, pour les tests et pour le journal."""
        return self._occupation

    def pomper(self) -> None:
        """
        Laisser matplotlib traiter ses evenements sans bloquer.

        `plt.pause` est deliberement evite : il appelle `time.sleep` et rendrait la
        cadence du noeud ROS2 dependante de la boucle graphique.
        """
        if self.figure is None:
            return
        self.figure.canvas.draw_idle()
        self.figure.canvas.flush_events()

    def fermer(self) -> None:
        """Fermer la figure, sans exiger qu'elle ait ete construite."""
        if self.figure is None:
            return
        import matplotlib.pyplot as plt  # noqa: PLC0415

        plt.close(self.figure)
        self.figure = None


def cap_vers_degres(theta_rad: float) -> float:
    """Convertir un cap turtlesim (radians) en degres, pour l'affichage seul."""
    return math.degrees(theta_rad)
