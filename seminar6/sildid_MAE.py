import cv2
import numpy as np
import os
import matplotlib.pyplot as plt
import time

product = "rulaad"
label = "label1"
rescale_factor = 1.0


def mean_absolute_error_image(path1: str, path2: str) -> tuple:
    start_time = time.perf_counter()
    
    img1 = cv2.imread(path1, cv2.IMREAD_UNCHANGED)
    img2 = cv2.imread(path2, cv2.IMREAD_UNCHANGED)

    if rescale_factor != 1.0:
        img1 = cv2.resize(img1, (int(img1.shape[1] * rescale_factor), int(img1.shape[0] * rescale_factor)), interpolation=cv2.INTER_AREA)
        img2 = cv2.resize(img2, (int(img2.shape[1] * rescale_factor), int(img2.shape[0] * rescale_factor)), interpolation=cv2.INTER_AREA)

    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]), interpolation=cv2.INTER_AREA)

    mae_value = float(np.mean(np.abs(img1.astype(np.float64) - img2.astype(np.float64))))
    end_time = time.perf_counter()
    
    return mae_value, end_time - start_time


def save_mae_histogram(mae_good_values, mae_bad_values, product, label, rescale_factor, out_dir='results', bins=30):
    if not (mae_good_values or mae_bad_values):
        print("No MAE values to plot")
        return

    os.makedirs(out_dir, exist_ok=True)
    plt.figure(figsize=(8, 5))
    if mae_good_values:
        plt.hist(mae_good_values, bins=bins, color='green', alpha=0.7, label='good')
    if mae_bad_values:
        plt.hist(mae_bad_values, bins=bins, color='red', alpha=0.7, label='bad')

    plt.xlabel('MAE')
    plt.ylabel('Count')
    plt.title('Good vs Bad MAE')
    plt.legend()
    plt.tight_layout()
    out_path = os.path.join(out_dir, f'mae_histogram_{product}_{label}_{rescale_factor}.png')
    plt.savefig(out_path)
    plt.close()
    print(f"Saved histogram: {out_path}")


good_dir = f"{product}/{label}"
bad_dir = f"no_label/{label}"

good_images = sorted([f for f in os.listdir(good_dir) if f.endswith('.png')])
bad_images = sorted([f for f in os.listdir(bad_dir) if f.endswith('.png')])

mae_good = []
mae_bad = []
calculation_times = []

if good_images:
    template_path = os.path.join(good_dir, good_images[0])

    for img in good_images[1:]:
        img_path = os.path.join(good_dir, img)
        mae_value, calc_time = mean_absolute_error_image(template_path, img_path)
        mae_good.append(mae_value)
        calculation_times.append(calc_time)

    for img in bad_images:
        img_path = os.path.join(bad_dir, img)
        mae_value, calc_time = mean_absolute_error_image(template_path, img_path)
        mae_bad.append(mae_value)
        calculation_times.append(calc_time)


print(f"MAE good: {len(mae_good)} values")
print(f"MAE bad: {len(mae_bad)} values")
save_mae_histogram(mae_good, mae_bad, product, label, rescale_factor)

if calculation_times:
    avg_time_ms = (sum(calculation_times) / len(calculation_times)) * 1000
    print(f"Average calculation time: {avg_time_ms:.2f} ms")
