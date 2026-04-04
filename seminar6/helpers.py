import base64
import io
import os
import re
import threading
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

    lines = [
        "+-----------------+-----------------+",
        f"| {tl_date} | {tr_date} |",
        "+-----------------+-----------------+",
        f"| {bl_date} | {br_date} |",
        "+-----------------+-----------------+",
    ]
    if include_context:
        lines = [
            "--- Kuupaeva tuvastamise tulemused (2x2 ruudustik) ---",
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
    }


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
    raw_date_texts: List[Optional[str]],
    expected_expiry_str: str,
    report_notes: List[str],
    processing_elapsed_ms: float,
    barcode_elapsed_ms: float,
    slicing_elapsed_ms: float,
    ocr_elapsed_ms: float,
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
            format_date_grid(raw_date_texts, expected_expiry_str, include_context=False),
            f"Tootlemise koguaeg (ilma piltide salvestamiseta): {format_ms(processing_elapsed_ms)}",
            f"Triipkoodi lugemise aeg: {format_ms(barcode_elapsed_ms)}",
            f"Loikamise aeg: {format_ms(slicing_elapsed_ms)}",
            f"Kuupaeva lugemise aeg: {format_ms(ocr_elapsed_ms)}",
            f"Piltide salvestamise aeg: {format_ms(save_elapsed_ms)}",
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
