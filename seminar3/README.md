# Ülesanne 1: Triipkoodide lugemine failidest

Selle harjutuse eesmärk on õppida tundma **Dynamsoft Barcode Reader SDK**-d. Kasutame eelmises kodutöös liikumistuvastusega salvestatud pildimaterjali.

## Juhised
1. Ava fail `yl1_triipkoodi_lugemine.py`.
2. Täida **ÜLESANNE 1.1**: Vali õige kaust (nt `kalkun`) ja failinime juur (nt `motion_capture_`), et programm leiaks üles salvestatud pildid.
3. Täida **ÜLESANNE 1.2**: Seadista `router` kasutama malli failist `minimal_template.json`.
4. Täida **ÜLESANNE 1.3**:
    *   Mõõda tuvastamisele kuluvat aega millisekundites (`time.perf_counter()`).
    *   Kasuta `router.capture(failitee, "ReadBarcodes_Default")` funktsiooni.
    *   Loo tsükkel üle leitud elementide (`get_items()`).
    *   Prindi välja failinimi, aeg, leitud koodide arv ja sisu.


# Ülesanne 2: Tooteinfo ja säilivusaeg

Nüüd, kus me oskame koode lugeda, peame need siduma päris andmetega.

## Juhised
1. Kasuta faili `yl2_toote_info.py`.
2. Täida **ÜLESANNE 2.1**: Loe sisse `barcode_data.json`. Veendu, et oskad JSON-i Pythoni sõnastikuks (dict) teisendada.
3. Täida **ÜLESANNE 2.2**:
    *   Leia koodile vastav tekstiline tootenimi.
    *   Kasuta `datetime` ja `timedelta` mooduleid, et arvutada säilivusaeg.
    *   Kui triipkoodi andmebaasist ei leita, kuva "Tundmatu toode".
    *   Kuva iga takti kohta EAN13 kood, tootenimi ja säilivusaeg.

## Andmebaasi näidis (barcode_data.json)
```json
{ "4740113054175": { "name": "Kalkuni kintsuliha", "expiry_duration": 7 } }
```
