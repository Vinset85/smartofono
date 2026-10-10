# Mandare i pezzi in produzione

Questo è l'elenco di cosa ordinare, a chi, con quale file e cosa controllare
alla consegna. Le quote non sono ripetute a mano: stanno nei DXF, e i DXF
nascono da `parametri.py`. Se un numero qui e un numero nel disegno non
coincidono, ha ragione il disegno.

Prima di ordinare, rigenera tutto e leggi l'ultima riga:

```
python3 parametri.py
```

Deve dire **`verifica interferenze: nessun problema`**. Se elenca dei problemi
non sono avvisi, sono pezzi che non entrano uno nell'altro.

---

## I quattro pezzi da far fare fuori

| # | Pezzo | File | A chi | Quantità |
|---|---|---|---|---|
| 1 | Vetro frontale stampato | `cad/01-vetro-frontale.dxf` | vetreria con serigrafia UV | 1 |
| 2 | Telaio portante | `cad/02-telaio-portante.dxf` | taglio laser + officina | 1 |
| 3 | Cassa da incasso | `cad/03-cassa-incasso.dxf` | lattoniere, **oppure** stampa 3D da `stl/cassa.stl` | 1 |
| 4 | Squadretta della scheda video | `cad/07-staffa-e-pezzi-piani.dxf` | lattoniere, o a mano | 1 |

Gli altri due DXF non si ordinano: `04-dima-muratura.dxf` si stampa in scala
1:1 su carta e serve a fare il buco nel muro, `05-disposizione.dxf` e
`06-gruppo-display.dxf` sono mappe di montaggio.

---

## 1. Vetro frontale

**Il pezzo da cui dipende tutto il resto, e l'unico irreversibile.** Si ordina
per ultimo in ordine di rischio e per primo in ordine di tempi, perché è quello
con la consegna più lunga.

- **Materiale**: Corning Gorilla Glass 3 da 2 mm, alluminosilicato rinforzato
  chimicamente. Un float temprato normale non va: a 2 mm di spessore non si
  tempra, e un vetro non temprato in facciata non è accettabile.
- **Formato**: 100 x 240 x 2, angoli raggiati 3 mm.
- **Stampa**: serigrafia a inchiostro UV **sul retro**, nera coprente su tutta
  la superficie tranne le finestre. Le icone (NFC, campanello) in nero
  semitrasparente, sul layer `SMOKE`.
- **Trattamento**: antiriflesso sul fronte. **Non è un optional**: la
  leggibilità in pieno giorno dipende da quello e non dai nit del display. Un
  vetro senza AR riflette il 4% per faccia e il contrasto utile crolla.

Alla consegna controlla tre cose: che la **finestra del display** misuri
69,0 x 122,0 e non di più, perché una finestra più larga della cornice del
pannello lascia vedere il bordo del modulo; che la **serigrafia sia sul retro**
e non sul fronte, dove si graffia; che gli angoli siano raggiati e non vivi.

## 2. Telaio portante

- **Materiale**: alluminio 5754 o 6082 da 3 mm, **anodizzato nero opaco**.
- **Lavorazioni**: taglio laser del profilo e delle aperture (layer `TAGLIO`),
  poi filettature in officina (layer `FILETTATURA`).

L'anodizzazione va fatta **dopo** le filettature, non prima: lo strato
anodico è spesso qualche micron e in un M2 si perde il gioco. Ed è isolante,
quindi dove serve continuità di massa fra telaio e cassa va prevista una
rondella dentellata che lo incida.

Due punti che si sbagliano facilmente, entrambi marcati sul disegno:

- **i due fori M2.5 della squadretta sono ciechi**, profondi 2 mm su 3 di
  spessore. Non sono un errore del disegno: cadono dietro il display, che corre
  a 1 mm dal fronte del telaio, e se li fai passanti la punta della vite lo
  tocca. È l'unica lavorazione cieca del progetto;
- **le sedi dei magneti sono passanti** e sono Ø4, non Ø5. A Ø5 con quel
  margine la sede nasceva tangente al bordo e diventava una tacca aperta.

## 3. Cassa da incasso

Due strade, entrambe valide, e la scelta cambia **una cosa sola** nel resto
del montaggio.

**Lamiera di acciaio zincato 1,5 mm**, piegata e puntata, verniciata a polvere.
Lo sviluppo è nel DXF, ma le quote di piega vanno ricalcolate dal lattoniere
sulla detrazione della sua macchina: le mie sono nominali.

**ASA stampato in 3D**, pareti 2 mm, 4 perimetri, da `stl/cassa.stl`. Da
evitare il **PLA**: rammollisce verso i 55 °C e dentro la scatola si arriva a
70 nei picchi.

La cosa che cambia: **il telaio è in alluminio e i magneti hanno bisogno di
ferro da attrarre.** Con la cassa in lamiera il riscontro è la lamiera stessa.
Con la cassa in ASA non c'è niente, e vanno incollati sulla battuta **sei
dischetti di acciaio dolce Ø8 x 1**, centrati sulle sedi del telaio. Senza
quelli il pannello non sta su.

## 4. Squadretta della scheda video

Alluminio 1,5 mm, 47 x 59 di sviluppo, **una piega a 90°** a 12 mm dal bordo.
È un pezzo che si fa anche a mano con una morsa e una lima. I fori sono Ø2,7:
quattro per la scheda sull'ala lunga, due per il telaio sull'ala corta.

---

## I ritagli piani, da fare in casa

Sono nel foglio 07, in scala 1:1: si stampa, si appoggia sul materiale e si
taglia col cutter.

| Pezzo | Misura | Materiale |
|---|---|---|
| Adesivo ottico del display | 70 x 125 | OCA 0,2 mm |
| Diaframma NFC | 38 x 40 | PET nero opaco 0,2 mm |
| Rete delle feritoie | 85 x 8, due pezzi | inox maglia 0,6 mm |

---

## La minuteria

L'elenco completo con le quantità è nella tabella **Minuteria** del
[README](README.md). Le tre cose che non vanno sostituite con quello che si
trova in ferramenta:

- il **biadesivo 3M VHB 4959**, 3,0 mm. Lo spessore non è arbitrario: è lui a
  fissare la distanza fra vetro e telaio, e tutto il resto della catena di
  quote parte da lì. Un VHB più sottile sposta il telaio verso il vetro e il
  display non ci sta più;
- il **silicone neutro ossimico**, non acetico. Quello acetico libera acido
  acetico mentre reticola e corrode alluminio ed elettronica;
- le **colonnine dell'altoparlante in nylon**, non metalliche, perché passano
  a filo della camera.

---

## L'ordine in cui farlo

1. **Rigenera e verifica** (`python3 parametri.py`). Se segnala interferenze,
   fermati qui.
2. **Ordina il vetro.** È il pezzo con i tempi più lunghi, e ora si può
   ordinare: il touch è integrato nel pannello e non esiste una lastra
   separata che possa cambiare lo spessore.
3. **Ordina telaio e cassa**, che arrivano prima.
4. **Monta tutto a banco**, fuori dal muro, e collauda. La procedura è in
   [ASSEMBLAGGIO.md](ASSEMBLAGGIO.md), e la fase di collaudo non è facoltativa:
   due passaggi sono irreversibili — la muratura della cassa e l'incollaggio
   del vetro — e vengono entrambi dopo.
5. **Poi** scava, mura, incolla.
