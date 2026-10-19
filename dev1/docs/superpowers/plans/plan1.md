# Plan 1

1. Dans code/thumb_detector.py, corriger is_thumb_extended pour que tout les tests passent

   Tests à faire passer : test_verdict_des_cinq_mains_canoniques,
   test_is_thumb_extended_refuse_un_pouce_en_crochet_non_monotone,
   test_pouce_leve_reste_valide_quelle_que_soit_lechelle,
   test_orientation_pouce_juste_sous_le_seuil_reste_vraie,
   test_orientation_pouce_juste_au_dessus_du_seuil_devient_fausse,
   test_count_thumbs_up_sur_liste_mixte_retourne_le_compte_et_lordre,
   test_explain_rend_la_raison_du_rejet_quand_faux,
   test_explain_mentionne_le_compte_de_doigts_replies_quand_vrai,
   test_build_hud_rend_une_ligne_par_main_en_plus_de_lentete,
   test_build_hud_distingue_la_couleur_dune_main_acceptee_et_rejetee,
   test_build_hud_ligne_de_main_reprend_lexplication_du_verdict.


