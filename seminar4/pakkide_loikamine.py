"""
Seminar 4: Toodete väljalõikamine ja ROI-de eraldamine

1) Lõikab 4K kaadrist (3840x2160) välja 4 individuaalset tootepakki (2x2 ruudustik)
2) Iga paki pealt lõikab välja:
   - kuupäeva-ala (date_region)
   - alumine silt (bottom_label)
   - ülemine silt (top_label)
   - tooteaken (product_window)

Koordinaadid salvestatakse JSON faili.
Väljalõigatud alad salvestatakse pildifailidena.
"""

import cv2
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ============================================================
# KONFIGURATSIOON – koordinaadid (pikslites, 3840×2160 pildil)
# ============================================================

# Iga paki ligikaudne keskpunkt ja suurus täispildil
# Formaat: (x_algus, y_algus, laius, kõrgus)
PACK_REGIONS = {
    "pakk_1_yleval_vasakul": (30,   20, 1870, 1050),
    "pakk_2_yleval_paremal": (1940, 20, 1870, 1050),
    "pakk_3_all_vasakul":    (30,   1090, 1870, 1050),
    "pakk_4_all_paremal":    (1940, 1090, 1870, 1050),
}

# ROI-d iga väljalõigatud paki sees (suhtelised koordinaadid paki suhtes)
# Need on ligikaudsed – tuleb kohandada vastavalt tegelikele piltidele!
# Formaat: (x_algus, y_algus, laius, kõrgus) pikslites paki-siseselt
ROI_REGIONS = {
    "kuupaev":        (0,   680, 250, 200),    # kuupäeva-ala (vasakul, kuupäeva kleebis)
    "alumine_silt":   (0,   780, 400, 270),    # alumine silt (vasakul all, triipkood + info)
    "ylemine_silt":   (0,   0,   400, 300),    # ülemine silt (vasakul üleval, tooteinfo)
    "tooteaken":      (350, 50,  850, 950),    # tooteaken (keskel, läbi kile nähtav toode)
}


def load_config(config_path):
    """Laeb koordinaadid JSON failist, kui see on olemas."""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"Koordinaadid laetud failist: {config_path}")
        return data
    return None


def save_config(config_path, pack_regions, roi_regions):
    """Salvestab koordinaadid JSON faili."""
    data = {
        "pack_regions": pack_regions,
        "roi_regions": roi_regions,
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Koordinaadid salvestatud: {config_path}")


def crop_region(image, region):
    """Lõikab piirkonna välja. region = (x, y, w, h)."""
    x, y, w, h = region
    # Piira pildi äärte sisse
    img_h, img_w = image.shape[:2]
    x = max(0, x)
    y = max(0, y)
    x2 = min(img_w, x + w)
    y2 = min(img_h, y + h)
    return image[y:y2, x:x2]


def process_frame(image_path, output_dir, pack_regions, roi_regions):
    """
    Töötleb ühe kaadri:
    1) Lõikab välja 4 pakki
    2) Iga paki pealt lõikab välja ROI-d
    3) Salvestab kõik pildifailidena
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"Ei suutnud lugeda: {image_path}")
        return

    frame_name = os.path.splitext(os.path.basename(image_path))[0]
    frame_dir = os.path.join(output_dir, frame_name)
    os.makedirs(frame_dir, exist_ok=True)

    print(f"\nTöötlen: {image_path}  (suurus: {img.shape[1]}x{img.shape[0]})")

    for pack_name, pack_rect in pack_regions.items():
        # Lõika pakk välja
        pack_rect_tuple = tuple(pack_rect) if isinstance(pack_rect, list) else pack_rect
        pack_img = crop_region(img, pack_rect_tuple)

        # Salvesta pakk
        pack_path = os.path.join(frame_dir, f"{pack_name}.jpg")
        cv2.imwrite(pack_path, pack_img)
        print(f"  {pack_name}: {pack_img.shape[1]}x{pack_img.shape[0]} -> {pack_path}")

        # Lõika ROI-d paki seest
        for roi_name, roi_rect in roi_regions.items():
            roi_rect_tuple = tuple(roi_rect) if isinstance(roi_rect, list) else roi_rect
            roi_img = crop_region(pack_img, roi_rect_tuple)

            roi_path = os.path.join(frame_dir, f"{pack_name}_{roi_name}.jpg")
            cv2.imwrite(roi_path, roi_img)
            print(f"    {roi_name}: {roi_img.shape[1]}x{roi_img.shape[0]}")


def create_overview_grid(image_path, output_path, pack_regions, roi_regions):
    """
    Loob ülevaatepildi mis näitab:
    - Graafik 1: Originaalpilt koos pakkide piirjoontega
    - Graafik 2: Kõik 4 pakki ROI piirjoontega
    """
    img = cv2.imread(image_path)
    if img is None:
        return
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    fig, axes = plt.subplots(1, 2, figsize=(20, 8))
    fig.suptitle("Pakkide ja ROI-de ülevaade", fontsize=16)

    # --- Graafik 1: originaalpilt + pakkide piirjooned ---
    ax1 = axes[0]
    ax1.imshow(img_rgb)
    ax1.set_title("Originaalpilt + pakkide piirjooned")
    colors_pack = ["red", "blue", "green", "orange"]
    for i, (pack_name, rect) in enumerate(pack_regions.items()):
        r = tuple(rect) if isinstance(rect, list) else rect
        x, y, w, h = r
        rect_patch = plt.Rectangle((x, y), w, h, linewidth=2,
                                   edgecolor=colors_pack[i], facecolor="none")
        ax1.add_patch(rect_patch)
        ax1.text(x + 5, y + 30, pack_name, color=colors_pack[i],
                 fontsize=7, fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7))
    ax1.axis("off")

    # --- Graafik 2: 4 pakki ROI-dega ---
    ax2 = axes[1]
    ax2.set_title("Pakkide ROI-d")
    colors_roi = {"kuupaev": "yellow", "alumine_silt": "cyan",
                  "ylemine_silt": "magenta", "tooteaken": "lime"}

    # Koosta 2x2 ruudustik pakkidest
    pack_items = list(pack_regions.items())
    pack_images = []
    for pack_name, rect in pack_items:
        r = tuple(rect) if isinstance(rect, list) else rect
        pack_img = crop_region(img_rgb, r)
        pack_images.append((pack_name, pack_img))

    # Normaliseeri suurused
    target_h = 500
    target_w = 900
    grid_img = np.zeros((target_h * 2, target_w * 2, 3), dtype=np.uint8)

    positions = [(0, 0), (0, target_w), (target_h, 0), (target_h, target_w)]
    for idx, (pack_name, pimg) in enumerate(pack_images):
        resized = cv2.resize(pimg, (target_w, target_h))
        gy, gx = positions[idx]
        grid_img[gy:gy+target_h, gx:gx+target_w] = resized

    ax2.imshow(grid_img)

    # Joonista ROI kastid iga paki peale ruudustikus
    for idx, (pack_name, pimg) in enumerate(pack_images):
        gy, gx = positions[idx]
        orig_h, orig_w = pimg.shape[:2]
        sx = target_w / orig_w
        sy = target_h / orig_h

        for roi_name, roi_rect in roi_regions.items():
            rr = tuple(roi_rect) if isinstance(roi_rect, list) else roi_rect
            rx, ry, rw, rh = rr
            rect_patch = plt.Rectangle(
                (gx + rx * sx, gy + ry * sy), rw * sx, rh * sy,
                linewidth=1.5, edgecolor=colors_roi.get(roi_name, "white"),
                facecolor="none"
            )
            ax2.add_patch(rect_patch)
            if idx == 0:  # Legend ainult esimese paki juures
                ax2.text(gx + rx * sx, gy + ry * sy - 5, roi_name,
                         color=colors_roi.get(roi_name, "white"), fontsize=6,
                         bbox=dict(boxstyle="round,pad=0.1", facecolor="black", alpha=0.5))
    ax2.axis("off")

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor="none", edgecolor=c, label=n)
                       for n, c in colors_roi.items()]
    ax2.legend(handles=legend_elements, loc="lower right", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\nÜlevaategraafik salvestatud: {output_path}")


def save_overview_text(output_path, pack_regions, roi_regions):
    """
    Salvestab 2 graafikut kirjeldava tekstifaili:
    - Graafik 1: pakkide asukohad
    - Graafik 2: ROI-de asukohad
    """
    lines = []
    lines.append("=" * 60)
    lines.append("SEMINAR 4: PAKKIDE JA ROI-DE ÜLEVAADE")
    lines.append("=" * 60)
    lines.append("")

    lines.append("GRAAFIK 1: Pakkide asukohad originaalpildil (3840x2160)")
    lines.append("-" * 60)
    lines.append(f"{'Pakk':<30} {'X':>6} {'Y':>6} {'Laius':>6} {'Kõrgus':>6}")
    lines.append("-" * 60)
    for name, rect in pack_regions.items():
        r = tuple(rect) if isinstance(rect, list) else rect
        lines.append(f"{name:<30} {r[0]:>6} {r[1]:>6} {r[2]:>6} {r[3]:>6}")
    lines.append("")

    lines.append("GRAAFIK 2: ROI-de asukohad iga paki sees")
    lines.append("-" * 60)
    lines.append(f"{'ROI ala':<20} {'X':>6} {'Y':>6} {'Laius':>6} {'Kõrgus':>6}")
    lines.append("-" * 60)
    for name, rect in roi_regions.items():
        r = tuple(rect) if isinstance(rect, list) else rect
        lines.append(f"{name:<20} {r[0]:>6} {r[1]:>6} {r[2]:>6} {r[3]:>6}")
    lines.append("")

    lines.append("METOODIKA")
    lines.append("-" * 60)
    lines.append("1) Mõõdetakse iga paki keskmine asukoht 4K pildil.")
    lines.append("   Koordinaadid salvestatakse JSON faili.")
    lines.append("2) Iga paki pealt lõigatakse välja 4 ROI-d:")
    lines.append("   - kuupaev:       kuupäeva-ala (alumine parempoolne nurk)")
    lines.append("   - alumine_silt:  alumine silt (paremal all)")
    lines.append("   - ylemine_silt:  ülemine silt (paremal üleval)")
    lines.append("   - tooteaken:     tooteaken (vasakul, läbi kile nähtav toode)")
    lines.append("3) Kõik koordinaadid on JSON failis, et neid oleks lihtne kohandada.")
    lines.append("")
    lines.append("=" * 60)

    text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Tekstifail salvestatud: {output_path}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    # Teed
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
    RULAAD_DIR = os.path.join(PROJECT_DIR, "rulaad")
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
    CONFIG_PATH = os.path.join(SCRIPT_DIR, "koordinaadid.json")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Laadi või salvesta koordinaadid
    config = load_config(CONFIG_PATH)
    if config:
        pack_regions = config["pack_regions"]
        roi_regions = config["roi_regions"]
    else:
        pack_regions = PACK_REGIONS
        roi_regions = ROI_REGIONS
        save_config(CONFIG_PATH, pack_regions, roi_regions)

    # Vali üks näidiskaader töötlemiseks
    # (saab muuta, et töötleks kõiki motion_frame faile)
    sample_frames = [
        os.path.join(RULAAD_DIR, "motion_frame_0001.jpg"),
        os.path.join(RULAAD_DIR, "motion_frame_0010.jpg"),
    ]

    for frame_path in sample_frames:
        if os.path.exists(frame_path):
            process_frame(frame_path, OUTPUT_DIR, pack_regions, roi_regions)

    # Loo ülevaategraafik esimesest olemasolevast kaadrist
    for frame_path in sample_frames:
        if os.path.exists(frame_path):
            overview_img = os.path.join(SCRIPT_DIR, "ylevaade_graafikud.png")
            create_overview_grid(frame_path, overview_img, pack_regions, roi_regions)
            break

    # Salvesta tekstifail kahe graafiku kirjeldusega
    text_path = os.path.join(SCRIPT_DIR, "graafikud_kokkuvote.txt")
    save_overview_text(text_path, pack_regions, roi_regions)

    print("\nValmis!")
