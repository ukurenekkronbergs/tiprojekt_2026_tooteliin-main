# RTSP voo tükeldamise kvaliteedi raport

## Kokkuvõte

Analüüsisime 4 toote (salami, veisesink, kalkun, rulaad) videovoogude piltide tükeldamise kvaliteeti.
Iga 4K kaader (3840x2160) jagatakse 4 pakendiks, need roteeritakse 90° vastupäeva ja normaliseeritakse
suurusele 1680x1000 px. Seejärel lõigatakse välja 4 ala: kuupäev, ülemine silt, alumine silt, tooteaken.

Koordinaadid (normaliseeritud pakendil 1680x1000):
- **Kuupäev (date_area)**: [[0, 1500], [450, 1660]]
- **Ülemine silt (label2_above)**: y = 0..380
- **Alumine silt (label1_below)**: y = 1300..1680
- **Tooteaken (product_area_between)**: y = 380..1300

---

## 1. Kuupäeva ala (date_area)

**Koordinaadid**: [[0, 1500], [450, 1660]] (normaliseeritud pakendil)

**Hinnang**: Rahuldav, aga mitte ideaalne.

Kuupäev on pakendi alumises vasakus nurgas. Väljalõige tabab kuupäeva kõigil toodetel,
kuid on mõned probleemid:

- Kuupäeva positsioon varieerub pakendite vahel veidi (s1 vs s3 vs s4), kuna pakendid on
  erinevate algkoordinaatidega ja normaliseerimine venitab neid erinevalt.
- Mõnel pildil on kuupäeva tekst osaliselt katkenud paremal serval (aastaarv "2026" lõpus).
- Taustakleebise positsioneerimise täpsus varieerub tootmisliinil.

**Näidispildid**:
- `raport_pildid/date_probleem_salami_f1_s1.png` - salami esimene kaader, pakend 1: tühi pakend, kuupäeva ei ole näha (tooted pole veel saabunud).
- `raport_pildid/date_hea_salami_f10_s3.png` - salami kaader 10, pakend 3: kuupäev "18.05.2026" loetav.

---

## 2. Ülemine silt (label2_above)

**Koordinaadid**: y = 0..380

**Hinnang**: Hea.

Ülemine silt sisaldab NÕO brändi logo, toote pilti ja osaliselt tootenime.
Väljalõige katab piisavalt brändi-ala.

- Tootenime tekst (nt "KALKUNIFILEESINK", "VASALLI KEEDUSALAAMI") jääb osaliselt
  label2 ja product_area piirile - osa nimest on label2 alumises servas, osa
  tooteakna ülemises servas.
- See ei ole kriitiline probleem, kuna tootenime tuvastamine pole primaarne eesmärk.

**Näidispildid**:
- `raport_pildid/label2_veis_f10_s1.png` - veisesink: "Fitlap NÕO" logo selgelt näha, aga tootenime tekst on alt ära lõigatud.
- `raport_pildid/label2_rulaad_f10_s1.png` - rulaad: NÕO logo ja toote pilt hästi näha.

---

## 3. Alumine silt (label1_below)

**Koordinaadid**: y = 1300..1680

**Hinnang**: Hea.

Alumine silt sisaldab koostisainete loetelu, triipkoodi, kuupäeva, säilitustemperatuuri
ja netokaalu infot. See ala on kõige informatiivsem ja väljalõige töötab hästi.

- Koostisainete tekst on loetav (kuigi väike).
- Triipkood on tervenisti nähtav.
- Kuupäev, säilitustemperatuur ja netokaal on alumises reas selgelt loetavad.
- Mõnel juhul jääb ülemine piir (y=1300) liiga kõrgele ja sisaldab tühja ala.

**Näidispildid**:
- `raport_pildid/label1_salami_f10_s1.png` - salami: kogu info hästi loetav, kuupäev "18.05.2026" vasakul all.
- `raport_pildid/label1_veis_f10_s3.png` - veisesink pakend 3: triipkood ja info selgelt näha.

---

## 4. Tooteaken (product_area_between)

**Koordinaadid**: y = 380..1300

**Hinnang**: Rahuldav.

Tooteaken näitab läbi kile pakendatud toodet. See on suurim ala ja sisaldab
peamiselt toote visuaalset infot.

Peamised probleemid:

- **Sildi lekkimine**: Tooteakna ülemises servas on mõnikord näha tootenime teksti
  (nt "KALKUNIFILEESINK TITARA FILEJA"), kuna piir y=380 jääb sildi ja toote
  üleminekualale. Seda on raske vältida, kuna piir ei ole kõigil pakenditel täpselt samas kohas.
- **Tühjad pakendid**: Esimestel kaadrite puhul (kui tooted alles saabuvad konveierile)
  võib tooteaken näidata tühja/läbipaistvat pakendit ilma tooteta.
- **Valguspeegeldused**: Kaamera valgustuse peegeldused pakendi kilel moonutavad
  toote pilti, eriti keskmises osas.

**Näidispildid**:
- `raport_pildid/tooteaken_hea_kalkun_f10_s1.png` - kalkun: toode hästi näha, aga ülemises servas on tootenime tekst ("KALKUNIFILEESINK TITARA FILEJA").
- `raport_pildid/tooteaken_tyhi_salami_f1_s1.png` - salami esimene kaader: tühi pakend, toode pole veel saabunud.

---

## Jõudlus

Mõõdetud näidispiltidel (4K kaader, 4 pakendi töötlemine):

| Toode   | Töötlemine (ms) | Salvestamine (ms) |
|---------|------------------|--------------------|
| Salami  | 18.7             | 820.2              |
| Veis    | 14.0             | 812.0              |
| Kalkun  | 13.2             | 831.4              |
| Rulaad  | 12.9             | 772.5              |

- **Töötlemine** (lõikamine + rotatsioon + normaliseerimine + detailide eraldamine): ~13-19 ms
- **Salvestamine** kettale (PNG formaat, 21 faili): ~770-830 ms

Salvestamine on ~50x aeglasem kui töötlemine. Reaalajas süsteemis tuleks salvestamine
teha vaid DEBUG_MODE puhul, nagu on ka implementeeritud.

---

## Kokkuvõte ja soovitused

1. **Kuupäeva ala** - koordinaadid töötavad, aga kuupäeva asukoht varieerub pakendite vahel.
   Võimalik parandus: suurendada ala veidi (x kuni 500px).
2. **Ülemine silt** - töötab hästi. Tootenime jaotus sildi ja tooteakna vahel on oodatud käitumine.
3. **Alumine silt** - kõige stabiilsem ala, info on alati loetav.
4. **Tooteaken** - peamine probleem on sildi teksti lekkimine ülemisse serva. Saaks parandada
   y algust 380 -> 420, aga siis kaotaksime osa tootest. Praegune kompromiss on mõistlik.
