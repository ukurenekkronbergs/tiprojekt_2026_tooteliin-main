import cv2
import os
import time
import numpy as np
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
ÜLESANNE 2: RTSP voo salvestamine rohelise ekraani (markeri) vahel.

See skript ootab voos esimest rohelist kaadrit, et alustada salvestamist.
Salvestamine toimub iga 9 sekundi järel kuni järgmise rohelise kaadrini.
See fail sisaldab juba Ülesanne 1 lahendust (kausta loomine, salvestamine).
"""

# --- KONFIGURATSIOON ---
# STREAM_URL = "rtsp://172.17.37.81:8554/salami"
# STREAM_URL = "rtsp://172.17.37.81:8554/veis"
# STREAM_URL = "rtsp://172.17.37.81:8554/kalkun"
STREAM_URL = "rtsp://172.17.37.81:8554/rulaad"
SAVE_INTERVAL = 9  # Sekundites

# --- ÜLESANNE 1: Seadistamine (Lahendatud) ---
folder_name = STREAM_URL.split('/')[-1]
os.makedirs(folder_name, exist_ok=True)

# --- ÜLESANNE 2: Rohelise ekraani tuvastamise funktsioon ---
def is_green_screen(frame):
    """
    Tuvastab, kas kaader on peamiselt roheline (marker).
    Sinu ülesanne: Implementeeri see kontroll.
    """
    # TODO: Sinu kood siia
    return False

# --- Videoühenduse algatamine ---
stream = RTSPStreamReader(STREAM_URL)
time.sleep(2)
if not stream.ret:
    print(f"Viga: Ei saanud ühendust aadressiga {STREAM_URL}")
    exit()

print(f"Ühendatud vooga {STREAM_URL}")
print(f"Salvestan kausta: '{folder_name}'")
print("Ootan rohelist märguannet alustamiseks...")

# --- ÜLESANNE 2: Olekumasina muutujad ---
started = False
green_cooldown = False 
last_save_time = 0
frame_count = 0

try:
    while True:
        ret, frame = stream.read()
        if not ret:
            print("Voodastus kadus.")
            break

        now = time.time()

        # --- ÜLESANNE 2: Kontrolli rohelist ekraani ja halda olekut ---
        # Sinu ülesanne: 
        # 1. Kui 'started' on False, siis oota esimest rohelist ekraani.
        #    Kui see ilmub, märgi 'started = True' ja salvesta esimene pilt.
        # 2. Kui 'started' on True:
        #    a) Kontrolli, kas on aeg lõpetada (tuli uus roheline ekraan).
        #       Vihje: pead veenduma, et sa ei lõpeta kohe esimese rohelise perioodi jooksul 
        #       (kasuta 'green_cooldown' muutujat).
        #    b) Salvesta pilte SAVE_INTERVAL sekundilise intervalliga.
        #
        # --- VIHJE: Ülesanne 1 salvestamise loogika, mida siin kasutada ---
        # filename = os.path.join(folder_name, f"frame_{frame_count:04d}.jpg")
        # cv2.imwrite(filename, frame)
        # print(f"Salvestatud: {filename}")
        # frame_count += 1
        # last_save_time = now

        # TODO: Sinu kood siia

finally:
    stream.stop()
    print("\nSkript suletud.")
