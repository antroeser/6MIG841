"""
__init__.py pour le package de tests.

Ajoute le répertoire du code au sys.path pour que unittest puisse
trouver les modules de dev2\code.
"""
import os
import sys

# Ajouter le répertoire du code au chemin de recherche des modules
_code_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'code'))
if _code_dir not in sys.path:
    sys.path.insert(0, _code_dir)
