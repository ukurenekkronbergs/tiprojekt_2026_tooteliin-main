# Kodutöö: RTSP voo tükeldamine reaalajas

Selles ülesandes rakendame eelmises seminaris õpitud piltide tükeldamise loogikat reaalajas tööstuslikule videovoole. Erinevalt eelmisest korrast, kus töötlesime kaustas olevaid pilte, peab see skript suutma toime tulla "elusa" andmevooga, kus tooted liiguvad konveieril.

## Ülesanne 1: RTSP Slicing (yl1_rtsp_slicing.py)

Sinu ülesandeks on täita koodis lõik (alates kommentaarist `# Siit algab kaadri juppideks lõikamise loogika`), mis tegeleb tuvastatud kaadri tükeldamisega.

### Eesmärk
Kui süsteem tuvastab liikumise ja triipkoodi (või kasutab eelmist teadaolevat konteksti), tuleb täiskaader jagada standardseteks tootepiltideks ja detailseteks aladeks.

### Sinu sammud:
1.  **Pakendite eraldamine:** Lõika täiskaadrilt välja 4 pakendit (`current_product["rois"]`), roteeri need 90 kraadi vastupäeva ning vii need ühtsele suurusele (normaliseerimine).
2.  **Detailide eraldamine:** Iga normaliseeritud pakendi pealt lõika välja 4 huvipakkuvat ala: kuupäev, ülemine silt, alumine silt ja toote sisu ala.
3.  **Tingimuslik salvestamine:** Salvestamine peab toimuma **ainult siis**, kui `DEBUG_MODE` on seadistatud väärtusele `True`.
4.  **Jõudluse mõõtmine:** Mõõda `time.perf_counter()` abil, kui kaua võtab aega piltide töötlemine enne salvestamist ja kui kaua kettale salvestamine, ja prindi need tulemused terminali.

### Oluline märkus:
Kuna tegemist on reaalajas süsteemiga, peab kood olema efektiivne. 

**Failid, mida vajad:**
*   `yl1_rtsp_slicing.py` – Põhikood, kuhu kirjutad lahenduse.
*   `helpers.py` – Sisaldab abifunktsioone liikumise ja rohelise ekraani tuvastamiseks.
*   `minimal_template.json` - Sisaldab barcode readeri seadistust
*   `barcode_data.json` – Sisaldab toodete koordinaate. (uuenda alade asukohti)

