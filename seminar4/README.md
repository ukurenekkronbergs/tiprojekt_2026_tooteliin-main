# Seminar 4: Piltide segmenteerimine ja andmete ettevalmistus

Selles seminaris astume sammu edasi reaalajas tuvastamisest ning keskendume kogutud andmete kvaliteetsele ettevalmistamisele tehisintellekti jaoks. Meie eesmärk on liikuda "toorest" täiskaadrist (full frame) standardiseeritud tootepiltideni.

## Ülesanne 1: Toodete väljalõikamine (yl1_toodete_cut.py)

Kvaliteetse treeningandmestiku või automaatkontrolli loomiseks on vaja igast tootest puhast ja standardset pilti. Praegused täiskaadrid sisaldavad korraga nelja toodet ning palju visuaalset müra (konveieri osad).

### Eesmärk
Lüüa täiskaadrid lahku individuaalseteks toodeteks, normaliseerida nende suurus ja asend. See on kriitiline eeldus, et hiljem saaksime igalt pildilt usaldusväärselt leida kuupäeva ja muid detaile.

### Sinu ülesanded:
1.  **Koordinaatide täpsustamine:** Ava `barcode_data.json`. Seal on kirjas `rois` (Region of Interest) koordinaadid. Sinu esimeseks ülesandeks on need üle vaadata ja vajadusel korrigeerida, et väljalõiked oleksid täpsed ja sisaldaksid tervet toodet ilma üleliigse taustata.
2.  **Väljalõikamine ja roteerimine:** Täienda Pythoni skripti nii, et see lõikaks pildid välja. Kuna tooted liiguvad konveieril külili, tuleb pildid peale lõikamist 90 kraadi roteerida, et need "püsti" panna.
3.  **Suuruse ühtlustamine (Normalization):** Erinevad ROI lõiked võivad olla piksli võrra erinevad (nt 1600x1000 vs 1601x999). AI mudelite ja edasise analüüsi jaoks on oluline, et kõik sisendpildid oleksid identse resolutsiooniga. Leia lõigete hulgast suurim mõõt ja skaleeri kõik pildid selle järgi.
4.  **Andmete organiseerimine:** Salvesta tulemused eraldi kausta `individual_products`.

### Tulemus
Kui ülesanne on edukalt lahendatud, peaks sul olema kaust täis individuaalseid tootepilte, mis on kõik ühesuurused ja õiget pidi. See on sinu "puhas andmestik" edasiseks tööks.

Edu lõikumisel!

## Ülesanne 2: Detailsete alade väljalõikamine (yl2_alade_cut.py)

Nüüd, kus meil on olemas terved toote pildid, on vaja nendelt isoleerida konkreetsed huvipakkuvad alad: parim enne kuupäev, ülemine ja alumine silt ning toote sisu ala.

### Eesmärk
Eraldada pildilt alamalad, et hiljem saaksime näiteks kuupäeva tuvastada ilma, et ülejäänud pakendi disain segaks.

### Sinu ülesanded:
1.  **Baasloogika kopeerimine:** Võta aluseks oma lahendus failist `yl1_toodete_cut.py`. See kood peab olema tsükli alguses, et saada kätte roteeritud ja normaliseeritud tootepildid.
2.  **Koordinaatide seadistamine:** Täienda `barcode_data.json` failis järgmisi välju: `date_area`, `label1_below`, `label2_above`, `product_area_between`. 
    *   Vihje: Pea meeles, et need koordinaadid kehtivad juba **püsti keeratud** ja **normaliseeritud** tootepildi kohta!
3.  **Alade lõikamine:** Rakenda tsükli sees lõiked vastavalt JSON-is kirjeldatud piiridele.
4.  **Salvestamine:** Salvesta iga ala pilt vastavasse alamkausta (`date`, `label1`, `label2`, `product_area`).

### Tulemus
Pärast skripti käivitamist peaksid vastavad alamkaustad täituma sadade väikeste piltidega, kus on ainult konkreetne info (nt ainult kuupäevad).
