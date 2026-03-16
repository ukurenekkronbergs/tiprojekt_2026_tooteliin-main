"""
Ettevalmistus: Triipkoodi tuvastuse lisamine ja tulemuste analüüs

Ühendab taktituvastuse (Seminar 2) ja triipkoodi lugemise (Seminar 3)
üheks terviklikuks süsteemiks.

Koopia failist RTSP_liikumine.py, millele on lisatud triipkoodi tuvastus.

Töövoog:
1. Ootab rohelist ekraani (tsükli algus).
2. Tuvastab liikumise (konveieri takt).
3. Ootab 2.5 sekundit (pilt stabiliseerub).
4. Teeb pildi ja otsib sellelt triipkoode.
5. Kordab kuni järgmise rohelise ekraanini (tsükli lõpp).
6. Väljastab statistika.
"""

import cv2
import os
import time
import numpy as np
import threading
from datetime import datetime, timedelta

# Dynamsoft triipkoodi lugeja
from dynamsoft_barcode_reader_bundle import *


class RTSPStreamReader:
    """Loeb RTSP voogu eraldi lõimes, et vältida puhvri kuhjumist."""
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
            if not self.running:
                break
            with self.lock:
                self.ret = ret
                self.frame = frame
            if not ret:
                break

    def read(self):
        with self.lock:
            if self.frame is None:
                return self.ret, None
            return self.ret, self.frame.copy()

    def stop(self):
        self.running = False
        self.thread.join(timeout=1.0)
        self.cap.release()


# =====================================================================
# KONFIGURATSIOON
# =====================================================================

# Vali voog (kommenteeri/eemalda kommentaar vastavalt vajadusele)
# STREAM_URL = "rtsp://172.17.37.81:8554/salami"
# STREAM_URL = "rtsp://172.17.37.81:8554/veis"
# STREAM_URL = "rtsp://172.17.37.81:8554/kalkun"
STREAM_URL = "rtsp://172.17.37.81:8554/rulaad"

MOTION_THRESHOLD = 15.0   # Lävend liikumise tuvastamiseks (MAE)
CAPTURE_DELAY = 2.5        # Sekundid peale liikumist enne pildi tegemist

# Video salvestamise kuupäev (teadaolev)
VIDEO_RECORDING_DATE = datetime(2026, 2, 14)

# Toodete andmebaas: EAN13 kood -> {nimi, säilivus_päevades}
# NB! Täida see tegelike andmetega pärast esimest käivitust!
PRODUCT_DB = {
    "4740574008052": {"nimi": "Rulaad",    "säilivus_päevades": 30},
    "4740574009820": {"nimi": "Salami",    "säilivus_päevades": 45},
    "4740574081192": {"nimi": "Veiseliha", "säilivus_päevades": 21},
    "4740574090002": {"nimi": "Kalkun",   "säilivus_päevades": 25},
}

# Dynamsoft litsentsi võti
# Hangi tasuta prooviversioon: https://www.dynamsoft.com/customer/license/trialLicense
LICENSE_KEY = "t0087YQEAABEsceOwFQkxeGWWbSyNJ6YlIHeOgV6f8h64WSLH4jccq4scXxhG+brADJDtjR/oeOnYT4BXNK3GUmC55EbrGaVm+sG0jyZ3M/HeLOpugXfDVEsO"


# =====================================================================
# TRIIPKOODI LUGEJA INITSIALISEERIMINE
# =====================================================================

try:
    LicenseManager.init_license(LICENSE_KEY)
    cvr = CaptureVisionRouter()
    barcode_reader_ready = True
    print("Dynamsoft triipkoodi lugeja initsialiseeritud.")
except Exception as e:
    print(f"HOIATUS: Triipkoodi lugeja initsialiseerimine ebaõnnestus: {e}")
    print("Kontrolli LICENSE_KEY väärtust!")
    barcode_reader_ready = False
    cvr = None


# =====================================================================
# ABIFUNKTSIOONID
# =====================================================================

# Kausta loomine voo nime järgi
folder_name = STREAM_URL.split('/')[-1]
os.makedirs(folder_name, exist_ok=True)


def is_green_screen(frame):
    """Tuvastab rohelise märguande ekraani."""
    if frame is None:
        return False
    small = cv2.resize(frame, (64, 64))
    avg_color = np.mean(small, axis=(0, 1))
    return avg_color[1] > 200 and avg_color[0] < 50 and avg_color[2] < 50


def measure_change(f1, f2):
    """Arvutab kahe kaadri vahelise erinevuse (MAE halltoonides, 160x90)."""
    start_time = time.perf_counter()

    gray1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
    small1 = cv2.resize(gray1, (160, 90))
    small2 = cv2.resize(gray2, (160, 90))

    score = float(np.mean(cv2.absdiff(small1, small2)))
    duration_ms = (time.perf_counter() - start_time) * 1000
    processing_times_ms.append(duration_ms)
    return score


def detect_barcodes(image_path):
    """
    Tuvastab triipkoodid pildilt Dynamsoft abil.
    Tagastab: (triipkoodide_list, aeg_ms)
    """
    if not barcode_reader_ready:
        return [], 0.0

    start_time = time.perf_counter()
    barcodes = []

    try:
        result = cvr.capture(image_path)
        if result.get_error_code() == EnumErrorCode.EC_OK:
            barcode_result = result.get_decoded_barcodes_result()
            if barcode_result is not None:
                for item in barcode_result.get_items():
                    barcodes.append({
                        "formaat": item.get_format_string(),
                        "kood": item.get_text(),
                    })
    except Exception as e:
        print(f"  Triipkoodi tuvastamise viga: {e}")

    duration_ms = (time.perf_counter() - start_time) * 1000
    return barcodes, duration_ms


def get_product_info(ean_code):
    """Otsib toote info andmebaasist EAN koodi järgi."""
    if ean_code in PRODUCT_DB:
        info = PRODUCT_DB[ean_code]
        expiry = VIDEO_RECORDING_DATE + timedelta(days=info["säilivus_päevades"])
        return info["nimi"], expiry.strftime("%d.%m.%Y")
    return "Tundmatu toode", "N/A"


# =====================================================================
# PEAMINE TSÜKKEL
# =====================================================================

stream = RTSPStreamReader(STREAM_URL)
time.sleep(2)

if not stream.ret:
    print(f"Viga ühendusega: {STREAM_URL}")
    exit()

print(f"\nVoog: {STREAM_URL}")
print(f"Seadistatud: lävend={MOTION_THRESHOLD}, viivitus={CAPTURE_DELAY}s")
print("Ootan rohelist ekraani tsükli alustamiseks...\n")

# Logid
change_times = []
change_scores = []
processing_times_ms = []

# Triipkoodi statistika
barcode_detection_times_ms = []
barcodes_per_frame = []
takt_results = []

# Olekumuutujad
started = False
green_cooldown = False
motion_triggered = False
trigger_time = 0
cycle_start_time = 0
frame_count = 1
threshold_crossings = 0
previous_above_threshold = False
total_tacts = 0

try:
    while True:
        ret1, frame1 = stream.read()
        time.sleep(0.02)
        ret2, frame2 = stream.read()

        if not ret1 or not ret2:
            break

        now = time.time()
        current_is_green = is_green_screen(frame2)

        # --- Rohelise ekraani loogika ---
        if not started:
            if current_is_green:
                print(">>> Roheline ekraan tuvastatud – tsükkel algab!")
                started = True
                green_cooldown = True
                cycle_start_time = now
        else:
            if green_cooldown and not current_is_green:
                green_cooldown = False

            if current_is_green and not green_cooldown:
                print("\n>>> Roheline ekraan tuvastatud – tsükkel lõpeb!")
                break

            if green_cooldown:
                previous_above_threshold = False
                continue

            # --- Liikumise tuvastamine ---
            change_score = measure_change(frame1, frame2)
            elapsed = now - cycle_start_time
            change_times.append(elapsed)
            change_scores.append(change_score)

            above_threshold = change_score > MOTION_THRESHOLD
            if above_threshold and not previous_above_threshold:
                threshold_crossings += 1

            if above_threshold and not previous_above_threshold and not motion_triggered:
                motion_triggered = True
                trigger_time = now
                total_tacts += 1

            # --- Pildi tegemine ja triipkoodi tuvastamine ---
            if motion_triggered and now - trigger_time >= CAPTURE_DELAY:
                filename = os.path.join(folder_name, f"motion_frame_{frame_count:04d}.jpg")
                cv2.imwrite(filename, frame2)

                # Tuvasta triipkoodid
                barcodes, bc_duration = detect_barcodes(filename)
                barcode_detection_times_ms.append(bc_duration)
                barcodes_per_frame.append(len(barcodes))

                # Väljasta tulemused
                takt_time = now - cycle_start_time
                print(f"\n--- Takt {total_tacts} | {takt_time:.1f}s ---")

                if barcodes:
                    for bc in barcodes:
                        kood = bc["kood"]
                        nimi, säilivus = get_product_info(kood)
                        print(f"  EAN: {kood} ({bc['formaat']})")
                        print(f"  Toode: {nimi} | Säilivusaeg: {säilivus}")
                    takt_results.append({
                        "takt": total_tacts,
                        "aeg": takt_time,
                        "leitud": True,
                        "triipkoode": len(barcodes),
                        "koodid": [bc["kood"] for bc in barcodes],
                    })
                else:
                    print(f"  Triipkoodi ei leitud")
                    takt_results.append({
                        "takt": total_tacts,
                        "aeg": takt_time,
                        "leitud": False,
                        "triipkoode": 0,
                        "koodid": [],
                    })

                print(f"  Triipkoode pildil: {len(barcodes)} | Otsimise aeg: {bc_duration:.0f} ms")
                print(f"  Pilt: {filename}")

                frame_count += 1
                motion_triggered = False

            previous_above_threshold = above_threshold

finally:
    stream.stop()

    # =================================================================
    # STATISTIKA
    # =================================================================
    print("\n" + "=" * 60)
    print("KOKKUVÕTE JA STATISTIKA")
    print("=" * 60)
    print(f"Voog: {STREAM_URL}")
    print(f"Takte kokku (liikumisi): {total_tacts}")
    print(f"Salvestatud kaadreid:     {frame_count - 1}")

    # Tuvastusmäär (mitu takti, kus vähemalt 1 triipkood leiti)
    captured_tacts = len(takt_results)
    tacts_with_barcode = sum(1 for r in takt_results if r["leitud"])
    if captured_tacts > 0:
        rate = tacts_with_barcode / captured_tacts * 100
        print(f"\nTuvastusmäär: {tacts_with_barcode}/{captured_tacts} ({rate:.1f}%)")
    else:
        print("\nTuvastusmäär: 0/0 (takte ei tuvastatud)")

    # Jõudlus
    if barcode_detection_times_ms:
        avg_bc = sum(barcode_detection_times_ms) / len(barcode_detection_times_ms)
        max_bc = max(barcode_detection_times_ms)
        print(f"\nTriipkoodi otsimise jõudlus:")
        print(f"  Keskmine aeg:     {avg_bc:.0f} ms")
        print(f"  Maksimaalne aeg:  {max_bc:.0f} ms")

    # Maht
    if barcodes_per_frame:
        avg_bpf = sum(barcodes_per_frame) / len(barcodes_per_frame)
        max_bpf = max(barcodes_per_frame)
        print(f"\nTriipkoodide arv pildi kohta:")
        print(f"  Keskmine:     {avg_bpf:.1f}")
        print(f"  Maksimaalne:  {max_bpf}")

    # Liikumise tuvastamise jõudlus
    if processing_times_ms:
        avg_proc = sum(processing_times_ms) / len(processing_times_ms)
        print(f"\nLiikumise tuvastamise keskmine aeg: {avg_proc:.2f} ms")

    print(f"Lävendi ületamisi: {threshold_crossings}")
    print("=" * 60)
