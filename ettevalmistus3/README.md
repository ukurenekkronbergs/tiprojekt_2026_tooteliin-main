# Kodutöö: Liikumise tuvastamine ja andmete analüüs

Selle ülesande eesmärk on simuleerida tööstuslikku kaamerasüsteemi, mis peab tegema tootest pildi täpselt sel hetkel, kui see on konveieril peatunud.

## Ülesande sisu

Kasutame faili `RTSP_liikumine.py`. Sinu ülesandeks on täiendada kahte osa:

### 1. Muutuse mõõtmise funktsioon (`measure_change`)
Kahe kaadri erinevuse leidmiseks kasuta näiteks **MAE (Mean Absolute Error)** meetodit.
*   Mõtle kuidas arvutuslikku kulu vähendada: halltoonides pilt (`cv2.cvtColor`) väiksem resolutsiooni (`cv2.resize`).
*   Leia pikslite vahede keskmine: `np.mean(cv2.absdiff(pilt1, pilt2))`.
*   **Lisa ajamõõtmine:** Kasuta `time.perf_counter()` funktsiooni, et mõõta, kui mitu millisekundit kulub ühel selle funktsiooni välja kutsumisel. Prindi see info terminali.

### 2. Sündmuspõhine salvestamine
Erinevalt eelmisest ülesandest ei salvesta me pilte enam kindla ajavahemiku tagant, vaid reageerime liikumisele.
*   Kui `measure_change` tagastab väärtuse, mis on suurem kui `MOTION_THRESHOLD`, märgi liikumine alanuks.
*   Kuna kaamera on udune liikumise ajal ja kohe selle järel, pead ootama `CAPTURE_DELAY` sekundit (nt 3 sek), enne kui teed tegeliku pildi.
*   Pärast pildi salvestamist peab süsteem olema valmis järgmiseks tooteks (reseti `motion_triggered` olek).

## 3. Analüüs ja esitamine

1.  **Graafik:** Programm peab genereerima töö lõpus faili `liikumise_graafik.png`, mis kuvab measure_change väljundid üle aja. Analüüsi seda graafikut.
    *   Q1: Kas liikumise "tõusud" on selgelt eristatavad?
    *   Q2: Kas sinu valitud lävend (`MOTION_THRESHOLD`) on sobiv või peaks seda muutma?
2.  **Taktituvastus:** loe kokku, mitu korda ületas graafik lävendit. 
    *   Q3: Kas see ühtib videos nähtud taktide arvuga?
3.  **Jõudlus:** 
    *   Q4: Kui kaua võttis aega piltide võrdlemine? Kas seda saaks teha reaalajas 30 kaadrit sekundis?

### Esitamine
Esita kaks faili: 1) `RTSP_liikumine.py` ja 2) dokumendifail (doc/PDF), milles on genereeritud graafik ja vastused küsimustele Q1-Q4.

Edu!
