# Kodutöö: KODUTÖÖ MUUTUS
On vaja teha lihtsalt seminar 5 ülesanne 2. Vt seminar 5 kausta.

**VASTA KÜSIMUSTELE MOODLE TESTI KAUDU**


##Ülesanne 2: Pilvepõhiste VLM-mudelite (OpenRouter) võrdlus ja kuluanalüüs

Selles ülesandes kasutame OpenRouteri platvormi kaudu ligipääsetavaid Vision Language mudeleid (VLM) kuupäevade tuvastamiseks ja analüüsime nende kulusid. See skript testib ühte OpenRouteri mudelit korraga kõigi tootekataloogide lõikes.

**Ettevalmistus:**
1.  **OpenRouter API võti:** Tuleta meelde oma OpenRouteri API võti.
2.  **Määra API võti:** Asenda `OPENROUTER_API_KEY` muutuja failis `yl2_OCR.py` oma API võtmega või määra see keskkonnamuutujana.
3.  **Vali VLM mudel:** Mine OpenRouteri mudelite lehele, filtreeri "text+image to text" mudelite järgi ja reasta need hinna järgi (odavaimad enne). Vali mõni mudel ja asenda see `OPENROUTER_MODEL` muutuja väärtusega.

**Töövoog:**
1.  Failis `yl2_OCR.py` kasutatakse `helpers.py` failis defineeritud `OpenRouterOCR` klassi, mille meetod `tuvastus_openrouter()` teostab tuvastuse, saates pildi OpenRouteri API-le koos spetsiifilise promptiga kuupäeva ekstraheerimiseks. 
2.  Lisaks tavalisele statistikale kogub skript ka OpenRouteri API kasutusstatistikat (tokenid, maksumus).
3.  Skript arvutab ka hinnangulise päevase kulu, eeldades 16-tunnist tööpäeva, ühte takti iga 7 sekundi järel ja 8 kuupäeva-ala tuvastamist taktis.

**Analüüs:**
-   **Tuvastusstatistika:** Võrdle VLM-i tuvastuse täpsust ja kiirust kohalike mudelitega.
-   **API kasutus:** Mitu tokenit kulus ühe pildi kohta? Mis oli ühe pildi tuvastamise maksumus?
-   **Päevane kulu:** Kui palju maksaks selle mudeli kasutamine 16 tundi päevas antud töökoormuse juures?

**Arutelu:**
-   Kas VLM-mudelid pakuvad paremat täpsust kui kohalikud mudelid? Mis hinnaga?
-   Kas VLM-i kasutamine on reaalajas süsteemi jaoks majanduslikult otstarbekas?
-   Millised on VLM-ide eelised ja puudused võrreldes kohalike OCR-lahendustega?
-   Kuidas mõjutab prompti kvaliteet VLM-i tulemusi?
-   Mõtle kokkuvõtele kõigi nelja mudeli (EasyOCR, PARSeq, PaddleOCR, OpenRouter VLM) tulemustest. Võrdle nende tugevusi ja nõrkusi täpsuse, kiiruse ja kulude osas. Tee järeldused, milline lahendus sobiks kõige paremini antud ülesande jaoks ja miks.
