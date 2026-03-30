# Ettevalmistus: Triipkoodi tuvastuse lisamine ja tulemuste analüüs

Sinu ülesanne on ühendada taktituvastus (Seminar 2) ja triipkoodi lugemine (Seminar 3) üheks terviklikuks süsteemiks.

## Ülesande sisu
1. Tee koopia failist `RTSP_liikumine.py` (enda oma eelmisest kodutööst või kui see ei tööta, siis näidisest siin kaustas).
2. Süsteem peab toimima kahe rohelise ekraani vahelisel ajal, reageerima liikumisele, ootama 2.5 sekundit, võtma pildi ja sellel tuvastama triipkoodi ja selle kaudu toote info.
3. Terminalis peab iga takti kohta ilmuma:
    *   Sekundite arv video algusest (pärast rohelise ekraani lõppu - vajalik taktide võrdlemiseks märgendatud andmetega).
    *   Toote EAN13 kood, toote nimi.
    *   Säilivusaeg (video salvestamise kuupäev (14.02.2026 + säilivuse kestus andmebaasist).

## Analüüs ja statistika
Programmi lõpus (uuesti rohelise ekraanini jõudes) peab süsteem väljastama statistilise ülevaate:
*   **Tuvastusmäär:** Mitmel taktil õnnestus triipkood leida, kui liikumine oli toimunud? Võib väljastada nt 14/24 (...%).
*   **Jõudlus:** Mis oli keskmine ja maksimaalne aeg, mis kulus pildilt triipkoodi leidmiseks? 
*   **Maht:** Kui mitu triipkoodi tuvastati keskmiselt ühe pildi pealt?



## Esitamine
1) Esita täidetud Pythoni fail.
2) Esita dokumendifail (pdf, doc etc), kus on näidatud väljundstatistika kõigi nelja videovoo kohta (analüüs ja statistika punktis arvutatu) ja vastused ka järgmistele küsimustele:
- Kas leitud triipkoodid vastavad õigele triipkoodile või leidub mõni valesti loetud triipkood?
- Milliste kaadrite puhul triipkood lugemata jäi (millist tüüpi kaadritega/probleemidega oli tegemist)?
- Kas tuvastus on piisavalt kiire reaalajas kasutuse jaoks?
- Mitu triipkoodi oli keskmiselt tegelikult pildil? Miks ei leitud neist suuremat hulka üles?
- Kas triipkoodide tuvastamise määr (mitmel protsendil taktidest triipkood tuvastati) on piisav, et lahendust kasutada? 
