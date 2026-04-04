import cv2
import os
import json
from datetime import datetime

# --- KONFIGURATSIOON ---
capture_date = datetime(2026, 2, 14)
INPUT_FOLDER = "salami/full_frames"  # Võid muuta vastavalt testitavale tootele

if not os.path.exists(INPUT_FOLDER):
    print(f"Viga: Sisendkausta '{INPUT_FOLDER}' ei eksisteeri.")
    exit()

image_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
image_files.sort()

# Alamkaustad erinevatele aladele (Need on sulle ette loodud)
SUBS = ["individual_products", "date", "label1", "label2", "product_area"]
base_path = os.path.dirname(INPUT_FOLDER)
for sub in SUBS:
    os.makedirs(os.path.join(base_path, sub), exist_ok=True)

# Vastavustabel
FOLDER_TO_EAN = {
    "rulaad": "4740574008052",
    "kalkun": "4740574090002",
    "veis": "4740574081192",
    "salami": "4740574009820"
}

folder_key = INPUT_FOLDER.split('/')[0]
ean = FOLDER_TO_EAN.get(folder_key)

with open('barcode_data.json', 'r') as f:
    barcode_data = json.load(f)

current_product = barcode_data.get(ean)
if not current_product:
    print(f"Viga: Tooteinfot EAN {ean} jaoks ei leitud.")
    exit()

# Kontrollime, et vajalikud väljad on JSON-is olemas (Sinu ülesanne on need seal täita!)
required_keys = ["rois", "date_area", "label1_below", "label2_above", "product_area_between"]
if not all(k in current_product for k in required_keys):
    print(f"Viga: Tootel {ean} puuduvad vajalikud koordinaadid JSON failis.")
    exit()

print(f"Alustame toote '{current_product.get('ITEMNAME')}' detailset tükeldamist...")

for filename in image_files:
    base_name = os.path.splitext(filename)[0]
    file_path = os.path.join(INPUT_FOLDER, filename)
    frame = cv2.imread(file_path)
    if frame is None: continue

    # TODO: Ülesanne 2.1 - Too siia oma lahendus Ülesandest 1
    # Sul on vaja koodi, mis lõikab täiskaadrilt välja 4 pakendit, 
    # keerab need õiget pidi ja viib ühtsele suurusele (resize).
    # Tulemuseks peaks olema list (nt 'temp_slices'), mis sisaldab 4 pilti.


    # TODO: Ülesanne 2.2 - Detailne tükeldamine (Slicing)
    # Käi läbi kõik normaliseeritud viilud ja lõika välja spetsiifilised alad.
    # Kasuta koordinaate 'current_product' sõnastikust:
    # 1. 'date_area' -> lõika kuupäeva ala ja salvesta kausta 'date'
    # 2. 'label1_below' -> lõika alumine silt (kõik mis jääb sellest piirist allapoole) -> kaust 'label1'
    # 3. 'label2_above' -> lõika ülemine silt (kõik mis jääb sellest piirist ülespoole) -> kaust 'label2'
    # 4. 'product_area_between' -> lõika ala kahe antud Y-koordinaadi vahel -> kaust 'product_area'
    
    # NB! Enne salvestamist kontrolli alati, kas lõigatud pilt ei ole tühi (crop.size > 0).
    
    # Näide kuupäeva salvestamiseks:
    # s_idx = i + 1
    # cv2.imwrite(os.path.join(base_path, "date", f"{base_name}_s{s_idx}_date.png"), date_crop)


    # TODO: Ülesanne 2.3 - JSON faili tuunimine
    # Ava 'barcode_data.json' ja muuda väärtusi nii, et lõiked oleksid täpsed.
    # See on iteratiivne protsess - muuda väärtust, jooksuta koodi, vaata tulemust kaustas.


    print(f"{filename} -> Detailid eraldatud.")

print("\nÜlesanne 2 lõpetatud.")
