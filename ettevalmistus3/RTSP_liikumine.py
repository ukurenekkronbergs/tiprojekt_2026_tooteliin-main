import cv2
import os
import time
import numpy as np
import matplotlib.pyplot as plt
import threading


class RTSPStreamReader:
    def __init__(self, url):
        self.cap = cv2.VideoCapture(url)
        self.ret = False
        self.frame = None
        self.running = True
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running:
            ret, frame = self.cap.read()
            if not self.running: break
            with self.lock:
                self.ret = ret
                self.frame = frame
            if not ret: break

    def read(self):
        with self.lock:
            if self.frame is None: return self.ret, None
            return self.ret, self.frame.copy()

    def stop(self):
        self.running = False
        self.thread.join(timeout=1.0)
        self.cap.release()

"""
TÖÖ ENNE SEMINARI 3: Liikumise tuvastamine ja viivitusega salvestamine.

Eesmärk: Tuvastada konveieril liikumine, oodata pildi stabiliseerumist ja salvestada kaader.
"""

# --- KONFIGURATSIOON ---
# STREAM_URL = "rtsp://172.17.37.81:8554/salami"
# STREAM_URL = "rtsp://172.17.37.81:8554/veis"
# STREAM_URL = "rtsp://172.17.37.81:8554/kalkun"
STREAM_URL = "rtsp://172.17.37.81:8554/rulaad"

MOTION_THRESHOLD = 15.0  # Lävend, millest suurem muutus loetakse liikumiseks
CAPTURE_DELAY = 3      # Sekundid, mida oodatakse peale liikumise algust enne pildi tegemist

# Kausta loomine (eelmise ülesande lahendus)
folder_name = STREAM_URL.split('/')[-1]
os.makedirs(folder_name, exist_ok=True)

def is_green_screen(frame):
    """ Tuvastab rohelise märguande (eelmise ülesande lahendus). """
    if frame is None: return False
    small = cv2.resize(frame, (64, 64))
    avg_color = np.mean(small, axis=(0, 1))
    return avg_color[1] > 200 and avg_color[0] < 50 and avg_color[2] < 50

# --- ÜLESANNE: Muutuse mõõtmine ---
def measure_change(f1, f2):
    """
    Arvutab kahe kaadri vahelise erinevuse.
    Sinu ülesanne: 
    1. Mõõda funktsiooni täitmise aega.
    2. Testi arvutuse kiirust: kas piltide muutmine halltoonidesse ja väiksemaks annab olulist võitu?
    3. Arvuta MAE (Mean Absolute Error), MSE või mõni muu ise välja mõeldud erinevuse või liikumise mõõdik
    4. Prindi välja kulunud aeg ja tagasta arvutatud skoor.
    """
    start_time = time.perf_counter()

    gray1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)

    small1 = cv2.resize(gray1, (160, 90))
    small2 = cv2.resize(gray2, (160, 90))

    score = float(np.mean(cv2.absdiff(small1, small2)))
    duration_ms = (time.perf_counter() - start_time) * 1000
    processing_times_ms.append(duration_ms)

    print(f"measure_change: {score:.2f} ({duration_ms:.2f} ms)")
    return score

stream = RTSPStreamReader(STREAM_URL)
time.sleep(2)
if not stream.ret:
    print(f"Viga ühendusega: {STREAM_URL}")
    exit()

print(f"Seadistatud: Lävend {MOTION_THRESHOLD}, viivitus {CAPTURE_DELAY}s")

# --- ÜLESANNE: Logi salvestamine
# loo siin tühjad listid, et talletada info "muutuse graafik üle aja" jaoks ---
change_times = []
change_scores = []
processing_times_ms = []


started = False
green_cooldown = False
motion_triggered = False
trigger_time = 0
cycle_start_time = 0
frame_count = 1
threshold_crossings = 0
previous_above_threshold = False

try:
    while True:
        # Loeme kaks järjestikust kaadrit
        ret1, frame1 = stream.read()
        time.sleep(0.02) # Väike paus, et kaadrid jõuaksid muutuda
        ret2, frame2 = stream.read()
        
        if not ret1 or not ret2: break

        now = time.time()
        current_is_green = is_green_screen(frame2)

        if not started:
            if current_is_green:
                print(">>> Alustame tsüklit!")
                started = True
                green_cooldown = True
                cycle_start_time = now
        else:
            if green_cooldown and not current_is_green:
                green_cooldown = False

            if current_is_green and not green_cooldown:
                print(">>> Lõpetame tsükli.")
                break

            if green_cooldown:
                previous_above_threshold = False
                continue

            # --- ÜLESANNE: Liikumise tuvastamine ja ajastus ---
            # 1. Kutsu välja measure_change() ja salvesta tulemus ka listi. salvesta ka ajahetk.
            # 2. Kui muutus ületab MOTION_THRESHOLD ja 'motion_triggered' on False:
            #    - Märgi liikumine tuvastatuks, salvesta hetke aeg 'trigger_time' muutujasse.
            # 3. Kui 'motion_triggered' on True ja 'CAPTURE_DELAY' aeg on täis:
            #    - Salvesta pilt (cv2.imwrite).
            #    - Reseti 'motion_triggered', et oodata järgmist liikumist.

            change_score = measure_change(frame1, frame2)
            change_times.append(now - cycle_start_time)
            change_scores.append(change_score)

            above_threshold = change_score > MOTION_THRESHOLD
            if above_threshold and not previous_above_threshold:
                threshold_crossings += 1

            if above_threshold and not previous_above_threshold and not motion_triggered:
                motion_triggered = True
                trigger_time = now
                print(f"Liikumine tuvastatud: {change_score:.2f}")

            if motion_triggered and now - trigger_time >= CAPTURE_DELAY:
                filename = os.path.join(folder_name, f"motion_frame_{frame_count:04d}.jpg")
                if cv2.imwrite(filename, frame2):
                    print(f"Salvestatud peale viivitust: {filename}")
                    frame_count += 1
                else:
                    print(f"Pildi salvestamine ebaonnestus: {filename}")
                motion_triggered = False

            previous_above_threshold = above_threshold

finally:
    stream.stop()
    # ÜLESANNE: joonista graafik, kasuta näiteks plt.plot(), plt.axhline()(lävendi jaoks), 
    # pane ka nimi ja telgede nimed. salvesta graafik faili
    graph_path = os.path.join(os.path.dirname(__file__), "liikumise_graafik.png")

    plt.figure(figsize=(10, 5))
    if change_times:
        plt.plot(change_times, change_scores, label="Muutuse skoor")
        plt.axhline(MOTION_THRESHOLD, color="red", linestyle="--", label="Lävend")
        plt.xlabel("Aeg alates tsükli algusest (s)")
        plt.ylabel("Muutuse skoor")
        plt.title("Liikumise mõõdik üle aja")
        plt.legend()
        plt.grid(True, alpha=0.3)
    else:
        plt.text(0.5, 0.5, "Andmeid ei kogunenud", ha="center", va="center")
        plt.title("Liikumise mõõdik üle aja")
        plt.axis("off")

    plt.tight_layout()
    plt.savefig(graph_path)
    plt.close()

    average_processing_time = (
        sum(processing_times_ms) / len(processing_times_ms)
        if processing_times_ms
        else 0.0
    )

    print(f"Graafik salvestatud: {graph_path}")
    print(f"Lävendi ületamisi: {threshold_crossings}")
    print(f"Keskmine measure_change aeg: {average_processing_time:.2f} ms")

