"""
Quick pipeline test: runs on a single RTSP stream for up to 90 seconds
or until the cycle ends, using easyocr (no API key needed).

Usage:
    python test_pipeline.py [stream_name]
    e.g. python test_pipeline.py rulaad
"""
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from queue import Queue

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import cv2
from dynamsoft_barcode_reader_bundle import *

from helpers import (
    RTSPStreamReader,
    TaktLogger,
    build_debug_image_jobs,
    build_takt_record,
    compare_labels_with_dino,
    create_date_ocr,
    create_label_matcher,
    create_product_classifier,
    create_worker_state,
    detect_anomalies,
    format_takt_report,
    format_worker_summary,
    generate_dashboard,
    infer_product_key,
    is_green_screen,
    laplacian_sharpness,
    measure_global_change,
    pick_sharpest_frame,
    play_alert_sound,
    predict_products,
    update_ocr_stats,
)

# --- CONFIG ---
stream_name = sys.argv[1] if len(sys.argv) > 1 else "rulaad"
STREAM_URL = f"rtsp://172.17.37.81:8554/{stream_name}"
MOTION_THRESHOLD = 15.0
CAPTURE_DELAY = 2.5
MONITOR_LOOP_SLEEP_SECONDS = 0.05
DYNAMSOFT_LICENSE = os.getenv("DYNAMSOFT_LICENSE", "")
ALERT_SOUND = False  # Quiet for testing
MULTI_FRAME_COUNT = 3
MAX_RUNTIME_SECONDS = 90
capture_date = datetime(2026, 2, 14)
DATE_OCR_METHOD = "vlm_batch_consistent"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "google/gemini-2.0-flash-001"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
print_lock = threading.Lock()


def log(message=""):
    with print_lock:
        print(message, flush=True)


log(f"Testing pipeline on: {STREAM_URL}")
log(f"OCR method: {DATE_OCR_METHOD}")
log(f"Multi-frame count: {MULTI_FRAME_COUNT}")
log(f"Max runtime: {MAX_RUNTIME_SECONDS}s")

# Init OCR
date_ocr = create_date_ocr(
    DATE_OCR_METHOD,
    openrouter_api_key=OPENROUTER_API_KEY,
    openrouter_model=OPENROUTER_MODEL,
)
log(f"Date OCR ready: {date_ocr.display_name}")

# Init label matcher
try:
    label_matcher = create_label_matcher(SCRIPT_DIR, "facebook/dinov2-small")
    log("Label matcher ready")
except Exception as exc:
    log(f"Label matcher failed: {exc}")
    label_matcher = None

# Init product classifier
PRODUCT_MODEL_PATH = os.path.join(SCRIPT_DIR, "logistic_regression_templates20.joblib")
try:
    product_classifier = create_product_classifier(PRODUCT_MODEL_PATH, label_matcher)
    log("Product classifier ready")
except Exception as exc:
    log(f"Product classifier failed: {exc}")
    product_classifier = None

# Init barcode reader
LicenseManager.init_license(DYNAMSOFT_LICENSE)
router = CaptureVisionRouter()
template_path = os.path.join(SCRIPT_DIR, "medium_template.json")
err_code, err_msg = router.init_settings_from_file(template_path)
if err_code != EnumErrorCode.EC_OK:
    log(f"Template load failed: {err_msg}")
    sys.exit(1)

barcode_data_path = os.path.join(SCRIPT_DIR, "barcode_data.json")
if not os.path.exists(barcode_data_path):
    barcode_data_path = os.path.join(os.path.dirname(SCRIPT_DIR), "seminar6", "barcode_data.json")
with open(barcode_data_path, "r", encoding="utf-8") as f:
    barcode_data = json.load(f)

folder_name = os.path.join(SCRIPT_DIR, stream_name)
os.makedirs(folder_name, exist_ok=True)

log_path = os.path.join(folder_name, "takt_log.jsonl")
dashboard_path = os.path.join(folder_name, "dashboard.html")
takt_logger = TaktLogger(log_path)

# Connect
stream = RTSPStreamReader(STREAM_URL)
time.sleep(2)

STOP_WORKER = object()
required_keys = ["rois", "date_area", "label1_below", "label2_above", "product_area_between"]


def process_capture_task(task, worker_state):
    frame2 = task["frame"]
    trigger_id = task["trigger_id"]
    process_start_t = time.perf_counter()
    barcode_elapsed_ms = slicing_elapsed_ms = ocr_elapsed_ms = 0.0
    product_elapsed_ms = label_elapsed_ms = 0.0
    raw_date_texts = []
    expected_expiry_str = "Teadmata"
    expected_product_key = None
    barcode_display = "Ei loetud"
    product_display = "Teadmata"
    expected_date_display = "Teadmata"
    predicted_products = None
    label_distances = None
    report_notes = []

    def emit_report():
        processing_elapsed_ms = (time.perf_counter() - process_start_t) * 1000
        worker_state["stats_times"].append(processing_elapsed_ms)

        anomalies = detect_anomalies(
            raw_date_texts=raw_date_texts,
            expected_expiry_str=expected_expiry_str,
            predicted_products=predicted_products,
            expected_product_key=expected_product_key,
            label_distances=label_distances,
        )
        if anomalies:
            report_notes.extend([f"ANOMAALIA: {a}" for a in anomalies])

        record = build_takt_record(
            trigger_id=trigger_id, barcode_display=barcode_display,
            product_display=product_display, expected_date=expected_expiry_str,
            expected_product_key=expected_product_key,
            raw_date_texts=raw_date_texts, predicted_products=predicted_products,
            label_distances=label_distances, processing_ms=processing_elapsed_ms,
            barcode_ms=barcode_elapsed_ms, slicing_ms=slicing_elapsed_ms,
            ocr_ms=ocr_elapsed_ms, product_ms=product_elapsed_ms,
            label_ms=label_elapsed_ms, anomalies=anomalies,
        )
        takt_logger.log_takt(record)

        if ALERT_SOUND and anomalies:
            play_alert_sound(anomalies)

        log(format_takt_report(
            trigger_id=trigger_id, barcode_display=barcode_display,
            product_display=product_display, expected_date_display=expected_date_display,
            expected_product_key=expected_product_key, raw_date_texts=raw_date_texts,
            predicted_products=predicted_products, expected_expiry_str=expected_expiry_str,
            report_notes=report_notes, processing_elapsed_ms=processing_elapsed_ms,
            barcode_elapsed_ms=barcode_elapsed_ms, slicing_elapsed_ms=slicing_elapsed_ms,
            ocr_elapsed_ms=ocr_elapsed_ms, product_elapsed_ms=product_elapsed_ms,
            label_elapsed_ms=label_elapsed_ms, label_distances=label_distances,
            save_elapsed_ms=0.0,
        ))

    # Barcode
    barcode_start_t = time.perf_counter()
    result = router.capture(frame2, "ReadBarcodes_Default")
    items = result.get_items() if result else None
    barcodes = [
        item.get_text() for item in items or []
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
            product_display = "EAN not found"
            emit_report()
            return
        current_product = product.copy()
        current_product["_ean"] = ean
        worker_state["current_product"] = current_product
    else:
        barcode_display = "Ei loetud sellest taktist"
        current_product = worker_state["current_product"]
        if current_product is None:
            emit_report()
            return

    if not all(k in current_product for k in required_keys):
        product_display = current_product.get("ITEMNAME", "?")
        emit_report()
        return

    product_name = current_product.get("ITEMNAME", "?")
    expected_product_key = infer_product_key(product_name)
    expiry_duration = current_product.get("BESTBEFOREDAYS", 0)
    expiry_date = capture_date + timedelta(days=expiry_duration)
    expected_expiry_str = expiry_date.strftime("%d.%m.%Y")
    product_display = product_name
    expected_date_display = expected_expiry_str

    # Slicing
    slicing_start_t = time.perf_counter()
    temp_slices = []
    for coords in current_product["rois"].values():
        x1, y1 = coords[0]
        x2, y2 = coords[1]
        roi_crop = frame2[y1:y2, x1:x2]
        rotated = cv2.rotate(roi_crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
        temp_slices.append(rotated)

    if not temp_slices:
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
        if crop is not None and crop.size > 0:
            valid_crop_indices.append(idx)
            valid_date_crops_rgb.append(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    slicing_elapsed_ms = (time.perf_counter() - slicing_start_t) * 1000
    worker_state["ocr_total_crops"] += len(date_crops_bgr)

    # OCR
    if valid_date_crops_rgb:
        ocr_start_t = time.perf_counter()
        try:
            predicted_texts = worker_state["date_ocr"].predict_batch(valid_date_crops_rgb)
        except Exception as exc:
            report_notes.append(f"OCR error: {exc}")
            predicted_texts = [None] * len(valid_date_crops_rgb)
        ocr_elapsed_ms = (time.perf_counter() - ocr_start_t) * 1000
        if len(predicted_texts) != len(valid_date_crops_rgb):
            predicted_texts = list(predicted_texts[:len(valid_date_crops_rgb)])
            predicted_texts.extend([None] * (len(valid_date_crops_rgb) - len(predicted_texts)))
        for idx, raw_text in zip(valid_crop_indices, predicted_texts):
            raw_date_texts[idx] = raw_text

    worker_state["ocr_takt_times"].append(ocr_elapsed_ms)
    update_ocr_stats(raw_date_texts, expected_expiry_str, worker_state)

    # Product classification
    product_result = predict_products(final_slices, current_product, worker_state.get("product_classifier"))
    if product_result:
        product_elapsed_ms = product_result["elapsed_ms"]
        predicted_products = product_result["predictions"]
        worker_state["product_check_times"].append(product_elapsed_ms)
        worker_state["product_total_crops"] += product_result["total_crops"]
        worker_state["product_empty_count"] += sum(1 for p in predicted_products if p == "empty")
        worker_state["product_predicted_count_non_empty"] += sum(1 for p in predicted_products if p != "empty")
        worker_state["product_correct_count_non_empty"] += sum(1 for p in predicted_products if p != "empty" and p == expected_product_key)

    # Label comparison
    label_result = compare_labels_with_dino(final_slices, current_product, product_name, worker_state.get("label_matcher"))
    if label_result:
        label_elapsed_ms = label_result["elapsed_ms"]
        worker_state["label_check_times"].append(label_elapsed_ms)
        worker_state["label_total_crops"] += label_result["total_crops"]
        label_distances = label_result

    emit_report()


def processing_worker(task_queue, worker_state):
    while True:
        task = task_queue.get()
        try:
            if task is STOP_WORKER:
                return
            process_capture_task(task, worker_state)
        except Exception as e:
            tid = task.get("trigger_id", "?") if isinstance(task, dict) else "?"
            log(f"Takt {tid} failed: {e}")
        finally:
            task_queue.task_done()


# --- MAIN LOOP ---
total_triggers = 0
started = False
green_cooldown = False
motion_triggered = False
trigger_time = 0
cycle_start_time = 0
pending_trigger_id = None
run_start = time.time()

worker_state = create_worker_state(date_ocr)
worker_state["label_matcher"] = label_matcher
worker_state["product_classifier"] = product_classifier

task_queue = Queue()
worker_thread = threading.Thread(target=processing_worker, args=(task_queue, worker_state), daemon=True)
worker_thread.start()

log(f"\nConnected to {STREAM_URL}. Waiting for green screen...")

try:
    while True:
        if time.time() - run_start > MAX_RUNTIME_SECONDS:
            log(f"\nMax runtime ({MAX_RUNTIME_SECONDS}s) reached. Stopping.")
            break

        ret1, frame1 = stream.read()
        time.sleep(MONITOR_LOOP_SLEEP_SECONDS)
        ret2, frame2 = stream.read()
        if not ret1 or not ret2:
            break

        now = time.time()
        current_is_green = is_green_screen(frame2)

        if not started:
            if current_is_green:
                log(">>> Green screen detected! Starting cycle.")
                started = True
                green_cooldown = True
        else:
            process_this_frame = False
            if not current_is_green and green_cooldown:
                log(">>> Green screen ended. Starting monitoring.")
                green_cooldown = False
                cycle_start_time = now
                total_triggers += 1
                pending_trigger_id = total_triggers
                process_this_frame = True
            elif not green_cooldown:
                if current_is_green:
                    log(">>> Next green screen. Ending cycle.")
                    break

                mae = measure_global_change(frame1, frame2)
                if mae > MOTION_THRESHOLD and not motion_triggered:
                    motion_triggered = True
                    trigger_time = now
                    total_triggers += 1
                    pending_trigger_id = total_triggers
                    log(f"Motion at {now - cycle_start_time:.2f}s. Waiting {CAPTURE_DELAY}s...")

                if motion_triggered and (now - trigger_time >= CAPTURE_DELAY):
                    process_this_frame = True
                    motion_triggered = False

            if process_this_frame and pending_trigger_id is not None:
                elapsed = now - cycle_start_time

                if MULTI_FRAME_COUNT > 1:
                    candidates = [frame2.copy()]
                    for _ in range(MULTI_FRAME_COUNT - 1):
                        time.sleep(0.05)
                        ret_extra, frame_extra = stream.read()
                        if ret_extra and frame_extra is not None:
                            candidates.append(frame_extra.copy())
                    best_frame = pick_sharpest_frame(candidates)
                    sharpness = laplacian_sharpness(best_frame)
                    log(f"[{elapsed:.2f}s] Picked sharpest from {len(candidates)} frames (score: {sharpness:.1f})")
                else:
                    best_frame = frame2.copy()

                task_queue.put({
                    "trigger_id": pending_trigger_id,
                    "elapsed": elapsed,
                    "frame": best_frame,
                    "captured_at": now,
                })
                log(f"[{elapsed:.2f}s] Takt {pending_trigger_id} queued.")
                pending_trigger_id = None

except KeyboardInterrupt:
    log("Stopped by user.")

finally:
    stream.stop()
    task_queue.join()
    task_queue.put(STOP_WORKER)
    worker_thread.join(timeout=5.0)
    log(format_worker_summary(total_triggers, worker_state, date_ocr.get_usage_totals()))

    try:
        generate_dashboard(log_path, dashboard_path)
        log(f"\nDashboard generated: {dashboard_path}")
    except Exception as exc:
        log(f"Dashboard generation failed: {exc}")
