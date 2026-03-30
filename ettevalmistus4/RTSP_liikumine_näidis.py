import cv2
import os
import time
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend to avoid GUI/Qt conflicts
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


# --- KONFIGURATSIOON ---
# STREAM_URL = "rtsp://172.17.37.81:8554/salami"
# STREAM_URL = "rtsp://172.17.37.81:8554/veis"
# STREAM_URL = "rtsp://172.17.37.81:8554/kalkun"
# STREAM_URL = "rtsp://172.17.37.81:8554/rulaad"
#STREAM_URL = "rtsp://172.17.37.81:8554/false_alarm"
STREAM_URL = "rtsp://172.17.37.81:8554/empty"

MOTION_THRESHOLD = 10.0  # Lävend, millest suurem muutus loetakse liikumiseks
CAPTURE_DELAY = 2.5      # Sekundid, mida oodatakse peale liikumise algust enne pildi tegemist

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
def measure_global_change(f1, f2):
    # Resize to 350x250 (perfectly divisible by 7x5 grid)
    # This resolution is high enough to detect objects but small enough to fit in cache.
    w, h = 350, 250
    g1 = cv2.cvtColor(cv2.resize(f1, (w, h)), cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(cv2.resize(f2, (w, h)), cv2.COLOR_BGR2GRAY)
    
    # Compute difference once for the whole image
    diff_map = cv2.absdiff(g1, g2)
    
    uw, uh = w // 7, h // 5  # Unit width (50px) and height (50px)
    maes = []

    # Sample 6 areas at (row, col) indices: (1,1), (1,3), (1,5), (3,1), (3,3), (3,5)
    for r in [1, 3]:
        for c in [1, 3, 5]:
            roi_diff = diff_map[r*uh : (r+1)*uh, c*uw : (c+1)*uw]
            maes.append(np.mean(roi_diff))

    # Return minimum: Only trigger if ALL regions show significant change (Global Motion)
    return min(maes)

stream = RTSPStreamReader(STREAM_URL)
time.sleep(2)
if not stream.ret:
    print(f"Viga ühendusega: {STREAM_URL}")
    exit()

print(f"Seadistatud: Lävend {MOTION_THRESHOLD}, viivitus {CAPTURE_DELAY}s")

# --- ÜLESANNE: Logi salvestamine
# loo siin tühjad listid, et talletada info "muutuse graafik üle aja" jaoks ---
timestamps=[]
changes=[]

started = False
green_cooldown = False
motion_triggered = False
trigger_time = 0
cycle_start_time = 0
frame_count = 0

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
        else:            
            # Kontrollime, kas oleme liikunud esimeselt roheliselt ekraanilt edasi videoni
            if not current_is_green and green_cooldown:
                print(">>> Roheline ekraan lõppes. Alustame monitooringut.")
                green_cooldown = False
                cycle_start_time = now

                # Salvestame 0. kaadri alati (esimene kaader peale rohelist märguannet)
                filename = os.path.join(folder_name, f"capture_{frame_count:03d}.jpg")
                cv2.imwrite(filename, frame2)
                print(f"Salvestatud esimene kaader (0:00): {filename}")
                frame_count += 1
                continue  # Jätame vahele, et vältida roheliselt ekraanilt tootele ülemineku "muutuse" salvestamist

            if not green_cooldown:
                # Lõpetame tsükli, kui roheline ekraan uuesti ilmub
                if current_is_green:
                    print(">>> Lõpetame tsükli.")
                    break

                # Mõõdame liikumist
                change = measure_global_change(frame1, frame2)
                timestamps.append(now - cycle_start_time)
                changes.append(change)

                if change > MOTION_THRESHOLD and not motion_triggered:
                    motion_triggered = True
                    trigger_time = now
                    elapsed = now - cycle_start_time
                    print(f"Motion detected at {elapsed:.2f}s (minMAE: {change:.2f})! Waiting {CAPTURE_DELAY}s to capture...")

                if motion_triggered and now - trigger_time >= CAPTURE_DELAY:
                    filename = os.path.join(folder_name, f"capture_{frame_count:03d}.jpg")
                    cv2.imwrite(filename, frame2)
                    print(f"Salvestatud liikumine: {filename}")
                    frame_count += 1
                    motion_triggered = False

finally:
    stream.stop()
    # ÜLESANNE: joonista graafik, kasuta näiteks plt.plot(), plt.axhline()(lävendi jaoks), 
    # pane ka nimi ja telgede nimed. salvesta graafik faili
    plt.figure(figsize=(10, 5))
    plt.plot(timestamps, changes, label="Muutus")
    plt.axhline(MOTION_THRESHOLD, color="red", linestyle="--", label="Lävend")
    plt.title("Muutuse graafik üle aja")
    plt.xlabel("Aeg (s)")
    plt.ylabel("Muutus")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(folder_name, "muutuse_graafik.png"))
    plt.close()
