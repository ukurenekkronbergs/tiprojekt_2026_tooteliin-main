import cv2
import os
import time
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
ÜLESANNE 1: RTSP voo lugemine ja piltide salvestamine

See skript ühendub RTSP vooga ja salvestab kaadri iga 9 sekundi järel.
Kasutaja peab skripti käsitsi seiskama (Ctrl+C), kui piisavalt kaadreid on koos ning nähtud on ka täiesti rohelist freimi.
"""

# --- KONFIGURATSIOON ---
# Vali voog, millega soovid töötada (eemalda kommentaar vastava rea eest):
# STREAM_URL = "rtsp://172.17.37.81:8554/salami"
# STREAM_URL = "rtsp://172.17.37.81:8554/veis"
# STREAM_URL = "rtsp://172.17.37.81:8554/kalkun"
STREAM_URL = "rtsp://172.17.37.81:8554/rulaad"

SAVE_INTERVAL = 9  # Sekundites

# --- ÜLESANNE 1.1: Seadista kaust ---
# Sinu ülesanne: eralda voo URL-ist nimi (viimane osa peale kaldkriipsu)
# ja loo selle nimeline kaust piltide salvestamiseks.
# Kui kaust on juba olemas, ei tohi programm veaga katkeda (vihje: exist_ok=True).

# TODO: Sinu kood siia (asenda järgmine rida)
folder_name = None #asenda see


# --- Videoühenduse algatamine ---
# See osa on ette antud ja seda muuta pole vaja.
stream = RTSPStreamReader(STREAM_URL)
time.sleep(2) # Ootame, kuni ühendus stabiliseerub
if not stream.ret:
    print(f"Viga: Ei saanud ühendust aadressiga {STREAM_URL}")
    exit()

print(f"Ühendatud vooga {STREAM_URL}")
print(f"Pildid salvestatakse kausta: '{folder_name}' iga {SAVE_INTERVAL} sekundi järel.")
print("Peatamiseks vajuta Ctrl+C.")


last_save_time = 0
frame_count = 0

try:
    while True:
        # Loeme värskeima kaadri voost
        ret, frame = stream.read()
        if not ret:
            print("Voodastus kadus.")
            break

        now = time.time()

        # --- ÜLESANNE 2: Ajastus ja salvestamine ---
        # Sinu ülesanne: kontrolli, kas viimasest salvestamisest on möödunud SAVE_INTERVAL sekundit.
        # Kui on, siis:
        # 1. Koosta pildi failinimi (nt "frame_0001.jpg"). Kasuta os.path.join().
        # 2. Salvesta pilt cv2.imwrite() funktsiooniga.
        # 3. Uuenda viimase salvestamise aega (last_save_time) ja kaadrite loendurit (frame_count).
        # 4. Prindi terminali teavitus salvestatud pildi kohta.

        # TODO: Sinu kood siia

finally:
    stream.stop()
    print("\nSkript suletud.")
