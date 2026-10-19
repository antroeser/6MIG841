"""
test_config.py - Tests de ihr_ros.config, le chargement de configuration du solutionnaire.

Etage 0 : tous les modules des trois travaux lisent leurs seuils, vitesses et delais ici
(workflow.md R7, aucune valeur numerique en dur ailleurs). Cette suite verifie le chemin
heureux ET les quatre chemins d'echec exiges : section absente, cle absente, IHR_CONFIG
pointant vers un fichier inexistant, IHR_CONFIG pointant vers un JSON malforme. Une cle
absente doit toujours nommer la cle ET lister les cles reellement presentes (jamais une
valeur par defaut silencieuse, voir l'en-tete de config.py).
"""

from __future__ import annotations

import json

import pytest

from ihr_ros import config


def _rediriger_config(tmp_path, monkeypatch, donnees: dict) -> None:
    """Ecrit `donnees` dans un fichier temporaire et fait pointer IHR_CONFIG dessus."""
    chemin = tmp_path / "config_test.json"
    chemin.write_text(json.dumps(donnees), encoding="utf-8")
    monkeypatch.setenv("IHR_CONFIG", str(chemin))
    config.load(force_reload=True)


# --------------------------------------------------------------------- chemin heureux

def test_chemin_par_defaut_pointe_vers_le_fichier_reel():
    """Sans IHR_CONFIG, config_path() resout vers ihr_config.json a cote du paquet ihr_ros."""
    chemin = config.config_path()
    assert chemin.name == "ihr_config.json"
    assert chemin.is_file()


def test_ihr_config_redirige_le_chemin_resolu(tmp_path, monkeypatch):
    """La variable d'environnement IHR_CONFIG l'emporte sur le chemin par defaut."""
    cible = tmp_path / "ailleurs.json"
    cible.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("IHR_CONFIG", str(cible))
    assert config.config_path() == cible.resolve()


def test_chargement_config_reelle_donne_les_sections_du_laboratoire():
    """La vraie ihr_config.json (lue, jamais modifiee) expose turtlesim et sim comme attendu."""
    turtlesim = config.section("turtlesim")
    sim = config.section("sim")
    # Valeurs mesurees sur turtlesim (ROS2), voir ihr_config.json._provenance.turtlesim/sim.
    assert turtlesim["canvas_width"] == pytest.approx(11.088)
    assert sim["cmd_timeout_seconds"] == pytest.approx(1.0)


def test_get_lit_une_valeur_existante():
    """get() retourne directement la valeur quand la cle demandee existe."""
    assert config.get("turtlesim", "queue_depth") == 10


# --------------------------------------------------------------------- chemins d'echec

def test_section_absente_leve_configerror_nommant_la_section(tmp_path, monkeypatch):
    """Une section manquante leve ConfigError et nomme cette section dans le message."""
    _rediriger_config(tmp_path, monkeypatch, {"turtlesim": {"canvas_width": 11.088}})
    with pytest.raises(config.ConfigError, match="devoir1"):
        config.section("devoir1")


def test_cle_absente_leve_configerror_nommant_la_cle_et_les_cles_presentes(tmp_path, monkeypatch):
    """Une cle manquante nomme la cle absente ET liste les cles reellement presentes."""
    _rediriger_config(tmp_path, monkeypatch, {
        "sim": {"tick_seconds": 0.05, "cmd_timeout_seconds": 1.0},
    })
    with pytest.raises(config.ConfigError) as exc_info:
        config.get("sim", "window_pixels")
    message = str(exc_info.value)
    assert "window_pixels" in message
    assert "tick_seconds" in message
    assert "cmd_timeout_seconds" in message


def test_get_sur_section_absente_leve_configerror_de_section(tmp_path, monkeypatch):
    """get() propage l'erreur de section() quand la section elle-meme est absente."""
    _rediriger_config(tmp_path, monkeypatch, {"sim": {}})
    with pytest.raises(config.ConfigError, match="projet"):
        config.get("projet", "angular_gain")


def test_ihr_config_fichier_inexistant_leve_configerror(tmp_path, monkeypatch):
    """IHR_CONFIG pointant vers un fichier absent leve ConfigError, jamais un crash brut."""
    monkeypatch.setenv("IHR_CONFIG", str(tmp_path / "n_existe_pas.json"))
    with pytest.raises(config.ConfigError, match="introuvable"):
        config.load(force_reload=True)


def test_ihr_config_json_malforme_leve_configerror(tmp_path, monkeypatch):
    """Un IHR_CONFIG au JSON corrompu leve ConfigError plutot qu'une JSONDecodeError brute."""
    chemin = tmp_path / "corrompu.json"
    chemin.write_text("{ceci n'est pas du JSON", encoding="utf-8")
    monkeypatch.setenv("IHR_CONFIG", str(chemin))
    with pytest.raises(config.ConfigError, match="illisible"):
        config.load(force_reload=True)
