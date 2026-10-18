# Prossimi passi: dal computer al muro

Questa è la lista da seguire in ordine. Non saltare un punto. Non murare
niente prima della prova termica. Non incollare il vetro vero prima del
collaudo a banco.

Due cose, una volta fatte, non si disfano:

1. l'incollaggio del vetro vero sul telaio;
2. la cassa murata nel tufo.

Tutto il resto si può rifare.

---

## Come è fatto, in tre pezzi

Immagina una scatola nel muro e un coperchio che si stacca.

- **Cassa** (plastica ASA): resta murata per sempre. Ha una cornice che
coincide col filo dell'intonaco.
- **Telaio** (alluminio): porta Raspberry, display, camera, NFC, audio.
Entra nella cassa e si tiene con sei magneti.
- **Vetro** (Gorilla Glass nero): è incollato al telaio. Da fuori si vede
solo lui, con 3 mm di fessura nera tutto intorno.

L'elettronica la hai già. Quello che manca sono i tre pezzi fatti fuori,
la minuteria, e poi montaggio + prove + posa.

---



## Regola d'oro sui numeri

I numeri giusti stanno nei file, non in questa guida.

- Disegno da mandare al fornitore: cartella `hardware/cad/`
- Pezzo da stampare in 3D: `hardware/stl/cassa.stl`
- Se un numero qui e un numero nel disegno non coincidono, **ha ragione il
disegno**.

Prima di mandare qualsiasi file, apri il Terminale, vai nella cartella
`hardware` e lancia questi due comandi, uno dopo l'altro:

```
python3 parametri.py
../.venv-cad/bin/python verifica_cad.py
```

Devi leggere, nell'ordine:

- `verifica interferenze: nessun problema`
- `I file CAD sono coerenti con i parametri`

Se vedi un elenco di problemi: **fermati**. Non ordinare. Correggi, poi
rilancia.

---



## L'ordine dei lavori (non cambiarlo)

```
Settimana 0     Prove sul tavolo (touch e NFC attraverso 2 mm di vetro)
Settimana 0     Ordine del vetro (ci mette di più: parti da qui)
Settimana 0     Nello stesso giorno: telaio, cassa, squadretta, minuteria
Settimane 1-3   Arrivano telaio e cassa. Li controlli col calibro
Settimane 2-4   Arriva il vetro. Lo controlli. Non lo incolli ancora
Settimana 4     Montaggio a banco + collaudo + prova termica
                SE la prova termica fallisce: non scavare
Settimana 5     Scavo, muratura, attesa della malta
Settimana 6     Incollaggio del vetro vero (72 ore di attesa)
Settimana 7     Inserimento del gruppo, prova pioggia, fine
```

Il vetro si ordina **per primo** (tempi lunghi) ma si incolla **per ultimo**
fra le cose irreversibili.

---



# PARTE A — Prima di spendere un euro



## A1. Prova il touch attraverso 2 mm di vetro

Ti serve: il display già acceso, una lastra di vetro da 2 mm (anche da
ferramenta), un goccio d'acqua o di glicerina.

1. Accendi il display.
2. Metti una goccia d'acqua sul touch.
3. Appoggia la lastra da 2 mm sopra, senza bolle d'aria grandi.
4. Tocca il vetro in tutti e quattro gli angoli e al centro.
5. Deve rispondere ovunque, non solo in mezzo.

Se non risponde agli angoli: **non ordinare il vetro**. Il controller del
touch non si regola. Con 2 mm deve funzionare; se non funziona, il modulo
non va.

## A2. Prova l'NFC attraverso 2 mm di vetro

1. Accendi il lettore PN532.
2. Metti la stessa lastra da 2 mm sopra l'antenna (la metà della scheda
  verso il connettore USB-C, non il centro della scheda).
3. Avvicina un tag o il telefono a circa 2 cm.
4. Deve leggere.

Se non legge: non è un problema del vetro, è della distanza o dell'antenna.
Non ordinare il vetro finché non hai capito perché.

## A3. Guarda i file che manderai

Apri queste anteprime (sono disegni in foto, non si misurano):


| File                                    | Cosa è               | Lo mandi a qualcuno?              |
| --------------------------------------- | -------------------- | --------------------------------- |
| `anteprime/01-vetro-frontale.png`       | il vetro             | sì, alla vetreria, insieme al DXF |
| `anteprime/02-telaio-portante.png`      | il telaio            | sì, al laser, insieme al DXF      |
| `anteprime/03-cassa-incasso.png`        | la cassa             | no, è solo per controllare        |
| `anteprime/04-dima-muratura.png`        | la sagoma del buco   | no, la stampi tu in carta 1:1     |
| `anteprime/07-staffa-e-pezzi-piani.png` | squadretta e ritagli | sì, al lattoniere, il pezzo 1     |


I file veri da allegare alle email sono i `.dxf` e lo `.stl`, non i PNG.

---



# PARTE B — Dove si fa ogni pezzo e cosa scrivere

Ci sono **quattro pezzi fatti da altri**. Gli altri li tagli tu col cutter.

## B1. Vetro frontale — vetreria con Gorilla Glass e serigrafia UV

**File da allegare:** `hardware/cad/01-vetro-frontale.dxf`

**Quanti:** 10 (il minimo di campione; 1 solo è un rischio: se sbagli la
laminazione hai finito).

**Chi:** una vetreria che fa Gorilla Glass su misura con CNC, rinforzo
chimico, serigrafia UV, antiriflesso e oleofobico. Esempi noti: Gelivable o
HP Cover Glass a Dongguan. Il MOQ di serie è 1000; in campione accettano 10.

**Cosa dire, parola per parola** (copia, incolla, compila le parentesi):

```
Oggetto: campione 10 pz cover glass 100 x 240 x 2 mm, Gorilla Glass 3

Buongiorno,
chiedo un preventivo per 10 pezzi campione.

MATERIALE
- Corning Gorilla Glass 3, 2,00 mm
- alluminosilicato con rinforzo chimico
- CS > 650 MPa, DOL > 40 µm
- voglio il certificato Corning sul lotto

MISURE
- 100,0 x 240,0 mm
- spessore 2,00 mm
- raggi agli angoli 3,0 mm
- bordo 2.5D lucidato
- il disegno è allegato (DXF, unità millimetri)

SEQUENZA OBBLIGATORIA (scrivetela sull'ordine)
1. taglio e fori CNC sul crudo
2. poi rinforzo chimico
3. poi stampa serigrafica
4. infine trattamenti AR e AF

Non tagliare e non forare DOPO il rinforzo chimico.
Non stampare PRIMA del rinforzo chimico.

STAMPA
- inchiostro UV, faccia INTERNA (lato display), non quella esterna
- nero coprente su tutta la lastra tranne le finestre del layer FINESTRE
- layer SMOKE: icona NFC a tre archi verso l'alto e un punto, senza
  cerchio, semitrasparente 15-20% (non è una finestra)
- i campanelli NON si serigrafano: sono pulsanti sul display

TRATTAMENTI, faccia ESTERNA
- antiriflesso (AR): obbligatorio, non optional
- oleofobico anti-impronta (AF)

VI CHIEDO PER ISCRITTO, prima di produrre
1. spessore totale della serigrafia, in micrometri
   (quante passate, quanti µm in tutto)
2. se potete tagliare anche il foglio di adesivo ottico (OCA)
   70,0 x 125,0 mm, spessore 0,35 mm, 10 fogli
3. trasmissione AR e angolo di contatto AF
4. tempi e prezzo dei 10 pezzi campione

Il disegno DXF ha i layer:
- TAGLIO = contorno e fori
- FINESTRE = zone senza inchiostro
- SMOKE = icona NFC semitrasparente
- SERIGRAFIA = nero coprente
```

**Quando rispondono, fai così:**

1. Se lo spessore della serigrafia è circa 30 µm: va bene, OCA da 0,35 mm.
2. Se dicono 90 µm (sei passate): apri `hardware/parametri.py`, cambia
  `SERIGRAFIA_S` nel valore che ti hanno dato in millimetri (90 µm = 0,090),
   rilancia `python3 parametri.py`. Ti dirà se serve un OCA più spesso.
3. Non confermare la produzione senza quel numero per iscritto.

**Quando arriva il vetro, controlla con il calibro prima di pagare il saldo:**

- [ ] misura esterna 100 x 240
- [ ] finestra display 69,0 x 122,0: se è più larga, si vede il bordo del
  ```
  pannello. Non va.
  ```
- [ ] serigrafia sul retro (la faccia opaca/opaca-inchiostro), non sul fronte
- [ ] angoli raggiati, non a spigolo vivo
- [ ] bordo lucido, non grezzo di taglio
- [ ] foro del microfono presente (tondo, 3 mm)
- [ ] finestra tonda dell'ottica presente
- [ ] icona NFC al centro del vetro, non spostata sulla spira

Metti i vetri in piedi, separati da carta velina, in una scatola rigida.
Non impilarli nudi.

---



## B2. Telaio portante — taglio laser + officina + anodizzazione

**File da allegare:** `hardware/cad/02-telaio-portante.dxf`

**Quanti:** 1 (meglio 2 se il laser è economico: un filetto strappato
significa rifare la piastra).

**Chi:** un'officina di taglio laser alluminio + un'officina che filetta e
anodizza. Può essere la stessa. In Italia: qualsiasi taglio laser che
lavori 5754 o 6082 da 3 mm. Poi un anodizzatore (nero opaco 15 µm).

**Cosa dire:**

```
Oggetto: 1 piastra alluminio 3 mm, taglio laser + filettature + anodizzazione

MATERIALE
- alluminio 5754 oppure 6082
- spessore 3,0 mm
- anodizzazione nera opaca 15 µm, DOPO le filettature (non prima)

FILE
- allego 02-telaio-portante.dxf, unità millimetri
- layer TAGLIO = contorno e aperture, da tagliare
- layer FILETTATURA = fori da filettare, NON da lasciare come fori passanti
  da 2,7

LAVORAZIONI
- taglio laser del layer TAGLIO
- sbavare tutti i bordi (si vedono attraverso il vetro)
- filettare i fori del layer FILETTATURA:
  * M2 i fori della camera e dell'altoparlante
  * M2.5 i fori del Raspberry
  * M3 i fori del lettore NFC
  * M2.5 i DUE fori della squadretta: questi sono CIECHI,
    profondi 2,0 mm su 3,0 di spessore, dal RETRO.
    Non farli passanti. Dietro c'è un display OLED a 1 mm.
    Se la punta della vite esce, lo rompe.
- le sei sedi magneti sono passanti Ø4,1 (non Ø5)
- i due fori perno sono passanti Ø4,3

POI anodizzare nero opaco.
Dopo l'anodizzazione non si filetta più.

Controllate sul pezzo, prima di spedire:
- ingombro 89 x 229 x 3
- i due fori ciechi M2.5 non bucano il fronte
```

**Quando arriva il telaio:**

- [ ] 89 x 229 x 3 mm
- [ ] zona dietro il display piena (niente finestra grande al centro)
- [ ] asola del flat in basso al display
- [ ] foro lente + 4 fori camera, un po' più in basso dell'asse del foro
- [ ] luce altoparlante sopra
- [ ] apertura NFC in basso, 30 x 32, non grande come tutta la scheda
- [ ] 6 sedi magnete Ø4
- [ ] 2 fori perno Ø4,3 in alto
- [ ] i due fori ciechi: dal fronte non si vede nessun buco
- [ ] prova un maschio M2.5 nei fori del Pi: deve prendere, non girare a vuoto

---



## B3. Cassa da incasso — stampa 3D in ASA

**File da mandare:** `hardware/stl/cassa.stl`

**File di controllo (non si stampa, si usa col calibro):**
`hardware/cad/03-cassa-incasso.dxf`

**Quanti:** 1 (tieni il file: se la prova termica chiede una cassa più
profonda, la ristampi).

**Chi:** un service di stampa 3D che ha ASA (non PLA, non PETG). In Italia
qualsiasi service FDM industriale. In casa, solo se la stampante fa ASA in
camera chiusa e sai gestire i fumi.

**Materiale: solo ASA.** Il PLA cede a 55-60 °C. Il PETG ammorbidisce sopra
i 70 °C. D'estate l'aria in cassa ci arriva vicino. L'ASA regge oltre 90 °C
e non teme gli UV né la malta.

**Cosa dire:**

```
Oggetto: 1 cassa da incasso, ASA, da STL

FILE
- allego cassa.stl, unità millimetri

MATERIALE
- ASA, non PLA, non PETG, non ABS se potete evitare
- colore nero o grigio scuro (non si vede, è nel muro)

STAMPA
- pezzo sdraiato sul FONDO (la faccia posteriore piana sul piatto)
- la cornice resta in alto
- supporti sotto la flangia (sporge 17,5 mm, a circa 45,5 mm dal piatto)
- supporti sotto la battuta interna (sporge 6 mm verso il vano,
  a circa 68 mm dal piatto)
- ponti: feritoie laterali 40 mm, feritoia bassa 80 mm.
  Se la macchina non fa un ponte da 80 mm, mettete un supporto anche lì
- almeno 4 perimetri
- riempimento 25%
- pareti del modello: 1,5 mm, non ingrossatele. Se le fate da 2 mm
  il telaio da 89 x 229 non entra più

CONTROLLO A FINE STAMPA (misurate e scrivetemi i numeri)
- luce interna: 91 x 231 mm
- cornice esterna: 109 x 249 mm
- sei sedi tonde sulla battuta: Ø6,4, profonde 1,2 mm
```

**Quando arriva la cassa:**

- [ ] luce interna 91 x 231: il telaio (89 x 229) deve entrarci con circa
  ```
  1 mm per lato
  ```
- [ ] cornice 109 x 249
- [ ] tre feritoie: una in basso 80 x 15, due sui fianchi in alto 40 x 15
- [ ] sopra le laterali c'è un dentino (gocciolatoio)
- [ ] sei buchettine Ø6,4 sulla battuta, non fori passanti
- [ ] due perni (o i loro fori) sulla battuta alta
- [ ] flangia larga, con fori, staccata dal fronte (non a filo vetro)
- [ ] due fori da 25 mm sul fondo (corrugati)

Se la luce interna è più stretta di 89 x 229: la cassa non va. Ristampa.

---



## B4. Squadretta della scheda di ingresso — lattoniere, o tu

**File:** `hardware/cad/07-staffa-e-pezzi-piani.dxf` — è il pezzo in alto,
quello con la linea di piega.

**Quanti:** 1.

**Chi:** un lattoniere, oppure tu con morsa, squadra e lima.

**Cosa dire:**

```
Alluminio 1,5 mm.
Sviluppo 47 x 59 mm (il disegno è in scala 1:1 nel DXF).
Una sola piega a 90 gradi, a 12 mm dal bordo corto.
Fori Ø2,7: quattro sull'ala lunga (la scheda), due sull'ala corta (il telaio).
Non anodizzare, o anodizzare nero: è dentro la cassa.
```

---



## B5. I ritagli che fai tu, in cucina

Stampa `cad/07-staffa-e-pezzi-piani.dxf` in scala 1:1 (la stampante deve
essere al 100%, non "adatta alla pagina"). Appoggia il foglio sul materiale,
ferma con nastro, taglia col cutter e con un righello di metallo.


| Cosa tagli    | Misura                 | Materiale                    | Dove si compra                                |
| ------------- | ---------------------- | ---------------------------- | --------------------------------------------- |
| Diaframma NFC | 38 x 40                | PET nero opaco 0,2 mm        | lastra PET in ferramenta / Amazon             |
| Rete bassa    | 85 x 20                | inox maglia 0,6 **filo 0,2** | rete inox da insetti, non zanzariera in fibra |
| Rete laterale | 45 x 20, **due** pezzi | la stessa rete               | —                                             |
| OCA           | 70 x 125               | adesivo ottico 0,35 mm       | **non tagliarlo tu**: chiedilo alla vetreria  |


Sulla rete, il filo 0,2 conta quanto la maglia. Se prendi filo 0,25, passa
meno aria di quella calcolata. Non va.

---



# PARTE C — Cosa comprare in ferramenta e online

Compra tutto **prima** del montaggio. Manca un pezzo, ti fermi.

### Non sostituire questi tre


| Pezzo                                                 | Perché non si cambia                                                              |
| ----------------------------------------------------- | --------------------------------------------------------------------------------- |
| 3M VHB **4959**, spessore **3,0 mm**, nastro da 12 mm | è lui che tiene il telaio a 5 mm dal filo vetro. Uno da 1,1 o da 2,0 sposta tutto |
| Primer **3M 94**                                      | sull'alluminio anodizzato il VHB senza primer non tiene                           |
| Silicone **neutro ossimico**                          | quello acetico (puzza di aceto) mangia alluminio e schede                         |




### Lista della spesa

Copia e porta in ferramenta / apri Amazon e cerca esatto:

- [ ] 6 magneti neodimio N42 **Ø4 x 3** (tutti uguali)
- [ ] 6 dischetti acciaio dolce **Ø6 x 1** (i magneti da soli sull'alluminio
  ```
  non tengono niente)
  ```
- [ ] 2 perni inox **Ø4 x 3**
- [ ] 1 ventosa **Ø30**
- [ ] 4 viti M2.5 x **14** + 4 distanziali **10 mm** (non 16, non 9,5)
- [ ] 4 viti M2 x 10 + 4 colonnine 6 mm
- [ ] 3 viti M3 x 18 + 3 colonnine **nylon** 14 mm (non metallo)
- [ ] 6 rondelle gomma M3
- [ ] 2 viti M3 x 6
- [ ] 4 viti M2.5 x 8 + 4 dadi
- [ ] 2 viti M2.5 x **4** (per i fori ciechi: più lunghe bucano il display)
- [ ] 1 membrana acustica PTFE Ø 8 mm
- [ ] 1 anello schiuma nera, esterno 10, interno 6, spesso 1 mm
- [ ] 6 cavetti M-F passo 2,54 da 20 cm
- [ ] 1 nastro 3M VHB 4959 da 3,0 mm, larghezza 12 mm
- [ ] 1 primer 3M 94
- [ ] 1 tubo silicone neutro ossimico
- [ ] 1 grasso al silicone (facoltativo)
- [ ] epossidica bicomponente (per magneti e dischetti)
- [ ] alcol isopropilico
- [ ] 1 foglio PET nero 0,2 mm
- [ ] rete inox maglia 0,6 filo 0,2, almeno 15 x 10 cm



### Cavi, obbligatori, non "se capita"

- [ ] patch ethernet **slim, connettore a 90°** (o keystone a 90°)
- [ ] cavo **micro-HDMI a 90°**, 20-30 cm (quello diritto **non ci sta**)
- [ ] flat camera CSI da **200 mm** (quello corto in dotazione è corto)
- [ ] cavo USB-C **a 90°** per il PN532



### Quello che deve esserci già (impianto)

- [ ] Raspberry Pi 5 8 GB, già funzionante
- [ ] SSD NVMe + adattatore
- [ ] PoE HAT (F) Waveshare
- [ ] HAT audio Pi MIC V3
- [ ] display OLED 5,5" + le sue due schede
- [ ] Camera Module 3 **standard** (non wide)
- [ ] PN532 USB
- [ ] altoparlante ovale ~70 x 32
- [ ] switch o injector **PoE+ 802.3at** (non PoE semplice: 12,95 W non
  bastano)
- [ ] elettroserratura **12 V DC fail-secure a impulso**, ≤ 800 mA, spunto
  ≤ 1 A (schema B, UPS). Vedi [SCHEMA-SERRATURA.md](SCHEMA-SERRATURA.md)
- [ ] MOSFET logic-level 3,3 V (o modulo opto) + 1N4007 + 220 Ω, se schema B

Il reed switch e il suo magnetino: si possono comprare dopo. Il software
oggi non lo legge ancora.

---



# PARTE D — Software, prima di murare

Il programma gira già. Prima della posa fai queste tre cose sul Pi, a banco.

1. Nel file di config del Pi, `mqtt.cmd_secret` non deve essere vuoto.
  Genera un token:
   Lo stesso valore va in tre posti:
  - `installer-rpi/app/config/config.yaml` → `mqtt.cmd_secret`
  - Home Assistant → `secrets.yaml` → `videocitofono_cmd_secret`
  - Home Assistant → helper `input_text.videocitofono_cmd_token`
2. EEPROM del Pi, **prima** di staccare l'USB-C e passare al PoE:
  ```
   sudo rpi-eeprom-config --edit
  ```
   Scrivi la riga `PSU_MAX_CURRENT=5000`, salva.
3. La ventola dell'HAT va nel connettore **FAN a 4 pin del Pi**, non sui 5 V
  dell'HAT. Se la attacchi all'HAT gira sempre e la senti in chiamata.

Il resto (installazione HA, LiveKit, card) è già descritto nei README di
`installer-rpi/` e `installer-ha/`. Non è un ostacolo alla produzione
meccanica.

---



# PARTE E — Montaggio a banco (ancora niente muro)

Apri `hardware/ASSEMBLAGGIO.md` e fai le fasi 1, 2, 3, 4. Qui sotto c'è
solo quello che si sbaglia sempre.

### Magneti

- I 6 magneti nel telaio: **tutti con la stessa faccia dallo stesso lato**.
Se uno è al contrario, quel punto respinge invece di attirare.
- I 6 dischetti di acciaio: **dentro** le sedi della cassa, a filo o sotto,
con l'epossidica. Non appiccicati sopra. Se sporgono, il vetro resta
fuori dal filo dell'intonaco di quanto sporgono.



### Microfono

L'buco del suono sta sulla faccia dei pin. Quella faccia va contro il
vetro. I fili si saldano **dall'altra faccia**. Il pettine a 6 pin si
toglie: è troppo alto.

### Display

Non incollare ancora il vetro vero. Per il collaudo usa la lastra da 2 mm
della prova A1, o il vetro vero solo appoggiato, senza VHB.

L'OCA (vetro vero ↔ display) è il primo incollaggio irreversibile del
vetro. Si fa nella fase 6, dopo che la cassa è già murata e il gruppo è
già collaudato.

### HDMI

La scheda di ingresso sta in piedi sul fianco **sinistro** (lato GPIO del
Pi). Il tapo HDMI-A guarda **verso il vano**, non verso la parete.

### Prova termica: il semaforo per scavare

È il passo 13 della fase 4. Senza questo semaforo verde, il muro non si
tocca.

1. Dischetti già nelle sedi.
2. Gruppo nel telaio, telaio nella cassa.
3. Vetro di prova appoggiato.
4. Cassa in piedi, come al muro.
5. Avvolgi la cassa in polistirolo da almeno 3 cm, lasciando libere solo
  la cornice e la fessura d'ombra.
6. Nastro sui due fori dei corrugati.
7. I tre pezzi di rete appoggiati sulle feritoie, nastro solo sui bordi.
8. Due ore a riposo (display spento, nessuna chiamata).
9. Un'ora a pieno carico (display acceso, chiamata o video).

A ogni prova annota su un foglio:


| Cosa                 | Dove si legge            | A riposo          | A carico          |
| -------------------- | ------------------------ | ----------------- | ----------------- |
| Temperatura stanza   | termometro               |                   |                   |
| Temperatura del Pi   | `vcgencmd measure_temp`  |                   |                   |
| Throttling           | `vcgencmd get_throttled` | deve essere `0x0` | deve essere `0x0` |
| Watt dalla porta PoE | pagina dello switch      | (stima 5)         | (stima 11,5)      |


**Semaforo verde** se: il Pi sta al massimo 40 gradi sopra la stanza, e
`get_throttled` è `0x0`.

Esempio: stanza 25 °C → Pi sotto 65 °C.

**Semaforo rosso** se il Pi va in throttling o sale più di 40 gradi:
non scavare. Abbassa luminosità e servizi, rilancia
`tune-system-thermal.sh`, ripeti la prova.

I watt letti sullo switch, se li hai, vanno scritti in `parametri.py`
nelle righe `POTENZA_RIPOSO` e `POTENZA_PICCO`. Poi `python3 parametri.py`
ricalcola i gradi.

---



# PARTE F — Il muro (solo a semaforo verde)



## F1. Stampa la dima

1. Apri `hardware/cad/04-dima-muratura.dxf`.
2. Stampala in scala **1:1**. Nella stampante: 100%, non "adatta alla
  pagina".
3. Sul foglio c'è una riga da 100 mm in cima. Misurala col calibro.
  Se non è 100,0 mm, la stampa è sbagliata. Non usarla.
4. Il rettangolo rosso è il buco da scavare: **135 x 275 mm**.
5. La profondità non sta sulla carta: è **86 mm**, misurata dalla
  superficie dell'intonaco di oggi, non dal tufo nudo.



## F2. Dove sta in altezza

Il centro del display sta a 120 mm dal bordo basso del vetro.

Se vuoi il centro del display a 150 cm da terra:

- bordo basso del vetro = 150 − 12 = **138 cm da terra**
- bordo basso della nicchia = un po' più in basso (la nicchia è più
alta del vetro). Usa la dima a piombo, non a occhio.



## F3. Scavo

1. Incolla la dima al muro, asse verticale a livella.
2. Traccia il rosso.
3. Scava 135 x 275 x 86.
4. Nel tufo potresti arrivare a 170 mm: non serve. 86 bastano.
5. Prima di chiudere, misura il gruppo vero: dal retro del telaio alla
  cima dei pin **coi connettori Dupont infilati**. Il progetto conta
   50,5 mm. Se superi **57 mm**, il canale d'aria dietro è troppo
   stretto: la cassa va ristampata più profonda. Fermati.



## F4. Corrugati

Due tubi da 25 mm nel fondo della cassa.

- Uno: cavo di rete PoE (è l'unico cavo che serve al pannello).
- Due: schema A, filo pilota 3,3 V verso il relè in quadro. Schema B
  (serratura sotto UPS): due fili 0,5–0,75 mm², 12 V e ritorno bobina, da
  [SCHEMA-SERRATURA.md](SCHEMA-SERRATURA.md). Domani tirare un cavo nel tufo
  murato costa una giornata.

Dove il tubo entra nella cassa: silicone neutro **intorno al tubo**.
Non nella fessura d'ombra sul fronte.

## F5. Muratura

1. Bagna il tufo finché non beve più.
2. Malta, cassa in sede, **cornice a filo dell'intonaco finito**.
  Non a filo del corpo della cassa: il corpo sta 5 mm più dentro.
3. La cornice è il regolo. Si rasa contro di lei.
4. Controlla che non sia storta: un millimetro di inclinazione si vede
  su 24 cm di vetro.
5. Aspetta che la malta abbia fatto presa. Non inserire il gruppo in
  malta fresca.



## F6. Solo ora, il vetro vero

Segui la fase 6 di `ASSEMBLAGGIO.md`. In sintesi:

1. Pulizia con alcol isopropilico, vetro e telaio.
2. Primer 3M 94 sull'alluminio, aspetta quanto dice il flacone.
3. OCA 70 x 125 sul display, tutto pieno, rullo di gomma dal centro
  verso i bordi. Niente cornice di biadesivo sul display.
4. VHB 4959 da 3,0 mm a cornice sul telaio.
5. Vetro sul telaio, allineato.
6. Premi (circa 15 N/cm²).
7. **72 ore** prima di tirare con la ventosa.



## F7. Inserimento e prove finali

1. Gruppo nella cassa: i due perni in alto trovano i fori, i magneti
  attaccano.
2. Il vetro deve essere a filo della cornice, non storto, non sporgente.
3. Fessura nera di 3 mm su tutti e quattro i lati. Niente silicone lì.
4. Prova pioggia con la canna, da tutte le direzioni, qualche minuto.
  Dentro deve restare asciutto, o l'acqua deve uscire dalla feritoia
   bassa, non ristagnare.
5. Prova suono: esce dai **fianchi**, non dal fronte.
6. Estrai con la ventosa Ø30 e reinserisci. Deve uscire intero.

---



# PARTE G — Cosa non fare (errori già pagati da questo progetto)

- Non chiedere IP65. La cassa è aperta per l'aria. Il grado è **IP44**,
sotto un portico, non certificato in laboratorio.
- Non mettere il pannello al sole diretto sul vetro.
- Non usare PLA o PETG per la cassa.
- Non mettere silicone nella fessura d'ombra.
- Non fare passanti i due fori della squadretta.
- Non usare VHB più sottile di 3,0 mm.
- Non usare viti del Pi più lunghe di 14 mm.
- Non usare colonnine metalliche sotto l'altoparlante.
- Non appoggiare i dischetti di acciaio sopra la battuta.
- Non murare prima della prova termica.
- Non incollare il vetro vero prima del collaudo a banco.
- Non girare il Raspberry con l'RJ45 in alto.
- Non usare un micro-HDMI diritto.

---



# Un foglio da stampare e tenere sul banco

```
[ ] parametri.py e verifica_cad.py: zero problemi
[ ] prova touch attraverso 2 mm
[ ] prova NFC attraverso 2 mm
[ ] email vetreria inviata + DXF 01 + chiesto µm serigrafia + OCA
[ ] email laser inviata + DXF 02 + fori ciechi scritti in grassetto
[ ] email stampa 3D inviata + STL cassa + "solo ASA"
[ ] squadretta ordinata o piegata
[ ] minuteria comprata (VHB 4959, primer 94, silicone neutro, reti)
[ ] cavi a 90° comprati
[ ] telaio arrivato e misurato 89 x 229, fori ciechi ok
[ ] cassa arrivata, luce 91 x 231, cornice 109 x 249
[ ] vetro arrivato, finestra 69 x 122, serigrafia sul retro
[ ] dischetti annegati nelle sedi
[ ] montaggio a banco
[ ] PSU_MAX_CURRENT=5000
[ ] ventola sul connettore FAN del Pi
[ ] prova termica: salto SoC ≤ 40 K, get_throttled = 0x0
[ ] watt PoE annotati
[ ] dima 1:1, quota 100 mm vera
[ ] nicchia 135 x 275 x 86, gruppo misurato ≤ 57
[ ] cassa murata, cornice a filo, corrugati sigillati
[ ] vetro incollato, 72 ore
[ ] inserito, a filo, prova pioggia, ventosa
```

Il dettaglio di ogni vite e di ogni filo sta in `ASSEMBLAGGIO.md`.
Questa guida ti dice solo **in che ordine** e **a chi** parlare.