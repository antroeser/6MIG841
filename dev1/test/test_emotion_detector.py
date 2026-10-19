"""
test_emotion_detector.py - Preuves du contrat de emotion_detector.py (Devoir 1,
extension "emotion", 6MIG841).

Aucune camera, aucun MediaPipe : les blendshapes sont des dicts nommes ecrits a la
main, la meme forme que rend `ihr_ros.face.FaceTracker.process` (workflow.md R5).
"""

from __future__ import annotations

import pytest

from emotion_detector import (
    EN_COLERE,
    HEUREUX,
    NEUTRE,
    SURPRIS,
    TRISTE,
    EmotionStabilizer,
    analyse_emotion,
    analyse_faces,
)


def _blendshapes(**scores: float) -> dict[str, float]:
    """Visage neutre par defaut ; seuls les noms passes en argument different de 0."""
    return dict(scores)


def test_visage_sans_blendshapes_est_neutre(emotion_cfg):
    """Un dict de blendshapes vide (aucun visage) doit rendre le verdict neutre."""
    verdict = analyse_emotion({}, emotion_cfg)
    assert verdict.label == NEUTRE


@pytest.mark.parametrize(
    "scores, attendu",
    [
        ({"mouthSmileLeft": 0.8, "mouthSmileRight": 0.7}, HEUREUX),
        ({"mouthFrownLeft": 0.6, "mouthFrownRight": 0.6}, TRISTE),
        ({"browDownLeft": 0.7, "browDownRight": 0.65}, EN_COLERE),
        ({"eyeWideLeft": 0.6, "eyeWideRight": 0.6, "jawOpen": 0.5}, SURPRIS),
    ],
    ids=["heureux", "triste", "en_colere", "surpris"],
)
def test_chaque_categorie_lemporte_quand_son_blendshape_domine(scores, attendu, emotion_cfg):
    """La categorie dont les blendshapes dominent doit etre celle rendue."""
    verdict = analyse_emotion(_blendshapes(**scores), emotion_cfg)
    assert verdict.label == attendu


def test_un_score_sous_le_seuil_minimal_reste_neutre(emotion_cfg):
    """Un sourire trop faible (sous min_score) ne doit pas basculer en 'heureux'."""
    faible = emotion_cfg["min_score"] / 2
    verdict = analyse_emotion(
        _blendshapes(mouthSmileLeft=faible, mouthSmileRight=faible), emotion_cfg
    )
    assert verdict.label == NEUTRE


def test_toutes_les_categories_sont_rapportees_meme_quand_neutre(emotion_cfg):
    """Le verdict doit porter les quatre scores, pas seulement celui retenu."""
    verdict = analyse_emotion({}, emotion_cfg)
    assert set(verdict.scores) == {HEUREUX, TRISTE, EN_COLERE, SURPRIS}


def test_explain_dun_verdict_neutre_ne_cite_aucun_score(emotion_cfg):
    """explain() d'un verdict neutre reste la simple chaine 'neutre'."""
    verdict = analyse_emotion({}, emotion_cfg)
    assert verdict.explain() == "neutre"


def test_explain_dun_verdict_retenu_cite_sa_categorie_et_son_score(emotion_cfg):
    """explain() d'un verdict retenu nomme la categorie et son score."""
    verdict = analyse_emotion(
        _blendshapes(mouthSmileLeft=0.9, mouthSmileRight=0.9), emotion_cfg
    )
    assert HEUREUX in verdict.explain()


def test_analyse_faces_rend_un_verdict_par_visage_dans_lordre_recu(emotion_cfg):
    """analyse_faces doit juger chaque visage independamment, dans l'ordre recu."""
    faces = [
        _blendshapes(mouthSmileLeft=0.9, mouthSmileRight=0.9),
        {},
        _blendshapes(browDownLeft=0.8, browDownRight=0.8),
    ]
    verdicts = analyse_faces(faces, emotion_cfg)
    assert [v.label for v in verdicts] == [HEUREUX, NEUTRE, EN_COLERE]


def test_stabilizer_ne_publie_quapres_debounce_frames_etiquettes_identiques(emotion_cfg):
    """Une etiquette repetee window fois doit etre publiee, pas avant."""
    stabilizer = EmotionStabilizer(emotion_cfg)
    window = stabilizer.window
    for _ in range(window - 1):
        assert stabilizer.update(HEUREUX) == NEUTRE
    assert stabilizer.update(HEUREUX) == HEUREUX


def test_stabilizer_alternance_ne_publie_jamais(emotion_cfg):
    """Une alternance stricte entre deux etiquettes ne doit jamais devenir stable."""
    stabilizer = EmotionStabilizer(emotion_cfg)
    for i in range(20):
        etiquette = HEUREUX if i % 2 == 0 else TRISTE
        assert stabilizer.update(etiquette) == NEUTRE


def test_stabilizer_reset_revient_a_neutre(emotion_cfg):
    """reset() doit vider l'historique et republier neutre au prochain appel isole."""
    stabilizer = EmotionStabilizer(emotion_cfg)
    for _ in range(stabilizer.window):
        stabilizer.update(HEUREUX)
    assert stabilizer.stable_label == HEUREUX

    stabilizer.reset()
    assert stabilizer.stable_label == NEUTRE
    assert stabilizer.update(TRISTE) == NEUTRE


def test_debounce_frames_a_zero_est_refuse():
    """Zero desactiverait le filtre sans le dire : refuse explicitement."""
    with pytest.raises(ValueError):
        EmotionStabilizer({"debounce_frames": 0, "min_score": 0.35})
