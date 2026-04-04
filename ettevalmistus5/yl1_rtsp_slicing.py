import cv2
import os
import time
import json
import numpy as np
from datetime import datetime, timedelta
from dynamsoft_barcode_reader_bundle import *
from helpers import RTSPStreamReader, is_green_screen, measure_global_change

# --- KONFIGURATSIOON ---
STREAM_URL = "rtsp://172.17.37.81:8554/rulaad"
MOTION_THRESHOLD = 10.0
CAPTURE_DELAY = 2.5
DYNAMSOFT_LICENSE = "t0084YQEAAIUx4hU4EqEOu9FaT9GprNtmXmbGA7IcvmG7V7l1yrR4WjV1JWPPrLuJoJN4HXVvqroIag2MeSFUJlbpkh0vhl8/Nrk3lffN1GzB7BvBtkl5"
DEBUG_MODE = True  # Kontrolli seda muutujat enne salvestamist
capture_date = datetime(2026, 2, 14)

# Initsialiseerimine
LicenseManager.init_license(DYNAMSOFT_LICENSE)
router = CaptureVisionRouter()
template_path = "minimal_template.json"
err_code, err_msg = router.init_settings_from_file(template_path)
if err_code != EnumErrorCode.EC_OK:
    print(f"Failed to load JSON settings from file: {err_msg}")
    exit()

with open('barcode_data.json', 'r') as f:
    barcode_data = json.load(f)

folder_name = STREAM_URL.split('/')[-1]
os.makedirs(folder_name, exist_ok=True)

stream = RTSPStreamReader(STREAM_URL)
time.sleep(2)

# --- Olekumuutujad ---
total_triggers = 0
started = False
green_cooldown = False
motion_triggered = False
trigger_time = 0
cycle_start_time = 0
current_product = None # we maintain a "current product", if a given frame does not have barcode, we proceed with last ean
required_keys = ["rois", "date_area", "label1_below", "label2_above", "product_area_between"]

print(f"Ühendatud vooga {STREAM_URL}. Ootan rohelist märguannet...")

try:
    while True:
        loop_start_t = time.perf_counter() #mõõdame kogu töötlemisele minevat aega
        ret1, frame1 = stream.read()
        time.sleep(0.02) # Väike paus, et kaadrid jõuaksid muutuda
        ret2, frame2 = stream.read()
        if not ret1 or not ret2: break

        now = time.time()
        current_is_green = is_green_screen(frame2)
        
        if not started:
            if current_is_green:
                print(">>> Roheline ekraan tuvastatud! Alustame tsüklit.")
                started = True
                green_cooldown = True
        else:
            process_this_frame = False
            if not current_is_green and green_cooldown:
                print(">>> Roheline ekraan lõppes. Alustame monitooringut.")
                green_cooldown = False
                cycle_start_time = now
                total_triggers += 1
                process_this_frame = True
            elif not green_cooldown:
                if current_is_green:
                    print(">>> Järgmine roheline ekraan tuvastatud. Lõpetan tsükli.")
                    break

                # Mõõdame liikumist
                mae = measure_global_change(frame1, frame2)
                if mae > MOTION_THRESHOLD and not motion_triggered:
                    motion_triggered = True
                    trigger_time = now
                    total_triggers += 1

                if motion_triggered and (now - trigger_time >= CAPTURE_DELAY):
                    process_this_frame = True
                    motion_triggered = False

            if process_this_frame:
                elapsed = now - cycle_start_time
                result = router.capture(frame2, "ReadBarcodes_Default")

                items = result.get_items() if result is not None else None
                barcodes = [item.get_text() for item in items or [] if item.get_type() == EnumCapturedResultItemType.CRIT_BARCODE]

                if len(barcodes) > 0:
                    ean = barcodes[0]
                    product = barcode_data.get(ean)
                    if product is None:
                        print(f"[{elapsed:.2f}s] EAN {ean}: tooteinfot ei leitud.")
                        continue 
                    current_product = product.copy()
                    current_product["_ean"] = ean                        
                
                if current_product is None:
                    print("Meil pole tooteinfot. Jätkame...")
                    continue
                
                if not all(k in current_product for k in required_keys):
                    print(f"VIGA: Tooteinfot EAN {current_product.get('_ean')} on puudulik!")
                    continue
                    
                product_name = current_product.get("ITEMNAME", "Tundmatu toode")
                expiry_duration = current_product.get("BESTBEFOREDAYS", 0)
                expiry_date = capture_date + timedelta(days=expiry_duration)
                ean_str = current_product.get("_ean", "Tundmatu")

                # =================================================================
                # TODO: ÜLESANNE - Siit algab kaadri juppideks lõikamise loogika
                # =================================================================
                
                # 1. Samm: Pakendite (ROIs) väljalõikamine
                # - Võta 'current_product["rois"]' ja lõika täiskaadrilt (frame2) välja 4 ala.
                # - Roteeri igaüht 90 kraadi vastupäeva.
                # - Leia suurim kõrgus/laius ja normaliseeri kõik 4 pilti (cv2.resize).
                
                # 2. Samm: Detailide eraldamine
                # - Kasuta standardiseeritud suurusega alasid, et lõigata välja:
                #   * 'date_area'
                #   * 'label1_below' (kõik mis jääb joonest alla)
                #   * 'label2_above' (kõik mis jääb joonest üles)
                #   * 'product_area_between' (kahe Y-koordinaadi vaheline ala)
                # Kuva kui palju aega läks kõigile sammudele kokku enne salvestamist
                #   time_to_process= (time.perf_counter() - loop_start_t)

                # 3. Samm: Tingimuslik salvestamine (Vaid juhul kui DEBUG_MODE == True)                
                # - Kasuta 'time.perf_counter()', et mõõta AINULT salvestamisele kuluvat aega ja prindi see.
                # - Veendu, et vajalikud alamkaustad ("date", "label1", "label2", "product_area", "full_frames") oleksid loodud.
                # - Salvesta täiskaader kausta "full_frames".
                # - Salvesta kõik lõigatud detailid vastavatesse kaustadesse.

                # Vihje failinimedeks: f"takt_{total_triggers}_s{slice_number}_date.png"

                # TODO: Sinu kood siia...

                print("\n -------------------------------------------- \n")
                print(f"Takt {total_triggers}. Liikumine oli tuvastatud {elapsed:.2f}s juures!")
                print(f"Kontekst: EAN {ean_str} | {product_name} | Aegub {expiry_date.strftime('%d.%m.%Y')}")
                print() #lisa töötlemisaja kuvamine, salvestamisaeg kuvatakse vaid debug puhul.

except KeyboardInterrupt:
    print("Peatatud.")
finally:
    stream.stop()
    print("\nTöö lõpetatud.")
