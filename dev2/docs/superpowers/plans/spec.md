# Spec

Détecter combien de mains lèvent le pouce dans une trame webcam, de façon stable
d'une image à l'autre (Devoir1).

Fonctions à implémenter dans `code/thumb_detector.py`, en respectant leurs
docstrings (Purpose, Inputs, Outputs) et leurs commentaires Indice :
- `is_thumb_extended` : compare les trois distances au poignet dans l'ordre
  MCP, IP, TIP (pouce déplié si elles croissent), plus le critère d'orientation.
  Aucun seuil absolu en coordonnées normalisées : le verdict doit rester valide
  quelle que soit la distance main-caméra (utiliser des rapports).
  Ne pas comparer directement deux ordonnées (la main peut être inclinée).
- `ThumbCounter.update` : ajouter la valeur à l'historique, ne publier qu'une
  valeur lorsque les `window` dernières valeurs sont toutes identiques.

La suite `test/` doit passer en entier. Ne fais que ce que le plan en cours
demande.

Interdit : modifier les fichiers de `test/`, changer la signature d'une fonction
existante, ajouter une dépendance, toucher à `code/detect_thumbs.py` ou
`code/emotion_detector.py` (plomberie fournie).
