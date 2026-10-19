"""
planif.world - Grille de planification, geometrie de cellule et occupation des obstacles.

Palier 0 des trois planificateurs (docs/superpowers/plans/6mig841-ameliorations/plan06.md) :
astar, thetastar, dstarlite, compare et app lisent tous la grille, la taille de cellule, le
depart, le but et les obstacles ici. Aucune valeur numerique n'est ecrite en dur ailleurs
(workflow.md R7).

Le fichier lu est `planif_config.json`, cherche dans cet ordre :
  1. le chemin donne par la variable d'environnement PLANIF_CONFIG,
  2. `planif_config.json` a cote du paquet `planif`.

Ce module est volontairement independant de `ihr_ros` : l'application matplotlib du Lab 1
(spec.md, "Le substitut tkinter et l'application matplotlib du Lab 1 restent separes") ne
depend que de matplotlib et numpy, jamais de la configuration du robot ni de son fichier
`ihr_config.json`.

Une cle absente ou une cellule invalide leve une erreur explicite qui nomme la cle ou la
cellule, jamais un repli silencieux (R3, R8).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Iterable

Cellule = tuple[int, int]  # (colonne, ligne)

_ENV_VAR = "PLANIF_CONFIG"
_FILENAME = "planif_config.json"

_cache: dict[str, Any] | None = None
_cache_path: Path | None = None

# Ordre fixe des huit deplacements : garantit un ordre de visite deterministe (R19), donc
# un depart-egalite deterministe pour A*, Theta* et D*-Lite.
_DEPLACEMENTS_8: tuple[tuple[int, int], ...] = (
    (1, 0), (1, 1), (0, 1), (-1, 1),
    (-1, 0), (-1, -1), (0, -1), (1, -1),
)


class ConfigError(RuntimeError):
    """Configuration de planification absente, illisible, ou cle manquante."""


class CelluleInvalideError(ValueError):
    """Cellule hors grille, ou pas de cellule nul/negatif rendant une conversion infinie."""


def config_path() -> Path:
    """
    --------------------------------------------------------------------------
    Purpose:
        Resoudre le chemin du fichier de configuration de planification, sans le lire.

    Inputs:
        aucun (lit la variable d'environnement PLANIF_CONFIG si elle existe)

    Outputs:
        path (Path): chemin absolu du fichier de configuration
    --------------------------------------------------------------------------
    """
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / _FILENAME).resolve()


def load_config(force_reload: bool = False) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Charger planif_config.json une seule fois par processus.

    Inputs:
        force_reload (bool): relire le fichier meme s'il est deja en cache

    Outputs:
        config (dict): contenu integral de planif_config.json
    --------------------------------------------------------------------------
    """
    global _cache, _cache_path
    path = config_path()
    if _cache is not None and not force_reload and _cache_path == path:
        return _cache

    if not path.is_file():
        raise ConfigError(
            f"Configuration de planification introuvable : {path}. "
            f"Definir {_ENV_VAR} ou replacer {_FILENAME} a cote du paquet planif."
        )
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Configuration de planification illisible ({path}) : {exc}") from exc

    _cache = data
    _cache_path = path
    return data


def config_section(name: str) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Retourner une section de premier niveau (grille, depart, but...).

    Inputs:
        name (str): nom de la section

    Outputs:
        section (dict): contenu de la section
    --------------------------------------------------------------------------
    """
    data = load_config()
    if name not in data:
        raise ConfigError(
            f"Section '{name}' absente de {config_path()}. "
            f"Sections presentes : {sorted(k for k in data if not k.startswith('_'))}."
        )
    return data[name]


def config_value(section_name: str, key: str) -> Any:
    """
    --------------------------------------------------------------------------
    Purpose:
        Lire une valeur de configuration, en echouant explicitement si absente.

    Inputs:
        section_name (str): nom de la section
        key (str): nom de la cle dans cette section

    Outputs:
        value (Any): valeur lue
    --------------------------------------------------------------------------
    """
    data = config_section(section_name)
    if key not in data:
        raise ConfigError(
            f"Cle '{key}' absente de la section '{section_name}' dans {config_path()}. "
            f"Cles presentes : {sorted(data)}."
        )
    return data[key]


def rectangle_vers_cellules(rectangle: dict[str, int]) -> set[Cellule]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Deplier un rectangle de configuration en l'ensemble de ses cellules.

    Inputs:
        rectangle (dict): cles colonne_min, colonne_max, ligne_min, ligne_max (incluses)

    Outputs:
        cellules (set[Cellule]): toutes les cellules du rectangle
    --------------------------------------------------------------------------
    """
    cellules: set[Cellule] = set()
    for colonne in range(rectangle["colonne_min"], rectangle["colonne_max"] + 1):
        for ligne in range(rectangle["ligne_min"], rectangle["ligne_max"] + 1):
            cellules.add((colonne, ligne))
    return cellules


class World:
    """
    Grille rectangulaire de cellules carrees, avec une occupation d'obstacle mutable.

    Toutes les valeurs geometriques viennent de planif_config.json (R7). Une instance peut
    aussi etre construite depuis un dictionnaire fourni par un appelant (un test, par
    exemple), pour les scenarios limites (arrivee enfermee, cellule hors grille, pas de
    cellule nul) sans toucher au fichier reel.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        donnees = config if config is not None else load_config()

        grille = donnees.get("grille")
        if grille is None:
            raise ConfigError("Section 'grille' absente de la configuration de planification.")
        for cle in ("largeur_cellules", "hauteur_cellules", "taille_cellule"):
            if cle not in grille:
                raise ConfigError(f"Cle '{cle}' absente de la section 'grille'.")

        self.largeur_cellules: int = grille["largeur_cellules"]
        self.hauteur_cellules: int = grille["hauteur_cellules"]
        self.taille_cellule: float = grille["taille_cellule"]
        self.origine_x: float = grille.get("origine_x", 0.0)
        self.origine_y: float = grille.get("origine_y", 0.0)

        if not self.taille_cellule or self.taille_cellule <= 0:
            raise CelluleInvalideError(
                f"Le pas de cellule (taille_cellule={self.taille_cellule!r}) ne peut pas "
                "etre nul ou negatif : toute conversion grille <-> unites deviendrait infinie."
            )

        self._occupees: set[Cellule] = set()
        obstacle_initial = donnees.get("obstacle_initial")
        if obstacle_initial:
            self._occupees |= rectangle_vers_cellules(obstacle_initial)

        depart = donnees.get("depart")
        but = donnees.get("but")
        self.depart: Cellule | None = (depart["colonne"], depart["ligne"]) if depart else None
        self.but: Cellule | None = (but["colonne"], but["ligne"]) if but else None

    def est_dans_la_grille(self, cellule: Cellule) -> bool:
        """Vrai si `cellule` tombe dans les bornes de la grille."""
        colonne, ligne = cellule
        return 0 <= colonne < self.largeur_cellules and 0 <= ligne < self.hauteur_cellules

    def _verifier_dans_la_grille(self, cellule: Cellule) -> None:
        if not self.est_dans_la_grille(cellule):
            raise CelluleInvalideError(
                f"Cellule {cellule} hors grille (largeur={self.largeur_cellules}, "
                f"hauteur={self.hauteur_cellules})."
            )

    def est_occupee(self, cellule: Cellule) -> bool:
        """Vrai si `cellule` porte un obstacle. Leve CelluleInvalideError si hors grille."""
        self._verifier_dans_la_grille(cellule)
        return cellule in self._occupees

    def vers_unites(self, cellule: Cellule) -> tuple[float, float]:
        """Convertit une cellule de grille vers les coordonnees de son centre, en unites."""
        self._verifier_dans_la_grille(cellule)
        colonne, ligne = cellule
        x = self.origine_x + (colonne + 0.5) * self.taille_cellule
        y = self.origine_y + (ligne + 0.5) * self.taille_cellule
        return (x, y)

    def vers_cellule(self, point: tuple[float, float]) -> Cellule:
        """Convertit un point en unites vers la cellule de grille qui le contient."""
        x, y = point
        colonne = math.floor((x - self.origine_x) / self.taille_cellule)
        ligne = math.floor((y - self.origine_y) / self.taille_cellule)
        cellule = (colonne, ligne)
        self._verifier_dans_la_grille(cellule)
        return cellule

    def definir_occupation(self, cellules: Iterable[Cellule], occupee: bool) -> list[Cellule]:
        """
        Marque `cellules` comme occupees ou libres. Rend la liste des cellules dont
        l'occupation a reellement change, pour que D*-Lite sache lesquelles reexaminer.
        """
        changees: list[Cellule] = []
        for cellule in cellules:
            self._verifier_dans_la_grille(cellule)
            deja_occupee = cellule in self._occupees
            if occupee and not deja_occupee:
                self._occupees.add(cellule)
                changees.append(cellule)
            elif not occupee and deja_occupee:
                self._occupees.discard(cellule)
                changees.append(cellule)
        return changees

    def voisins(self, cellule: Cellule) -> list[Cellule]:
        """
        Rend les cellules voisines (8-connexite) dans la grille, ni occupees ni hors
        grille, dans un ordre fixe (R19). Refuse une diagonale qui couperait un coin
        entre deux cellules occupees adjacentes.
        """
        self._verifier_dans_la_grille(cellule)
        colonne, ligne = cellule
        resultat: list[Cellule] = []
        for dc, dl in _DEPLACEMENTS_8:
            voisine = (colonne + dc, ligne + dl)
            if not self.est_dans_la_grille(voisine) or voisine in self._occupees:
                continue
            if dc != 0 and dl != 0:
                cote_a = (colonne + dc, ligne)
                cote_b = (colonne, ligne + dl)
                if cote_a in self._occupees and cote_b in self._occupees:
                    continue
            resultat.append(voisine)
        return resultat

    def voisins_potentiels(self, cellule: Cellule) -> list[Cellule]:
        """
        Cellules geometriquement adjacentes (8-connexite), sans filtrer l'occupation.
        Sert a D*-Lite pour retrouver, apres un changement d'occupation sur `cellule`,
        toutes les cellules dont le cout de deplacement vers `cellule` a pu changer.
        """
        self._verifier_dans_la_grille(cellule)
        colonne, ligne = cellule
        return [
            (colonne + dc, ligne + dl)
            for dc, dl in _DEPLACEMENTS_8
            if self.est_dans_la_grille((colonne + dc, ligne + dl))
        ]

    def cout_deplacement(self, a: Cellule, b: Cellule) -> float:
        """Distance euclidienne entre deux cellules, en unites (pas necessairement adjacentes)."""
        ax, ay = a
        bx, by = b
        return math.hypot(bx - ax, by - ay) * self.taille_cellule

    def distance_heuristique(self, a: Cellule, b: Cellule) -> float:
        """
        Distance octile entre deux cellules, en unites : heuristique admissible et
        coherente pour un cout de deplacement euclidien 8-connexe (utilisee par A*,
        Theta* et D*-Lite).
        """
        dc = abs(a[0] - b[0])
        dl = abs(a[1] - b[1])
        droit = max(dc, dl) - min(dc, dl)
        diagonal = min(dc, dl)
        return (droit + diagonal * math.sqrt(2)) * self.taille_cellule

    def ligne_de_vue_libre(self, a: Cellule, b: Cellule) -> bool:
        """
        Vrai si le segment entre les centres de `a` et `b` ne traverse aucune cellule
        occupee (Bresenham, toutes directions). Les deux extremites elles-memes ne sont
        pas testees : seules les cellules strictement intermediaires comptent.
        """
        self._verifier_dans_la_grille(a)
        self._verifier_dans_la_grille(b)
        # Indice : parcours exact de grille (DDA/Amanatides-Woo) : avancer cellule par cellule vers la frontiere la plus proche, tester l'occupation a chaque cellule visitee sauf aux deux extremites
        # Tests : test_ligne_de_vue_libre_a_cote_de_l_obstacle_mais_pas_a_travers, test_ligne_de_vue_libre_diagonale_qui_traverse_une_cellule_occupee_est_bloquee, test_ligne_de_vue_libre_refuse_le_coin_partage_par_deux_cellules_occupees_en_diagonale
        raise NotImplementedError(
            "fonction 'World.ligne_de_vue_libre' a implementer (voir l'enonce et les tests cites)"
        )

    def cellules_obstacle(self) -> frozenset[Cellule]:
        """Copie immuable des cellules actuellement occupees, pour l'affichage."""
        return frozenset(self._occupees)
