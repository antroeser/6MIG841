# Progress
**Goal.** The ledger: one section per plan, each a list of tasks, telling the
harness which plan is current and which steps are done.

**Contents.** Task lines only, pointing at `plan<N>.md` for the detail. Never a
restatement of a plan. Marks: `- [ ]` not done, `- [x]` done and audited clean,
`- [!]` audit raised an issue, with one line naming it.

## plan1.md
- [ ] code/state_machine.py : 

- [ ] requirements.txt: declare any package this plan imports

- [ ] in folder test/test_state_machine.py tests : test_refus_en_confirmation_commande_renvoie_a_ecoute_jamais_a_interpretation, test_refus_en_confirmation_action_renvoie_a_interpretation_jamais_a_ecoute

- [ ] in folder test/test_state_machine.py tests : test_signer_is_forward_vrai_rend_une_vitesse_lineaire_positive, test_signer_is_clockwise_vrai_rend_une_vitesse_angulaire_negative

- [ ] tests pass



## plan2.md
- [ ] code/arcs.py : 

- [ ] requirements.txt: declare any package this plan imports

- [ ] in folder test/test_arcs.py tests : test_arc_dont_le_segment_etait_libre_est_refuse, test_arc_entre_dans_l_obstacle_est_detecte, test_arc_frole_l_obstacle_sans_le_toucher

- [ ] tests pass


## plan3.md

- [ ] code/trajectory.py : 

- [ ] requirements.txt: declare any package this plan imports

- [ ] in folder test/test_trajectory.py tests : test_evaluer_ecrete_avant_le_depart_et_apres_la_fin, test_vitesse_nulle_aux_deux_bouts, test_vitesse_maximale_respectee

- [ ] tests pass