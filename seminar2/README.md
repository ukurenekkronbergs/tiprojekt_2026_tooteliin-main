# Seminar 2: RTSP voo töötlemine ja piltide kogumine

Selles seminaris õpime, kuidas lugeda reaalajas videovoogu (RTSP) ja koguda sealt andmeid edasiseks analüüsiks.

## Ülesanne1: RTSP voo automaatne salvestamine (RTSP_lugemine.py)

Sinu eesmärk on täiendada faili `RTSP_lugemine.py`, et see salvestaks automaatselt kaadreid määratud ajavahemiku tagant.

### 1. Kausta ettevalmistamine
Programmi alguses on antud muutuja `STREAM_URL`. Sa pead:
*   Eraldama sealt voo nime (nt URL-i lõpp `rulaad`).
*   Looma sellenimelise kausta, kasutades moodulit `os` (vihje: `os.makedirs`).
*   Veenduma, et programm ei katkeks veaga, kui kaust on juba varem loodud (`exist_ok=True`).

### 2. Piltide salvestamise loogika
Põhiline töö käib `while True` tsükli sees. Sinu ülesandeks on realiseerida ajastus:
*   Kasuta funktsiooni `time.time()`, et saada kätte praegune aeg sekundites.
*   Kontrolli, kas viimasest salvestamisest on möödunud vähemalt `SAVE_INTERVAL` (9 sekundit).
*   Kui on aeg salvestada:
    *   Koosta failinimi formaadis `frame_0001.jpg`, kus number suureneb igal korral.
    *   Kasuta `os.path.join(kaust, nimi)`, et luua korrektne tee pildini.
    *   Salvesta 9 sekundi järel üks kaader kettale, kasutades näiteks `cv2.imwrite()`.
    *   Uuenda loendureid, et järgmine salvestus toimuks õigel ajal.

### Kuidas käivitada?
1.  Ava terminal ja navigeeri õigesse kausta.
2.  Käivita skript: `python3 RTSP_lugemine.py`.
3.  Lase programmil töötada, kuni saad 10+ pilti, sealhulgas täiesti rohelise pildi.
4.  Peatamiseks vajuta klaviatuuril `Ctrl + C`.

## Ülesanne 2: Automaatne käivitamine ja seiskamine (RTSP_roheline.py)

Selles ülesandes muudame andmete kogumise "nutikamaks". Skript ei hakka pilte salvestama kohe, vaid ootab videovoo sees olevat märguannet (rohelist ekraani).

### 1. Rohelise ekraani tuvastamine
Täienda funktsiooni `is_green_screen(frame)` failis `RTSP_roheline.py`:
*   Muuda pilt väiksemaks (`cv2.resize`) või võta mitte kogu pilt, et kontroll oleks kiirem.
*   Arvuta pildi keskmine värvus (`np.mean`) või tee võrdlust igal pikslil ning ühenda (`np.all()`) abil (kumb on kiirem? kumb on usaldusväärsem?)
*   Tagasta `True`, kui roheline kanal on kõrge, kuid teised mitte.

### 2. Olekumasina (State Machine) loomine
`while` tsükli sees pead hindama ja haldama programmi olekut:
*   **Ooterežiim:** Programm loeb kaadreid, aga ei salvesta midagi. Kui `is_green_screen` muutub tõeseks, liigu salvestamise režiimi.
*   **Salvestamise režiim:** Salvesta pilte iga 9 sekundi järel (kasuta Ülesanne 1 loogikat ja koodi).
*   **Lõpetamine:** Kui oled salvestamise režiimis ja näed uuesti rohelist ekraani, siis peata tsükkel (`break`).
*   **Vihje:** Kasuta `green_cooldown` loogikat, et programm ei lõpetaks tööd kohe juba esimese rohelise ekraani jooksul. Pead veenduma, et oled rohelisest perioodist "mööda läinud", enne kui uut märki otsima hakkad.

Edu ülesande lahendamisel!