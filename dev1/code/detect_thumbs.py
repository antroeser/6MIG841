"""
detect_thumbs.py - Devoir 1 : compter les pouces leves devant la camera.

Assemble la camera (OpenCV), le suivi de main (`ihr_ros.hands`, API Tasks de
MediaPipe) et la decision (`thumb_detector`). Tout ce qui decide vit dans
`thumb_detector`, tout ce qui touche au materiel et a l'affichage vit ici. C'est
cette separation qui permet de tester le Devoir 1 sans webcam (workflow.md R5).

Usage :
    python Devoir1/code/detect_thumbs.py
    python Devoir1/code/detect_thumbs.py --camera-index 1
    python Devoir1/code/detect_thumbs.py --source video.mp4
    python Devoir1/code/detect_thumbs.py --headless --max-frames 30 --json

Touches : q ou Echap pour quitter, r pour remettre le filtre temporel a zero.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Permet de lancer le script directement, sans variable PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ihr_ros import config  # noqa: E402
from ihr_ros.hands import HandTracker, hand_connections  # noqa: E402
from ihr_ros.overlay import CYAN, GREEN, RED, WHITE, draw_hand, draw_lines, put_text  # noqa: E402

from emotion_detector import EmotionStabilizer, analyse_faces  # noqa: E402
from thumb_detector import ThumbCounter, count_thumbs_up  # noqa: E402


def configure_streams() -> None:
    """Forcer utf-8 sur stdout et stderr, sans jamais lever (console cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def open_source(source: str | int, camera_cfg: dict[str, Any]):
    """
    --------------------------------------------------------------------------
    Purpose:
        Ouvrir la camera ou le fichier video, et verifier qu'une trame arrive.
        `isOpened()` seul ne suffit pas : sous Windows, une camera deja prise par
        Teams ou Zoom s'ouvre sans erreur puis ne rend aucune image.

    Inputs:
        source (str | int): index de camera, ou chemin d'un fichier video
        camera_cfg (dict): section camera de la configuration

    Outputs:
        capture (cv2.VideoCapture): source ouverte et verifiee
    --------------------------------------------------------------------------
    """
    import cv2

    capture = cv2.VideoCapture(source)
    if isinstance(source, int):
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(camera_cfg["frame_width"]))
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(camera_cfg["frame_height"]))
        capture.set(cv2.CAP_PROP_FPS, int(camera_cfg["fps"]))

    if not capture.isOpened():
        capture.release()
        raise SystemExit(
            f"ERREUR : source '{source}' impossible a ouvrir.\n"
            "  - camera occupee par Teams, Zoom ou l'application Camera de Windows ?\n"
            "  - mauvais index ? essayer --camera-index 1\n"
            "  - verifier avec : python Lab1/code/check_env.py --camera"
        )

    ok, frame = capture.read()
    if not ok or frame is None:
        capture.release()
        raise SystemExit(
            f"ERREUR : source '{source}' ouverte mais aucune trame lue. "
            "La camera est probablement utilisee par une autre application."
        )
    return capture


def build_hud(verdicts, stable_count: int, raw_count: int, fps: float,
             emotion_label: str | None = None):
    """
    --------------------------------------------------------------------------
    Purpose:
        Composer les lignes de l'affichage tete haute. La justification de chaque
        main y figure : un etudiant qui lit "3 doigts replies sur 4 exiges" corrige
        son geste, la ou un compteur nu le laisse deviner.

    Inputs:
        verdicts (list): un ThumbVerdict par main detectee
        stable_count (int): decompte filtre dans le temps
        raw_count (int): decompte de la trame courante
        fps (float): cadence mesuree, images par seconde
        emotion_label (str | None): etiquette d'emotion stable, absente si le
                                    suivi de visage est desactive

    Outputs:
        lines (list): couples (texte, couleur BGR)
    --------------------------------------------------------------------------
    """
    lines = [
        (f"Pouces leves : {stable_count}", GREEN),
        (f"trame : {raw_count}    {fps:5.1f} ips", WHITE),
    ]
    for index, verdict in enumerate(verdicts):
        lines.append((f"main {index + 1} : {verdict.explain()}",
                      GREEN if verdict.is_up else RED))
    if emotion_label is not None:
        lines.append((f"emotion : {emotion_label}", CYAN))
    return lines


def run(args: argparse.Namespace) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Boucle principale : lire une trame, suivre les mains, decider, afficher.

    Inputs:
        args (Namespace): arguments de la ligne de commande

    Outputs:
        summary (dict): trames traitees, cadence, dernier decompte stable
    --------------------------------------------------------------------------
    """
    import cv2

    devoir1 = config.section("devoir1")
    camera_cfg = config.section("camera")

    source: str | int = args.source if args.source else int(
        args.camera_index if args.camera_index is not None else camera_cfg["index"]
    )
    flip = bool(camera_cfg["flip_horizontal"]) and not args.source

    capture = open_source(source, camera_cfg)
    counter = ThumbCounter(devoir1)
    quit_keys = {int(code) for code in devoir1["quit_key_codes"]}
    connections = hand_connections()

    frames = 0
    started = time.monotonic()
    fps = 0.0
    last_verdicts: list[Any] = []
    raw_count = 0

    print(f"Devoir 1 - decompte des pouces leves (source : {source})")
    print(f"Filtre temporel : {counter.window} trames consecutives identiques.")

    tracker = HandTracker(
        max_hands=int(devoir1["max_num_hands"]),
        min_detection_confidence=float(devoir1["min_detection_confidence"]),
        min_tracking_confidence=float(devoir1["min_tracking_confidence"]),
    )
    print(f"Modele MediaPipe : {tracker.model_path}")

    # Suivi d'emotion, optionnel : desactivable par --no-emotion, sans toucher au
    # decompte de pouces si le modele de visage est absent ou indesirable.
    emotion_cfg = devoir1.get("emotion")
    face_tracker = None
    emotion_stabilizer = None
    stable_emotion: str | None = None
    if emotion_cfg and not args.no_emotion:
        from emotion_detector import NEUTRE  # noqa: PLC0415
        from ihr_ros.face import FaceTracker  # noqa: PLC0415

        face_tracker = FaceTracker(
            max_faces=int(emotion_cfg["max_num_faces"]),
            min_detection_confidence=float(emotion_cfg["min_face_detection_confidence"]),
            min_presence_confidence=float(emotion_cfg["min_face_presence_confidence"]),
            min_tracking_confidence=float(emotion_cfg["min_tracking_confidence"]),
        )
        emotion_stabilizer = EmotionStabilizer(emotion_cfg)
        stable_emotion = NEUTRE
        print(f"Modele MediaPipe (emotion) : {face_tracker.model_path}")

    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                if args.source:
                    break  # fin normale d'un fichier video
                print("Trame vide ignoree.", file=sys.stderr)
                continue

            if flip:
                frame = cv2.flip(frame, 1)

            tracked = tracker.process(frame)
            height, width = frame.shape[:2]
            raw_count, last_verdicts = count_thumbs_up(
                [hand.landmarks for hand in tracked], width, height, devoir1
            )
            stable = counter.update(raw_count)

            if face_tracker is not None:
                faces = face_tracker.process(frame)
                emotion_verdicts = analyse_faces(
                    [face.blendshapes for face in faces], emotion_cfg
                )
                raw_emotion = emotion_verdicts[0].label if emotion_verdicts else NEUTRE
                stable_emotion = emotion_stabilizer.update(raw_emotion)

            frames += 1
            elapsed = time.monotonic() - started
            if elapsed > 0:
                fps = frames / elapsed

            if not args.headless:
                for hand in tracked:
                    draw_hand(frame, hand.landmarks, connections)
                draw_lines(frame, build_hud(last_verdicts, stable, raw_count, fps,
                                            stable_emotion))
                put_text(frame, "q / Echap : quitter    r : reinitialiser",
                         (12, height - 14), WHITE, 0.45, 1)
                cv2.imshow("Devoir 1 - pouces leves", frame)

                key = cv2.waitKey(1) & 0xFF
                if key in quit_keys:
                    break
                if key == ord("r"):
                    counter.reset()
                    if emotion_stabilizer is not None:
                        emotion_stabilizer.reset()
                    print("Filtre reinitialise.")

            if args.max_frames and frames >= args.max_frames:
                break
    finally:
        tracker.close()
        if face_tracker is not None:
            face_tracker.close()
        capture.release()
        if not args.headless:
            cv2.destroyAllWindows()

    return {
        "trames": frames,
        "ips": round(fps, 2),
        "decompte_stable": counter.stable_count,
        "decompte_brut_dernier": raw_count,
        "mains_dernier_verdict": [asdict(v) for v in last_verdicts],
        "emotion_stable": stable_emotion,
    }


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    parser = argparse.ArgumentParser(
        description="Devoir 1 - compter les pouces leves devant la camera."
    )
    parser.add_argument("--camera-index", type=int, default=None,
                        help="index de camera OpenCV (defaut : celui de ihr_config.json)")
    parser.add_argument("--source", default=None,
                        help="fichier video a la place de la camera")
    parser.add_argument("--headless", action="store_true",
                        help="ne rien afficher, utile en test ou sans ecran")
    parser.add_argument("--no-emotion", action="store_true",
                        help="desactiver le suivi d'emotion faciale")
    parser.add_argument("--max-frames", type=int, default=0,
                        help="s'arreter apres N trames (0 = illimite)")
    parser.add_argument("--json", action="store_true",
                        help="imprimer le resume final en JSON")
    args = parser.parse_args(argv)

    summary = run(args)

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"\n{summary['trames']} trames, {summary['ips']} images par seconde, "
              f"dernier decompte stable : {summary['decompte_stable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
