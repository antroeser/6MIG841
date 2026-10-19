"""
ihr_ros.config - Chargement de la configuration commune du laboratoire 6MIG841.

Etage 0 du solutionnaire : tous les modules des trois travaux lisent leurs seuils,
vitesses, topics et delais ici. Aucune valeur numerique n'est ecrite en dur ailleurs
(voir workflow.md, regle R7).

Le fichier lu est `ihr_config.json`, cherche dans cet ordre :
  1. le chemin donne par la variable d'environnement IHR_CONFIG,
  2. `ihr_config.json` a cote du paquet `ihr_ros`.

Une cle absente est une erreur explicite qui nomme la cle et le fichier attendu, jamais
une valeur par defaut silencieuse.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_ENV_VAR = "IHR_CONFIG"
_FILENAME = "ihr_config.json"

_cache: dict[str, Any] | None = None
_cache_path: Path | None = None


class ConfigError(RuntimeError):
    """Configuration absente, illisible, ou cle manquante."""


def config_path() -> Path:
    """
    --------------------------------------------------------------------------
    Purpose:
        Resoudre le chemin du fichier de configuration sans le lire.

    Inputs:
        aucun (lit la variable d'environnement IHR_CONFIG si elle existe)

    Outputs:
        path (Path): chemin absolu du fichier de configuration
    --------------------------------------------------------------------------
    """
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / _FILENAME).resolve()


def load(force_reload: bool = False) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Charger la configuration complete, une seule fois par processus.

    Inputs:
        force_reload (bool): relire le fichier meme s'il est deja en cache

    Outputs:
        config (dict): contenu integral de ihr_config.json
    --------------------------------------------------------------------------
    """
    global _cache, _cache_path
    path = config_path()
    if _cache is not None and not force_reload and _cache_path == path:
        return _cache

    if not path.is_file():
        raise ConfigError(
            f"Configuration introuvable : {path}. "
            f"Definir {_ENV_VAR} ou replacer {_FILENAME} a cote du paquet ihr_ros."
        )
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Configuration illisible ({path}) : {exc}") from exc

    _cache = data
    _cache_path = path
    return data


def section(name: str) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Retourner une section de premier niveau (turtlesim, devoir1, projet...).

    Inputs:
        name (str): nom de la section

    Outputs:
        section (dict): contenu de la section
    --------------------------------------------------------------------------
    """
    data = load()
    if name not in data:
        raise ConfigError(
            f"Section '{name}' absente de {config_path()}. "
            f"Sections presentes : {sorted(k for k in data if not k.startswith('_'))}."
        )
    return data[name]


def get(section_name: str, key: str) -> Any:
    """
    --------------------------------------------------------------------------
    Purpose:
        Lire une valeur, en echouant de maniere explicite si la cle manque.

    Inputs:
        section_name (str): nom de la section
        key (str): nom de la cle dans cette section

    Outputs:
        value (Any): valeur lue
    --------------------------------------------------------------------------
    """
    data = section(section_name)
    if key not in data:
        raise ConfigError(
            f"Cle '{key}' absente de la section '{section_name}' dans {config_path()}. "
            f"Cles presentes : {sorted(data)}."
        )
    return data[key]
