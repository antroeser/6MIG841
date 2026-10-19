# Plan 2

1. Dans code/thumb_detector.py, remplacer le raise NotImplementedError de
   ThumbCounter.update en suivant son docstring et son commentaire Indice :
   ajouter la valeur reçue à l'historique (conserver au plus `window` valeurs),
   puis publier cette valeur seulement quand l'historique contient exactement
   `window` valeurs toutes identiques ; sinon ne rien publier. Ne pas modifier
   test/, ni reset() ni la signature de la classe.
   Tests à faire passer : test_valeur_repetee_window_fois_est_publiee,
   test_valeur_repetee_moins_que_window_fois_nest_pas_publiee,
   test_valeurs_alternees_ne_publient_jamais,
   test_reset_remet_le_decompte_stable_a_zero,
   test_les_premieres_maj_ne_publient_quau_dernier_tour_de_la_fenetre.
