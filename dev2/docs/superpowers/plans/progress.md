# Progress
**Goal.** The ledger: one section per plan, each a list of tasks, telling the
harness which plan is current and which steps are done.

**Contents.** Task lines only, pointing at `plan<N>.md` for the detail. Never a
restatement of a plan. Marks: `- [ ]` not done, `- [x]` done and audited clean,
`- [!]` audit raised an issue, with one line naming it.

## plan1.md
- [x] Prendre connaissance de l'objectif de la fonction Transitions.repondu dans code/state_machine.py
- [x] Implémenter UNIQUEMENT la fonction Transitions.repondu en tenant compte du contexte et en respectant les rêgles de programmation et de présentation du code. L'etat courant decide ou mene un refus ; SORTIE et INDECIS d'abord
- [x] Prendre connaissance de l'objectif de la fonction signer dans code/state_machine.py
- [x] Implémenter UNIQUEMENT la fonction signer en tenant compte du contexte et en respectant les rêgles de programmation et de présentation du code. La convemtion à utiliser est la suivante : REP-103, antihoraire positif, horaire negatif
- [x] tests - suite a verifier apres les corrections (tous les tests de test_state_machine.py passent)


## plan2.md
- [x] code/arcs.py : Implémentation de echantillonner_arc (Euler explicite, detection collision)

- [x] in folder test/test_arcs.py tests : test_arc_dont_le_segment_etait_libre_est_refuse, test_arc_entre_dans_l_obstacle_est_detecte, test_arc_frole_l_obstacle_sans_le_toucher

- [x] tests pass


## plan3.md

- [ ] code/trajectory.py : 

- [ ] in folder test/test_trajectory.py tests : test_evaluer_ecrete_avant_le_depart_et_apres_la_fin, test_vitesse_nulle_aux_deux_bouts, test_vitesse_maximale_respectee

- [ ] tests pass
