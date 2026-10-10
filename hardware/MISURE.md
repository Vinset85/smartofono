# Scheda di rilievo

Le quote che il progetto assumeva e quelle misurate sui pezzi reali, pezzo per
pezzo. Dove la colonna "reale" è vuota la quota non è ancora stata presa; dove
c'è, `parametri.py` la porta già e quanto ne è seguito è scritto sotto la
tabella. Il modo di usare questo file non cambia: si compila, si corregge
`parametri.py`, si rigenera, e il controllo di interferenza dice subito se
qualcosa non entra più. È così che sono venute a galla quasi tutte le
conseguenze elencate qui.

## Cosa resta

**Il rilievo col calibro è finito.** Sono state prese tutte le quote dei pezzi
che si avevano in mano: lo stack del Pi, il muro, l'altoparlante, il microfono,
il PN532, il pannello con la sua coda, il suo flat e le due schede del display.
La camera non si misura perché viene dal datasheet ufficiale.

Il **touch è integrato nel pannello**, confermato dalla scheda del prodotto: non
è una lastra separata, e quindi dietro il vetro non c'è nulla di più spesso di
quanto il progetto conti. Era l'ultima cosa che poteva muovere il piano da cui
parte tutto, e **il vetro si può ordinare.**

Resta un'osservazione e restano due quote su pezzi non ancora acquistati:

1. su quale **bordo** sta il connettore del flat, su ciascuna delle due schede
   del display: da quello dipende come si girano in piedi sul fianco. Non
   cambia nessuna lavorazione, cambia il montaggio.
2. l'**impedenza dell'altoparlante**, dall'etichetta, e il **reed switch**, che
   non è ancora stato scelto. Entrambe rifiniscono quote già prudenti.

La ~~piazzola di dimming del backlight~~ non serve più: il pannello è un OLED,
non ha backlight, e la luminosità si abbassa in software. L'argomento è lo
spessore misurato — 0,4 mm per il pannello nudo, dove un LCD IPS vorrebbe
almeno il doppio solo per il suo backlight — ed è spiegato nel
[README](README.md#il-pannello-è-oled-e-questo-cambia-il-problema-della-notte).

Il gruppo del display, che è quello che il rilievo ha cambiato di più, ha un
foglio suo: `cad/06-gruppo-display.dxf`, con l'anteprima in
`anteprime/06-gruppo-display.png`. Mostra i 2,0 mm dietro il vetro, il percorso
dei due flat e dove vanno le due schede.

## Quello che il rilievo ha cambiato

Le misure hanno confermato quasi tutto, e il progetto non è stato rifatto da
nessuna parte. Ma cinque cose sono cambiate, e nessuna era un numero sbagliato
di poco: erano tutte **osservazioni**, cioè cose che si guardano e non si
misurano.

1. **L'apertura acustica del microfono sta sul lato dei pin**, quindi i fili
   vanno saldati dalla faccia opposta (sezione 7).
2. **L'antenna del PN532 non è centrata**, e la zona NFC del telaio è stata
   ridisegnata: apertura più piccola e spostata, due viti invece di quattro
   (sezione 5).
3. **I micro-HDMI del Pi escono sul fianco**, non in basso, e questo ha fissato
   l'orientamento del Raspberry e imposto il cavo angolato (sezione 2).
4. **Il display è spesso 1,8 e non 3,0**, e questo ha smascherato un errore di
   impostazione: la distanza del telaio dal vetro la fissa il biadesivo del
   telaio, non il display (sezione 1).
5. **La scheda del display è in due pezzi**, e vanno entrambi sul fianco
   sinistro (sezione 3).

## 1. Il modulo del display — misurato

| Quota | Assunta | Reale |
|---|---|---|
| Pannello, bordi inclusi | 70 x 123 | **70,0 x 125,0** |
| Cornice, in larghezza | 1,0 | **0,98** |
| Cornice, in altezza | 1,0 | **2,02** |
| Spessore del solo pannello | — | **0,4** |
| Spessore col flat ripiegato | 3,0 | **1,8** |

Due millimetri in più in altezza, e sono tutti cornice: **la cornice non è
uniforme**, 0,98 mm sui fianchi e 2,02 sopra e sotto. Sui fianchi resta quindi
il vincolo più stretto del progetto — su un millimetro non si incolla un
biadesivo perimetrale, e l'adesivo ottico in pieno diventa una scelta
obbligata — ma sopra e sotto c'è il doppio di superficie. La finestra
serigrafata del vetro sborda di 0,5 mm per lato sulla cornice, e il controllo
di interferenza ora verifica che ci resti dentro: su 0,98 mm basta mezzo
millimetro di troppo per vedere il bordo del pannello.

Il pannello nudo è **0,4 mm**, cioè una lastra di vetro: l'1,8 complessivo è
quasi tutto coda ripiegata.

### L'1,8 invece di 3,0 ha fatto emergere un errore di impostazione

Era la quota più importante che restava, e il valore reale è più piccolo
dell'assunto. Ma `DISPLAY_MODULO_S` non era lo spessore di un componente fra
tanti: `Z_TELAIO` — il piano da cui partono tutti gli altri — era calcolato
come vetro più adesivo ottico più display, cioè come se fosse il display a
tenere lontano il telaio.

Non è così. **Il telaio lo tiene il suo biadesivo**, una cornice di VHB da
3,0 mm, e il display gli sta dietro. Con i numeri assunti la cosa non si vedeva,
perché display più adesivo facevano 3,2 e il nastro 3,0; coi numeri misurati
fanno 2,0, e un nastro da 3,0 mm non si comprime di un millimetro.

`Z_TELAIO` dipende ora dal più spesso dei due incollaggi, e dietro il display
restano **1,0 mm d'aria**. Vanno bene: il pannello è incollato in pieno al vetro
con l'adesivo ottico, che su una lastra da 0,4 mm basta e avanza, e la coda
ripiegata resta libera invece di essere schiacciata dall'alluminio.

Il risultato è che la misura **non ha spostato quasi niente**: profondità usata
da 58,2 a 58,0 mm, cassa e nicchia identiche. Il componente che quei 3,0 mm li
usa per intero è il microfono, con la sua basetta da 2,5, e `verifica()` ora
controlla sia che ci stia sia che il nastro del telaio non sia più sottile di
display più adesivo. È la prova che il valore di questa scheda non sta nei
numeri che conferma ma nelle impostazioni sbagliate che smaschera.

### La coda — misurata

| Quota | Assunta | Reale |
|---|---|---|
| Larghezza | — | **70,0**, cioè tutto il pannello |
| Quanto sporge sotto il bordo | 0 | **28,0** |
| Spessore | — | **0,5** |
| Si ripiega dietro? | — | **sì** |

Ripiegata rientra nell'1,8 complessivo, quindi non chiede né svasature né
asole: dall'asola del telaio passa solo il flat. Se non si ripiegasse
scenderebbe nella fascia sotto il display, dove fino al lettore NFC ci sono
9,5 mm; `DISPLAY_CODA_RIPIEGATA` tiene in vita quel controllo.

### Il flat del pannello — misurato

| Quota | Assunta | Reale |
|---|---|---|
| Larghezza | 20 | **13,0** |
| Lunghezza fino al connettore | — | **~100**, con curve |
| Posizione dell'asse | centrato | **centrato**, confermato |
| Le due linguette rigide | ? | **ancoraggi**, spesse come il flat |
| Da quale bordo esce | inferiore | confermato |

Le linguette erano l'unico dubbio che avrebbe costretto a rifare l'asola più
larga: essendo spesse come il flat, ci passano. L'asola scende invece da 24 a
**18 mm**, che è il flat misurato più due e mezzo di gioco per lato.

Il **touch è integrato nel pannello**: non è una lastra separata incollata
sopra, e quindi non aggiunge spessore dietro il vetro. Viaggia nello stesso
flat, e il suo USB esce dalla scheda di ingresso.

## 2. Stack del Raspberry — misurato

| Quota | Assunta | Reale |
|---|---|---|
| Altezza del gruppo, **dal telaio** alla cima dei pin liberi | — | **40,5** |
| Altezza del gruppo, **coi Dupont dell'NVMe innestati** | 50,0 | **50,0** |
| L'HAT audio sporge oltre il profilo del Pi? | no | **no** |
| Sporgenza del RJ45 dal bordo PCB, **con cavo inserito** | — | **34** |
| Sporgenza del micro-HDMI, **con cavo inserito** | — | **20** |

I 50 mm sono esattamente il valore che il progetto assumeva, quindi la cassa
resta a 75 e il canale d'aria a 20,5: su questo non c'è niente da cambiare. Il
margine fino al limite di 64 mm resta di quattordici millimetri.

Le ultime due hanno invece cambiato il progetto, e per capire come serve
sapere **dove sono sul Pi 5**: RJ45 e connettore PCIe stanno sul bordo corto da
56 mm, i micro-HDMI sul bordo lungo da 85. Nel pannello il bordo corto è
orizzontale, quindi i primi due sporgono in verticale, dove c'è posto fra il
lettore NFC e la scheda, mentre il terzo sporge su un fianco, dove di
millimetri ce ne sono 17,5. **Venti non ci stanno**: serve un micro-HDMI a
uscita angolata a 90°, che scende a circa 8. Non è un accessorio opzionale,
perché un cavo diritto spinge contro la parete della cassa e fa lavorare in
leva il connettore del Pi.

Da questo è seguita anche la **scheda video sul fianco opposto**, quello del
lato GPIO: stava a +36 mm, cioè proprio dal lato dei micro-HDMI, e fra il bordo
del Pi e la scheda restano 3 mm, dove nemmeno il cavo angolato entra.

La prima dimensiona la cassa e va **misurata dal piano del telaio**, non dal
PCB del Pi: è l'errore in cui si cade, perché il modello tiene separati i 10 mm
di base NVMe sotto il Pi e i 40 di HAT sopra, mentre col calibro si prende
comodamente solo il totale. Il riepilogo di `parametri.py` stampa adesso quella
quota con l'etichetta `gruppo del Pi`, così c'è un numero con cui confrontarsi.

I 50 mm dichiarati lasciano **20,5 mm di canale** fra il pezzo più profondo e
il fondo interno della cassa, che resta a 75. Il gruppo mangia il canale uno a
uno, e il canale cessa di funzionare quando la sua sezione scende sotto quella
delle feritoie, cioè sotto i 7 mm: succede con un gruppo da **64**. Ci sono
quindi quattordici millimetri di margine, e la verifica lo dice da sé se la
misura reale li supera.

Va presa **con i connettori dei fili inseriti sui pin in cima**, perché quelli
non si possono togliere: sui pin dell'header arrivano l'alimentazione
dell'adattatore NVMe e i fili del microfono, e il guscio di un femmina Dupont
in verticale aggiunge più di un centimetro. Se la misura coi connettori supera i
60 mm, prima di approfondire la nicchia conviene rifare quei due collegamenti
saldati o con femmina angolati a 90°, che è anche quello che va fatto per
togliere il contatto a frizione dal disco di avvio.

Serve anche sapere **quanto sporge l'ansa dei fili** che dalla cima dello stack
torna giù alla base dell'SSD: gira attorno a tutto il gruppo, e ai fianchi
restano 17,5 mm dove passa già il cavo di rete.

| Quota | Assunta | Reale |
|---|---|---|
| Altezza della base NVMe **sotto** il Pi, con SSD montato | 10,0 | **9,5** |
| Sporgenza dell'ansa del flat PCIe oltre il bordo del Pi | — | **25** |
| Ingombro in pianta della base NVMe | — | **51 x 65** |

I tre volumi che escono dal bordo inferiore del Pi sono adesso nel modello e la
verifica li controlla. Ci stanno, ma di poco: **l'ansa del flat si ferma a 2 mm
dal lettore NFC** e **il patch di rete gli passa sopra a 1,7 mm**, perché il
connettore sta sul piano del PCB e l'NFC finisce più avanti. Sono margini da
rispettare in montaggio, non da verificare una volta e dimenticare: una fascetta
che schiaccia il patch verso il vetro lo fa appoggiare sul lettore.

Queste due vengono dalle foto dello stack e non erano nel progetto. L'SSD non è
su un HAT sopra il Pi come si era assunto, ma su una base sotto, e i 10 mm di
distanziali che il progetto destinava al passaggio dell'aria sono in realtà
occupati da lei. Se la base è più alta di 10 mm vanno allungati i distanziali:
schiacciare il flat PCIe su un raggio stretto fa perdere il link.

L'ansa del flat serve invece a verificare i 17,5 mm dei fianchi, dove passa già
il connettore di rete.

Le ultime due servono a verificare i 17,5 mm che restano ai fianchi del Pi. Se un
connettore con cavo supera quella misura, servono cavi angolati o va allargata
la cassa. Il PoE non elimina il problema: toglie l'USB-C ma lascia l'RJ45, che
è il più ingombrante dei due.

## 3. La scheda del display — misurata, ed è in due pezzi

Pannello **Wisecoco 1080 x 1920**, 350 cd/m², su HDMI. La scheda non è un
pezzo unico come il progetto assumeva, ma due, collegate da un flat largo.

| Scheda di ingresso | Assunta | Reale |
|---|---|---|
| Larghezza del PCB | 60,0 | **43,0** |
| Altezza del PCB | 35,0 | **43,0** |
| Interasse dei fori | — | **39,0 x 39,0** |
| Diametro dei fori | — | **2,5** |
| Spessore, dal retro alla cima dell'HDMI | 10,0 | **4,5** |
| Sporgenza di HDMI-A e USB-C dal bordo | — | **nessuna** |

| Schedina terminale | Assunta | Reale |
|---|---|---|
| PCB | — | **39,0 x 20,0** |
| Spessore coi due connettori | — | **2,0** |

| Flat largo fra le due | Assunta | Reale |
|---|---|---|
| Lunghezza | — | **95,0** |
| Larghezza | — | **25,0** |

È quasi tutto più piccolo dell'assunto, e lo spessore è meno della metà: 4,5 mm
contro 10 su un fianco che ne ha 17,5. Il gruppo è quindi più facile da
collocare di quanto il progetto temesse, ma va collocato in due punti invece
che in uno.

### Dove vanno

Entrambe **in piedi sul fianco sinistro**, la schedina terminale cinque
centimetri sotto la scheda di ingresso. Non è una preferenza:

- in piano non c'è posto, perché la fascia sotto il Pi è occupata dall'ansa del
  flat PCIe e dal patch di rete, e quella sopra è fuori dalla portata dei
  100 mm del flat del pannello;
- il fianco destro è quello dei micro-HDMI del Pi, il cui cavo angolato ha
  bisogno di tutti i 17,5 mm di luce;
- a y = 100 i due flat arrivano entrambi: 56 mm in linea d'aria dall'asola alla
  schedina, 50 fra le due schede. `verifica()` controlla le due distanze
  lasciando un quarto di margine per le curve.

Il percorso è disegnato in `cad/06-gruppo-display.dxf`.

**L'HDMI-A resta il punto delicato**, anche se non sporge dal PCB: al
connettore si innesta un plug da una ventina di millimetri di guscio più la
curva del cavo. Va girato verso l'interno del vano, non verso la parete.

### Il dimming non è più una domanda aperta

| Quota | Assunta | Reale |
|---|---|---|
| ~~C'è un pin di **dimming del backlight**?~~ | — | **non serve: è OLED** |
| ~~La scheda risponde al DDC/CI?~~ | — | **no, verificato** |

Il pannello è un OLED, quindi non ha un backlight da pilotare: la luminosità si
abbassa nell'app, e su OLED quello è il modo giusto e non un ripiego, perché
l'emissione è per pixel. Fra l'altro il software **lo fa già**:
`modules/brightness.py` non trova nessun backlight in `/sys/class/backlight` e
ricade sull'overlay nero ad alpha variabile, che è esattamente ciò che va fatto
su un pannello emissivo. Entrambe le strade hardware sono quindi chiuse e non
servono: il DDC/CI non risponde
(verificato: sul bus `/dev/i2c-14` c'è solo la EEPROM dell'EDID a `0x50`,
l'indirizzo `0x37` è muto) e l'ingresso PWM non esiste perché non c'è un
backlight. GPIO12 e GPIO13 restano liberi.

Al suo posto nasce un problema diverso, che però è software e non hardware: il
**burn-in**. Un'interfaccia di videocitofono sta ferma per anni, e su OLED
questo si incide. Nel progetto l'elemento esposto è uno e preciso: l'indirizzo
in `96sp` dello screensaver, fisso nella stessa posizione in quello che è lo
stato prevalente del pannello. Le mitigazioni sono nel [README](README.md).

## 4. Camera Module 3 — risolta dal datasheet

Variante **standard**, confermata dal Raspberry: `libcamera` la riporta come
`imx708` e non `imx708_wide`. Le quote vengono dal product brief ufficiale di
giugno 2024, con tolleranza dichiarata 0,2 mm, e sono già nei parametri.

| Quota | Valore |
|---|---|
| PCB | 25 x 23,862 x 1,12 |
| Interasse fori | 21 x 12,5, Ø2,2, zona di rispetto Ø4,75 |
| Posizione dei fori | 2,0 dal bordo del connettore e 2,0 dai bordi laterali |
| Asse ottico | **14,5 dal bordo del connettore: 6,25 fuori dal centro dei fori** |
| Base del gruppo ottico | 10,8 x 10,8, alta 2,75 sopra il PCB |
| Barilotto | Ø5,75 |
| Altezza totale dal retro del PCB | 11,3 |
| Campo visivo | 66° x 41°, 75° in diagonale |
| Fuoco | da 10 cm a infinito |

Due di queste hanno cambiato il progetto. L'altezza di 11,3 mm non entra nei
6,2 mm fra retro del telaio e vetro, quindi la camera va **arretrata su
colonnine da 6 mm** col barilotto che attraversa il telaio e si ferma a 0,9 mm
dal vetro. E l'asse ottico è 6,25 mm fuori centro rispetto ai quattro fori, che sono
quindi decentrati in basso di altrettanto nel disegno del telaio: la fila
superiore finisce proprio sull'asse dell'obiettivo.

Restano due quote da prendere col calibro:

| Quota | Assunta | Reale |
|---|---|---|
| Diametro della lente frontale in vista | 4,0 | |
| Sporgenza dei componenti dietro il PCB | 2,6 | |
| Su quale faccia sta il connettore del flat | quella dell'obiettivo | |

Nessuna delle tre è quotata dai documenti ufficiali, nemmeno dal disegno
meccanico dedicato. Il modello STEP ufficiale dà gli ultimi due valori, ma è
dichiarato «simple» e in profondità non è fedele: modella il PCB spesso 0,67 mm
contro gli 1,12 quotati, e l'altezza totale 10,2 contro 11,3. In pianta invece
coincide col disegno al centesimo, ed è così che è venuto fuori il
decentramento dei fori. Quindi: le quote in pianta vengono dai documenti, quelle
in profondità vanno prese col calibro.

La prima rifinisce il diametro della finestra nel vetro, oggi 10 mm contro gli
8,5 calcolati come minimo: nel modello il gruppo frontale sta dentro 5 mm,
quindi il valore assunto è prudente e la finestra regge comunque.
La seconda e la terza verificano il margine verso l'altoparlante, arretrato di
14 mm per scavalcare la camera. Se il connettore è davvero sulla faccia
dell'obiettivo, il flat si piega nello spazio delle colonnine e dietro restano
solo componenti bassi: il margine passa da 2 a 4 mm e non c'è nulla da
cambiare. Se invece è dietro, le colonnine dell'altoparlante vanno allungate.

## 5. Lettore PN532 — misurato

| Quota | Assunta | Reale |
|---|---|---|
| PCB | 43 x 41 | **60 x 38** |
| Interasse fori | 37 x 35 | **54 x 32** |
| Spessore totale con connettori e DIP switch | 6,0 | **5,0** |
| Su quale faccia si trova l'antenna | lato componenti | **lato USB-C** |
| Distanza della spira dal bordo sinistro | — | da confermare, ~2,3 |

Lo spessore è il dato buono: 5 mm contro una soglia di 7,7, quindi il patch di
rete ci passa sopra con margine. **Il resto ha richiesto di ridisegnare la zona
NFC**, perché la scheda è mezza scheda più grande di quanto assunto e, soprattutto,
**l'antenna non è al centro**: la spira occupa la metà sinistra, l'altra metà
porta il PN532, il convertitore USB e il connettore. Misurata sulla foto, la
spira sta fra 2,3 e 34,6 mm dal bordo, quindi il suo centro cade 11,5 mm a
sinistra del centro della scheda. Questa stima va confermata col calibro: è
l'unica quota di questo gruppo che non viene dal pezzo.

Da qui quattro modifiche, tutte nei parametri e nei disegni:

- **la scheda resta centrata sul pannello** e si sposta l'icona serigrafata.
  Centrare l'antenna avrebbe portato il connettore USB-C a filo del fianco
  della cassa, dove il cavo non entra;
- **l'icona NFC sul vetro si sposta a x = −11,5**, cioè dove legge davvero la
  spira. Lasciarla al centro vorrebbe dire invitare ad appoggiare il tag dove
  la scheda ha il convertitore USB;
- **l'apertura del telaio scende da 46 x 40 a 30 x 32** e cade dentro la spira
  invece che attorno. Coprire d'alluminio i conduttori attenua poco, mentre
  l'area interna deve restare libera, e così resta un appoggio continuo di 3 mm
  su tutto il perimetro del PCB;
- **dei quattro fori se ne filettano due**, quelli dal lato dell'elettronica.
  Gli altri due cadono a mezzo millimetro dall'apertura e non lascerebbero
  alluminio da filettare. Per una scheda da dieci grammi che appoggia su tutto
  il perimetro, due viti bastano.

C'è infine il **cavo USB-C**, che il progetto non aveva considerato: il
connettore sporge dal bordo e il cavo esce verso il fianco della cassa. Con
un'uscita angolata a 90° arriva a 41,3 mm dall'asse contro i 45,5 disponibili;
con un cavo diritto, no. È la seconda volta che questo progetto chiede un cavo
angolato, dopo il micro-HDMI del Pi.

**La soglia dello spessore è 7,7 mm**, e viene da un vincolo che non si
immaginerebbe: il lettore sta a 8 mm dal vetro e cresce verso il fondo, mentre
il patch di rete gli passa sopra appoggiato al piano del PCB del Pi, che sta a
17,7 mm dal vetro. I due si inseguono nello stesso punto. Se il lettore è più
spesso di 7,7 mm, non è lui a non entrare: è il connettore di rete che gli
finisce addosso.

L'interasse dei fori conta perché oggi i quattro fori filettati stanno a 29 mm
dall'asse con interasse verticale 14: nascono dall'apertura dell'antenna, non
dalla scheda, e se la scheda ha un interasse diverso vanno rifatti.

## 6. Il muro — noto

| Quota | Valore |
|---|---|
| Materiale | **tufo** |
| Spessore del muro | **200 mm** |
| Profondità raggiungibile per la nicchia | **170 mm** |
| Spessore di intonaco + rasante esistente | **10,0 — confermato** |

Dei 170 mm se ne usano 81, con la cassa a 75. Lo spazio serve a due cose: al
gruppo del Pi, che col PoE HAT misura 50 mm dal telaio, e al **canale d'aria
dietro i componenti**, che resta a 20,5. Oltre non comprerebbe niente:
l'alimentatore non va dentro, perché l'alimentazione arriva in PoE.

Il tufo porta con sé due cose che non riguardano le quote ma la posa. La prima è
che **è isolante**: non va considerato una via di dissipazione per il calore,
che deve uscire dal fronte e dalle feritoie. La seconda è che è **poroso e
capillare**, quindi assorbe l'acqua della malta e la malta non fa presa: il vano
va bagnato a rifiuto prima di annegare la cassa. La stessa porosità trasporta
umidità, e il vano resterà più umido di quanto sarebbe in un laterizio.

Lo spessore dell'intonaco determina l'arretramento della flangia, oggi fissato a
10 mm: se è più sottile la flangia resta in vista, se è più spesso la cassa
affonda e il vetro non arriva a filo.

## 7. Basetta del microfono I2S — misurato

Si stacca dall'HAT e si incolla al vetro, dietro al foro: queste quote
determinano l'asola nel telaio e se la basetta sta nei 3,0 mm
fra vetro e telaio.

| Quota | Assunta | Reale |
|---|---|---|
| PCB | 16 x 16 | **15,5 x 6,5** |
| Spessore del solo PCB | 1,6 | **1,5** |
| Spessore totale col microfono sopra | 2,6 | **2,5** |
| Su quale faccia si trova l'apertura acustica | lato saldature | **lato pin** |

I 2,5 mm stanno dentro la soglia di 3,2 e non c'è niente da cambiare nelle
quote. **L'ultima riga però cambia il montaggio**: l'apertura acustica è sulla
faccia dei pin, non su quella delle saldature, quindi è quella faccia che va
incollata al vetro, girata rispetto a come il progetto la immaginava. E ne
segue una prescrizione sui fili: vanno saldati **dal lato opposto**, infilandoli
nei fori del pettine dissaldato, perché saldarli sulla faccia a vista
vorrebbe dire mettere lo stagno fra la basetta e il vetro, dove di spazio ce
n'è zero.

La basetta è poi una strisciolina, non il quadrato che il progetto assumeva:
6,5 mm di altezza invece di 16 lasciano molto più alluminio nella fascia dei
fori dell'altoparlante.

**La soglia è 3,0 mm**, ed è lo spessore del biadesivo che tiene il telaio al
vetro. La basetta col microfono sopra misura 2,5: ci sta, con mezzo millimetro
di margine, ed è il componente che quello spazio lo usa per intero. È per questo
che il nastro del telaio non si assottiglia a 2,0 anche se il display, misurato,
di millimetri ne vuole solo due: dietro il vetro non c'è solo il display.

Il pettine a sei pin, alto 8,5 mm, va comunque dissaldato: i fili si saldano
direttamente ai pad.

## 8. Altoparlante

Quote stimate dalla foto, da riprendere col calibro. Da queste dipendono i tre
fori filettati nel telaio e l'altezza delle colonnine.

| Quota | Assunta | Reale |
|---|---|---|
| Flangia | 70 x 32 | **69,5 x 30,5** |
| Spessore totale col magnete | 16,0 | **16,5** |
| Interasse dei quattro fori | 62 x 24 | **63,5 x 24** |
| Diametro dei fori di flangia | 3,2 | **3,5** |
| Impedenza e potenza | 8 Ω, 2 W | |

Tutte dentro il millimetro e mezzo dalle stime, e nessuna cambia qualcosa: i
tre fori filettati si spostano di 0,75 mm verso l'esterno e restano a 5,2 mm dal
magnete più vicino. I 3,5 mm del foro di flangia confermano che una M3 passa
con gioco, quindi il filetto sta nel telaio come previsto. Resta solo
l'impedenza, che si legge sull'etichetta e non cambia la meccanica.

L'amplificatore dell'HAT regge da 2 a 8 Ω, quindi qualunque valore va bene, ma
cambia il volume a pari livello software. I due altoparlanti saldati sull'HAT
non si usano: vanno disattivati con i microswitch sul retro della scheda.

Il suo arretramento, oggi 14 mm, serve a scavalcare la camera, che a sua volta
è su colonnine da 6 mm: la somma da verificare è nella sezione 4.

## 9. Reed switch di antimanomissione

| Quota | Assunta | Reale |
|---|---|---|
| Corpo | 14 x 4 | |
| Distanza di commutazione col suo magnete | — | |

## Prove da fare prima di ordinare, non misure

**Il touch attraverso il vetro.** Appoggia sul touch una lastra da 2 mm con un
velo d'acqua o glicerina fra i due, e verifica che risponda su tutta la
superficie. La sensibilità del controller non è regolabile dal Raspberry, ed è
il motivo per cui il vetro è passato da 4 a 2 mm: a 2 mm si è dentro il margine
di qualunque controller, ma la prova costa niente e va fatta prima di ordinare.

**Il PN532 attraverso lo stesso vetro.** Stesso pezzo di prova, un tag a 2 cm:
se non legge, il problema va risolto prima e non dopo.

~~**OLED o LCD, la conferma diretta.**~~ **Fatta: è OLED.** Mezzo schermo nero e
mezzo bianco sul pezzo collegato: il nero è indistinguibile dalla cornice spenta
e **resta nero di sbieco a 45 gradi**, dove un IPS schiarisce sempre perché i
cristalli liquidi perdono allineamento fuori asse. La prova del calore sulla
sola metà bianca non ha dato segnale, ma su 5,5 pollici a 350 nit il delta è di
frazioni di watt: non è sensibile, non contraddice. Via software la tecnologia
non si legge — l'EDID dichiara solo "Wisecoco" su una scheda driver generica del
2018 — e il consumo non si può pesare dal Pi, perché il display è alimentato dal
suo USB-C e sul rail HDMI passano 6 mA, cioè la sola EEPROM.

## Suggerimento prima di ordinare

Prima di far fare il vetro temperato, fatti tagliare una **dima in PMMA o MDF
da 3 mm** con le stesse forature del telaio, e montaci tutto. Costa pochi euro
e verifica in mezz'ora tutte le quote di questa scheda. Il vetro temperato
serigrafato è l'ultimo pezzo da ordinare, perché è l'unico che non si corregge.
