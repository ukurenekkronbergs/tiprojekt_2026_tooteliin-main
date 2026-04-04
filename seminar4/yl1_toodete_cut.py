import cv2
import os
import json
from datetime import datetime

# --- KONFIGURATSIOON (Eelmistest ülesannetest tuttav) ---
INPUT_FOLDER = "rulaad/full_frames"  # Kaust, kus asuvad täiskaadrid
OUTPUT_SUBFOLDER = "individual_products"
capture_date = datetime(2026, 2, 14)

if not os.path.exists(INPUT_FOLDER):
    print(f"Viga: Sisendkausta '{INPUT_FOLDER}' ei eksisteeri.")
    exit()

image_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
image_files.sort()
print(f"Leiti {len(image_files)} pilti töötlemiseks.")

# Loome väljundkausta
output_base = os.path.join(os.path.dirname(INPUT_FOLDER), OUTPUT_SUBFOLDER)
os.makedirs(output_base, exist_ok=True)

# Vastavustabel kausta nime ja EAN koodi vahel
FOLDER_TO_EAN = {
    "rulaad": "4740574008052",
    "kalkun": "4740574090002",
    "veis": "4740574081192",
    "salami": "4740574009820"
}

# Leiame õige toote info kausta nime järgi
folder_key = INPUT_FOLDER.split('/')[0]
ean = FOLDER_TO_EAN.get(folder_key)

with open('barcode_data.json', 'r') as f:
    barcode_data = json.load(f)

current_product = barcode_data.get(ean)
if not current_product:
    print(f"Viga: Tooteinfot EAN {ean} jaoks ei leitud.")
    exit()

current_product["_ean"] = ean

# --- ÜLESANNE 1: Toodete lõikamine ja normaliseerimine ---

for filename in image_files:
    file_path = os.path.join(INPUT_FOLDER, filename)
    frame = cv2.imread(file_path)
    if frame is None: continue
    
    base_name = os.path.splitext(filename)[0]
    temp_slices = []

    # TODO: Ülesanne 1.1 - Pakendite väljalõikamine ja ettevalmistus
    # 1. Käi läbi kõik pakendid 'current_product["rois"]' sõnastikus.
    # 2. Lõika täiskaadrilt välja vastavad koordinaadid (ROI).
    # 3. Kuna tooted on konveieril külili, siis roteeri iga väljalõiget 90 kraadi vastupäeva (cv2.ROTATE_90_COUNTERCLOCKWISE).
    # 4. Lisa roteeritud pildid ajutisse listi 'temp_slices'.
    # NB! Selles sammus pead tõenäoliselt parandama koordinaate 'barcode_data.json' failis, 
    # et pildid saaksid korrektselt lõigatud.


    # TODO: Ülesanne 1.2 - Piltide normaliseerimine (Resize)
    # 1. Leia 'temp_slices' nimekirjast suurim kõrgus ja laius.
    # 2. Skaleeri (cv2.resize) kõik nimekirjas olevad pildid sellele maksimaalsele suurusele.


    # TODO: Ülesanne 1.3 - Salvestamine
    # 1. Salvesta iga toote pilt eraldi .png failina 'individual_products' kausta.
    # 2. Failinimi peab olema unikaalne (nt frame_0001_slice_1.png).


    print(f"{filename} -> Tükeldatud ja salvestatud.")

print("\nÜlesanne 1 lõpetatud.")
