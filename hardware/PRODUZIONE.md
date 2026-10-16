# Mandare i pezzi in produzione

La sequenza da seguire, con i testi da mandare ai fornitori e la lista della
spesa, è in [PROSSIMI-PASSI.md](PROSSIMI-PASSI.md). Questo file resta il
riferimento di cosa ordinare e cosa controllare.

Questo è l'elenco di cosa ordinare, a chi, con quale file e cosa controllare
alla consegna. Le quote non sono ripetute a mano: stanno nei DXF, e i DXF
nascono da `parametri.py`. Se un numero qui e un numero nel disegno non
coincidono, ha ragione il disegno.

Prima di ordinare, rigenera tutto e leggi l'ultima riga di entrambi:

```
python3 parametri.py      # i pezzi entrano uno nell'altro?
python3 verifica_cad.py   # i file dicono quello che dicono i parametri?
```

Il primo deve dire **`verifica interferenze: nessun problema`**. Se elenca dei
problemi non sono avvisi, sono pezzi che non entrano uno nell'altro.

Il secondo deve dire **`I file CAD sono coerenti con i parametri`**, e serve
perché il primo verifica solo se stesso: fra i parametri e il file che mandi al
fornitore c'è il generatore, che può sbagliare per conto suo. Misura i DXF e gli
STL già scritti, che sono quello che il fornitore riceve davvero.

---

## I quattro pezzi da far fare fuori

| # | Pezzo | File | A chi | Quantità |
|---|---|---|---|---|
| 1 | Vetro frontale stampato | `cad/01-vetro-frontale.dxf` | vetreria con serigrafia UV | 1 |
| 2 | Telaio portante | `cad/02-telaio-portante.dxf` | taglio laser + officina | 1 |
| 3 | Cassa da incasso | `stl/cassa.stl`, controllo su `cad/03-cassa-incasso.dxf` | stampa 3D in ASA | 1 |
| 4 | Squadretta della scheda di ingresso | `cad/07-staffa-e-pezzi-piani.dxf` | lattoniere, o a mano | 1 |

Gli altri tre DXF non si ordinano: `04-dima-muratura.dxf` si stampa in scala
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
- **Formato**: 100 x 240 x 2, angoli raggiati 3 mm, **bordo 2.5D lucidato**.
- **Stampa**: serigrafia a inchiostro UV **sul retro**, nera coprente su tutta
  la superficie tranne le finestre del layer `FINESTRE`. Sul layer `SMOKE` c'è
  un solo elemento, l'**icona NFC**: tre archi verso l'alto e un punto, senza
  cerchio, circa 8,5 × 7 mm, tratto 0,28 mm. Va stampata semitrasparente al
  15-20% con meno passate dello stesso inchiostro: è un segno, non una
  finestra. I campanelli non hanno icone serigrafate, perché sono pulsanti sul
  display.
- **Trattamento**: antiriflesso sul fronte, più oleofobico anti-impronta. L'AR
  **non è un optional**: la leggibilità in pieno giorno dipende da quello e non
  dai nit del display. Un vetro senza AR riflette il 4% per faccia e il
  contrasto utile crolla.

### La sequenza va scritta nell'ordine

È la riga più importante di tutto l'ordine, e va messa nera su bianco:

> **taglio e lavorazioni CNC sul crudo, poi rinforzo chimico, poi stampa,
> infine i trattamenti.**

Il rinforzo chimico è uno scambio ionico a 400-450 °C che crea uno strato in
compressione sulla superficie e sui bordi. Se il vetro viene tagliato o
sagomato **dopo**, il bordo nuovo nasce senza quello strato, e un bordo che
sporge 5,5 mm oltre il telaio è proprio il punto che prende i colpi. La stampa
viene dopo perché l'inchiostro UV cura sotto i 200 °C e nel forno dello scambio
ionico non sopravvivrebbe.

### Due numeri da farsi dare per iscritto

**Lo spessore totale della serigrafia**, in µm. Non è una curiosità: l'adesivo
ottico del display è tagliato a misura del modulo, 70 x 125, mentre la finestra
trasparente è 69,0 x 122,0, quindi la laminazione scavalca il bordo
dell'inchiostro. Quel gradino l'adesivo lo deve assorbire. Il progetto assume
30 µm (due o tre passate) e su quella base prescrive un **OCA da 0,35 mm**: se
il fornitore risponde che ne fa sei, aggiorna `SERIGRAFIA_S` in `parametri.py`
e rilancia la verifica, che ti dirà quale spessore serve.

**Se possono fornire l'adesivo ottico già tagliato**, 70 x 125 e dello spessore
che risulta dal punto sopra. Costa poco e risolve il problema peggiore della
laminazione a mano, che è il bordo rifilato col cutter: è da lì che partono le
bolle.

### Al ricevimento

Controlla quattro cose: che la **finestra del display** misuri 69,0 x 122,0 e
non di più, perché una finestra più larga della cornice del pannello lascia
vedere il bordo del modulo; che la **serigrafia sia sul retro** e non sul
fronte, dove si graffia; che gli angoli siano raggiati e non vivi; e che il
**bordo sia lucidato**, non grezzo di taglio.

Conviene ordinare il campione da **dieci pezzi** che questi fornitori
accettano. Non è uno spreco: su un pezzo dove va laminato a mano un adesivo
ottico, i nove di scorta sono la differenza fra un errore e un disastro.

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

**ASA stampato in 3D**, da `stl/cassa.stl`, pareti **1,5 mm** come il
modello. Una strada sola: la lamiera piegata, che il progetto prevedeva in
alternativa, non fa la cornice, i gocciolatoi e gli smussi di scarico, e il
foglio 03 non è più uno sviluppo ma un disegno di controllo, da usare col
calibro sul pezzo stampato. Il PETG è escluso perché ammorbidisce sopra i
70 °C, e d'estate a pieno carico l'aria in cassa ci arriva vicino; il **PLA**
ancora di più. Le pareti non possono superare 2,0: oltre, la misura esterna è
fissata dalla fessura d'ombra e il telaio da 89 x 229 non entra più nel vano.

Come stamparla:

- **sdraiata sul fondo**, con la cornice in alto: il fondo è l'unica faccia
  piana e grande, e così battuta, flangia e cornice crescono in verticale e
  le loro quote vengono dalla precisione in z della stampante;
- **supporti** sotto la flangia, che sporge di 17,5 mm a 45,5 mm dal piatto e
  porta la cornice, e sotto la battuta, che sporge di 6 mm verso l'interno a
  68 mm dal piatto; si tolgono dalla bocca. Le feritoie si chiudono a ponte,
  40 mm le laterali e 80 la bassa: se la stampante non regge un ponte da 80,
  un supporto anche lì;
- **almeno 4 perimetri e 25% di riempimento**: le pareti da 1,5 mm sono tutte
  perimetri, ma flangia e battuta prendono carico, la prima dalla malta e la
  seconda dai magneti;
- dopo la stampa, misura col calibro **luce interna 91 x 231** e **cornice
  109 x 249** sul foglio 03: sono le due quote che decidono se il telaio entra
  e se il vetro va a filo. Un ASA che ritira più del previsto si vede qui.

**Il telaio è in alluminio e i magneti hanno bisogno di ferro da attrarre**, e
la cassa in ASA non ne ha: servono **sei dischetti di acciaio dolce Ø6 x 1**,
uno per magnete. Senza quelli il pannello non sta su.

I dischetti vanno **annegati nelle sei sedi** che il modello 3D già prevede,
Ø6,4 profonde 1,2 sulla faccia di battuta, non incollati sopra. Appoggiati sulla
battuta si infilerebbero fra battuta e magnete e alzerebbero tutto il gruppo di
un millimetro, mentre il vetro deve restare a filo dell'intonaco.

Sul disegno le sedi **non sono concentriche ai magneti**, e non è una svista:
stanno sull'asse dell'anello di battuta, 3 mm dal bordo del vano. L'anello è
largo 6 mm ma i magneti ne stanno a 4 dal bordo, quindi una sede centrata su di
loro sborderebbe nel vano, e allargare l'anello non si può perché sotto, a mezzo
millimetro, passa il lettore NFC. Spostata sull'asse, la sede ci sta e il
dischetto copre comunque tutto il magnete, che è l'unica cosa che conta.

## 4. Squadretta della scheda di ingresso

Alluminio 1,5 mm, 47 x 59 di sviluppo, **una piega a 90°** a 12 mm dal bordo.
È un pezzo che si fa anche a mano con una morsa e una lima. I fori sono Ø2,7:
quattro per la scheda sull'ala lunga, due per il telaio sull'ala corta.

---

## I ritagli piani

Le sagome sono nel foglio 07, in scala 1:1: si stampa, si appoggia sul
materiale e si taglia col cutter.

| Pezzo | Misura | Materiale |
|---|---|---|
| Diaframma NFC | 38 x 40 | PET nero opaco 0,2 mm |
| Rete della feritoia bassa | 85 x 20, un pezzo | inox maglia 0,6 mm, filo 0,2 |
| Rete delle feritoie laterali | 45 x 20, due pezzi | la stessa |

La rete è più grande della feritoia, 80 x 15 la bassa e 40 x 15 le laterali,
perché va incollata dentro e le servono 2,5 mm di bordo per l'adesivo **su
tutti i quattro lati**: un ritaglio grande esattamente come la feritoia non
avrebbe dove attaccarsi. Il filo da 0,2 non è un dettaglio: con maglia 0,6 la
tela lascia passare il 56% dell'aria, che è il numero su cui è calcolata la
ventilazione, ed è cieca per le gocce che arrivano radenti, che è quello su
cui è calcolata la protezione dall'acqua. Una rete con filo più sottile passa
più aria e meno pioggia, una con filo più grosso il contrario.

**L'adesivo ottico del display fa eccezione**, pur essendo disegnato sullo
stesso foglio: 70 x 125 di **OCA da 0,35 mm**, e va ordinato già tagliato.
Rifilarlo col cutter lascia un bordo con microbave, e quelle diventano le bolle
che poi si vedono in trasparenza.

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
3. **Ordina il telaio e stampa la cassa**, che arrivano prima.
4. **Monta tutto a banco**, fuori dal muro, e collauda. La procedura è in
   [ASSEMBLAGGIO.md](ASSEMBLAGGIO.md), e la fase di collaudo non è facoltativa:
   due passaggi sono irreversibili — la muratura della cassa e l'incollaggio
   del vetro — e vengono entrambi dopo. Del collaudo, la prova termica in
   cassa chiusa è quella che decide se si mura.
5. **Poi** scava, mura, incolla.
