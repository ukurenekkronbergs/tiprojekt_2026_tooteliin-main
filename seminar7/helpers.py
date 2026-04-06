import base64
import io
import json
import os
import re
import threading
import time
import winsound
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


AVAILABLE_DATE_OCR_METHODS = (
    "easyocr",
    "parseq",
    "paddleocr",
    "vlm_single",
    "vlm_batch_independent",
    "vlm_batch_consistent",
)

DEFAULT_VLM_SINGLE_SYSTEM_PROMPT = (
    "You are an expert OCR system. Your task is to extract the expiry date from the "
    "provided image. The date format is DD.MM.YYYY. If you cannot find a date, respond "
    "with 'N/A'."
)
DEFAULT_VLM_SINGLE_USER_PROMPT = (
    "Extract the expiry date from this image. Respond ONLY with the date in "
    "DD.MM.YYYY format, or 'N/A' if no date is found."
)
DEFAULT_VLM_BATCH_INDEPENDENT_SYSTEM_PROMPT = (
    "You are an expert OCR system. Your task is to extract the expiry date from each "
    "of the provided images. The date format is DD.MM.YYYY. If you cannot find a date "
    "for a specific image, respond with 'N/A' for that image. Provide the results as a "
    "comma-separated list of dates, corresponding to the order of images provided."
)
DEFAULT_VLM_BATCH_INDEPENDENT_USER_PROMPT = (
    "Extract the expiry date from each image. Respond ONLY with a comma-separated list "
    "of dates in DD.MM.YYYY format, or 'N/A' for each image if no date is found. The "
    "order of dates should match the order of images."
)
DEFAULT_VLM_BATCH_CONSISTENT_SYSTEM_PROMPT = (
    "You are an expert OCR system. Your task is to extract the expiry date from each of "
    "the provided images. The date format is DD.MM.YYYY. In normal circumstances, all "
    "dates across these images should be identical. Only deviate from this assumption "
    "if there is strong visual evidence that a date is incomplete, unreadable, genuinely "
    "different, or the crop is irrelevant. For each image, respond with the extracted "
    "date. If you cannot find a date for a specific image, respond with 'N/A' for that "
    "image. Provide the results as a comma-separated list of dates in image order."
)
DEFAULT_VLM_BATCH_CONSISTENT_USER_PROMPT = (
    "Extract the expiry date from each image. Respond ONLY with a comma-separated list "
    "of dates in DD.MM.YYYY format, or 'N/A' for each image if no date is found. If the "
    "dates look consistent, keep them the same. If there is strong evidence of a "
    "different date or unreadability, reflect that."
)


class RTSPStreamReader:
    def __init__(self, url, max_retries=5, retry_delay=2.0):
        self.url = url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.cap = cv2.VideoCapture(url)
        self.ret = False
        self.frame = None
        self.running = True
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        retries = 0
        while self.running:
            try:
                ret, frame = self.cap.read()
            except Exception:
                ret, frame = False, None
            if not self.running:
                break
            if ret:
                retries = 0
                with self.lock:
                    self.ret = ret
                    self.frame = frame
            else:
                retries += 1
                if retries > self.max_retries:
                    with self.lock:
                        self.ret = False
                    break
                time.sleep(self.retry_delay)
                try:
                    self.cap.release()
                    self.cap = cv2.VideoCapture(self.url)
                except Exception:
                    pass

    def read(self):
        with self.lock:
            if self.frame is None:
                return self.ret, None
            return self.ret, self.frame.copy()

    def stop(self):
        self.running = False
        self.thread.join(timeout=1.0)
        self.cap.release()


def is_green_screen(frame):
    if frame is None:
        return False
    small = cv2.resize(frame, (64, 64))
    avg_color = np.mean(small, axis=(0, 1))
    return avg_color[1] > 200 and avg_color[0] < 50 and avg_color[2] < 50


def measure_global_change(f1, f2):
    # Resize to 350x250 (perfectly divisible by 7x5 grid)
    # This resolution is high enough to detect objects but small enough to fit in cache.
    w, h = 210, 150
    g1 = cv2.cvtColor(cv2.resize(f1, (w, h)), cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(cv2.resize(f2, (w, h)), cv2.COLOR_BGR2GRAY)

    # Compute difference once for the whole image
    diff_map = cv2.absdiff(g1, g2)

    uw, uh = w // 7, h // 5  # Unit width and height for the grid
    maes = []

    # Sample 6 areas at (row, col) indices: (0,0), (0,3), (0,6), (4,0), (4,3), (4,6)
    for r in [0, 4]:
        for c in [0, 3, 6]:
            roi_diff = diff_map[r * uh : (r + 1) * uh, c * uw : (c + 1) * uw]
            maes.append(np.mean(roi_diff))

    # Return minimum: only trigger if all regions show significant change.
    return min(maes)


def get_formatted_date(date_string):
    """Your provided post-processing logic."""
    if not isinstance(date_string, str):
        return None
    date_string = re.sub(r"[^a-zA-Z0-9]", "", date_string)
    letter_to_number_map = {
        "O": "0",
        "I": "1",
        "L": "1",
        "Z": "2",
        "S": "5",
        "B": "8",
        "R": "8",
        "A": "4",
    }
    date_string = "".join(letter_to_number_map.get(char, char) for char in date_string)

    if len(date_string) == 8 and date_string.isdigit():
        if date_string[2] not in ["0", "1"]:
            others_to_m1 = {
                "2": "1",
                "3": "0",
                "4": "1",
                "5": "0",
                "6": "0",
                "7": "1",
                "8": "0",
                "9": "0",
            }
            date_string = date_string[:2] + others_to_m1[date_string[2]] + date_string[3:]

        day, month, year = int(date_string[:2]), int(date_string[2:4]), int(date_string[4:])
        datestr = f"{day:02}.{month:02}.{year:04}"
        if 1 <= day <= 31 and 1 <= month <= 12:
            return datestr
        return datestr
    return "NA"


def format_date_grid(
    detected_dates_ordered: List[Optional[str]],
    expected_date_str: str,
    expected_product_key: Optional[str] = None,
    predicted_products: Optional[List[str]] = None,
    label_distances: Optional[Dict[str, List[float]]] = None,
    include_context: bool = True,
) -> str:
    """
    Returns a 2x2 grid of detected dates with color coding as a single string.
    Assumes detected_dates_ordered is in the order: Top-Left, Bottom-Left, Top-Right, Bottom-Right.
    Colors: Green (match), Red (mismatch), Yellow (no date).
    """
    color_reset = "\033[0m"
    color_green = "\033[92m"
    color_red = "\033[91m"
    color_yellow = "\033[93m"
    processed_dates = []
    for detected_raw in detected_dates_ordered:
        formatted_date = get_formatted_date(detected_raw)
        display_text = formatted_date if formatted_date else "N/A"

        if display_text in ["N/A", "NA"]:
            color = color_yellow
        elif display_text == expected_date_str:
            color = color_green
        else:
            color = color_red

        padded_text = f"{display_text:<15}"
        processed_dates.append(f"{color}{padded_text}{color_reset}")

    while len(processed_dates) < 4:
        padded_na = f"{'N/A':<15}"
        processed_dates.append(f"{color_yellow}{padded_na}{color_reset}")

    tl_date = processed_dates[0]
    bl_date = processed_dates[1]
    tr_date = processed_dates[2]
    br_date = processed_dates[3]

    def format_label_value(value: Optional[float]) -> str:
        if value is None:
            return f"{color_yellow}{'N/A':<15}{color_reset}"
        color = color_green if value < 0.5 else color_red
        return f"{color}{value:.2f}{'':<11}{color_reset}"

    def format_product_value(value: Optional[str]) -> str:
        if value is None:
            return f"{color_yellow}{'N/A':<15}{color_reset}"
        if value == "empty":
            color = color_yellow
        elif value == expected_product_key:
            color = color_green
        else:
            color = color_red
        return f"{color}{value:<15}{color_reset}"

    label1_values = (label_distances or {}).get("label1_distances", [])
    label2_values = (label_distances or {}).get("label2_distances", [])
    product_values = list(predicted_products or [])

    while len(label1_values) < 4:
        label1_values.append(None)
    while len(label2_values) < 4:
        label2_values.append(None)
    while len(product_values) < 4:
        product_values.append(None)

    tl_l1 = format_label_value(label1_values[0])
    bl_l1 = format_label_value(label1_values[1])
    tr_l1 = format_label_value(label1_values[2])
    br_l1 = format_label_value(label1_values[3])
    tl_l2 = format_label_value(label2_values[0])
    bl_l2 = format_label_value(label2_values[1])
    tr_l2 = format_label_value(label2_values[2])
    br_l2 = format_label_value(label2_values[3])
    tl_prod = format_product_value(product_values[0])
    bl_prod = format_product_value(product_values[1])
    tr_prod = format_product_value(product_values[2])
    br_prod = format_product_value(product_values[3])

    lines = [
        "+-----------------+-----------------+",
        f"| L2 {tl_l2} | L2 {tr_l2} |",
        f"| PR {tl_prod} | PR {tr_prod} |",
        f"| DT {tl_date} | DT {tr_date} |",
        f"| L1 {tl_l1} | L1 {tr_l1} |",
        "+-----------------+-----------------+",
        f"| L2 {bl_l2} | L2 {br_l2} |",
        f"| PR {bl_prod} | PR {br_prod} |",
        f"| DT {bl_date} | DT {br_date} |",
        f"| L1 {bl_l1} | L1 {br_l1} |",
        "+-----------------+-----------------+",
    ]
    if include_context:
        lines = [
            "---Tuvastamise tulemused (2x2 ruudustik) ---",
            f"Oodatav aegumiskuupaev: {expected_date_str}",
            *lines,
        ]

    return "\n".join(lines)


def print_date_grid(detected_dates_ordered: List[Optional[str]], expected_date_str: str):
    print(format_date_grid(detected_dates_ordered, expected_date_str))


def format_ms(value_ms: float) -> str:
    return f"{value_ms:.2f} ms"


def create_worker_state(date_ocr) -> Dict[str, Any]:
    """Creates the mutable state shared by the single processing worker."""
    return {
        "stats_times": [],
        "stats_counts": [],
        "success_count": 0,
        "current_product": None,
        "date_ocr": date_ocr,
        "ocr_backend_name": getattr(date_ocr, "display_name", date_ocr.name),
        "ocr_takt_times": [],
        "ocr_total_crops": 0,
        "ocr_match_count": 0,
        "ocr_na_count": 0,
        "ocr_error_count": 0,
        "label_check_times": [],
        "label_total_crops": 0,
        "product_check_times": [],
        "product_total_crops": 0,
        "product_empty_count": 0,
        "product_predicted_count_non_empty": 0,
        "product_correct_count_non_empty": 0,
    }


def infer_product_key(product_name: str) -> Optional[str]:
    normalized = (product_name or "").lower()
    if "salami" in normalized or "salaami" in normalized:
        return "salami"
    for key in ("rulaad", "veis", "kalkun"):
        if key in normalized:
            return key
    return None


class DINOLabelMatcher:
    """Compares label crops against one reference image per product/label on CPU."""

    def __init__(self, base_dir: str, model_name: str = "facebook/dinov2-small"):
        self.base_dir = Path(base_dir)
        self.model_name = model_name
        self.device = "cpu"
        self.processor = None
        self.model = None
        self.references: Dict[str, Dict[str, np.ndarray]] = {}
        self.ready = False

    def _load_model(self) -> None:
        if self.ready:
            return

        import torch
        from transformers import AutoImageProcessor, AutoModel

        self.torch = torch
        self.processor = AutoImageProcessor.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name).to(self.device)
        self.model.eval()
        self.ready = True

    def _embed_rgb_batch(self, images_rgb: List[np.ndarray]) -> np.ndarray:
        inputs = self.processor(images=images_rgb, return_tensors="pt")
        with self.torch.inference_mode():
            outputs = self.model(**inputs)
        embeddings = outputs.last_hidden_state[:, 0]
        embeddings = self.torch.nn.functional.normalize(embeddings, dim=1)
        return embeddings.cpu().numpy()

    def _load_reference(self, product_key: str, label_name: str) -> np.ndarray:
        product_refs = self.references.setdefault(product_key, {})
        if label_name in product_refs:
            return product_refs[label_name]

        label_dir = self.base_dir / product_key / label_name
        image_path = sorted(label_dir.glob("*.png"))[0]
        image_bgr = cv2.imread(str(image_path))
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        product_refs[label_name] = self._embed_rgb_batch([image_rgb])[0]
        return product_refs[label_name]

    def compare_product_labels(
        self,
        product_key: str,
        label1_crops_bgr: List[np.ndarray],
        label2_crops_bgr: List[np.ndarray],
    ) -> Dict[str, Any]:
        self._load_model()

        # DINO processor accepts different input sizes, so all 8 crops can go in one batch.
        all_crops_rgb = [cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) for crop in label1_crops_bgr + label2_crops_bgr]

        started_at = time.perf_counter()
        embeddings = self._embed_rgb_batch(all_crops_rgb)
        elapsed_ms = (time.perf_counter() - started_at) * 1000

        ref_label1 = self._load_reference(product_key, "label1")
        ref_label2 = self._load_reference(product_key, "label2")

        label1_count = len(label1_crops_bgr)
        label1_embeddings = embeddings[:label1_count]
        label2_embeddings = embeddings[label1_count:]

        label1_distances = 1.0 - label1_embeddings @ ref_label1
        label2_distances = 1.0 - label2_embeddings @ ref_label2

        return {
            "label1_distances": label1_distances.tolist(),
            "label2_distances": label2_distances.tolist(),
            "elapsed_ms": elapsed_ms,
            "total_crops": len(all_crops_rgb),
        }


def create_label_matcher(base_dir: str, model_name: str = "facebook/dinov2-small") -> DINOLabelMatcher:
    return DINOLabelMatcher(base_dir=base_dir, model_name=model_name)


def compare_labels_with_dino(
    final_slices: List[np.ndarray],
    current_product: Dict[str, Any],
    product_name: str,
    label_matcher: Optional[DINOLabelMatcher],
) -> Optional[Dict[str, Any]]:
    if label_matcher is None:
        return None

    product_key = infer_product_key(product_name)
    if product_key is None:
        return None

    label1_crops_bgr = [slice_img[current_product["label1_below"] :, :] for slice_img in final_slices]
    label2_crops_bgr = [slice_img[: current_product["label2_above"], :] for slice_img in final_slices]
    return label_matcher.compare_product_labels(product_key, label1_crops_bgr, label2_crops_bgr)


class ProductClassifier:
    def __init__(self, model_path: str, embedder: Optional[DINOLabelMatcher] = None):
        import joblib

        self.classifier = joblib.load(model_path)
        self.embedder = embedder

    def predict_batch(self, product_crops_bgr: List[np.ndarray]) -> Dict[str, Any]:
        if self.embedder is None:
            return {"predictions": [], "elapsed_ms": 0.0, "total_crops": 0}

        self.embedder._load_model()
        images_rgb = [cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) for crop in product_crops_bgr]
        started_at = time.perf_counter()
        features = self.embedder._embed_rgb_batch(images_rgb)
        predictions = list(self.classifier.predict(features))
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        return {
            "predictions": predictions,
            "elapsed_ms": elapsed_ms,
            "total_crops": len(product_crops_bgr),
        }


def create_product_classifier(model_path: str, embedder: Optional[DINOLabelMatcher] = None) -> ProductClassifier:
    return ProductClassifier(model_path=model_path, embedder=embedder)


def predict_products(
    final_slices: List[np.ndarray],
    current_product: Dict[str, Any],
    product_classifier: Optional[ProductClassifier],
) -> Optional[Dict[str, Any]]:
    if product_classifier is None:
        return None

    py1, py2 = current_product["product_area_between"]
    product_crops_bgr = [slice_img[py1:py2, :] for slice_img in final_slices]
    return product_classifier.predict_batch(product_crops_bgr)


def update_ocr_stats(
    raw_date_texts: List[Optional[str]],
    expected_expiry_str: str,
    worker_state: Dict[str, Any],
):
    """Updates aggregate OCR statistics from one takt's raw OCR outputs."""
    for raw_text in raw_date_texts:
        formatted_date = get_formatted_date(raw_text)
        if raw_text is None:
            worker_state["ocr_error_count"] += 1
        elif formatted_date in (None, "NA"):
            worker_state["ocr_na_count"] += 1
        elif formatted_date == expected_expiry_str:
            worker_state["ocr_match_count"] += 1


def build_debug_image_jobs(
    folder_name: str,
    trigger_id: int,
    frame: np.ndarray,
    final_slices: List[np.ndarray],
    date_crops_bgr: List[np.ndarray],
    current_product: Dict[str, Any],
) -> List[tuple]:
    """Builds the list of debug images to save for one processed takt."""
    for sub in ["date", "label1", "label2", "product_area", "individual_products", "full_frames"]:
        os.makedirs(os.path.join(folder_name, sub), exist_ok=True)

    images_to_save = [
        (os.path.join(folder_name, "full_frames", f"takt_{trigger_id}_full.png"), frame)
    ]
    py1, py2 = current_product["product_area_between"]

    for i, s_img in enumerate(final_slices):
        s_idx = i + 1
        images_to_save.extend(
            [
                (
                    os.path.join(
                        folder_name, "individual_products", f"takt_{trigger_id}_slice_{s_idx}.png"
                    ),
                    s_img,
                ),
                (
                    os.path.join(folder_name, "date", f"takt_{trigger_id}_s{s_idx}_date.png"),
                    date_crops_bgr[i],
                ),
                (
                    os.path.join(folder_name, "label1", f"takt_{trigger_id}_s{s_idx}_l1.png"),
                    s_img[current_product["label1_below"] :, :],
                ),
                (
                    os.path.join(folder_name, "label2", f"takt_{trigger_id}_s{s_idx}_l2.png"),
                    s_img[: current_product["label2_above"], :],
                ),
                (
                    os.path.join(folder_name, "product_area", f"takt_{trigger_id}_s{s_idx}_prod.png"),
                    s_img[py1:py2, :],
                ),
            ]
        )
    return images_to_save


def format_takt_report(
    *,
    trigger_id: int,
    barcode_display: str,
    product_display: str,
    expected_date_display: str,
    expected_product_key: Optional[str],
    raw_date_texts: List[Optional[str]],
    predicted_products: Optional[List[str]],
    expected_expiry_str: str,
    report_notes: List[str],
    processing_elapsed_ms: float,
    barcode_elapsed_ms: float,
    slicing_elapsed_ms: float,
    ocr_elapsed_ms: float,
    product_elapsed_ms: float,
    label_elapsed_ms: float,
    label_distances: Optional[Dict[str, List[float]]],
    save_elapsed_ms: float,
) -> str:
    """Formats the per-takt worker output as one printable text block."""
    report_lines = [
        "",
        f"=== Takti {trigger_id} tulemused ===",
        f"Triipkood: {barcode_display}",
        f"Toode: {product_display}",
        f"Oodatav aegumiskuupaev: {expected_date_display}",
    ]
    report_lines.extend(f"Markus: {note}" for note in report_notes)
    report_lines.extend(
        [
            "Kuupaevade 2x2 maatriks:",
            format_date_grid(
                raw_date_texts,
                expected_expiry_str,
                expected_product_key=expected_product_key,
                predicted_products=predicted_products,
                label_distances=label_distances,
                include_context=False,
            ),
            f"Tootlemise koguaeg (ilma piltide salvestamiseta): {format_ms(processing_elapsed_ms)}",
            f"Triipkoodi lugemise aeg: {format_ms(barcode_elapsed_ms)}",
            f"Loikamise aeg: {format_ms(slicing_elapsed_ms)}",
            f"Kuupaeva lugemise aeg: {format_ms(ocr_elapsed_ms)}",
            f"Tootetuvastuse aeg: {format_ms(product_elapsed_ms)}",
            f"Siltide DINO vordluse aeg: {format_ms(label_elapsed_ms)}",
            f"Piltide salvestamise aeg: {format_ms(save_elapsed_ms)}",
            "",
        ]
    )
    return "\n".join(report_lines)


def format_worker_summary(total_triggers: int, worker_state: Dict[str, Any], usage_totals: Dict[str, Any]) -> str:
    """Formats the final end-of-run summary shown after the queue drains."""
    stats_times = worker_state["stats_times"]
    stats_counts = worker_state["stats_counts"]
    success_rate = (worker_state["success_count"] / total_triggers * 100) if total_triggers else 0.0
    avg_time = (sum(stats_times) / len(stats_times)) if stats_times else 0.0
    max_time = max(stats_times) if stats_times else 0.0
    avg_barcodes = (sum(stats_counts) / len(stats_counts)) if stats_counts else 0.0

    ocr_total_crops = worker_state["ocr_total_crops"]
    ocr_total_time_ms = sum(worker_state["ocr_takt_times"])
    avg_ocr_takt_ms = (
        ocr_total_time_ms / len(worker_state["ocr_takt_times"])
        if worker_state["ocr_takt_times"]
        else 0.0
    )
    avg_ocr_crop_ms = (ocr_total_time_ms / ocr_total_crops) if ocr_total_crops else 0.0
    ocr_match_rate = (
        worker_state["ocr_match_count"] / ocr_total_crops * 100 if ocr_total_crops else 0.0
    )
    ocr_mismatch_count = max(
        0,
        ocr_total_crops
        - worker_state["ocr_match_count"]
        - worker_state["ocr_na_count"]
        - worker_state["ocr_error_count"],
    )
    label_total_time_ms = sum(worker_state["label_check_times"])
    label_total_crops = worker_state["label_total_crops"]
    avg_label_takt_ms = (
        label_total_time_ms / len(worker_state["label_check_times"])
        if worker_state["label_check_times"]
        else 0.0
    )
    avg_label_crop_ms = (label_total_time_ms / label_total_crops) if label_total_crops else 0.0
    product_total_time_ms = sum(worker_state["product_check_times"])
    product_total_crops = worker_state["product_total_crops"]
    avg_product_takt_ms = (
        product_total_time_ms / len(worker_state["product_check_times"])
        if worker_state["product_check_times"]
        else 0.0
    )
    avg_product_crop_ms = (product_total_time_ms / product_total_crops) if product_total_crops else 0.0
    empty_rate = (
        worker_state["product_empty_count"] / product_total_crops * 100 if product_total_crops else 0.0
    )
    non_empty_correct_rate = (
        worker_state["product_correct_count_non_empty"] / worker_state["product_predicted_count_non_empty"] * 100
        if worker_state["product_predicted_count_non_empty"]
        else 0.0
    )

    lines = [
        "",
        "--- KOKKUVOTE ---",
        f"Total triggers: {total_triggers}",
        f"Triipkoodi tuvastamise onnistumise protsent: {success_rate:.2f}%",
        f"Keskmine takti tootlemise aeg: {avg_time:.2f} ms",
        f"Maksimaalne takti tootlemise aeg: {max_time:.2f} ms",
        f"Keskmine leitud triipkoodide arv takti kohta: {avg_barcodes:.2f}",
        "",
        "--- KUUPAEVA OCR ---",
        f"Tuvastusmeetod: {worker_state['ocr_backend_name']}",
        f"Toodeldud kuupaevaloike: {ocr_total_crops}",
        f"Oodatud kuupaevaga kattuvad tulemused: {worker_state['ocr_match_count']} ({ocr_match_rate:.2f}%)",
        f"NA tulemused: {worker_state['ocr_na_count']}",
        f"Mittevastavused: {ocr_mismatch_count}",
        f"Kuupaevatuvastusel tekkinud veateated: {worker_state['ocr_error_count']}",
        f"Keskmine OCR aeg takti kohta: {avg_ocr_takt_ms:.2f} ms",
        f"Keskmine OCR aeg cropi kohta: {avg_ocr_crop_ms:.2f} ms",
        "",
        "--- SILTIDE DINO ---",
        f"Toodeldud sildiloike: {label_total_crops}",
        f"Keskmine sildivordluse aeg takti kohta: {avg_label_takt_ms:.2f} ms",
        f"Keskmine sildivordluse aeg cropi kohta: {avg_label_crop_ms:.2f} ms",
        "",
        "--- TOOTED ---",
        f"Toodeldud tooteloike: {product_total_crops}",
        f"Tuhje pakke: {worker_state['product_empty_count']} ({empty_rate:.2f}%)",
        f"Oigesti tuvastatud mittetuhje tooteid: {worker_state['product_correct_count_non_empty']} ({non_empty_correct_rate:.2f}%)",
        f"Mittetuhju tooteennustusi kokku: {worker_state['product_predicted_count_non_empty']}",
        f"Keskmine tootetuvastuse aeg takti kohta: {avg_product_takt_ms:.2f} ms",
        f"Keskmine tootetuvastuse aeg cropi kohta: {avg_product_crop_ms:.2f} ms",
    ]

    if usage_totals:
        lines.extend(
            [
                "",
                "--- OPENROUTER OCR ---",
                f"Total API Calls: {usage_totals['calls']}",
                f"Total Prompt Tokens: {usage_totals['prompt_tokens']:,}",
                f"Total Completion Tokens: {usage_totals['completion_tokens']:,}",
                f"Total Tokens: {usage_totals['total_tokens']:,}",
                f"Estimated Cost: ${usage_totals['cost']:.6f}",
            ]
        )
    return "\n".join(lines)


class BaseDateOCR:
    name = "unknown"
    display_name = "unknown"

    def predict_batch(self, image_batch: List[np.ndarray]) -> List[Optional[str]]:
        raise NotImplementedError

    def get_usage_totals(self) -> Dict[str, Any]:
        return {}


class EasyOCRDateOCR(BaseDateOCR):
    name = "easyocr"
    display_name = "easyocr"

    def __init__(self):
        try:
            import easyocr
        except ImportError as exc:
            raise RuntimeError(
                "DATE_OCR_METHOD='easyocr' requires the 'easyocr' package."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to import EasyOCR: {exc}") from exc

        try:
            self.reader = easyocr.Reader(["en"])
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize EasyOCR reader: {exc}") from exc

    def predict_batch(self, image_batch: List[np.ndarray]) -> List[Optional[str]]:
        if not image_batch:
            return []

        raw_texts = []
        for img_np_array in image_batch:
            try:
                results = self.reader.readtext(img_np_array)
                raw_texts.append(" ".join(res[1] for res in results))
            except Exception as exc:
                print(f"EasyOCR failed on one date crop: {exc}")
                raw_texts.append(None)
        return raw_texts


class ParseqDateOCR(BaseDateOCR):
    name = "parseq"
    display_name = "parseq"

    def __init__(self):
        try:
            import torch
            from PIL import Image
            from torchvision import transforms as T
        except ImportError as exc:
            raise RuntimeError(
                "DATE_OCR_METHOD='parseq' requires 'torch', 'torchvision', and 'Pillow'."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to import PARSeq dependencies: {exc}") from exc

        self.torch = torch
        self.image_cls = Image
        self.transforms = T
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            self.model = torch.hub.load(
                "baudm/parseq",
                "parseq",
                pretrained=True,
                map_location=self.device,
            ).to(self.device).eval()
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize PARSeq model: {exc}") from exc

        self.img_transform = T.Compose(
            [
                T.Resize(self.model.hparams.img_size, T.InterpolationMode.BICUBIC),
                T.ToTensor(),
                T.Normalize(0.5, 0.5),
            ]
        )

    def predict_batch(self, image_batch: List[np.ndarray]) -> List[Optional[str]]:
        if not image_batch:
            return []

        pil_images = [self.image_cls.fromarray(img_rgb) for img_rgb in image_batch]
        transformed_imgs = [self.img_transform(pil_img) for pil_img in pil_images]
        batch_tensor = self.torch.stack(transformed_imgs).to(self.device)

        with self.torch.no_grad():
            logits = self.model(batch_tensor)

        pred = logits.softmax(-1)
        labels, _ = self.model.tokenizer.decode(pred)
        return list(labels)


class PaddleOCRDateOCR(BaseDateOCR):
    name = "paddleocr"
    display_name = "paddleocr"

    def __init__(self):
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ.setdefault("OMP_NUM_THREADS", "1")

        try:
            import paddlex as pdx
        except ImportError as exc:
            raise RuntimeError(
                "DATE_OCR_METHOD='paddleocr' requires the 'paddlex' package."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to import PaddleX: {exc}") from exc

        try:
            self.model = pdx.create_model("PP-OCRv5_server_rec")
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize PaddleOCR model: {exc}") from exc

    def predict_batch(self, image_batch: List[np.ndarray]) -> List[Optional[str]]:
        if not image_batch:
            return []

        predictions = list(self.model.predict(image_batch))
        raw_texts = []
        for pred in predictions:
            if pred and "rec_text" in pred:
                raw_texts.append(pred.get("rec_text", ""))
            else:
                raw_texts.append("")
        return raw_texts


class OpenRouterOCR:
    """
    Klass OpenRouteri VLM-i kasutamiseks OCR-i jaoks.
    Kapseldab API kliendi, viibad ja kasutusstatistika jalgimise.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        app_referer: str,
        app_title: str,
        batch_independent_system_prompt: str = "",
        batch_independent_user_prompt: str = "",
        batch_consistent_system_prompt: str = "",
        batch_consistent_user_prompt: str = "",
    ):
        try:
            from openai import OpenAI
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "DATE_OCR_METHOD='openrouter' requires the 'openai' and 'Pillow' packages."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to import OpenRouter dependencies: {exc}") from exc

        self.image_cls = Image
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": app_referer,
                "X-Title": app_title,
            },
        )
        self.model = model
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.batch_independent_system_prompt = (
            batch_independent_system_prompt or system_prompt
        )
        self.batch_independent_user_prompt = batch_independent_user_prompt or user_prompt
        self.batch_consistent_system_prompt = (
            batch_consistent_system_prompt or batch_independent_system_prompt or system_prompt
        )
        self.batch_consistent_user_prompt = (
            batch_consistent_user_prompt or batch_independent_user_prompt or user_prompt
        )
        self.usage_totals = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0,
            "last_call_info": None,
        }

    def _usage_to_dict(self, usage_obj) -> dict:
        if usage_obj is None:
            return {}
        return {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
            "total_tokens": getattr(usage_obj, "total_tokens", 0),
            "cost": getattr(usage_obj, "cost", 0.0),
        }

    def record_usage(self, usage_obj, *, step: str):
        u = self._usage_to_dict(usage_obj)
        if not u:
            return

        self.usage_totals["calls"] += 1
        self.usage_totals["prompt_tokens"] += int(u.get("prompt_tokens", 0))
        self.usage_totals["completion_tokens"] += int(u.get("completion_tokens", 0))
        self.usage_totals["total_tokens"] += int(u.get("total_tokens", 0))
        self.usage_totals["cost"] += float(u.get("cost", 0.0))
        self.usage_totals["last_call_info"] = {"step": step, **u}

    def _prepare_image_content(self, image_batch: List[np.ndarray]) -> List[dict]:
        content_blocks = []
        for img_rgb in image_batch:
            pil_img = self.image_cls.fromarray(img_rgb)
            buffered = io.BytesIO()
            pil_img.save(buffered, format="JPEG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            content_blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                }
            )
        return content_blocks

    def tuvastus_openrouter(self, image_batch: List[np.ndarray]) -> List[Optional[str]]:
        if not image_batch:
            return []

        raw_texts = []
        for img_rgb in image_batch:
            pil_img = self.image_cls.fromarray(img_rgb)
            buffered = io.BytesIO()
            pil_img.save(buffered, format="JPEG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

            messages = [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                        },
                    ],
                },
            ]
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    max_tokens=20,
                )
                self.record_usage(response.usage, step="ocr_predict")
                content = response.choices[0].message.content
                raw_texts.append(content.strip() if content is not None else "")
            except Exception as exc:
                print(f"OpenRouter OCR failed on one date crop: {exc}")
                raw_texts.append(None)
        return raw_texts

    def tuvastus_openrouter_batch_independent(
        self, image_batch: List[np.ndarray]
    ) -> List[Optional[str]]:
        if not image_batch:
            return []

        image_content_blocks = self._prepare_image_content(image_batch)
        messages = [
            {"role": "system", "content": self.batch_independent_system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.batch_independent_user_prompt},
                    *image_content_blocks,
                ],
            },
        ]
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                max_tokens=100,
            )
            self.record_usage(response.usage, step="ocr_predict_batch_independent")
            content = response.choices[0].message.content
            if not content:
                return [None] * len(image_batch)

            raw_texts = [s.strip() for s in content.split(",")]
            raw_texts.extend([None] * (len(image_batch) - len(raw_texts)))
            return raw_texts[: len(image_batch)]
        except Exception as exc:
            print(f"OpenRouter OCR batch-independent failed: {exc}")
            return [None] * len(image_batch)

    def tuvastus_openrouter_batch_consistent(
        self, image_batch: List[np.ndarray]
    ) -> List[Optional[str]]:
        if not image_batch:
            return []

        image_content_blocks = self._prepare_image_content(image_batch)
        messages = [
            {"role": "system", "content": self.batch_consistent_system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.batch_consistent_user_prompt},
                    *image_content_blocks,
                ],
            },
        ]
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                max_tokens=100,
            )
            self.record_usage(response.usage, step="ocr_predict_batch_consistent")
            content = response.choices[0].message.content
            if not content:
                return [None] * len(image_batch)

            raw_texts = [s.strip() for s in content.split(",")]
            raw_texts.extend([None] * (len(image_batch) - len(raw_texts)))
            return raw_texts[: len(image_batch)]
        except Exception as exc:
            print(f"OpenRouter OCR batch-consistent failed: {exc}")
            return [None] * len(image_batch)

    def get_usage_totals(self) -> dict:
        return self.usage_totals

    def get_model_name(self) -> str:
        return self.model


class OpenRouterDateOCR(BaseDateOCR):
    name = "vlm"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        app_referer: str,
        app_title: str,
        batch_independent_system_prompt: str,
        batch_independent_user_prompt: str,
        batch_consistent_system_prompt: str,
        batch_consistent_user_prompt: str,
        mode: str,
    ):
        self.client = OpenRouterOCR(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            app_referer=app_referer,
            app_title=app_title,
            batch_independent_system_prompt=batch_independent_system_prompt,
            batch_independent_user_prompt=batch_independent_user_prompt,
            batch_consistent_system_prompt=batch_consistent_system_prompt,
            batch_consistent_user_prompt=batch_consistent_user_prompt,
        )
        self.mode = mode
        self.display_name = f"{mode} ({model})"

    def predict_batch(self, image_batch: List[np.ndarray]) -> List[Optional[str]]:
        if self.mode == "vlm_batch_independent":
            return self.client.tuvastus_openrouter_batch_independent(image_batch)
        if self.mode == "vlm_batch_consistent":
            return self.client.tuvastus_openrouter_batch_consistent(image_batch)
        return self.client.tuvastus_openrouter(image_batch)

    def get_usage_totals(self) -> Dict[str, Any]:
        return self.client.get_usage_totals()


def create_date_ocr(
    method: str,
    *,
    openrouter_api_key: str = "",
    openrouter_model: str = "",
    system_prompt: str = DEFAULT_VLM_SINGLE_SYSTEM_PROMPT,
    user_prompt: str = DEFAULT_VLM_SINGLE_USER_PROMPT,
    app_referer: str = "https://ai-project-course-2025.com",
    app_title: str = "AI Project Course OCR",
    batch_independent_system_prompt: str = DEFAULT_VLM_BATCH_INDEPENDENT_SYSTEM_PROMPT,
    batch_independent_user_prompt: str = DEFAULT_VLM_BATCH_INDEPENDENT_USER_PROMPT,
    batch_consistent_system_prompt: str = DEFAULT_VLM_BATCH_CONSISTENT_SYSTEM_PROMPT,
    batch_consistent_user_prompt: str = DEFAULT_VLM_BATCH_CONSISTENT_USER_PROMPT,
):
    normalized_method = (method or "").strip().lower()
    method_aliases = {
        "openrouter": "vlm_single",
        "openrouter_batch_independent": "vlm_batch_independent",
        "openrouter_batch_consistent": "vlm_batch_consistent",
    }
    normalized_method = method_aliases.get(normalized_method, normalized_method)

    if normalized_method not in AVAILABLE_DATE_OCR_METHODS:
        supported = ", ".join(AVAILABLE_DATE_OCR_METHODS)
        raise ValueError(
            f"Invalid DATE_OCR_METHOD '{method}'. Supported values: {supported}."
        )

    if normalized_method == "easyocr":
        return EasyOCRDateOCR()
    if normalized_method == "parseq":
        return ParseqDateOCR()
    if normalized_method == "paddleocr":
        return PaddleOCRDateOCR()

    if not openrouter_api_key:
        raise ValueError(
            f"DATE_OCR_METHOD='{normalized_method}' requires OPENROUTER_API_KEY to be set."
        )
    if not openrouter_model:
        raise ValueError(
            f"DATE_OCR_METHOD='{normalized_method}' requires OPENROUTER_MODEL to be set."
        )

    return OpenRouterDateOCR(
        api_key=openrouter_api_key,
        model=openrouter_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        app_referer=app_referer,
        app_title=app_title,
        batch_independent_system_prompt=batch_independent_system_prompt,
        batch_independent_user_prompt=batch_independent_user_prompt,
        batch_consistent_system_prompt=batch_consistent_system_prompt,
        batch_consistent_user_prompt=batch_consistent_user_prompt,
        mode=normalized_method,
    )


# ---------------------------------------------------------------------------
# BLUR DETECTION: Laplacian variance – pick sharpest frame from N candidates
# ---------------------------------------------------------------------------

def laplacian_sharpness(frame: np.ndarray) -> float:
    """Return Laplacian variance as a sharpness score (higher = sharper)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def pick_sharpest_frame(frames: List[np.ndarray]) -> np.ndarray:
    """Given a list of frames, return the one with the highest sharpness score."""
    if not frames:
        raise ValueError("No frames provided")
    if len(frames) == 1:
        return frames[0]
    scores = [laplacian_sharpness(f) for f in frames]
    best_idx = int(np.argmax(scores))
    return frames[best_idx]


# ---------------------------------------------------------------------------
# JSON LOGGING: Save per-takt results to a JSONL file
# ---------------------------------------------------------------------------

class TaktLogger:
    """Appends one JSON line per takt to a log file."""

    def __init__(self, log_path: str):
        self.log_path = log_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    def log_takt(self, record: Dict[str, Any]) -> None:
        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_takt_record(
    *,
    trigger_id: int,
    barcode_display: str,
    product_display: str,
    expected_date: str,
    expected_product_key: Optional[str],
    raw_date_texts: List[Optional[str]],
    predicted_products: Optional[List[str]],
    label_distances: Optional[Dict[str, Any]],
    processing_ms: float,
    barcode_ms: float,
    slicing_ms: float,
    ocr_ms: float,
    product_ms: float,
    label_ms: float,
    anomalies: List[str],
) -> Dict[str, Any]:
    """Build a flat dict suitable for JSON logging."""
    formatted_dates = [get_formatted_date(t) for t in raw_date_texts]
    return {
        "timestamp": datetime.now().isoformat(),
        "trigger_id": trigger_id,
        "barcode": barcode_display,
        "product": product_display,
        "expected_date": expected_date,
        "expected_product_key": expected_product_key,
        "detected_dates": formatted_dates,
        "predicted_products": predicted_products,
        "label1_distances": (label_distances or {}).get("label1_distances"),
        "label2_distances": (label_distances or {}).get("label2_distances"),
        "processing_ms": round(processing_ms, 2),
        "barcode_ms": round(barcode_ms, 2),
        "slicing_ms": round(slicing_ms, 2),
        "ocr_ms": round(ocr_ms, 2),
        "product_ms": round(product_ms, 2),
        "label_ms": round(label_ms, 2),
        "anomalies": anomalies,
    }


# ---------------------------------------------------------------------------
# ANOMALY DETECTION & AUDIO ALERTS
# ---------------------------------------------------------------------------

LABEL_DISTANCE_THRESHOLD = 0.5


def detect_anomalies(
    *,
    raw_date_texts: List[Optional[str]],
    expected_expiry_str: str,
    predicted_products: Optional[List[str]],
    expected_product_key: Optional[str],
    label_distances: Optional[Dict[str, Any]],
) -> List[str]:
    """Return a list of human-readable anomaly strings for this takt."""
    anomalies: List[str] = []

    # Date mismatches
    for i, raw in enumerate(raw_date_texts):
        fmt = get_formatted_date(raw)
        if fmt in (None, "NA", "N/A"):
            anomalies.append(f"Pakend {i+1}: kuupäev loetamatu")
        elif fmt != expected_expiry_str:
            anomalies.append(f"Pakend {i+1}: vale kuupäev {fmt} (oodati {expected_expiry_str})")

    # Product mismatches
    if predicted_products and expected_product_key:
        for i, pred in enumerate(predicted_products):
            if pred == "empty":
                anomalies.append(f"Pakend {i+1}: tühi pakk")
            elif pred != expected_product_key:
                anomalies.append(f"Pakend {i+1}: vale toode '{pred}' (oodati '{expected_product_key}')")

    # Label distance too high
    if label_distances:
        for label_key in ("label1_distances", "label2_distances"):
            dists = label_distances.get(label_key, [])
            label_name = "alumine silt" if "label1" in label_key else "ülemine silt"
            for i, d in enumerate(dists):
                if d is not None and d >= LABEL_DISTANCE_THRESHOLD:
                    anomalies.append(
                        f"Pakend {i+1}: {label_name} kaugus {d:.2f} (lävend {LABEL_DISTANCE_THRESHOLD})"
                    )

    return anomalies


def play_alert_sound(anomalies: List[str]) -> None:
    """Play a Windows beep if there are anomalies. Non-blocking."""
    if not anomalies:
        return
    try:
        # Short beep: 1000 Hz, 200ms
        winsound.Beep(1000, 200)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HTML DASHBOARD GENERATOR
# ---------------------------------------------------------------------------

def generate_dashboard(log_path: str, output_path: str) -> None:
    """Read a JSONL log file and generate a self-contained HTML dashboard."""
    records = []
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    total = len(records)
    if total == 0:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("<html><body><h1>Dashboard</h1><p>Andmed puuduvad.</p></body></html>")
        return

    # Compute stats
    anomaly_count = sum(1 for r in records if r.get("anomalies"))
    ok_count = total - anomaly_count
    avg_processing = sum(r.get("processing_ms", 0) for r in records) / total
    avg_ocr = sum(r.get("ocr_ms", 0) for r in records) / total

    date_correct = 0
    date_total = 0
    for r in records:
        for d in (r.get("detected_dates") or []):
            date_total += 1
            if d == r.get("expected_date"):
                date_correct += 1
    date_accuracy = (date_correct / date_total * 100) if date_total else 0

    product_correct = 0
    product_total = 0
    for r in records:
        preds = r.get("predicted_products") or []
        exp = r.get("expected_product_key")
        for p in preds:
            if p and p != "empty":
                product_total += 1
                if p == exp:
                    product_correct += 1
    product_accuracy = (product_correct / product_total * 100) if product_total else 0

    # Anomaly type breakdown
    anomaly_types: Dict[str, int] = {}
    for r in records:
        for a in (r.get("anomalies") or []):
            if "kuupäev" in a or "kuupaev" in a:
                key = "Kuupäev"
            elif "vale toode" in a:
                key = "Vale toode"
            elif "tühi" in a or "tyhi" in a:
                key = "Tühi pakk"
            elif "silt" in a:
                key = "Sildi kaugus"
            else:
                key = "Muu"
            anomaly_types[key] = anomaly_types.get(key, 0) + 1

    # Build table rows
    table_rows = []
    for r in records:
        anoms = r.get("anomalies") or []
        status = "⚠️" if anoms else "✅"
        dates_str = ", ".join(str(d) for d in (r.get("detected_dates") or []))
        prods_str = ", ".join(str(p) for p in (r.get("predicted_products") or []))
        anom_str = "; ".join(anoms) if anoms else "-"
        table_rows.append(
            f"<tr class='{'anomaly-row' if anoms else ''}'>"
            f"<td>{status}</td>"
            f"<td>{r.get('trigger_id','?')}</td>"
            f"<td>{r.get('timestamp','?')[:19]}</td>"
            f"<td>{r.get('barcode','?')}</td>"
            f"<td>{r.get('product','?')}</td>"
            f"<td>{r.get('expected_date','?')}</td>"
            f"<td>{dates_str}</td>"
            f"<td>{prods_str}</td>"
            f"<td>{r.get('processing_ms',0):.0f}</td>"
            f"<td>{anom_str}</td>"
            f"</tr>"
        )

    anomaly_bars = "".join(
        f"<div class='bar-item'><span class='bar-label'>{k}</span>"
        f"<div class='bar' style='width:{v*5}px'>{v}</div></div>"
        for k, v in sorted(anomaly_types.items(), key=lambda x: -x[1])
    )

    html = f"""<!DOCTYPE html>
<html lang="et">
<head>
<meta charset="utf-8">
<title>Tooteliini Dashboard</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
  h1 {{ color: #333; }}
  .stats {{ display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 20px; }}
  .stat-card {{ background: white; border-radius: 8px; padding: 20px; min-width: 180px;
               box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
  .stat-card .value {{ font-size: 2em; font-weight: bold; }}
  .stat-card .label {{ color: #666; margin-top: 5px; }}
  .stat-card.green .value {{ color: #2ecc71; }}
  .stat-card.red .value {{ color: #e74c3c; }}
  .stat-card.blue .value {{ color: #3498db; }}
  table {{ width: 100%; border-collapse: collapse; background: white;
           box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }}
  th {{ background: #2c3e50; color: white; padding: 12px 8px; text-align: left; font-size: 0.85em; }}
  td {{ padding: 8px; border-bottom: 1px solid #eee; font-size: 0.85em; }}
  tr:hover {{ background: #f0f0f0; }}
  .anomaly-row {{ background: #fff3f3; }}
  .anomaly-row:hover {{ background: #ffe0e0; }}
  .bar-item {{ display: flex; align-items: center; margin: 4px 0; }}
  .bar-label {{ width: 120px; font-size: 0.9em; }}
  .bar {{ background: #e74c3c; color: white; padding: 2px 8px; border-radius: 4px;
          font-size: 0.85em; min-width: 30px; text-align: center; }}
  .section {{ background: white; border-radius: 8px; padding: 20px;
              box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>Tooteliini kvaliteedikontroll</h1>
<p>Genereeritud: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>

<div class="stats">
  <div class="stat-card green"><div class="value">{ok_count}</div><div class="label">OK takte</div></div>
  <div class="stat-card red"><div class="value">{anomaly_count}</div><div class="label">Anomaaliaga takte</div></div>
  <div class="stat-card blue"><div class="value">{total}</div><div class="label">Kokku takte</div></div>
  <div class="stat-card blue"><div class="value">{date_accuracy:.1f}%</div><div class="label">Kuupäeva täpsus</div></div>
  <div class="stat-card blue"><div class="value">{product_accuracy:.1f}%</div><div class="label">Toote täpsus</div></div>
  <div class="stat-card"><div class="value">{avg_processing:.0f}ms</div><div class="label">Kesk. töötlusaeg</div></div>
  <div class="stat-card"><div class="value">{avg_ocr:.0f}ms</div><div class="label">Kesk. OCR aeg</div></div>
</div>

<div class="section">
  <h2>Anomaaliate jaotus</h2>
  {anomaly_bars if anomaly_bars else '<p>Anomaaliaid ei leitud.</p>'}
</div>

<h2>Taktide detail</h2>
<table>
<thead>
<tr><th></th><th>Takt</th><th>Aeg</th><th>Triipkood</th><th>Toode</th><th>Oodatav kp</th><th>Tuvastatud kp</th><th>Tuvastatud tooted</th><th>Aeg (ms)</th><th>Anomaaliad</th></tr>
</thead>
<tbody>
{''.join(table_rows)}
</tbody>
</table>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
