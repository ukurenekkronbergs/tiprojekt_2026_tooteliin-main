import cv2
import os
import json
import time
from datetime import datetime, timedelta
from dynamsoft_barcode_reader_bundle import *

# Dynamsoft Litsents
DYNAMSOFT_LICENSE = "t0084YQEAAIUx4hU4EqEOu9FaT9GprNtmXmbGA7IcvmG7V7l1yrR4WjV1JWPPrLuJoJN4HXVvqroIag2MeSFUJlbpkh0vhl8/Nrk3lffN1GzB7BvBtkl5"
LicenseManager.init_license(DYNAMSOFT_LICENSE)

# Initsialiseerime triipkoodi lugeja (Router), sätime seaded nii nagu Demo alusel otsustasime
router = CaptureVisionRouter()

template_path = "minimal_template.json"
if not os.path.exists(template_path):
    print(f"Error: Could not find the JSON template at '{template_path}'")
    exit()

err_code, err_msg = router.init_settings_from_file(template_path)
if err_code != EnumErrorCode.EC_OK:
    print(f"Failed to load JSON settings from file: {err_msg}")
    exit()

    

# --- ÜLESANNE 2.1: JSON Andmete lugemine ---
# Meil on fail 'barcode_data.json', kus on info toodete kohta.
# TODO: Loe sisse JSON fail ja salvesta see muutujasse 'product_db'
product_db = {}

# Märgime video salvestamise ajaks päeva, mil see tegelikult lindistati 14.02.2026  
capture_date = datetime(2026, 2, 14)

folder_path = "kalkun" 
file_prefix = "motion_capture_"
files = sorted([f for f in os.listdir(folder_path) if f.startswith(file_prefix) and f.endswith(".jpg")])

print(f"Töötlen tooteid kuupäevaga: {capture_date.strftime('%d.%m.%Y')}")

for filename in files:
    full_path = os.path.join(folder_path, filename)
    
    # --- TODO: Mõõda tuvastamise aega ja kasuta "ReadBarcodes_Default" malli ---
    # Pane siia ülesanne 1 lahendus 

    
    if not items:
        print(f"[{filename}] Triipkoodi ei leitud.")
        continue

    for item in items:
        if item.get_type() == EnumCapturedResultItemType.CRIT_BARCODE:
            ean = item.get_text()
            
            # --- ÜLESANNE 2.2: Toote otsing ja säilivusaeg ---
            # Sinu ülesanne on:
            # 1. Otsida 'product_db' sõnastikust toodet EAN koodi järgi.
            # 2. Kui toode leiti, võta selle 'name' ja 'expiry_duration' (päevades).
            # 3. Arvuta säilivusaeg: capture_date + expiry_duration.
            # 4. Prindi välja tulemus viisakalt.
            
            # TODO: Sinu kood siia
            
            # Näidisväljund:
            # [motion_capture_0001.jpg] TOODE: Kalkuni kintsuliha | SÄILIB KUNI: 25.05.2025
            
            pass