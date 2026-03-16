"""
Seminar 3: Liikumise tuvastamine RTSP voogudest ja graafikute genereerimine

Töötleb kahte RTSP voogu (empty, false_alarm), tuvastab liikumise
ja genereerib 2 graafikut + kokkuvõtte tekstifaili.

Videofailid: empty.mkv, false_alarm.mkv
RTSP voogud: rtsp://172.17.37.81:8554/empty, rtsp://172.17.37.81:8554/false_alarm
"""

import cv2
import os
import time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- KONFIGURATSIOON ---
STREAMS = {
    "empty": "rtsp://172.17.37.81:8554/empty",
    "false_alarm": "rtsp://172.17.37.81:8554/false_alarm",
}

# Alternatiiv: kohalikud .mkv failid (kui RTSP pole kättesaadav)
LOCAL_FILES = {
    "empty": os.path.join(SCRIPT_DIR, "empty.mkv"),
    "false_alarm": os.path.join(SCRIPT_DIR, "false_alarm_test.mkv"),
}

MOTION_THRESHOLD = 15.0
SAMPLE_INTERVAL = 0.02  # sekundit kaadrite vahel


def measure_change(f1, f2):
    """Arvutab kahe kaadri vahelise erinevuse (MAE halltoonides)."""
    gray1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
    small1 = cv2.resize(gray1, (160, 90))
    small2 = cv2.resize(gray2, (160, 90))
    return float(np.mean(cv2.absdiff(small1, small2)))


def is_green_screen(frame):
    """Tuvastab rohelise märguande."""
    if frame is None:
        return False
    small = cv2.resize(frame, (64, 64))
    avg_color = np.mean(small, axis=(0, 1))
    return avg_color[1] > 200 and avg_color[0] < 50 and avg_color[2] < 50


def process_video(source, name):
    """
    Töötleb ühe video/voo ja tagastab liikumise andmed.
    Tagastab: (times, scores, threshold_crossings)
    """
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"  Ei saanud avada: {source}")
        return [], [], 0

    times = []
    scores = []
    threshold_crossings = 0
    previous_above = False

    ret, prev_frame = cap.read()
    if not ret:
        cap.release()
        return [], [], 0

    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        score = measure_change(prev_frame, frame)
        times.append(frame_idx / fps)
        scores.append(score)

        above = score > MOTION_THRESHOLD
        if above and not previous_above:
            threshold_crossings += 1
        previous_above = above
        prev_frame = frame

    cap.release()
    return times, scores, threshold_crossings


def create_graphs(results):
    """
    Loob 2 graafikut:
    - Graafik 1: empty voo liikumise mõõdik üle aja
    - Graafik 2: false_alarm voo liikumise mõõdik üle aja
    """
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))
    fig.suptitle("Seminar 3: Liikumise tuvastamine", fontsize=14)

    for idx, (name, data) in enumerate(results.items()):
        ax = axes[idx]
        times, scores, crossings = data

        if times:
            ax.plot(times, scores, linewidth=0.8, label="Muutuse skoor (MAE)")
            ax.axhline(MOTION_THRESHOLD, color="red", linestyle="--",
                       linewidth=1, label=f"Lävend ({MOTION_THRESHOLD})")
            ax.set_xlabel("Aeg (s)")
            ax.set_ylabel("Muutuse skoor")
            ax.legend(loc="upper right", fontsize=8)
            ax.grid(True, alpha=0.3)
            max_score = max(scores) if scores else 0
            avg_score = np.mean(scores) if scores else 0
            ax.set_title(
                f"Graafik {idx+1}: {name} | "
                f"Lävendi ületamisi: {crossings}, "
                f"Max: {max_score:.1f}, Keskm: {avg_score:.1f}"
            )
        else:
            ax.text(0.5, 0.5, f"{name}: andmeid ei kogunenud",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_title(f"Graafik {idx+1}: {name}")

    plt.tight_layout()
    output_path = os.path.join(SCRIPT_DIR, "graafikud.png")
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Graafikud salvestatud: {output_path}")
    return output_path


def save_summary_text(results):
    """Salvestab 2 graafikut kirjeldava tekstifaili."""
    lines = []
    lines.append("=" * 60)
    lines.append("SEMINAR 3: LIIKUMISE TUVASTAMISE GRAAFIKUD")
    lines.append("=" * 60)
    lines.append("")

    for idx, (name, data) in enumerate(results.items()):
        times, scores, crossings = data
        lines.append(f"GRAAFIK {idx+1}: {name.upper()}")
        lines.append("-" * 60)

        if scores:
            lines.append(f"  Voog:                {name}")
            lines.append(f"  Kaadrite arv:        {len(scores)}")
            lines.append(f"  Kestus:              {times[-1]:.1f} s")
            lines.append(f"  Lävend:              {MOTION_THRESHOLD}")
            lines.append(f"  Lävendi ületamisi:   {crossings}")
            lines.append(f"  Max muutus:          {max(scores):.2f}")
            lines.append(f"  Keskmine muutus:     {np.mean(scores):.2f}")
            lines.append(f"  Mediaanmuutus:       {np.median(scores):.2f}")

            above_count = sum(1 for s in scores if s > MOTION_THRESHOLD)
            lines.append(f"  Kaadrid üle lävendi: {above_count} ({100*above_count/len(scores):.1f}%)")
        else:
            lines.append("  Andmeid ei kogunenud.")

        lines.append("")

    lines.append("METOODIKA")
    lines.append("-" * 60)
    lines.append("1) Loetakse RTSP voost (või .mkv failist) kaadreid.")
    lines.append("2) Iga kaadripaari vahel arvutatakse MAE (Mean Absolute Error)")
    lines.append("   halltoonidesse teisendatud ja 160x90 suuruseks muudetud piltidel.")
    lines.append(f"3) Lävend liikumise tuvastamiseks: {MOTION_THRESHOLD}")
    lines.append("4) Rohelise ekraani tuvastamine tsükli alguse/lõpu märgina.")
    lines.append("")
    lines.append("VOOGUD")
    lines.append("-" * 60)
    lines.append("  empty:       rtsp://172.17.37.81:8554/empty")
    lines.append("  false_alarm: rtsp://172.17.37.81:8554/false_alarm")
    lines.append("")
    lines.append("=" * 60)

    text = "\n".join(lines)
    output_path = os.path.join(SCRIPT_DIR, "graafikud_kokkuvote.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Kokkuvõte salvestatud: {output_path}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    results = {}

    for name in ["empty", "false_alarm"]:
        print(f"\n--- Töötlen: {name} ---")

        # Proovi kõigepealt kohalikku faili, siis RTSP voogu
        source = LOCAL_FILES[name]
        if not os.path.exists(source):
            source = STREAMS[name]
            print(f"  Kohalik fail puudub, kasutan RTSP: {source}")
        else:
            print(f"  Kasutan kohalikku faili: {source}")

        times, scores, crossings = process_video(source, name)
        results[name] = (times, scores, crossings)
        print(f"  Tulemus: {len(scores)} kaadrit, {crossings} lävendi ületamist")

    create_graphs(results)
    save_summary_text(results)
    print("\nValmis!")
