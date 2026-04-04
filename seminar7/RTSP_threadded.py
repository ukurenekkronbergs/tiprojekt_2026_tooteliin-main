import json
import os
import threading
import time
from datetime import datetime, timedelta
from queue import Queue

import cv2
from dynamsoft_barcode_reader_bundle import *

from helpers import (
    RTSPStreamReader,
    build_debug_image_jobs,
    compare_labels_with_dino,
    create_product_classifier,
    create_worker_state,
    create_date_ocr,
    create_label_matcher,
    format_takt_report,
    format_worker_summary,
    is_green_screen,
    measure_global_change,
    predict_products,
    infer_product_key,
    update_ocr_stats,
)

# --- KONFIGURATSIOON ---
STREAM_URL = "rtsp://172.17.37.81:8554/rulaad"
MOTION_THRESHOLD = 15.0
CAPTURE_DELAY = 2.5
MONITOR_LOOP_SLEEP_SECONDS = 0.05
DYNAMSOFT_LICENSE = "t0084YQEAAIUx4hU4EqEOu9FaT9GprNtmXmbGA7IcvmG7V7l1yrR4WjV1JWPPrLuJoJN4HXVvqroIag2MeSFUJlbpkh0vhl8/Nrk3lffN1GzB7BvBtkl5"
DEBUG_MODE = False  # Silumisreziim piltide salvestamiseks
capture_date = datetime(2026, 2, 14)

# DATE_OCR_METHOD voimalikud variandid:
# - "parseq"
# - "paddleocr"
# - "easyocr"
# - "vlm_single"
# - "vlm_batch_independent"
# - "vlm_batch_consistent"
DATE_OCR_METHOD = "vlm_batch_consistent"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "google/gemini-2.0-flash-001"
LABEL_DINO_MODEL = "facebook/dinov2-small"
PRODUCT_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logistic_regression_templates20.joblib")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEMINAR6_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "seminar6")
print_lock = threading.Lock()


def log(message=""):
    with print_lock:
        print(message, flush=True)

try:
    date_ocr = create_date_ocr(
        DATE_OCR_METHOD,
        openrouter_api_key=OPENROUTER_API_KEY,
        openrouter_model=OPENROUTER_MODEL,
    )
except Exception as exc:
    log(f"Date OCR initialization failed: {exc}")
    raise SystemExit(1) from exc

try:
    label_matcher = create_label_matcher(SCRIPT_DIR, LABEL_DINO_MODEL)
except Exception as exc:
    log(f"Label DINO initialization failed: {exc}")
    label_matcher = None

try:
    product_classifier = create_product_classifier(PRODUCT_MODEL_PATH, label_matcher)
except Exception as exc:
    log(f"Product classifier initialization failed: {exc}")
    product_classifier = None

# Initsialiseerimine
LicenseManager.init_license(DYNAMSOFT_LICENSE)
router = CaptureVisionRouter()
template_path = os.path.join(SCRIPT_DIR, "medium_template.json")
if not os.path.exists(template_path):
    template_path = os.path.join(SEMINAR6_DIR, "medium_template.json")
err_code, err_msg = router.init_settings_from_file(template_path)
if err_code != EnumErrorCode.EC_OK:
    log(f"Failed to load JSON settings from file: {err_msg}")
    raise SystemExit(1)

barcode_data_path = os.path.join(SCRIPT_DIR, "barcode_data.json")
if not os.path.exists(barcode_data_path):
    barcode_data_path = os.path.join(SEMINAR6_DIR, "barcode_data.json")
with open(barcode_data_path, "r", encoding="utf-8") as f:
    barcode_data = json.load(f)

folder_name = os.path.join(SCRIPT_DIR, STREAM_URL.split("/")[-1])
os.makedirs(folder_name, exist_ok=True)

stream = RTSPStreamReader(STREAM_URL)
time.sleep(2)

STOP_WORKER = object()


# Tootlemine on jaotatud kaheks:
# 1. Põhitsükkel jälgib striimi, rohelise ekraani ja liikumise sündmusi.
# 2. Worker võtab triggeri hetkel salvestatud kaadrid queue'st ja teeb raske töö:
#    barcode -> slicing -> OCR -> raport -> debug-piltide salvestus.
def process_capture_task(task, worker_state):
    """Processes one queued takt frame and prints a compact per-takt report."""
    frame2 = task["frame"]
    trigger_id = task["trigger_id"]

    process_start_t = time.perf_counter()
    barcode_elapsed_ms = 0.0
    slicing_elapsed_ms = 0.0
    ocr_elapsed_ms = 0.0
    product_elapsed_ms = 0.0
    label_elapsed_ms = 0.0
    raw_date_texts = []
    expected_expiry_str = "Teadmata"
    expected_product_key = None
    barcode_display = "Ei loetud"
    product_display = "Teadmata"
    expected_date_display = "Teadmata"
    predicted_products = None
    label_distances = None
    report_notes = []
    images_to_save = []

    def emit_report():
        processing_elapsed_ms = (time.perf_counter() - process_start_t) * 1000
        worker_state["stats_times"].append(processing_elapsed_ms)

        save_elapsed_ms = 0.0
        if DEBUG_MODE and images_to_save:
            save_start_t = time.perf_counter()
            for path, img in images_to_save:
                if img is not None and img.size > 0:
                    cv2.imwrite(path, img)
            save_elapsed_ms = (time.perf_counter() - save_start_t) * 1000

        log(
            format_takt_report(
                trigger_id=trigger_id,
                barcode_display=barcode_display,
                product_display=product_display,
                expected_date_display=expected_date_display,
                expected_product_key=expected_product_key,
                raw_date_texts=raw_date_texts,
                predicted_products=predicted_products,
                expected_expiry_str=expected_expiry_str,
                report_notes=report_notes,
                processing_elapsed_ms=processing_elapsed_ms,
                barcode_elapsed_ms=barcode_elapsed_ms,
                slicing_elapsed_ms=slicing_elapsed_ms,
                ocr_elapsed_ms=ocr_elapsed_ms,
                product_elapsed_ms=product_elapsed_ms,
                label_elapsed_ms=label_elapsed_ms,
                label_distances=label_distances,
                save_elapsed_ms=save_elapsed_ms,
            )
        )

    barcode_start_t = time.perf_counter()
    result = router.capture(frame2, "ReadBarcodes_Default")
    items = result.get_items() if result is not None else None
    barcodes = [
        item.get_text()
        for item in items or []
        if item.get_type() == EnumCapturedResultItemType.CRIT_BARCODE
    ]
    barcode_elapsed_ms = (time.perf_counter() - barcode_start_t) * 1000
    worker_state["stats_counts"].append(len(barcodes))

    current_product = None
    if barcodes:
        worker_state["success_count"] += 1
        ean = barcodes[0]
        barcode_display = ean
        product = barcode_data.get(ean)
        if product is None:
            product_display = "Triipkoodi tooteinfot ei leitud"
            report_notes.append(f"EAN {ean} puudub failist barcode_data.json.")
            emit_report()
            return

        current_product = product.copy()
        current_product["_ean"] = ean
        worker_state["current_product"] = current_product
    else:
        barcode_display = "Ei loetud sellest taktist"
        current_product = worker_state["current_product"]
        if current_product is None:
            report_notes.append(
                "Triipkoodi ei leitud ning varasem tootekontekst puudub."
            )
            report_notes.append(
                "Kuupaeva oigsust ei saanud kontrollida ilma tootetekstita."
            )
            emit_report()
            return

        previous_ean = current_product.get("_ean", "Teadmata")
        report_notes.append(
            f"Kasutati eelmisest taktist jaanud tootekonteksti (EAN {previous_ean})."
        )

    if not all(k in current_product for k in required_keys):
        product_name = current_product.get("ITEMNAME", "Tundmatu toode")
        if barcodes:
            product_display = product_name
            expected_date_display = "Teadmata"
        else:
            product_display = f"{product_name} (eelmise takti kontekst)"
            expected_date_display = "Teadmata (eelmise takti kontekst)"
        report_notes.append(
            f"Tooteinfo EAN-ile {current_product.get('_ean', 'Teadmata')} on puudulik."
        )
        emit_report()
        return

    product_name = current_product.get("ITEMNAME", "Tundmatu toode")
    expected_product_key = infer_product_key(product_name)
    expiry_duration = current_product.get("BESTBEFOREDAYS", 0)
    expiry_date = capture_date + timedelta(days=expiry_duration)
    expected_expiry_str = expiry_date.strftime("%d.%m.%Y")

    if barcodes:
        product_display = product_name
        expected_date_display = expected_expiry_str
    else:
        product_display = f"{product_name} (eelmise takti kontekst)"
        expected_date_display = f"{expected_expiry_str} (eelmise takti kontekst)"

    slicing_start_t = time.perf_counter()
    temp_slices = []
    for coords in current_product["rois"].values():
        x1, y1 = coords[0]
        x2, y2 = coords[1]
        roi_crop = frame2[y1:y2, x1:x2]
        rotated = cv2.rotate(roi_crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
        temp_slices.append(rotated)

    if not temp_slices:
        report_notes.append("Toote loike ei leitud.")
        slicing_elapsed_ms = (time.perf_counter() - slicing_start_t) * 1000
        emit_report()
        return

    max_h = max(s.shape[0] for s in temp_slices)
    max_w = max(s.shape[1] for s in temp_slices)
    final_slices = [cv2.resize(s, (max_w, max_h)) for s in temp_slices]

    dx1, dy1 = current_product["date_area"][0]
    dx2, dy2 = current_product["date_area"][1]
    date_crops_bgr = [s_img[dy1:dy2, dx1:dx2] for s_img in final_slices]

    raw_date_texts = [None] * len(date_crops_bgr)
    valid_crop_indices = []
    valid_date_crops_rgb = []
    for idx, crop in enumerate(date_crops_bgr):
        if crop is None or crop.size == 0:
            continue
        valid_crop_indices.append(idx)
        valid_date_crops_rgb.append(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))

    slicing_elapsed_ms = (time.perf_counter() - slicing_start_t) * 1000
    worker_state["ocr_total_crops"] += len(date_crops_bgr)

    if valid_date_crops_rgb:
        ocr_start_t = time.perf_counter()
        try:
            predicted_texts = worker_state["date_ocr"].predict_batch(valid_date_crops_rgb)
        except Exception as exc:
            report_notes.append(f"Kuupaeva OCR ebaonnestus: {exc}")
            predicted_texts = [None] * len(valid_date_crops_rgb)
        ocr_elapsed_ms = (time.perf_counter() - ocr_start_t) * 1000

        if len(predicted_texts) != len(valid_date_crops_rgb):
            report_notes.append(
                "Kuupaeva OCR tagastas oodatust erineva arvu tulemusi. "
                "Puuduvad vaartused margiti kujul N/A."
            )
            predicted_texts = list(predicted_texts[: len(valid_date_crops_rgb)])
            predicted_texts.extend(
                [None] * (len(valid_date_crops_rgb) - len(predicted_texts))
            )

        for idx, raw_text in zip(valid_crop_indices, predicted_texts):
            raw_date_texts[idx] = raw_text
    else:
        report_notes.append("Kuupaeva OCR-i jaoks sobivaid loike ei leitud.")

    worker_state["ocr_takt_times"].append(ocr_elapsed_ms)

    update_ocr_stats(raw_date_texts, expected_expiry_str, worker_state)

    product_result = predict_products(
        final_slices,
        current_product,
        worker_state.get("product_classifier"),
    )
    if product_result is not None:
        product_elapsed_ms = product_result["elapsed_ms"]
        predicted_products = product_result["predictions"]
        worker_state["product_check_times"].append(product_elapsed_ms)
        worker_state["product_total_crops"] += product_result["total_crops"]
        worker_state["product_empty_count"] += sum(
            1 for prediction in predicted_products if prediction == "empty"
        )
        worker_state["product_predicted_count_non_empty"] += sum(
            1 for prediction in predicted_products if prediction != "empty"
        )
        worker_state["product_correct_count_non_empty"] += sum(
            1 for prediction in predicted_products if prediction != "empty" and prediction == expected_product_key
        )

    # Pärast kuupaeva OCR-i vektoriseerime korraga 4 label1 ja 4 label2 loiku.
    label_result = compare_labels_with_dino(
        final_slices,
        current_product,
        product_name,
        worker_state.get("label_matcher"),
    )
    if label_result is not None:
        label_elapsed_ms = label_result["elapsed_ms"]
        worker_state["label_check_times"].append(label_elapsed_ms)
        worker_state["label_total_crops"] += label_result["total_crops"]
        label_distances = label_result

    if DEBUG_MODE:
        images_to_save.extend(
            build_debug_image_jobs(
                folder_name=folder_name,
                trigger_id=trigger_id,
                frame=frame2,
                final_slices=final_slices,
                date_crops_bgr=date_crops_bgr,
                current_product=current_product,
            )
        )

    emit_report()


def processing_worker(task_queue, worker_state):
    """Consumes queued takts sequentially so heavy OCR work never blocks monitoring."""
    while True:
        task = task_queue.get()
        try:
            if task is STOP_WORKER:
                return
            process_capture_task(task, worker_state)
        except Exception as e:
            trigger_id = task.get("trigger_id", "?") if isinstance(task, dict) else "?"
            log(f"Takt {trigger_id} tootlemine ebaonnestus: {e}")
        finally:
            task_queue.task_done()


# Põhitsükli olek: need muutujad juhivad sama tsükliloogikat, mis eelmistel seminaridel,
# kuid raske töö ise on välja tõstetud workerisse.
total_triggers = 0
started = False
green_cooldown = False
motion_triggered = False
trigger_time = 0
cycle_start_time = 0
pending_trigger_id = None
required_keys = ["rois", "date_area", "label1_below", "label2_above", "product_area_between"]

worker_state = create_worker_state(date_ocr)
worker_state["label_matcher"] = label_matcher
worker_state["product_classifier"] = product_classifier

task_queue = Queue()
worker_thread = threading.Thread(
    target=processing_worker,
    args=(task_queue, worker_state),
    daemon=True,
)
worker_thread.start()

log(f"Date OCR backend: {worker_state['ocr_backend_name']}")
log(f"Yhendatud vooga {STREAM_URL}. Ootan rohelist marguannet...")

try:
    while True:
        ret1, frame1 = stream.read()
        # Hoidke monitoriloop tahtlikult kerge: me ei vaja maksimaalset FPS-i,
        # vaid piisavalt tihedat proovimist, et taktid kätte saada ja workerile
        # CPU-aega jatta.
        time.sleep(MONITOR_LOOP_SLEEP_SECONDS)
        ret2, frame2 = stream.read()
        if not ret1 or not ret2:
            break

        now = time.time()
        current_is_green = is_green_screen(frame2)

        if not started:
            if current_is_green:
                log(">>> Roheline ekraan tuvastatud! Alustame tsuklit.")
                started = True
                green_cooldown = True
        else:
            process_this_frame = False
            if not current_is_green and green_cooldown:
                log(">>> Roheline ekraan loppes. Alustame monitooringut.")
                green_cooldown = False
                cycle_start_time = now
                total_triggers += 1
                pending_trigger_id = total_triggers
                process_this_frame = True
            elif not green_cooldown:
                if current_is_green:
                    log(">>> Jargmine roheline ekraan tuvastatud. Lopetan tsukli.")
                    break

                # Moodame liikumist
                mae = measure_global_change(frame1, frame2)
                if mae > MOTION_THRESHOLD and not motion_triggered:
                    motion_triggered = True
                    trigger_time = now
                    total_triggers += 1
                    pending_trigger_id = total_triggers
                    log(
                        f"Liikumine tuvastatud {now - cycle_start_time:.2f}s juures! "
                        f"Ootan {CAPTURE_DELAY}s..."
                    )

                if motion_triggered and (now - trigger_time >= CAPTURE_DELAY):
                    process_this_frame = True
                    motion_triggered = False

            if process_this_frame and pending_trigger_id is not None:
                elapsed = now - cycle_start_time
                task_queue.put(
                    {
                        "trigger_id": pending_trigger_id,
                        "elapsed": elapsed,
                        "frame": frame2.copy(),
                        "captured_at": now,
                    }
                )
                log(f"[{elapsed:.2f}s] Takt {pending_trigger_id} lisatud tootlemisjarjekorda.")
                pending_trigger_id = None

except KeyboardInterrupt:
    log("Peatatud.")

finally:
    stream.stop()

    # Laseme queue'l alati enne loppu tühjaks joosta, et viimane takt ei katkeks pooleli.
    task_queue.join()
    task_queue.put(STOP_WORKER)
    worker_thread.join(timeout=5.0)
    log(format_worker_summary(total_triggers, worker_state, date_ocr.get_usage_totals()))
