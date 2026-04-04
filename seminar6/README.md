# 1. Reaalajas kuupäevatuvastuse ja OCR-mudelite integreerimine

Eesmärk on integreerida optilise märgituvastuse (OCR) mudel reaalajas RTSP videovoo töötlemise süsteemi. Süsteem tuvastab konveieril liikuvad tooted, lõikab neist välja lisaks teistele aladele ka kuupäeva alad ja proovib tuvastada "parim enne" kuupäevad.

## Tutvu failidega: `RTSP_with_date.py` ja `helpers.py`

Helpers.py failis on implementeeritud kõik OCR lahendused, mida kasutasime. Samuti uued kasutusviisid VLMi jaoks (openrouter'i kaudu). Vaata need läbi, loe ka prompte.

`RTSP_with_date.py` failis defineeritakse millist tuvastamise varianti kasutatakse ning adaptiivselt luuakse vastav tuvastusmudeli objekt ja kutsustakse õiget funktsiooni välja. See fail haldab ka vastuste kuvamist ja statistika kogumist.

## Lahenduse testimine ja analüüs

Testi `RTSP_with_date.py` lahendusi ja analüüsi tulemusi.

**Testimine:**

* Testi skripti kolme erineva vlm'i variandiga (vlm_single, vlm_batch_independent, vlm_batch_consistent) ühel tootegrupil (vali nendest üks):
    * `rtsp://172.17.37.81:8554/rulaad`
    * `rtsp://172.17.37.81:8554/kalkun`
    * `rtsp://172.17.37.81:8554/veis`
    * `rtsp://172.17.37.81:8554/salami`
* Lase skriptil töötada piisavalt kaua, et koguda statistikat (nt kuni rohelise ekraani teistkordse ilmumiseni).
* Jäta meelde tuvastuse kvaliteet ning ka keskmine töötlusaeg kuupäevatuvastuseks.


# 2. Sildituvastuse esialgne versioon

Fail `sildid_MAE.py` sisaldab koodi, mis arvutab siltide vahelisi kauguseid. Esialgu on tegu lihtsalt koodiga, mis võtab ühe näidissildi, õiged sildid ja valed sildid ning arvutab nendel pikslitevahelise kauguse (MAE - mean absolute error) näidissildiga. Seejärel väljastab kood histogrammi, kus on näha, kas selle kaugusega oli võimalik eristada olemasolevaid ja puuduvaid silte.

Sinu ülesandeks on jooksutada koodi erinevate toodete peal, erinevate siltide peal (label1 - alumine silt, label2 - ülemine silt) ning muuta ka pildi suuruse muutmise faktorit ning analüüsida tulemusi. Kas saame eristada sellisel viisil olemasolevaid ja puuduvaid silte?