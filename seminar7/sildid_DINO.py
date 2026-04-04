from pathlib import Path
import time

import cv2
import matplotlib
matplotlib.use('Agg')  # Must be called before importing plt
import matplotlib.pyplot as plt
import numpy as np
import torch
from transformers import AutoImageProcessor, AutoModel


product = "rulaad"
label = "label1"
batch_size = 16
model_name = "facebook/dinov2-small"

base_dir = Path(__file__).resolve().parent
good_dir = base_dir / ".." / "seminar6" / product / label
bad_dir = base_dir / ".." / "seminar6" / "no_label" / label


def load_rgb_batch(image_paths: list[Path]) -> list[np.ndarray]:
    return [cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB) for path in image_paths]


def embed_images(image_paths: list[Path], processor, model, batch_size: int) -> tuple[np.ndarray, float]:
    all_embeddings = []
    start_time = time.perf_counter()

    for start in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[start:start + batch_size]
        batch_images = load_rgb_batch(batch_paths)
        inputs = processor(images=batch_images, return_tensors="pt")

        with torch.inference_mode():
            outputs = model(**inputs)

        embeddings = outputs.last_hidden_state[:, 0]
        embeddings = torch.nn.functional.normalize(embeddings, dim=1)
        all_embeddings.append(embeddings.cpu().numpy())

    elapsed = time.perf_counter() - start_time
    return np.concatenate(all_embeddings, axis=0), elapsed


def cosine_distance(reference_embedding: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
    return 1.0 - embeddings @ reference_embedding


def save_histogram(good_values, bad_values, product, label, out_dir="results", bins=30):
    Path(out_dir).mkdir(exist_ok=True)
    plt.figure(figsize=(8, 5))
    plt.hist(good_values, bins=bins, alpha=0.7, label="good", color="green")
    plt.hist(bad_values, bins=bins, alpha=0.7, label="bad", color="red")
    plt.xlabel("Cosine distance")
    plt.ylabel("Count")
    plt.title(f"DINO: {product} / {label}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(Path(out_dir) / f"dino_histogram_{product}_{label}.png")
    plt.close()


processor = AutoImageProcessor.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name).to("cpu")
model.eval()

good_images = sorted(good_dir.glob("*.png"))
bad_images = sorted(bad_dir.glob("*.png"))

template_path = good_images[0]
same_label_paths = good_images[1:]

reference_embedding, reference_time = embed_images([template_path], processor, model, batch_size=1)
good_embeddings, good_time = embed_images(same_label_paths, processor, model, batch_size)
bad_embeddings, bad_time = embed_images(bad_images, processor, model, batch_size)

good_distances = cosine_distance(reference_embedding[0], good_embeddings)
bad_distances = cosine_distance(reference_embedding[0], bad_embeddings)

save_histogram(good_distances, bad_distances, product, label)

print(f"DINO good: {len(good_distances)}")
print(f"DINO bad: {len(bad_distances)}")
print(f"Reference embedding time: {reference_time:.3f} s")
print(f"Good batch time: {good_time:.3f} s")
print(f"Bad batch time: {bad_time:.3f} s")
print(f"Average DINO time per image: {(reference_time + good_time + bad_time) / (1 + len(same_label_paths) + len(bad_images)):.4f} s")
