# Scatola da incasso e frontalino in vetro

Progetto meccanico del videocitofono: pannello in vetro a filo muro, telaio
portante estraibile, cassa da murare. Tutte le quote nascono da un unico file
di parametri, quindi i disegni 2D e il modello 3D non possono divergere.

## Quote d'insieme

| Pezzo | Dimensioni (mm) | Materiale |
|---|---|---|
| Vetro frontale | 100 x 240 x 2 | Gorilla Glass 3, rinforzato chimicamente, stampato |
| Finestra serigrafata | 69 x 122 a y 59 | area attiva 68,04 x 120,96 |
| Telaio portante | 89 x 229 x 3 | alluminio 5754 o 6082 anodizzato nero |
| Cassa da incasso | 94 x 234 x 75 | lamiera zincata 1,5 mm o ASA stampato |
| Luce finita dell'intonaco | 106 x 246 | — |
| Nicchia da scavare | 124 x 264 x 81 | nel tufo, dove se ne potrebbero fare 150 |

Il vetro copre interamente la cassa e lascia su tutto il perimetro una
**fessura d'ombra di 3 mm** verso l'intonaco. È l'unico dettaglio visibile del
montaggio, e insieme è la via d'aria: le feritoie di ventilazione si affacciano
lì dentro, quindi restano invisibili guardando il pannello di fronte.

Della profondità disponibile ne sono impegnati 58,5 mm su 75: vetro, adesivo,
modulo display, telaio, distanziali e stack Pi 5 con NVMe, HAT audio e ventola.
I 20,0 mm residui sono il plenum di aria sul fondo, 18,2 cm² di sezione.

## File

```
cad/01-vetro-frontale.dxf    da mandare alla vetreria
cad/02-telaio-portante.dxf   da mandare al taglio laser
cad/03-cassa-incasso.dxf     sviluppo lamiera / riferimento stampa 3D
cad/04-dima-muratura.dxf     sagoma 1:1 da stampare per fare il foro
cad/05-disposizione.dxf      mappa dei componenti: pianta e sezione
cad/06-gruppo-display.dxf    come si monta il gruppo del display
cad/07-staffa-e-pezzi-piani.dxf  squadretta della scheda di ingresso, ritagli
render/                      render e filmati, non quotati
render/schermata-*.jpg       le interfacce reali, fotografate dal display
render/monta-video.sh        rimonta i filmati dai fotogrammi
cad/videocitofono.scad       modello 3D parametrico (OpenSCAD)
stl/                         cassa, telaio e vetro per stampa o verifica
anteprime/                   PNG di controllo di tutte le tavole
PRODUZIONE.md                cosa ordinare, a chi, e cosa controllare
ASSEMBLAGGIO.md              procedura di montaggio passo per passo
MISURE.md                    scheda di rilievo delle quote da verificare
```

I DXF sono organizzati a layer, uno per tipo di lavorazione: `TAGLIO`,
`SERIGRAFIA`, `FINESTRE`, `SMOKE`, `PIEGA`, `FILETTATURA`, più `INGOMBRI`,
`QUOTE` e `NOTE` che non vanno lavorati.

Per rigenerare tutto dopo una modifica alle quote:

```
python3 parametri.py      # verifica le interferenze ed esporta cad/parametri.scad
python3 genera_dxf.py
python3 anteprime.py
./genera_3d.sh            # richiede OpenSCAD
python3 verifica_cad.py   # misura i file appena generati
```

`parametri.py` esce con errore se due componenti si sovrappongono, se
un'apertura del telaio arriva troppo vicina al bordo o se lo stack non entra
nella cassa. È il controllo che ha fatto emergere due errori di questo
progetto: l'altoparlante tondo da 40 mm che collideva con la camera, e
l'apertura NFC che invadeva la finestra del display.

`verifica_cad.py` fa un lavoro diverso e per questo è un file separato:
`parametri.py` verifica se stesso, quindi un parametro sbagliato ma coerente con
gli altri passa indisturbato, e fra il parametro e il file c'è il generatore,
che può sbagliare per conto suo. `verifica_cad.py` apre i DXF e gli STL già
scritti e li misura come farebbe il fornitore che li riceve: controlla che i
solidi siano chiusi, che le unità siano dichiarate in millimetri, che i contorni
di taglio siano chiusi, che non ci siano entità tagliate due volte né scritte
sovrapposte, che il profilo del telaio nel DXF coincida con quello nel modello
3D, e quanto materiale resta fra i fori più vicini. Due difetti di questo
progetto si sono visti solo così: un offset nel modello OpenSCAD che spostava
tutte le piastre di mezzo spessore, e la griglia dell'altoparlante serigrafata
sopra le sedi dei magneti, che si sarebbero viste attraverso il vetro.

## Materiali consigliati

### Vetro frontale

**Corning Gorilla Glass 3 da 2 mm**, alluminosilicato rinforzato chimicamente
(CS oltre 650 MPa, DOL oltre 40 µm), con **stampa serigrafica a inchiostro UV**
sulla faccia interna, bordi 2.5D lucidati, e sulla faccia esterna
**antiriflesso** e **oleofobico anti-impronta**.

La ragione della scelta è lo spessore, non il marchio. Il touch capacitivo deve
leggere attraverso il vetro e la sensibilità di questo modulo non è regolabile:
4 mm sono al limite di quello che un controller gestisce, 2 mm no. Anche la
lettura NFC guadagna i 2 mm che il vetro non ha più. E **sotto i 3 mm il float
non si tempra termicamente**: è esattamente il motivo per cui l'industria usa
l'alluminosilicato chimicamente rinforzato per i cover glass sottili. Volendo
2 mm, quella è l'unica strada.

Il rinforzo chimico cambia anche la sequenza di produzione, che va comunicata
chiaramente al fornitore: **taglio e lavorazioni CNC sul crudo, poi rinforzo
chimico, poi stampa, infine i trattamenti**. Lo scambio ionico avviene a
400-450 °C e l'inchiostro UV, che cura sotto i 200 °C, viene dopo e non lo
disturba. Sul temperato termico, invece, serigrafia e tempra stavano nello
stesso ciclo.

Due cose si perdono rispetto al float temperato con smalto ceramico, e vanno
accettate consapevolmente. La prima è la durata della grafica: lo smalto
vetrificato a 650 °C è eterno, un inchiostro UV industriale è resistente e sta
sulla faccia interna al riparo dall'abrasione, ma resta organico, e su una
facciata esposta a sud in quindici anni può virare. La seconda è il modo di
rottura: il rinforzato chimico non frantuma in granuli come il temperato, si
spacca in pezzi grandi. Qui resta laminato all'adesivo ottico e incollato al
telaio, quindi i frammenti non vanno da nessuna parte, ma formalmente non è un
vetro di sicurezza certificato.

C'è infine un punto costruttivo: il vetro sporge 5,5 mm oltre il telaio su tutto
il perimetro, e a 2 mm quel bordo in aggetto è più vulnerabile a un colpo
laterale di quanto fosse a 4. Da qui la richiesta di **bordo 2.5D con rinforzo
chimico eseguito dopo la lavorazione**, non prima.

I fornitori che trattano Gorilla su misura (per esempio Gelivable o HP Cover
Glass, entrambi a Dongguan) lavorano spessori da 0,4 a 2,0 mm con CNC, fori,
asole, bordi, rinforzo, serigrafia fino a sei strati, AR, AF e DLC. I sei strati
servono più di quanto sembri: la finestra semitrasparente al 15-20% dell'icona
NFC si ottiene variando il numero di passate, invece di giocare sulla densità di
un unico smalto. Il MOQ di produzione è di mille pezzi, ma in fase campione si
parte da **dieci**, con prototipi in circa una settimana. Dieci pannelli non
sono uno, ma per un pezzo su cui va laminato un adesivo ottico a mano, avere
nove ricambi è più un vantaggio che uno spreco.

Nel preventivo vanno chiesti esplicitamente: grado e spessore del materiale,
certificato Corning, sequenza di produzione, tipo di inchiostro con resistenza
UV dichiarata, **numero di passate e spessore totale della serigrafia**,
trasmissione dell'AR, angolo di contatto dell'AF, profilo del bordo, e se
possono fornire l'adesivo ottico già tagliato a misura. Lo spessore
dell'inchiostro non è una curiosità: è il gradino che l'adesivo ottico deve
assorbire, e decide quale OCA ordinare.

Alternativa economica per un primo prototipo: PMMA colato nero 3 mm con le
finestre fresate e lucidate. Costa un quarto, ma si riga, si opacizza al sole e
si deforma sopra i 70 °C: va bene per provare gli ingombri, non per restare in
facciata.

#### Perché 2 mm e non 4: il touch

I controller capacitivi hanno la sensibilità tarata sullo spessore della *cover
lens*: quelli buoni arrivano a 4-5 mm, molti si fermano a 2. Il modulo in uso
presenta il touch come HID generico attraverso un bridge USB-I2C WCH
(`1a86:e5e3 USB2IIC_CTP_CONTROL`), quindi **la sensibilità non è regolabile dal
Raspberry**: è fissata nel firmware e quello che c'è è quello che c'è. Con 4 mm
si andava a scommettere; con 2 mm si è dentro il margine di qualunque
controller.

La prova resta comunque consigliata, e costa niente: appoggia sul touch una
lastra da 2 mm, con un velo d'acqua o di glicerina a fare da accoppiamento al
posto dell'adesivo, e verifica che risponda su tutta la superficie, non solo al
centro. Senza quel velo la prova è pessimistica, perché l'aria interposta vale
sette volte il suo spessore.

### Telaio portante

Alluminio **5754** (o 6082) da 3 mm, taglio laser, anodizzato nero opaco 15 µm.
Porta display, Raspberry, camera, altoparlante e lettore, ed è l'unico pezzo che
si estrae per manutenzione. L'alluminio serve anche come massa termica e come
schermo elettromagnetico fra il display e l'elettronica.

Due accorgimenti non negoziabili:

- la zona NFC in basso è **aperta** (30 x 32 mm). Una piastra di alluminio alle
  spalle della bobina azzererebbe la portata di lettura: la scheda PN532 si
  monta sul retro del telaio e legge attraverso l'apertura, a 8 mm dal vetro;
- l'anodizzazione è isolante. Dove serve continuità di massa fra telaio e cassa,
  prevedere una rondella dentellata che incida lo strato, o mascherare un'area
  di contatto.

Le filettature M2 su 3 mm di alluminio reggono due filetti e mezzo: sufficiente
per camera e altoparlante, che non sono sollecitati. Il telaio porta inoltre
sei sedi passanti da 4 mm per i magneti, da incollare a filo della faccia
posteriore con epossidica e tutti con la stessa polarità.

### Cassa da incasso

Due strade, entrambe valide:

**Lamiera di acciaio zincato 1,5 mm**, piegata e puntata, verniciata a polvere.
È la soluzione industriale delle cassette da incasso: indeformabile, si mura
senza precauzioni, costa poco se si ha un lattoniere. Lo sviluppo è nel DXF 03,
ma le quote di piega vanno ricalcolate dal lattoniere sulla detrazione della sua
macchina.

**ASA o PETG stampato in 3D**, pareti 2 mm, 4 perimetri. Comodo per
l'autoproduzione e per iterare sulla geometria. Da evitare assolutamente il
**PLA**: rammollisce intorno ai 55-60 °C e dentro la scatola si arriva a 70 °C
nei picchi. L'ASA è preferibile al PETG per stabilità dimensionale e resistenza
UV; entrambi tollerano bene gli alcali della malta.

Il Raspberry è collegato in **ethernet cablato** (`eth0`, WiFi non attivo) e
alimentato dallo stesso cavo in **PoE**, con il PoE HAT (F) di Waveshare
impilato fra il Pi e l'HAT audio. Quindi una cassa metallica non crea problemi
di radio. Se in futuro si passasse
al WiFi, la cassa metallica più il telaio in alluminio lo renderebbero
inutilizzabile: in quel caso solo ASA/PETG.

Due dettagli della cassa che vale la pena non perdere di vista:

- la **flangia di muratura è arretrata di 10 mm** rispetto al fronte. Se fosse a
  filo resterebbe in vista, perché è più larga del vetro: arretrata, finisce
  sotto lo spessore di intonaco e rasante;
- sul fronte corre una **battuta interna larga 6 mm**. Il telaio si appoggia
  lì; senza battuta cadrebbe dentro la cassa, dato che è più piccolo della luce
  interna. È un gradino profondo 4 mm: dietro il vano torna pieno, altrimenti
  la scheda video non ci starebbe. Sulla battuta alta ci sono due **perni di
  centraggio** da 4 mm a passo 48, e sei riscontri per i magneti.

Sui riscontri serve un avvertimento, perché è il genere di dettaglio che si
scopre a pannello montato: **il telaio è in alluminio e l'alluminio non è
ferromagnetico**, quindi i magneti non tengono niente da soli. Con la cassa in
lamiera zincata il riscontro è la lamiera stessa e non c'è nulla da aggiungere.
Con la **cassa stampata in ASA il magnete non ha nulla da attrarre**: servono
sei dischetti di **acciaio dolce Ø6 x 1**, uno per magnete. Costano niente e
senza di loro il pannello non sta su.

Vanno **annegati nelle sei sedi** che il modello della cassa prevede, Ø6,4
profonde 1,2 sulla faccia di battuta, non incollati sopra. Appoggiati sulla
battuta si infilerebbero fra battuta e magnete e alzerebbero tutto il gruppo di
un millimetro, mentre il vetro deve restare a filo dell'intonaco.

Le sedi non sono concentriche ai magneti: stanno sull'asse dell'anello di
battuta, 3 mm dal bordo del vano. L'anello è largo 6 mm ma i magneti ne stanno a
4 dal bordo, quindi una sede centrata su di loro sborderebbe nel vano, e
allargare l'anello non si può perché a mezzo millimetro da lì passa il lettore
NFC. Decentrata di quel millimetro la sede ci sta, e il dischetto copre comunque
tutto il magnete.

### Incollaggio del vetro

Il vetro porta due incollaggi diversi, su due piani diversi, e confonderli è
l'errore che manda in pezzi il progetto.

Il **display** si incolla direttamente al vetro: deve stare a contatto ottico,
altrimenti fra vetro e pannello compaiono riflessi interni e doppia immagine.

L'adesivo va steso **in pieno**, su tutta la superficie, con un foglio di OCA
(adesivo ottico trasparente) da 0,35 mm. Una cornice perimetrale sarebbe più
facile da applicare, ma lascerebbe un'intercapedine d'aria fra vetro e pannello,
e su un touch capacitivo quella è la scelta peggiore possibile. Il conto è
semplice: quello che il sensore "vede" non è lo spessore, ma lo spessore diviso
la costante dielettrica. Il vetro ha εr ≈ 7, l'aria 1. Due decimi di millimetro
d'aria pesano quindi come **1,4 mm di vetro in più**: su un pannello che ne ha
già 4 davanti significa chiedere al touch di lavorare come se fossero 5,4,
cioè un 35% in più, per risparmiarsi una laminazione. A questo si aggiunge
l'ottica: un'intercapedine introduce due interfacce vetro-aria, ognuna delle
quali riflette un 4%, e il risultato è un'immagine slavata con riflessi interni.

Il modulo ha **1 mm di cornice**, quindi una striscia perimetrale sarebbe anche
larga 1 mm su un perimetro di 386 mm: non si taglia col cutter e andrebbe
fustellata. Fra fustellare una cornice e laminare un foglio, conviene il
foglio.

#### Lo spessore dell'OCA non lo decide l'ottica, lo decide la serigrafia

Il foglio è tagliato a misura del **modulo**, 70 x 125, ma la finestra
trasparente nel vetro è 69,0 x 122,0. Sono due misure diverse per un motivo
sano — l'OCA deve incollare tutto il modulo, cornice compresa — e la
conseguenza è che la laminazione **scavalca il bordo dell'inchiostro su tutto
il perimetro**: mezzo millimetro sui fianchi, un millimetro e mezzo sopra e
sotto.

Su quel gradino l'adesivo deve rifluire. Se non ce la fa resta un canale d'aria
lungo il bordo della finestra, cioè un anello di bolle esattamente dove l'occhio
va a cercare il bordo dell'immagine. Un nero coprente in serigrafia UV sta sulle
due o tre passate da 8-15 µm, quindi il gradino è **nell'ordine dei 30 µm**, ma
il fornitore può arrivare a sei passate, e allora diventano 90.

Da qui i **0,35 mm** al posto dei 0,2 che il progetto portava prima. Il
criterio è un rapporto di almeno cinque fra adesivo e gradino: il limite fisico
di un OCA morbido sta intorno a un terzo del proprio spessore, ma quello vale
in autoclave, e qui si lamina a mano con un rullo. Con 0,35 il rapporto regge
anche nel caso a sei passate.

**La cosa migliore di questa correzione è che non costa niente.** La quota del
telaio la fissa il VHB da 3,0 mm, non l'adesivo del display: display più OCA
arrivano a 2,15, quindi il pacchetto resta un millimetro sotto e nessuna
quota si muove. Il controllo è in `parametri.py` e lo spessore dell'inchiostro
è un parametro, `SERIGRAFIA_S`: **va confermato dal fornitore nel preventivo**,
perché è lui a scegliere quante passate fare, e se risponde 90 µm il controllo
chiede un OCA da 0,45.

Quell'adesivo però non deve portare il peso del pannello, perché **dietro il
display il telaio resta pieno**, senza nessuna finestra, e il modulo ci appoggia
sopra col retro. Il display risulta così in sandwich fra vetro e alluminio, con
la pressione distribuita su tutta la faccia invece che concentrata su una
cornice stretta, che è proprio il modo di farsi venire gli aloni. L'adesivo
serve a tenerlo centrato e a contatto ottico, non appeso.

Il telaio pieno risolve anche un problema che una finestra avrebbe creato: i
**quattro fori di fissaggio del Raspberry cadono in pieno nell'area del
display**, a 24,5 mm dall'asse, e in una finestra non avrebbero avuto materiale
da filettare. L'unica apertura in quella zona è l'asola da 18 x 8 per il flat,
a cavallo del bordo inferiore del modulo.

Il **telaio** si incolla al vetro con **3M VHB 4959 da 3,0 mm**, in cornice
continua sul perimetro. Lo spessore non è una scelta estetica: è il nastro che
fissa la distanza del telaio dal vetro, e quindi `Z_TELAIO`, il piano da cui
partono tutti i componenti. Con un VHB da 1,1 mm il telaio arriverebbe a
spingere sul display, che con il suo adesivo ottico occupa 2,0 mm; con i 3,0
resta invece un millimetro d'aria dietro il pannello, e i 2,5 mm della basetta
del microfono ci stanno. La schiuma assorbe anche le differenze di dilatazione
fra vetro e alluminio, che su 240 mm e 40 °C di escursione valgono qualche
decimo, e le ondulazioni del vetro temperato.

Pulire entrambe le superfici con alcol isopropilico, applicare il primer 3M 94
sull'alluminio anodizzato, premere a 15 N/cm² e attendere 72 ore prima di
sollecitare il giunto.

### Minuteria

| Quantità | Articolo | Dove |
|---|---|---|
| 6 | magnete neodimio N42 Ø4 x 3 | sedi nel telaio, tutti con la stessa polarità |
| 2 | perno inox Ø4 x 3 | centraggio sulla battuta alta, a filo del fronte del telaio |
| 1 | reed switch NC + magnete | antimanomissione, su GPIO |
| 1 | ventosa Ø30 | per estrarre il pannello |
| 4 | M2.5 x 14 + distanziali 9,5 mm | Raspberry al telaio. **Non più lunghe**: oltre i 3 mm di telaio c'è il display |
| 4 | M2 x 10 + colonnine 6 mm | camera arretrata sul telaio |
| 3 | M3 x 18 + colonnine **nylon** 14 mm | altoparlante arretrato sul telaio |
| 6 | rondella in gomma M3 | sotto flangia e testa vite dell'altoparlante |
| 2 | M3 x 6 | PN532 appoggiato al retro del telaio, senza distanziali |
| 2 | rete inox maglia 0,6 mm, 85 x 13 mm | feritoie di ventilazione, 2,5 mm di bordo per incollarla |
| 1 | squadretta in alluminio 1,5 mm, 47 x 59 piegata | tiene in piedi la scheda di ingresso, DXF 07 |
| 4 | M2.5 x 8 + dado | scheda di ingresso alla squadretta |
| 2 | M2.5 x 4 | squadretta al telaio, nei due fori **ciechi** |
| 1 | membrana acustica PTFE Ø 8 mm | fra vetro e basetta del microfono |
| 1 | anello schiuma nera, est. 10 int. 6, 1 mm | fra obiettivo e vetro |
| 6 | cavetto M-F passo 2,54 da 20 cm | prolunga del microfono fino all'HAT |
| 1 | foglio OCA 0,35 mm, 70 x 125 mm | display al vetro, in pieno. Chiedilo tagliato al fornitore del vetro |
| 1 | foglio PET nero opaco 0,2 mm, 38 x 40 mm | diaframma dietro la zona NFC |
| 1 | **3M VHB 4959**, 3,0 mm, nastro da 12 mm | cornice fra vetro e telaio. Lo spessore **non è sostituibile**: è lui a fissare la distanza vetro-telaio e tutta la catena di quote parte da lì |
| 1 | primer 3M 94 | sull'alluminio del telaio, prima del VHB |
| 6 | dischetto di acciaio dolce Ø6 x 1 | **solo se la cassa è stampata**: riscontro dei magneti, annegato nelle sedi della battuta |
| 1 | silicone neutro ossimico nero | fessura d'ombra, solo sui lati |

Il diaframma in PET serve perché l'apertura nel telaio lascerebbe intravedere
il circuito del lettore attraverso la serigrafia semitrasparente dell'icona
NFC. Il PET non è conduttivo e non disturba l'antenna, a differenza di qualsiasi
schermatura metallica.

Il silicone deve essere **neutro ossimico**, non acetico: quello acetico
libera acido acetico durante la reticolazione e corrode alluminio ed
elettronica.

## Alimentazione

Tutto arriva dal cavo di rete, in **PoE**, con il PoE HAT (F) di Waveshare
impilato fra il Pi e l'HAT audio: entrambi hanno l'header a 40 pin passante,
quindi convivono senza prolunghe. Al pannello va così un cavo solo.

Lo switch o l'injector devono essere **802.3at**, cioè PoE+, non PoE semplice.
Il PoE af consegna al carico 12,95 W e fra Pi, NVMe e display siamo sui dieci:
resterebbe un margine troppo sottile per i picchi di corrente del Pi 5
all'avvio. Con l'at il budget è 25,5 W e l'HAT eroga 5 V/4,5 A, abbondanti.

Due cose vanno fatte prima di staccare l'USB-C, e sono facili da dimenticare
perché oggi funzionano da sole.

La prima è scrivere **`PSU_MAX_CURRENT=5000` nell'EEPROM** del bootloader, con
`sudo rpi-eeprom-config --edit`. Oggi il firmware riporta `max_current` a 5000 mA
e `usb_max_current_enable` a 1, ma non perché siano configurati: li ricava dalla
negoziazione PD con l'alimentatore ufficiale da 27 W, che si dichiara capace di
5 V/5 A. L'HAT PoE inietta i 5 V sull'header GPIO e non negozia niente, quindi
quella negoziazione sparisce, i due valori tornano al default e con loro si
stringe il budget delle porte USB. Il driver del display, che prende i 5 V dal
Pi, è il primo che resterebbe a secco.

La seconda è collegare la **ventola dell'HAT al connettore FAN a 4 pin del Pi**
e non ai 5 V dell'HAT. Alimentata dall'HAT gira sempre e al massimo, perché la
sua ventola è a due fili e non ha nessun controllo; sul connettore del Pi è
pilotata in PWM, riporta i giri e sotto i 50 °C **sta ferma**. In una cassa
chiusa a pochi centimetri dal microfono è la differenza fra un fruscio continuo
in ogni chiamata e il silenzio, e vale il lavoro fatto con i distanziali in
nylon sotto l'altoparlante.

Il PoE **non** risolve l'ingombro del connettore di rete, che resta il vincolo
dei fianchi: servono comunque il patch angolato o il keystone a 90°. Lo rende
anzi più delicato, perché da quel connettore passa anche l'alimentazione e un
falso contatto non fa perdere la rete, spegne il pannello.

Infine l'HAT è un convertitore isolato con rendimento intorno all'87%: dei watt
che entrano, uno e mezzo resta dentro la cassa come calore in più rispetto
all'alimentazione via USB-C, dove la conversione avviene nel quadro. È poco ma
va nel conto della ventilazione.

### L'alimentazione dell'SSD è il punto fragile

L'adattatore NVMe non è impilato sul connettore GPIO: sta su una base sotto il
Pi, collegato dal flat PCIe, e **l'alimentazione gliela portano dei fili volanti
infilati sui pin** 5 V e massa del connettore. Che siano solo alimentazione è
verificabile: `pinctrl get` mostra che dei pin del connettore a 40 vie sono in
uso soltanto l'I2S della scheda audio, GPIO2 e 3 per l'I2C, la seriale e
GPIO16, che il kernel dichiara come `sdmode`, cioè lo shutdown
dell'amplificatore audio. Tutti gli altri risultano `none`: nessun segnale va
all'adattatore.

Il problema non è elettrico ma meccanico. Quei fili alimentano **il disco da cui
il sistema fa il boot**, e i connettori Dupont tengono per frizione: in una
scatola murata, con il ciclo termico giorno-notte e l'umidità che il tufo
trasporta, un contatto che si allenta o si ossida non degrada le prestazioni,
fa sparire il disco di avvio. Prima di chiudere il pannello vanno **rifatti
crimpati e ritenuti**, con un connettore JST a scatto o saldati direttamente,
e i fili vanno fermati con fascette perché nessuno tiri sul contatto.

Il link PCIe, intanto, va lasciato come è: `lspci` riporta `Speed 5GT/s
(downgraded), Width x1`, cioè Gen2, perché in `config.txt` non c'è
`dtparam=pciex1_gen=3`. Sul Pi 5 il Gen3 non è dichiarato supportato, e con un
flat esteso fino a una base distaccata è una scorciatoia che si paga in errori
di collegamento: 450 MB/s abbondano per un videocitofono.

### Perché gli altri due HAT restano impilati

Quello che vale per l'adattatore NVMe non si estende alla scheda audio, e il
motivo è prima geometrico che elettrico. Dislocarla sembra promettere venti
millimetri di stack, ma in pianta vuole una fascia da 65 mm e sul telaio le
fasce libere sono due, 22 mm fra il lettore NFC e il Pi e 25 fra il Pi e la
camera; ai fianchi del Pi restano 17,5 mm per lato. Non avendo dove andare, la
scheda finirebbe comunque sopra il Pi, solo appesa a dei fili invece che
all'header: il guadagno si riduce all'altezza del connettore, otto millimetri.
Gli stessi otto millimetri, e senza toccare un collegamento, si recuperano
riportando in basso i fili che oggi si infilano sui pin in cima — l'altezza
vera là sopra non la fanno i pin ma i gusci dei connettori Dupont infilati in
verticale.

E non servono. Il canale d'aria è a 20,0 mm, la cassa a 75 e la nicchia a 81,
contro i 170 che il tufo concederebbe: non c'è nessun vincolo da rilassare.

Il costo invece sarebbe concreto. I pin da portare non sono pochi: l'I2S
completo, cioè GPIO18, 19, 20 e 21, più GPIO16 per lo `sdmode`
dell'amplificatore, i 3,3 V, i 5 V dell'amplificatore, più masse, più GPIO0 e 1
se si vuole conservare il riconoscimento automatico via EEPROM, che oggi
funziona ed è il motivo per cui la scheda si dichiara come `Pi MIC V3` senza
una riga di configurazione. Fanno una decina di fili, su cui corre un clock a
3,07 MHz — 48 kHz per 32 bit per due canali — accanto ai picchi di corrente di
un amplificatore da 2 x 5 W. È il modo classico di guadagnare un ronzio e di
perdere il margine sull'eco che abbiamo misurato a 70 dB. Il microfono, poi, è
già prolungato su sei fili: dislocare anche la scheda metterebbe due stadi di
cablaggio volante in serie sull'elemento più sensibile del progetto.

### L'orientamento del Raspberry non è libero

Le misure dei connettori, prese col cavo inserito, hanno chiuso una libertà che
il progetto credeva di avere. Sul Pi 5 **l'RJ45 e il connettore PCIe stanno sul
bordo corto da 56 mm, i micro-HDMI sul bordo lungo da 85**: nel pannello il
bordo corto è orizzontale, quindi i primi due sporgono in verticale e il terzo
sporge su un fianco. E i due versi non si equivalgono, perché in verticale c'è
posto e ai fianchi ce ne sono 17,5 mm.

| Cosa esce | Sporgenza misurata | Dove va |
|---|---|---|
| Patch di rete sull'RJ45 | 34 mm | in basso, sopra il lettore NFC |
| Ansa del flat PCIe | 25 mm | in basso, fra NFC e bordo scheda |
| Cavo micro-HDMI diritto | 20 mm | su un fianco: **non ci sta** |

Da qui tre prescrizioni. L'**RJ45 va in basso**: girando la scheda il patch
andrebbe addosso all'altoparlante, che è arretrato di 14 mm e lo intercetta in
profondità, mentre in basso passa sopra il lettore NFC senza toccarlo. Serve un
**micro-HDMI con uscita angolata a 90°**, che dai 20 mm scende a 8: un cavo
diritto spinge contro la parete della cassa e fa lavorare in leva il connettore
del Pi, che sul Pi 5 è un micro e non perdona. E la **scheda video passa sul
fianco opposto**, quello del lato GPIO, dove in orizzontale non esce niente:
stava dal lato dei micro-HDMI, e lì fra il bordo del Pi e la scheda restano
3 mm, dove nemmeno il cavo angolato entra.

Restano due margini stretti, entrambi in basso e entrambi sopra il lettore NFC:
l'ansa del flat PCIe si ferma a **2 mm** dal suo bordo, e il patch di rete gli
passa sopra a **2,0 mm**, perché il connettore sta sul piano del PCB mentre il
lettore arriva più avanti. Il modello li controlla, ma sono margini di
montaggio: una fascetta che schiaccia il patch verso il vetro basta a farlo
appoggiare sul lettore.

## Ventilazione

Le due feritoie sono profonde 8 mm e larghe 80, e stanno nelle **pareti
orizzontali** della cassa, non sul fronte: il fronte è coperto interamente dal
vetro e l'aria non avrebbe modo di uscire. Si affacciano nella fessura d'ombra
fra vetro e intonaco, dove nessuno le vede. Sono 6,4 cm² per lato.

Quella sezione è il vincolo di tutto il raffreddamento, perché il muro è in
**tufo**: con 0,2-0,5 W/mK di conduttività, quattro volte meno di un laterizio
pieno, come dissipatore non esiste. Gli undici watt e mezzo di Pi, display,
scheda driver e conversione PoE devono quindi uscire tutti da qui e dal vetro. Per tenere l'aria interna
dieci gradi sopra l'ambiente serve mezzo litro d'aria al secondo e qualcosa, che
su 3,2 cm² vorrebbe dire farla correre a 2,6 m/s: troppo per un tiraggio
naturale e troppa perdita di carico anche per la ventola. Con 6,4 cm² si scende
a 1,5 m/s. I millimetri in più sono presi nella direzione della profondità,
quindi da fuori non cambia niente.

Le feritoie cadono **dietro la battuta**, a 8 mm dal fronte, non a cavallo di
essa. Il motivo non è l'aria ma i magneti: quattro dei sei stanno a x ±32, cioè
dentro la larghezza della feritoia, e i loro riscontri appoggiano proprio
sull'anello di battuta. Con la feritoia più avanti quell'anello restava tagliato
esattamente dove il magnete deve tirare. Starci dietro giova anche al flusso,
perché l'aria sbuca nel vano invece di dover girare attorno all'anello.

Il percorso dell'aria è: ingresso dalla fessura d'ombra inferiore, salita lungo
il retro del display, attraversamento del dissipatore del Pi al centro, uscita
dalla feritoia alta. Per questo il Raspberry è centrato in altezza.

I 10 mm fra telaio e PCB del Pi erano pensati come passaggio d'aria, ma nel
montaggio reale **non lo sono**: lì sotto c'è la base con l'SSD NVMe, collegata
al Pi da un flat PCIe che fa un'ansa oltre il bordo della scheda. L'aria che
entra dal basso deve quindi girare attorno a quella base invece di infilarsi
sotto il Pi, e l'SSD, che scalda, si trova nel punto più freddo del circuito
anziché nel flusso. Non è un difetto bloccante — la sezione del canale dietro
lo stack resta quella che conta — ma va saputo quando si leggeranno le
temperature della prova in cassa chiusa.

Il telaio non ha feritoie proprie, e non servirebbero: davanti a lui c'è il
vetro incollato, quindi quel volume è chiuso, e l'aria circola tutta nel vano
dietro, dove le due feritoie della cassa si affacciano direttamente.

Dalla feritoia superiore esce anche il suono dell'altoparlante: la griglia sul
vetro non è forata, il vetro lì è pieno. Il vano fa da camera di compressione e
la feritoia da porta d'uscita, che per la voce è più che sufficiente.

Le tre strisce della griglia sono però **finestre nella serigrafia**, cioè vetro
nudo, non inchiostro: attraverso di loro si vede quello che c'è dietro. Dietro
c'è la luce dell'altoparlante nel telaio, da 213 a 226, con il cono arretrato di
14 mm; una fessura larga 1,5 mm su 14 mm di profondità lascia passare lo sguardo
solo in perpendicolare, quindi da fuori si legge come una griglia nera su nero.
È anche il motivo per cui la quota della prima striscia non è libera: a 223 la
terza arrivava a 231,5, in pieno sulla fascia dei due magneti alti e dei due
fori dei perni, che si sarebbero visti in trasparenza come quattro buchi.

Per questo l'altoparlante **non si affaccia al vetro**: sta arretrato di 14 mm
dal retro del telaio, su tre colonnine, abbastanza indietro da scavalcare la
camera. Il cono guarda il telaio e carica la cavità in cui si apre la feritoia,
che resta più avanti e libera. È quel che consente di usare un cono ovale da
70 x 32 invece di un piccolo receiver: in quella posizione lo spazio c'è, sulla
faccia del telaio no. Le viti sono tre e non quattro perché il quarto foro
cadrebbe dietro la basetta del microfono.

Le colonnine però vanno in **nylon, non in metallo**, con una rondella di gomma
sotto la flangia e sotto la testa della vite. Non è una finezza: il microfono è
incollato al vetro, il vetro è incollato al telaio e il telaio porta
l'altoparlante, quindi esiste un percorso rigido dal cono al microfono che non
passa per l'aria. La cancellazione d'eco lavora bene sull'eco acustica — misurata
sull'impianto, `module-echo-cancel` con backend WebRTC abbatte 70 dB — ma
l'accoppiamento strutturale le arriva in anticipo e distorto, ed è quello che le
riesce peggio. Il VHB fra vetro e telaio è già una schiuma viscoelastica e
smorza; nylon e gomma chiudono l'altra metà del percorso.

Il microfono non va lasciato libero nel vano, altrimenti raccoglie il fruscio
della ventola e lo manda in chiamata. L'HAT audio MIC+ V3 lo monta su una
**basetta staccabile**, collegata da sei fili a passo 2,54 (3V3, GND, BCLK,
DOUT, WB, SEL) e dichiarata prolungabile: si stacca dallo stack e si incolla
alla faccia interna del vetro, dietro al foro da 3 mm, con la membrana PTFE e
un anellino di schiuma che fa tenuta. Così il microfono è accoppiato all'aria
esterna e non al vano. Sta nei 3,0 mm fra vetro e telaio, cioè nello spessore
che più in basso occupa il display: il pettine a sei pin va dissaldato e i fili
saldati ai pad, perché da solo è alto 8,5 mm, e nel telaio basta allora
un'asola di passaggio da 12 x 4. È il motivo per cui nel progetto non esiste
nessun setto acustico, che del resto chiuderebbe l'uscita dell'aria calda.

Lo stesso HAT porta anche **due altoparlanti saldati a bordo**, che vanno
disattivati con i due microswitch sul retro della scheda: suonerebbero chiusi
dentro il vano, contro il fondo della cassa. L'altoparlante del videocitofono è
quello sui morsetti a vite, dietro la griglia serigrafata.

Entrambe le feritoie vanno chiuse con rete inox a maglia 0,6 mm: ferma insetti e
ragni, che in un vano caldo e riparato ci entrano nel giro di una stagione.

La fessura d'ombra va sigillata con silicone **solo sui due lati verticali**.
Sopra e sotto deve restare aperta: è l'unica via d'aria, e in basso fa anche da
scarico della condensa.

C'è un dettaglio di cantiere che decide se la ventilazione funziona o no. Le
feritoie non si affacciano direttamente all'esterno, ma nel canale che resta
dietro l'aggetto del vetro, fra il fianco della cassa e lo spigolo
dell'intonaco. Quel canale **non deve essere riempito dal rasante**: va
protetto con un profilo a perdere o una striscia di schiuma durante la
rasatura, da togliere dopo. Se si stucca, le feritoie restano cieche e la
scatola si comporta come se fossero chiuse.

Con questa geometria la stima è **50 °C a riposo e 72 °C di picco** con 35 °C di
ambiente esterno, contro gli 85-90 °C che si misurerebbero in una scatola
chiusa. Il margine di throttling del Pi 5 è a 80 °C.

Quei numeri sono la giunzione del Raspberry, non il pannello, e la distinzione
conta perché **un OLED ha un campo di funzionamento più stretto di un LCD**:
tipicamente fino a 50 °C contro 70, e l'invecchiamento dei pixel accelera col
calore. Il pannello sta però dalla parte giusta del telaio, incollato al vetro e
affacciato all'aria esterna, con tre millimetri di alluminio e tutto il canale
di ventilazione fra sé e il dissipatore. La sua temperatura segue quindi quella
del vetro, non quella del processore — ed è un'altra ragione per la posizione
riparata, perché un vetro nero al sole diretto arriva a 60 o 70 °C da solo,
indipendentemente da cosa c'è dietro.

## Il display: 350 nit, e perché bastano solo grazie all'AR

Il pannello è un **Wisecoco 1080 x 1920** (l'EDID lo dichiara così) su HDMI, con
**350 cd/m² di luminanza massima**, 60 Hz, copertura 100% sRGB e **touch
multi-punto integrato nel pannello**, non una lastra separata incollata sopra.
Questo chiude l'ultima incognita che teneva fermo l'ordine del vetro: dietro il
vetro non c'è nulla di più spesso di quanto il progetto conti.

350 cd/m² sono un valore modesto per un apparecchio all'aperto, dove i prodotti
dichiarati sunlight readable stanno fra 800 e 1000, e il motivo per cui qui
funziona è tutto nel trattamento del vetro.

Quello che rende illeggibile un display all'esterno non è la sua luminanza, è il
velo di luce riflesso dalla superficie. Vale \(L = E \cdot R / \pi\), dove `E`
è l'illuminamento sulla facciata e `R` la riflettanza del sistema vetro più
pannello. Con il vetro AR e l'incollaggio OCA a tutta superficie, che elimina
l'interfaccia aria-vetro interna, `R` sta intorno all'**1,5%**; un vetro nudo
appoggiato sul display, con il suo strato d'aria, arriva all'8%.

| Condizione | Illuminamento | Velo con AR+OCA | Contrasto |
|---|---|---|---|
| Sole diretto sul vetro | 40 000 lux | 191 cd/m² | 1,8 : 1 |
| Sole radente | 20 000 lux | 95 cd/m² | 3,7 : 1 |
| Ombra luminosa | 8 000 lux | 38 cd/m² | 9 : 1 |
| Cielo coperto | 2 000 lux | 10 cd/m² | 37 : 1 |

Prendendo 3 : 1 come contrasto minimo per leggere senza fatica, la soglia è a
**24 000 lux**: ci sta tutto tranne il sole che batte diretto sul vetro. Gli
stessi 350 nit dietro un vetro senza AR e senza OCA avrebbero una soglia di
4 600 lux, cioè sarebbero già illeggibili all'ombra di una giornata serena. Le
due lavorazioni che sembravano un vezzo estetico sono quindi quelle che tengono
in piedi la scelta del pannello, e questo sposta la domanda da "quanti nit
serve il display" a **"dove guarda la parete"**.

### Il pannello è OLED, e questo cambia il problema della notte

La scheda del prodotto dice **OLED**, e poi dice anche "design IPS" e
"contrasto 17000:1": le due cose non stanno insieme, perché IPS è una
tecnologia a cristalli liquidi e un contrasto finito è un numero da LCD. Testo
di marketplace, copiato male. La questione è però stata chiusa in due modi
indipendenti, e **il pannello è OLED**.

Il primo è il calibro: **il pannello nudo misura 0,4 mm.** Un LCD IPS da 5,5
pollici non può starci dentro, perché oltre al sandwich di cristalli liquidi fra
due lastre di vetro — 0,5 o 0,7 mm già da solo — gli serve il **backlight**,
cioè riflettore, guida di luce, diffusori e fila di LED: altri quattro o cinque
decimi, nella migliore delle ipotesi. Un pannello da 0,4 mm che si ripiega su
una coda FPC è un OLED flessibile da smartphone e non può essere nient'altro.

Il secondo è la prova diretta, fatta sul pezzo collegato con mezzo schermo nero
e mezzo bianco. Il nero è **indistinguibile dalla cornice spenta**, con i bordi
che si riconoscono a fatica, e soprattutto **resta nero guardandolo di sbieco a
45 gradi**. È la prova che vale: lo *IPS glow* non è un difetto di qualità, è
strutturale — i cristalli liquidi perdono allineamento fuori asse e un IPS
schiarisce sempre al grigio o al violaceo. Un pannello che non lo fa non ha
cristalli liquidi dietro.

(La terza prova, il calore sulla sola metà bianca, non ha dato segnale: su 5,5
pollici a 350 nit il delta è di frazioni di watt e il vetro del pannello lo
spalma. Non contraddice, semplicemente non è sensibile.)

Via software la tecnologia non si legge: l'EDID dichiara solo "Wisecoco" su una
scheda driver generica — vendor `CVT`, settimana 32 del 2018 — e l'EDID 1.3 non
ha un campo per la tecnologia del pannello. Il rail HDMI del Pi assorbe 6 mA,
cioè solo la EEPROM dell'EDID, perché il display è alimentato dal suo USB-C: per
la stessa ragione il consumo non si può pesare dal Raspberry, e il 5V non mostra
alcuna correlazione col contenuto a schermo.

Da questo seguono tre cose, e la prima capovolge quello che il progetto dava per
perso.

**Il dimming notturno si risolve in software.** Su un OLED non c'è backlight da
pilotare: ogni pixel emette per conto suo, e abbassare i valori dell'immagine
abbassa davvero la luce emessa. Il sistema gira su `labwc`, cioè Wayland con
`wlr-gamma-control`, quindi la rampa si attenua senza hardware aggiuntivo e
senza alcun pin da cercare sulla scheda. Su un LCD la stessa operazione è il
peggiore dei rimedi — il nero diventa grigio illuminato e di notte si vede un
rettangolo lattiginoso — ma su OLED è il modo giusto, non un ripiego. Cadono
quindi entrambe le altre strade, e non è una perdita: il ~~DDC/CI~~ era già stato
provato e non risponde (sul bus `/dev/i2c-14` c'è solo la EEPROM dell'EDID a
`0x50`, l'indirizzo `0x37` è muto), e l'~~ingresso PWM di dimming~~ non esiste
perché non c'è un backlight da dimmerare. GPIO12 e GPIO13 restano liberi.

**Il nero è nero, e il vetro nero funziona per davvero.** Un pixel spento su
OLED non emette: a display acceso ma interfaccia scura, il pannello è
indistinguibile dal vetro intorno. È esattamente l'effetto che lo stile Ekinex
cerca, e su un LCD IPS non si otterrebbe — il backlight filtra sempre, il nero
è grigio e di sbieco si vede il rettangolo del display anche a schermo spento.
In più il consumo e il calore seguono il contenuto: un'interfaccia nera
consuma una frazione di una bianca, che per un apparecchio chiuso in una cassa
murata non è un dettaglio.

**Il burn-in diventa il rischio principale del software.** È il rovescio della
medaglia, e per un videocitofono è un rischio concreto, perché l'interfaccia
sta ferma per anni: gli stessi pulsanti, lo stesso orologio, la stessa barra.
Un LCD se ne infischia, un OLED no. Quattro accortezze, tutte gratuite:

- **schermo spento quando nessuno lo guarda**, non uno screensaver: è la
  mitigazione che conta più di tutte le altre insieme, e il progetto la vuole
  già per il consumo e per non fare da lampione. Oggi non lo fa: dopo 60
  secondi l'app entra nello stato `screensaver` e **ci resta per sempre**, al
  20% ma accesa. Lo strumento però c'è già: `install.sh` installa `wlr-randr`,
  che in tutto il progetto non viene mai chiamato con `--off`;
- **sfondo nero e pochi elementi luminosi**, che è già lo stile scelto: su OLED
  il nero non invecchia, perché il pixel è spento;
- **luminosità bassa di default**, perché l'invecchiamento va con la corrente:
  i 350 nit servono contro il sole, non alle nove di sera;
- **spostare di qualche pixel gli elementi fissi**. Qui l'interfaccia ne ha
  uno vero e grosso: lo screensaver scrive l'indirizzo in `96sp` grassetto,
  chiaro su nero, **sempre nella stessa posizione**, ed è lo stato in cui il
  pannello passerà quasi tutta la sua vita. Non era un rischio teorico, era
  l'unico elemento statico del progetto che un OLED può imprimere, ed è
  **fatto**: `ScreensaverScreen` sposta il blocco di 8 dp lungo un giro di nove
  posizioni, una ogni tre minuti, con il giro che riprende da dove era rimasto
  invece di ripartire dal centro a ogni rientro. Il `padding` di 32 dp assorbe
  lo spostamento, quindi niente si avvicina ai bordi.

### Come si attenua, in pratica

**È già fatto, e per il motivo giusto.** L'interfaccia non è una pagina in un
browser, è l'app Kivy in `installer-rpi/app/`, e `modules/brightness.py` cerca
un backlight in `/sys/class/backlight`, non lo trova — il display è in HDMI —
e ricade sul *software dim*: un rettangolo nero fullscreen di cui `main.py`
anima l'alpha. Su un LCD sarebbe un trucco a metà, perché il backlight resta
acceso dietro e il nero diventa grigio. Su OLED è la cosa fisicamente corretta:
abbassare il valore del pixel **spegne il pixel**.

E l'effetto è più forte di quanto la formula lasci pensare. L'alpha agisce sui
valori RGB, ma l'emissione segue il gamma: `brightness_idle_pct: 20` dà un
alpha di 0,68, i valori scendono al 32% e la luce emessa a 0,32 ^ 2,2 ≈ **7%**,
cioè una ventina di nit sui 350. Di notte è quello che serve.

Resta disponibile, se un giorno servisse agire su tutto l'output e non solo
sull'app, `gammastep -b 0.35`, che parla `wlr-gamma-control` e sta nei repo
Debian (2.0.9, non installato); `wlsunset` 0.2.0 regola solo la temperatura
colore. Ma non serve: la soglia giorno/notte la dà Home Assistant, che sa già
a che ora siamo, e i due `brightness_*_pct` sono già in configurazione.

### L'esposizione della parete

Il citofono va **in posizione riparata, dove il sole non batte mai diretto sul
vetro**: un portico, una pensilina, un sottobalcone. È la condizione che
cancella l'unica riga critica della tabella sopra. Il caso peggiore che il
pannello vedrà davvero è il sole radente, 3,7 : 1, e nella pratica starà
sull'ombra luminosa, 9 : 1. Da qui in avanti la leggibilità diurna non è più un
problema aperto, a condizione che **l'AR e l'incollaggio OCA restino nella
specifica del vetro**: sono loro a fare il lavoro, non i nit.

## I render e i due filmati

In `render/` ci sono due serie di immagini e i filmati che se ne ricavano. Non
sono disegni e non vanno misurati: servono a vedere il risultato prima di
scavare il muro, e un paio di cose le hanno già fatte emergere.

**`installazione.mp4`**, dai cinque fotogrammi `inst-*.jpg`, segue l'ordine
della procedura in `ASSEMBLAGGIO.md`: la nicchia scavata nel tufo con i due
corrugati che arrivano dal fondo, la cassa murata nella malta fresca con la
flangia sotto il filo dell'intonaco finito, il telaio portante che entra con il
suo gruppo di schede e il cavo di rete già innestato, il vetro che si posa sui
magneti, il pannello finito a filo della parete.

**`giorno-notte.mp4`**, dai cinque `func-*.jpg`, mostra il funzionamento:
riposo diurno all'ombra del portico, la chiamata col dito sul vetro, poi la
notte in due versioni, **a piena luminosità e attenuata**, e infine un
visitatore illuminato dal solo schermo.

Il filmato notturno è quello che vale la pena guardare due volte, perché il
confronto fra il terzo e il quarto fotogramma è esattamente il problema dei
350 nit lasciati al massimo di notte: nel primo il pannello illumina l'intonaco
per quaranta centimetri intorno a sé e si comporta da lampada, nel secondo resta
leggibile senza invadere la facciata. Essendo il pannello OLED, il secondo
fotogramma è ottenibile in software, e i render descrivono quindi una cosa che
si può fare e non un desiderio. Il quinto fotogramma mostra
l'altro problema aperto, l'illuminazione del volto: lo schermo da solo lo
illumina dal basso e lascia le orbite in ombra, che è la peggiore luce
possibile per il riconoscimento facciale.

I filmati non portano didascalie perché l'`ffmpeg` installato è compilato senza
`libfreetype` e il filtro `drawtext` non c'è; le fasi sono quelle elencate qui
sopra. `monta-video.sh` li rigenera dai fotogrammi, con una dissolvenza di 0,8 s
e una lenta carrellata di zoom su ciascuno, e ne ricava le GIF di anteprima.

## Montaggio

La procedura completa, passo per passo e con i collegamenti elettrici, è in
[ASSEMBLAGGIO.md](ASSEMBLAGGIO.md). In sintesi l'ordine è: preparazione e
anodizzazione del telaio, montaggio dell'elettronica sul retro, **collaudo a
banco**, muratura della cassa, incollaggio del vetro, inserimento del gruppo e
sigillatura.

Due passaggi sono irreversibili: la muratura della cassa e l'incollaggio del
vetro. Il collaudo a banco viene prima di entrambi e non è facoltativo.

Il gruppo vetro-telaio-elettronica si tiene su sei magneti e si estrae come
pezzo unico con una ventosa sul vetro. Non esiste nessuna vite: sul fronte
finirebbe sotto il vetro incollato, dal basso avrebbe la testa annegata nella
malta, e la fessura d'ombra da 3 mm non lascia passare una chiave. È il motivo
per cui il pannello è pulito.

Al posto della vite di sicurezza c'è un **reed switch** sul retro del telaio,
con il magnete sulla battuta: se qualcuno stacca il pannello, il Raspberry lo
rileva su GPIO e lo segnala a Home Assistant, che ha già la camera sul posto.
È una protezione più utile di una vite, che comunque si svita.

## Cosa hanno cambiato i pezzi reali

Le prime misure col calibro hanno confermato quasi tutto, ma tre
**osservazioni** — non tre numeri — hanno cambiato il disegno più di qualunque
millimetro. Vale la pena saperlo in anticipo: su questi componenti la quota che
conta non è la dimensione, è da che parte guarda.

### Il microfono va saldato dal lato sbagliato

La basetta I2S è una striscia da 15,5 x 6,5, non il quadratino che il progetto
assumeva, e sta in 2,5 mm col microfono sopra: ci entra nei 3,0 mm fra vetro e
telaio. Ma **l'apertura acustica è sulla faccia dei pin**, non su quella delle
saldature, e quella faccia va rivolta al vetro perché il foro del vetro è lì.
I fili vanno quindi saldati dalla faccia opposta, infilandoli nei fori del
pettine dissaldato: saldarli sulla faccia a vista vorrebbe dire mettere lo
stagno fra la basetta e il vetro.

### L'antenna del PN532 non è centrata

Il lettore è 60 x 38, e la spira sta in 32,3 x 35 **spostata di 11,5 mm** verso
il lato del connettore USB-C: l'altra metà della scheda è elettronica. Il
progetto metteva l'apertura del telaio e l'icona NFC in mezzo al lettore, cioè
sopra i componenti. Quattro conseguenze, tutte in `parametri.py`:

- il PCB resta centrato (`NFC_PCB_X = 0`), perché così il cavo USB-C sta nel
  fianco del vano invece di sbattere contro la parete;
- l'icona sul vetro si sposta a `NFC_X = -11,5`, sopra la spira, perché è lì che
  il telefono va avvicinato;
- l'apertura nel telaio scende a 30 x 32 e cade **dentro** la spira, non attorno
  alla scheda: 3 mm di appoggio su tutti i lati, e alluminio risparmiato
  esattamente dove serve filettare;
- si filettano **due fori invece di quattro**, entrambi dal lato
  dell'elettronica, perché dal lato della spira i fori della scheda cadrebbero
  a filo dell'apertura. `posizioni_fori_nfc()` li calcola.

### Il display è più sottile dell'assunto

Il pannello è 70 x **125**, non 123, e i due millimetri in più sono tutti
cornice: 0,98 mm sui fianchi, 2,02 sopra e sotto. Sui fianchi resta il vincolo
più stretto del progetto, ed è il motivo per cui l'adesivo ottico in pieno è
obbligatorio e non una preferenza.

L'altra quota è lo spessore col flat ripiegato: **1,8 mm invece di 3,0**. Il
pannello nudo è 0,4, cioè una lastra di vetro, e il resto è coda ripiegata.

Qui c'era un errore di impostazione nel progetto, che la misura ha fatto
emergere. `Z_TELAIO` — il piano da cui partono tutti i componenti — era
calcolato come vetro più adesivo ottico più display, cioè come se fosse il
display a tenere lontano il telaio. Non è così: **il telaio lo tiene il suo
biadesivo**, una cornice di VHB da 3,0 mm, e il display gli sta dietro senza
toccarlo. Con il display misurato la differenza salta agli occhi, perché 3,0 mm
di nastro contro 2,0 di display più adesivo non si conciliano: la schiuma non si
comprime di un millimetro.

`Z_TELAIO` dipende ora dal più spesso dei due incollaggi, che è quello del
telaio, e dietro il display restano **1,0 mm d'aria**. Vanno bene: il pannello è
incollato in pieno al vetro con l'adesivo ottico, che su una lastra da 0,4 mm
basta e avanza, e la coda ripiegata resta libera invece di essere schiacciata
dall'alluminio. Un VHB da 2,0 mm esiste, ma la schiuma più spessa assorbe meglio
le ondulazioni del vetro temperato e le dilatazioni differenziali.

Il risultato è che **la misura del display non ha spostato quasi niente**: la
profondità usata passa da 58,2 a 58,0 mm. Il componente che quei 3,0 mm li usa
per intero è il microfono, con la sua basetta da 2,5, e `verifica()` ora
controlla sia che ci stia sia che il nastro del telaio non sia più sottile di
display più adesivo.

### La scheda del display è in due pezzi, e vanno entrambi sul fianco

Non è un pezzo unico: è una **scheda di ingresso** quadrata, 43 x 43 x 4,5, con
HDMI-A e USB-C, più una **schedina terminale** da 39 x 20 x 2,0 col connettore
del pannello, unite da un flat largo 25 e lungo 95. Tutto più piccolo
dell'assunto, e lo spessore è meno della metà.

Vanno entrambe in piedi sul fianco sinistro, la terminale cinque centimetri
sotto l'altra, e non è una preferenza: in piano non c'è posto, perché la fascia
sotto il Pi è occupata dall'ansa del flat PCIe e dal patch, e quella sopra è
fuori dalla portata dei 100 mm del flat del pannello. Il fianco destro è quello
dei micro-HDMI. A quell'altezza i due flat arrivano entrambi, con un quarto di
margine per le curve, e `verifica()` controlla le due distanze.

L'**HDMI-A** resta il punto delicato anche se non sporge dal PCB: al connettore
si innesta un plug da una ventina di millimetri di guscio più la curva del cavo,
e il fianco è largo 17,5. Va girato verso l'interno del vano, non verso la
parete.

La **coda del pannello** si ripiega dietro, quindi rientra nell'1,8 complessivo
e non chiede né svasature né asole: dall'asola del telaio, che scende da 24 a
18 mm, passa solo il flat largo 13.

Il percorso dei flat, i 3.0 mm dietro il vetro e la posizione delle due schede
sono disegnati in `cad/06-gruppo-display.dxf`.

### La squadretta, perché il biadesivo qui non basta

La scheda di ingresso era l'unico componente del progetto a non avere un
fissaggio: la procedura diceva "biadesivo o una squadretta", che è un modo di
rinviare la decisione. Ma su quella scheda si innesta e si disinnesta il **plug
HDMI-A**, e un adesivo che prende quella leva a sbalzo cede. Ora il pezzo
esiste, è in `cad/07-staffa-e-pezzi-piani.dxf`: una L di lamiera d'alluminio da
1,5 mm, 47 x 59 di sviluppo, una piega sola.

Due cose l'hanno disegnata, e nessuna delle due era prevedibile a mano:

- **l'ala corta non può superare i 12 mm.** Il controllo delle interferenze l'ha
  bocciata al primo tentativo da 14: oltre quella misura va sotto la piastra
  dell'NVMe, che comincia a x −25,5 e sta esattamente alla stessa quota;
- **i suoi due fori nel telaio devono essere ciechi.** Cadono nell'ombra del
  display, perché il pannello è largo 70 su un telaio da 89 e un punto comodo
  fuori da quell'ombra non esiste. Il fronte del telaio ha il pannello a 1 mm:
  un foro passante, e la punta della vite lo trova. Vanno quindi filettati M2.5
  **dal retro, profondi 2 su 3 di spessore**, e il disegno del telaio li marca
  come tali. È l'unica lavorazione cieca di tutto il progetto, ed è segnata in
  tre posti perché dimenticarla costa il display.

L'ala lunga sta dalla parte del fianco e non verso l'interno: da quel lato
restano 5 mm fino alla parete della cassa, che bastano per le teste delle viti,
mentre verso l'interno ce ne sono 3 e ci passa il Pi.

## Da verificare prima di ordinare

Il rilievo col calibro è finito e sta in [MISURE.md](MISURE.md), pezzo per
pezzo. **Il vetro si può ordinare**: il touch è integrato nel pannello e non è
una lastra separata, che era l'ultima cosa capace di muovere il piano da cui
parte tutto il progetto.

Restano un'osservazione — su quale bordo sta il connettore del flat, su ciascuna
delle due schede del display, che cambia il montaggio e non le lavorazioni — e
due quote su pezzi non ancora acquistati: l'impedenza dell'altoparlante e il
reed switch. Nessuna delle tre blocca una produzione.

Quanto all'**altezza del gruppo del Pi**, era da riprendere col calibro prima di
scavare, perché il gruppo e il canale d'aria si scambiano i millimetri uno a
uno. La quota da prendere è una sola e il riepilogo di `parametri.py` la stampa:
dal piano del telaio alla cima dei pin, oggi 50 mm, che si spartiscono in 10 mm
di base NVMe sotto il Pi e 40 di HAT sopra. Con 50 la cassa sta a 75, con 58,2
di componenti davanti e 20,0 mm di canale libero fra il pezzo più profondo e il
fondo interno della cassa. Il canale diventa più stretto delle feritoie, e
quindi il collo di bottiglia del raffreddamento, solo sotto i 7 mm, cioè con un
gruppo da 64: ci sono quattordici millimetri fra la misura e il limite, che
bastano anche a coprire i gusci dei connettori infilati sui pin in cima.

Le quote dell'**altoparlante** non sono più stimate: 69,5 x 30,5 x 16,5 con
fori da 3,5 a interasse 63,5 x 24, dentro il millimetro e mezzo dalle stime
fatte sulla foto, quindi i tre fori filettati nel telaio restano dove erano.

Quelle della **camera** invece non sono più stimate: vengono dal product brief
ufficiale del Camera Module 3, nella variante standard che `libcamera` riporta
come `imx708`. Due hanno cambiato il progetto. L'obiettivo sporge 11,3 mm dal
retro del suo PCB contro i 6,0 mm che ci sono fra telaio e vetro, quindi la
scheda **non può appoggiare al telaio** e va arretrata su colonnine da 6 mm,
col barilotto che attraversa il foro e si ferma a 0,7 mm dal vetro. E l'asse
ottico sta a 14,5 mm dal bordo del connettore, mentre i quattro fori stanno a
2,0 mm dallo stesso bordo con interasse 12,5: l'asse è quindi **6,25 mm fuori
dal centro dei fori**, che in pratica vuol dire che la fila di fori opposta al
connettore cade sull'asse dell'obiettivo. Nel telaio i fori sono decentrati di
altrettanto. Qui vanno tenuti distinti due decentramenti che è facile
confondere: quello dei fori, 6,25 mm, che serve a filettare il telaio, e quello
del centro del PCB, 2,569 mm, che serve solo a sapere dove finisce la scheda.

La finestra dell'ottica non è una quota estetica: si comporta come un diaframma
davanti all'obiettivo, e `finestra_ottica_minima()` la calcola dal campo
diagonale e dalla distanza dal vetro. Per i 75° della variante standard servono
8,5 mm e il disegno ne porta 10, con margine. Con la variante **wide**, che per
un citofono sarebbe la scelta naturale, i 120° diagonali ne chiederebbero 11,6
e l'altezza maggiore lascerebbe solo 0,2 mm per il paraluce: è un cambio da
decidere prima di ordinare il vetro, non dopo.

Se una di queste quote cambia, correggere `parametri.py` e rigenerare: il
controllo di interferenza dirà subito se il nuovo ingombro entra ancora.
