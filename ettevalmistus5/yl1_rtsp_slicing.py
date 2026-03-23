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
                # Siit algab kaadri juppideks lõikamise loogika
                # =================================================================

                # 1. Samm: Pakendite (ROIs) väljalõikamine
                rois = current_product["rois"]
                rotated_packages = []
                for pkg_name, roi in rois.items():
                    crop = frame2[roi[0][1]:roi[1][1], roi[0][0]:roi[1][0]]
                    rotated = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    rotated_packages.append(rotated)

                # Normaliseerimine: leia suurim kõrgus/laius
                max_h = max(r.shape[0] for r in rotated_packages)
                max_w = max(r.shape[1] for r in rotated_packages)
                normalized = [cv2.resize(r, (max_w, max_h)) for r in rotated_packages]

                # 2. Samm: Detailide eraldamine
                date_area = current_product["date_area"]
                label1_y = current_product["label1_below"]
                label2_y = current_product["label2_above"]
                prod_area = current_product["product_area_between"]

                details = {"date": [], "label1": [], "label2": [], "product_area": []}
                for norm_img in normalized:
                    details["date"].append(norm_img[date_area[0][1]:date_area[1][1], date_area[0][0]:date_area[1][0]])
                    details["label1"].append(norm_img[label1_y:, :])
                    details["label2"].append(norm_img[:label2_y, :])
                    details["product_area"].append(norm_img[prod_area[0]:prod_area[1], :])

                time_to_process = time.perf_counter() - loop_start_t

                # 3. Samm: Tingimuslik salvestamine
                if DEBUG_MODE:
                    save_start = time.perf_counter()

                    subdirs = ["full_frames", "date", "label1", "label2", "product_area"]
                    for sd in subdirs:
                        os.makedirs(os.path.join(folder_name, sd), exist_ok=True)

                    # Täiskaader
                    cv2.imwrite(os.path.join(folder_name, "full_frames", f"takt_{total_triggers}.png"), frame2)

                    # Pakendid ja detailid
                    for i in range(len(normalized)):
                        s = i + 1
                        cv2.imwrite(os.path.join(folder_name, "full_frames", f"takt_{total_triggers}_s{s}.png"), normalized[i])
                        for detail_name, detail_list in details.items():
                            cv2.imwrite(os.path.join(folder_name, detail_name, f"takt_{total_triggers}_s{s}_{detail_name}.png"), detail_list[i])

                    time_to_save = time.perf_counter() - save_start
                    print(f"  Salvestamine: {time_to_save*1000:.1f} ms")

                print("\n -------------------------------------------- \n")
                print(f"Takt {total_triggers}. Liikumine oli tuvastatud {elapsed:.2f}s juures!")
                print(f"Kontekst: EAN {ean_str} | {product_name} | Aegub {expiry_date.strftime('%d.%m.%Y')}")
                print(f"  Töötlemine: {time_to_process*1000:.1f} ms")

except KeyboardInterrupt:
    print("Peatatud.")
finally:
    stream.stop()
    print("\nTöö lõpetatud.")
