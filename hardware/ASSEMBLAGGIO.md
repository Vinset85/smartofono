# Istruzioni di assemblaggio

Montaggio completo del videocitofono: dai pezzi grezzi al pannello murato e
funzionante. Le quote citate sono tutte in millimetri e vengono da
`parametri.py`; i disegni sono in `cad/`.

L'ordine conta. Due passaggi sono irreversibili e sono segnalati come tali:
l'incollaggio del vetro e la muratura della cassa.

## Prova zero, prima di ordinare il vetro

Appoggia sul touch una lastra di vetro da 2 mm, con un velo d'acqua o di
glicerina fra i due a fare da accoppiamento, e verifica che risponda su tutta la
superficie. Il controller presenta il touch come HID generico attraverso un
bridge USB-I2C, quindi **la sensibilità non è regolabile in software**: è il
motivo per cui il vetro è da 2 mm e non da 4. Fai la stessa prova col PN532 e un
tag a 2 cm.

## Prima di cominciare

### Pezzi

| Pezzo | Riferimento |
|---|---|
| Vetro frontale serigrafato | `cad/01-vetro-frontale.dxf` |
| Telaio portante in alluminio | `cad/02-telaio-portante.dxf` |
| Cassa da incasso, stampata in ASA | `stl/cassa.stl`, controllo su `cad/03-cassa-incasso.dxf` |

### Elettronica

| Componente | Collegamento | Note |
|---|---|---|
| Raspberry Pi 5 8 GB | — | boot da NVMe, nessuna microSD |
| Adattatore NVMe + SSD | PCIe sotto il Pi | Phison PS5021-E21 |
| HAT audio Raspiaudio Pi MIC V3 | GPIO 40 pin | si presenta come Google voiceHAT |
| Ventola | connettore FAN del Pi 5 | PWM, gestita dal kernel |
| Display OLED 5,5" 1080 x 1920 | micro-HDMI + scheda driver in due pezzi | si presenta come HDMI-A-2 |
| Touch capacitivo | USB | `1a86:e5e3 USB2IIC_CTP_CONTROL` |
| Camera Module 3 standard (IMX708, 66° x 41°) | flat CSI | connettore CAM del Pi 5 |
| Altoparlante ovale 70 x 32 | morsetti a vite dell'HAT audio | arretrato nel vano, non a filo telaio |
| Microfono I2S | basetta staccabile dall'HAT, 6 fili | va incollato dietro al foro del vetro |
| Lettore NFC PN532 | USB tramite adattatore CH340 | `1a86:7523`, appare come `/dev/ttyUSB0` |
| PoE HAT (F) Waveshare | GPIO 40 pin + header PoE a 4 pin | l'HAT audio si impila sopra |
| Switch o injector **802.3at** | — | PoE+, non PoE semplice |
| Cavo ethernet | RJ45 | porta rete **e** alimentazione; il WiFi non è usato |

Nella scatola **non entra nessun relè**: l'apertura del cancello passa da Home
Assistant, che chiama `script.cancello_ingresso`. Con il PoE nei corrugati va
quindi **un solo cavo**, quello di rete. Il secondo passaggio resta e va
lasciato libero con un filo pilota: nel tufo, murato, tirare un cavo nuovo
domani costa più di predisporlo oggi.

### Minuteria e consumabili

Vedi la tabella in `README.md`. Procurati in anticipo il biadesivo **3M VHB
4959** da 3,0 mm (cornice del telaio), l'adesivo ottico del display (**foglio di
OCA da 0,35 mm**, meglio se tagliato a misura dal fornitore del vetro: il bordo
di un foglio rifilato a mano è il punto da cui partono le bolle), il primer
**3M 94**, la rete inox a maglia 0,6 mm con filo 0,2, la
membrana acustica in PTFE e il foglio di PET nero opaco.

### Attrezzi

Brugole da 2 e 2,5 mm, cacciavite Torx/Phillips piccolo, alcol isopropilico,
calibro, livella, pistola per silicone, **ventosa da 30 mm** per estrarre il
pannello, colla epossidica bicomponente per i magneti, **rullo di gomma** per
laminare l'adesivo ottico e un saldatore a punta fine per i fili del microfono.

### Cavi: la scelta che fa la differenza

Il Pi sta in verticale al centro del vano, e ai suoi fianchi restano 17,5 mm.
Un RJ45 normale e un micro-HDMI normale non ci curvano dentro. Usa:

- patch ethernet **slim** con connettore **angolato**, o un keystone a 90°.
  Il PoE non risparmia questo pezzo, lo rende più critico: da quel connettore
  passa anche l'alimentazione, quindi un falso contatto non fa perdere la rete
  ma spegne il pannello;
- cavo **micro-HDMI angolato a 90°**, lunghezza 20-30 cm. Questo è
  obbligatorio, non preferibile: col cavo diritto sono 20 mm misurati dal bordo
  del PCB contro i 17,5 che ci sono, quindi il cavo spinge sulla parete della
  cassa e fa lavorare in leva un connettore micro. Angolato scende a 8;
- flat CSI da 200 mm, non quello corto in dotazione;
- sei cavetti **maschio-femmina passo 2,54** da 20 cm per prolungare il
  microfono dell'HAT, oppure un cavo a sei vie con connettore da crimpare.

## Fase 1 — Preparazione del telaio

1. Verifica il telaio sul disegno: zona piena dietro il display, foro della
   lente con i suoi quattro fori decentrati verso il basso, luce
   dell'altoparlante sopra la lente, apertura NFC in basso,
   asola 12 x 4 dei fili del microfono in alto a sinistra.
2. Verifica anche le sei sedi dei magneti da 4 mm e i due fori perno da 4,3.
3. Sbava tutti i bordi tagliati al laser. L'anodizzazione arriva dopo, ma una
   bava sul bordo della finestra si vede attraverso il vetro.
4. Filetta M2 i fori della camera e dell'altoparlante, M2.5 quelli del Pi,
   M3 quelli del lettore. Su 3 mm di alluminio usa il maschio a macchina con
   olio: un filetto strappato qui significa rifare la piastra.
5. Fai anodizzare il telaio nero opaco. **Dopo** l'anodizzazione non lavorare
   più: il maschio porterebbe via lo strato e lascerebbe l'alluminio a vista.
6. Se vuoi continuità di massa fra telaio e cassa, maschera un'areola di
   contatto prima dell'anodizzazione, oppure usa una rondella dentellata.

## Fase 2 — Montaggio dei componenti sul telaio

Il telaio ha un fronte (verso il vetro) e un retro (verso il muro). Tutto si
monta sul retro, tranne il display.

1. **Diaframma NFC**: incolla il foglio di PET nero opaco sul retro del telaio,
   centrato sull'apertura 30 x 32. Impedisce di intravedere il circuito del
   lettore attraverso la serigrafia dell'icona. Non usare nastro di alluminio:
   schermerebbe l'antenna.
2. **Lettore PN532**: montalo sul retro **appoggiato direttamente al telaio**,
   con l'antenna rivolta verso di esso. Niente distanziali: la distanza
   dell'antenna dal vetro non è una scelta, è `Z_TELAIO + TELAIO_S`, cioè 8 mm,
   e alzare il lettore di 5 mm lo porterebbe a sbattere sotto il Raspberry — il
   controllo in `parametri.py` fallisce. Il contatto è sicuro perché
   l'anodizzazione del telaio è isolante, e la spira affaccia sull'apertura,
   non sull'alluminio. Qui ci sono tre cose controintuitive, e
   vengono tutte dal fatto che **sull'antenna del PN532 la spira non è
   centrata**: sta spostata di 11,5 mm verso il lato del connettore USB-C, e
   l'altra metà della scheda è elettronica.
   - La scheda **non va centrata sull'apertura**, e non è centrata nemmeno
     l'apertura: il PCB sta in mezzo al telaio, la spira gli cade a sinistra e
     l'apertura da 30 x 32 cade dentro la spira, non attorno alla scheda. Il
     controllo è che attraverso l'apertura si veda rame avvolto, non
     componenti.
   - Si usano **due viti, non quattro**, entrambe dal lato dell'elettronica,
     cioè quello opposto alla spira: dall'altro lato i fori della scheda
     cadrebbero a filo dell'apertura e non ci sarebbe più alluminio da
     filettare. `posizioni_fori_nfc()` dà le due posizioni.
   - Il **cavo USB-C va orientato verso il fianco del vano**, non verso la
     parete, e deve essere angolato: diritto non ci sta.
3. **Camera**: dal retro, su quattro colonnine M2 da 6 mm, col barilotto
   infilato nel foro del telaio. L'obiettivo sporge 11,3 mm dal retro del suo
   PCB, mentre fra telaio e vetro ci sono 6,0: **senza le colonnine la lente
   sfonda il pannello**, non è un dettaglio di finitura. A montaggio finito
   resta 0,7 mm fra la punta dell'obiettivo e il vetro, da riempire con
   l'anello di schiuma nera che fa anche da paraluce.
   Due avvertenze. Il **connettore del flat va verso il basso**, dove c'è il
   Pi: montata al rovescio l'obiettivo finisce 12,5 mm fuori posto, cioè
   completamente fuori dalla finestra, e il flat va torto. E i quattro fori del telaio sono **volutamente decentrati**
   rispetto al foro dell'ottica, di 6,25 mm: è il decentramento dell'asse
   ottico dichiarato da Raspberry, non un errore del disegno. Il controllo
   rapido è che i **due fori più vicini all'ottica sono alla sua stessa
   altezza**, non sopra di essa.
4. **Altoparlante**: dal retro, su tre colonnine **in nylon** da 14 mm e tre M3
   con rondella di gomma sotto la flangia e sotto la testa, col cono
   rivolto verso il telaio. L'arretramento serve a scavalcare la camera, che
   gli finisce davanti: non montarlo a contatto del telaio e non accorciare le
   colonnine. Il quarto foro resta vuoto, lì dietro c'è la basetta del
   microfono. **Usa viti corte**, che non affiorino sul fronte del telaio: la
   punta toccherebbe il vetro o la basetta.
5. **Raspberry**: quattro distanziali M2.5 da 10 mm, scheda col lato lungo in
   verticale, il dissipatore rivolto verso il fondo della cassa e **l'RJ45
   verso il basso**. L'orientamento non è una preferenza: girando la scheda il
   patch, che sporge 34 mm misurati, finirebbe addosso all'altoparlante, mentre
   verso il basso passa sopra il lettore NFC. Da questo segue che i micro-HDMI
   escono sul fianco destro, che va tenuto libero.
   I 10 mm dei distanziali ospitano la base dell'SSD, misurata 9,5 mm con l'SSD
   montato, e sotto il bordo inferiore della scheda passa l'ansa del flat PCIe,
   che sporge 25 mm. Se cambi base e la nuova è più alta, allunga i distanziali
   invece di schiacciare il flat, che su un raggio stretto perde il link PCIe.
   **I due margini stretti sono qui**: l'ansa si ferma a 3,5 mm dal lettore
   NFC e il patch gli passa sopra a 2,0 mm. Non fascettare il patch verso il vetro,
   o lo fai appoggiare sul lettore.
   **Rifai l'alimentazione dell'SSD**: i fili che oggi arrivano ai pin 5 V e
   massa con connettori Dupont vanno ricrimpati su un connettore ritenuto, o
   saldati. Tengono su il disco di avvio, e un contatto a frizione dentro un
   muro non è riparabile senza smontare tutto.
6. **Scheda video del display**: sono **due pezzi**, non uno, uniti da un flat
   largo. La **scheda di ingresso**, quella con HDMI-A e USB-C, va in piedi sul
   fianco **sinistro**, a 36 mm dall'asse, sulla **squadretta del DXF 07**.
   Prima la squadretta: due viti M2.5 **da 4 mm** nei due fori ciechi del
   telaio, e non più lunghe — il filetto è profondo 2 su 3 mm di alluminio e
   dall'altra parte, a un millimetro, c'è il pannello. Poi la scheda, dentro
   l'ala lunga, con quattro M2.5 e dado.
   In orizzontale non c'è posto: fra il Pi e la camera restano
   27 mm e la scheda è alta 35. Il fianco è quello del lato GPIO, non quello
   dei micro-HDMI: da quel lato il cavo ha bisogno di tutti i 17,5 mm e fra
   bordo del Pi e scheda ne restano 3.
   **L'HDMI-A va girato verso l'interno del vano, non verso la parete**: al
   connettore si innesta un plug da una ventina di millimetri di guscio più la
   curva del cavo, e il fianco è largo 17,5. Girata nel verso sbagliato la
   scheda entra e il cavo no.
   La **schedina terminale** va dietro il telaio, vicino all'asola del flat del
   display, tenuta dal suo biadesivo: è il pezzo che si colloca più
   facilmente, perché il flat largo lascia scegliere dove metterlo. Verifica
   prima che il flat arrivi: se è corto, la schedina deve stare vicina alla
   scheda di ingresso e il flat del pannello è quello che deve allungarsi.
7. **Magneti**: incollali nelle sei sedi con l'epossidica, a filo della faccia
   posteriore, **tutti con la stessa polarità**. Se ne giri uno al contrario
   non te ne accorgi finché non provi a montare il pannello.
8. **Reed switch**: incollalo sul retro in basso, nella posizione indicata sul
   layer INGOMBRI, e portane i due fili al GPIO.
9. **Display**: non si fissa, viene incollato al vetro nella fase 6 e
   appoggerà col retro sulla zona piena del telaio. Per ora fai solo passare il
   suo flat verso il retro, dall'asola 18 x 8 sul bordo basso. Il touch è
   integrato nel pannello e viaggia in quello stesso flat: dal display non esce
   nient'altro, e l'USB del touch parte dalla scheda di ingresso. Quella zona del telaio **non va forata né graffiata**: ci appoggia il
   pannello.
   Sotto il bordo basso del pannello c'è la **coda rigida** col chip del
   driver, larga 70 mm come tutto il pannello: dall'asola passa solo il flat
   nero, largo 13, e la coda va ripiegata dietro. Fallo una volta e con raggio
   ampio, non a spigolo. Ripiegata il gruppo misura 1,8 mm e il telaio gli
   resta a un millimetro: **il display non appoggia al telaio**, lo tiene
   l'adesivo ottico sul vetro, e quel millimetro serve a non schiacciare la
   coda.

## Fase 3 — Collegamenti

1. **Prima** di infilare l'HAT audio, fai due cose sul suo retro, perché dopo
   non ci arrivi più: porta i due microswitch degli altoparlanti di bordo nella
   posizione opposta a `ON`, altrimenti i due speaker saldati sulla scheda
   suonano chiusi dentro il vano; e sfila la basetta del microfono dal suo
   pettine a sei pin.
2. HAT audio sul pettine GPIO, premendo a fondo e in piano.
3. **Microfono**: dissalda il pettine dalla basetta e salda i sei fili
   direttamente ai suoi pad, rispettando l'ordine dei contatti: 3V3, GND, BCLK,
   DOUT, WB, SEL. Col pettine montato la basetta è alta 8,5 mm e nei 3,0 mm fra
   vetro e telaio non entra. I fili passano nell'asola 12 x 4 del telaio e
   vanno al pettine dell'HAT; la basetta si incolla al vetro nella fase 6.
   Lascia 5 cm di gioco, il pannello si estrae e il cavo deve seguirlo.
4. Altoparlante ai morsetti a vite dell'HAT, rispettando la fase.
5. Flat CSI della camera al connettore CAM, contatti verso il lato giusto
   (linguetta sollevata, flat dentro, linguetta chiusa).
6. Micro-HDMI dalla scheda video alla porta HDMI0 del Pi.
7. USB del touch e USB del CH340 su due porte diverse.
8. Ventola del PoE HAT sul connettore **FAN a 4 pin del Pi**, non sui 5 V
   dell'HAT: così resta pilotata in PWM e sotto i 50 gradi sta ferma. In una
   cassa chiusa accanto al microfono è la differenza fra un fruscio continuo e
   il silenzio.
9. Reed switch su GPIO27 e massa. Il progetto tiene GPIO17 libero per un
   eventuale pulsante di chiamata, quindi non usare quello. Tieni presente che
   l'HAT audio occupa GPIO25 per il suo LED.
10. Ethernet lasciato uscire verso il fondo, con un'ansa di scarico.

Fissa i cavi con fascette alla piastra, lontano dal percorso dell'aria e dal
dissipatore. Un flat che sventola davanti alla ventola fa rumore in chiamata.

I pin che spuntano in cima allo stack **non sono liberi e non vanno tagliati**:
lì sono infilati i fili che alimentano l'adattatore NVMe e quelli del
microfono. Vale invece la pena cambiare il modo in cui si collegano. Oggi i
connettori femmina si infilano in verticale e il loro guscio aggiunge più di un
centimetro sopra i pin, poi i fili devono tornare giù verso la base dell'SSD
facendo un'ansa che gira attorno a tutto lo stack, in uno spazio dove ai
fianchi restano 17,5 mm e dove passa già il cavo di rete.

Tre modi di risolverlo, dal migliore al peggiore. **Saldare** i due fili di
alimentazione dell'SSD ai pin 5 V e massa dal lato inferiore dello stack, dove
sono già accessibili: il percorso diventa corto, l'ansa sparisce e si elimina
insieme il contatto a frizione sul disco di avvio. Oppure crimpare su
**connettori femmina angolati a 90°**, che coricano il guscio invece di
alzarlo. Oppure, se si lascia tutto come è, **misurare l'altezza coi connettori
inseriti** e verificare che l'ansa dei fili non vada a sbattere sui fianchi
della cassa. In profondità c'è spazio: il canale dietro lo stack è di 20,0 mm e
il limite è a 64 di gruppo contro i 50 di oggi.

## Fase 4 — Collaudo a banco

**Non salta questa fase.** Dopo l'incollaggio del vetro non si torna indietro.

Alimenta il gruppo appoggiato sul tavolo, con un pezzo di vetro di prova da
2 mm appoggiato davanti al lettore NFC, e verifica:

1. il display si accende, risoluzione 1080 x 1920 verticale;
2. il touch risponde e le coordinate non sono invertite;
3. `rpicam-still --list-cameras` vede l'IMX708 e l'immagine non è vignettata
   dal foro del telaio;
4. `aplay -l` mostra la scheda voiceHAT e l'altoparlante suona pulito al
   volume di chiamata, senza vibrazioni sul telaio; i due speaker di bordo
   dell'HAT restano muti, altrimenti i microswitch sono nel verso sbagliato;
5. il microfono registra **con la prolunga collegata**: `arecord -d 5` e
   riascolto. Se il segnale è sporco o assente la prolunga è troppo lunga o i
   sei fili sono invertiti, e si risolve adesso, non col vetro incollato;
6. `/dev/ttyUSB0` esiste e il PN532 legge un tag **attraverso il vetro di
   prova**, a 2 cm. Se non legge, il problema è qui e non dopo;
7. la temperatura a pieno carico resta sotto i 70 °C in aria libera. La prova
   va fatta **dopo** `installer-rpi/scripts/tune-system-thermal.sh`, che
   disabilita i servizi inutili: prima di quello si misura un carico che
   nell'impianto finito non c'è;
8. il reed switch cambia stato avvicinando il suo magnete;
9. la chiamata completa verso Home Assistant funziona, audio e video compresi;
10. l'eco non torna all'interlocutore. La cancellazione c'è ed è efficace, ma
    va controllata **a pannello montato**, perché è lì che l'altoparlante è
    vicino al microfono e accoppiato per via meccanica. Il controllo rapido:
    `pactl info` deve dare `ec_sink` come sink predefinito e `ec_source` come
    sorgente predefinita. Se dopo un riavvio tornano i dispositivi ALSA
    diretti, l'audio bypassa la cancellazione e il Larsen è garantito.
11. **l'alimentazione PoE regge.** Prima di staccare l'USB-C scrivi
    `PSU_MAX_CURRENT=5000` con `sudo rpi-eeprom-config --edit`, poi passa al
    cavo PoE e verifica tre cose: `vcgencmd get_throttled` deve dare `0x0`
    anche sotto carico, `cat /proc/device-tree/chosen/power/max_current` deve
    leggere 5000, e il driver del display deve accendersi al primo colpo. È lui
    il carico che cede per primo se il budget USB si è stretto. Lo switch deve
    essere **802.3at**: con il PoE semplice i 12,95 W non bastano.
12. **la ventola si ferma da sola.** Con il sistema a riposo,
    `cat /sys/class/hwmon/hwmon*/fan1_input` deve dare 0 sotto i 50 °C. Se gira
    sempre, la ventola dell'HAT è attaccata ai 5 V dell'HAT invece che al
    connettore FAN del Pi, e dentro la cassa la sentirai in ogni chiamata.
13. **la prova termica in cassa chiusa**, che decide se si mura. Il calore esce
    per più di metà dal vetro e dal muro, non dalle feritoie (README,
    Ventilazione), e il conto che lo dice è una stima: va misurato. Infila il
    gruppo nella cassa stampata, coi dischetti già annegati (fase 5, passo 3),
    appoggia il vetro di prova sul fronte del telaio e chiudi la cassa in una
    scatola di polistirolo spessa almeno 3 cm, lasciando libere solo cornice e
    fessura d'ombra. Il polistirolo isola più del tufo, quindi la prova è più
    severa della realtà. Tieni la cassa in piedi come andrà murata, chiudi col
    nastro i due fori dei corrugati, che in opera saranno sigillati, e
    appoggia i tre ritagli di rete sulle feritoie con un pezzetto di nastro
    sui bordi: la rete dimezza la sezione, e senza la prova sarebbe indulgente.
    Poi:
    - due ore **a riposo**, nell'uso normale: display spento, Home Assistant
      collegato, nessuna chiamata. Annota la temperatura ambiente, quella del
      SoC con `vcgencmd measure_temp`, e la potenza assorbita dalla porta PoE
      dello switch, se la mostra: è il numero che il conto stima in 5 W;
    - un'ora **a pieno carico**: display acceso al massimo, chiamata aperta o
      stream video, ventola libera di girare.
    Il criterio è il **salto del SoC sopra la stanza**, che non dipende da
    quanto è calda la stanza: deve restare entro i **40 gradi**, a riposo e a
    fine carico, con `vcgencmd get_throttled` a `0x0`. Con la stanza a 25 °C
    vuol dire sotto i 65; in opera, con 35 °C fuori, vuol dire 75, cinque gradi
    sotto il throttling. Se la prova la supera, in opera la supera di sicuro,
    perché il tufo disperde più del polistirolo. Se non la supera, il margine
    dipende dal tufo, cioè da un numero che nessuno ha misurato: abbassa la
    potenza di riposo (luminosità, servizi, `tune-system-thermal.sh`) e ripeti,
    prima di scavare il muro.

Lascia il gruppo acceso un'ora e ricontrolla la temperatura.

## Fase 5 — Muratura della cassa

**Irreversibile.** Misura due volte.

1. Stampa `cad/04-dima-muratura.dxf` in scala 1:1 e verifica la quota di
   controllo da 100 mm con il calibro.
2. Incolla la dima al muro, asse verticale a piombo, all'altezza voluta. Il
   centro del display cade a 119 mm dal bordo inferiore del vetro, cioè
   praticamente a metà pannello: per averlo a 150 cm da terra, il bordo
   inferiore del vetro va a 138 cm.
3. Se non l'hai già fatto per la prova termica, incolla ora i sei dischetti di
   acciaio dolce Ø6 x 1 nelle sei sedi della battuta, con l'epossidica. Vanno
   fatti prima di murare perché dopo quelle sedi sono in fondo a una nicchia.
   Devono restare **a filo o sotto** la faccia di battuta: se sporgono, il
   telaio appoggia su di loro e il vetro resta fuori filo di quanto sporgono.
   Il telaio è in alluminio, la cassa in ASA, e senza questi dischetti i
   magneti non hanno niente da attrarre.
4. Scava la nicchia **135 x 275 x 86**, con la profondità misurata **dalla
   superficie dell'intonaco esistente**, non dal tufo. Nel tufo si arriverebbe
   a 170 mm, ma non servono: la profondità è il gruppo del Pi più il canale
   d'aria dietro di lui, che deve superare 13,2 mm e qui ne ha 20,0. Prima di
   scavare però **misura il gruppo montato, dal telaio alla cima dei pin coi
   Dupont innestati**: il progetto conta 50,5 mm, e oltre i 57 il canale
   diventa il collo di bottiglia e la cassa va rifatta più profonda.
5. Porta i corrugati nella nicchia, fermali e infilali nei due fori del fondo
   della cassa. Sigilla col silicone neutro il giunto fra corrugato e fondo e
   tappa l'interno del corrugato attorno ai cavi: da lì entrerebbero l'aria
   umida della casa e, se il corrugato arriva da fuori, l'acqua.
6. **Bagna il tufo a rifiuto** e aspetta che l'acqua in superficie sia
   assorbita. Il tufo è poroso e capillare: su un supporto asciutto si beve
   l'acqua di impasto e la malta non fa presa, resta polverosa e la cassa si
   muove. Non è una raccomandazione generica da manuale, è il modo in cui si
   sbaglia questo lavoro sul tufo.
7. Mura la cassa con il **fronte della cornice a filo dell'intonaco finito**,
   cioè della superficie dell'intonaco esistente intorno alla nicchia. Il
   riferimento è la cornice, non il fronte del corpo, che sta 5 mm più
   indietro: un regolo appoggiato all'intonaco a cavallo della nicchia deve
   toccare la cornice su tutti e quattro i lati. Ancora la flangia con la malta
   nei suoi fori, verifica bolla e piombo sui due assi, e controlla che la
   cornice non sia svergolata. **Nessuna pendenza**: il vetro è parallelo alla
   cornice, e inclinarla lo porterebbe fuori filo in alto o in basso. L'acqua
   non ha bisogno di pendenza per uscire, perché la feritoia bassa guarda in
   giù e gli smussi del fondo la portano lì.
8. Proteggi la luce della cornice con nastro e cartone e lascia maturare.
9. Chiudi con malta e poi con rasante l'anello fra cornice e bordo della
   nicchia, fino a filo dell'intonaco esistente. La cornice fa da sponda: il
   canale d'aria sta dentro di lei e la flangia lo chiude dietro, quindi il
   rasante non ci può entrare. Non rasare sopra la cornice e non stuccarne la
   luce.
10. Verifica che la luce finita sia **106 x 246**, cioè 3 mm per lato oltre il
   filo del vetro, e che dalla fessura si veda il canale libero fino alle
   feritoie.
11. Incolla la rete inox sull'interno delle tre feritoie: un ritaglio
    85 x 20 sulla feritoia bassa da 80 x 15, due ritagli 45 x 20 sulle laterali
    da 40 x 15. I 2,5 mm che avanzano su ogni lato sono la superficie su cui
    prende l'adesivo, quindi vanno rispettati su tutti e quattro i lati e non
    solo in lunghezza. Va fatto adesso, con la cassa vuota, ma va fatto dopo la
    malta: la polvere di cantiere intaserebbe la maglia.

## Fase 6 — Incollaggio del vetro

**Irreversibile.** Dopo questa fase il vetro non si stacca senza romperlo.

1. Pulisci la faccia interna del vetro e il fronte del telaio con alcol
   isopropilico e lascia evaporare.
2. Applica il primer 3M 94 sulla cornice del telaio, dove andrà il VHB.
3. **Display**: incollalo al vetro centrato sulla finestra serigrafata, con
   l'area attiva allineata, usando un **foglio di OCA da 0,35 mm su tutta la
   superficie**. Non una cornice perimetrale: il pannello è touch capacitivo e
   l'intercapedine d'aria che resterebbe peserebbe come 1,4 mm di vetro in più,
   oltre a dare riflessi interni e immagine slavata. Lamina partendo da un
   bordo, con un rullo di gomma, premendo avanti la bolla d'aria invece di
   intrappolarla.
   Il foglio è più grande della finestra, quindi **sale sul bordo
   dell'inchiostro** per mezzo millimetro sui fianchi e un millimetro e mezzo
   sopra e sotto: è quel gradino, non l'ottica, a volere 0,35 mm di adesivo.
   Insisti col rullo proprio lungo il perimetro della finestra, dove il gradino
   sta, e guarda in controluce: se è rimasto un filo d'aria si vede come una
   riga chiara che segue il bordo. Si recupera solo adesso.
   Allinea a secco, con l'adesivo ancora protetto, e segna i riferimenti: un
   errore di mezzo millimetro si vede, perché la serigrafia lascia in vista
   solo mezzo millimetro di cornice per lato.
   L'adesivo non deve portare il peso: il display appoggerà col retro sulla
   zona piena del telaio, in sandwich fra vetro e alluminio. Il flat va infilato
   nella sua asola prima di accostare il telaio.
4. **Microfono**: incolla la membrana PTFE sulla faccia interna del vetro,
   sopra il foro da 3 mm, poi incolla la basetta del microfono sulla membrana,
   centrata sul foro, con la sua apertura acustica rivolta al vetro e un
   anellino di biadesivo di schiuma da 1 mm che faccia tenuta attorno. Va fatto
   adesso, prima di accostare il telaio: la basetta sta nei 3,0 mm fra vetro e
   telaio e i suoi fili passano per l'asola. È la tenuta attorno al foro che
   impedisce al microfono di sentire la ventola: se l'anellino non chiude, la
   basetta ascolta il vano e in chiamata si sente solo soffio.
5. **Telaio**: applica il VHB 4959 da 3,0 mm in cornice continua sul perimetro
   del telaio, togli la pellicola e accosta il telaio al vetro facendo entrare
   il display nella finestra. I 3,0 mm di schiuma portano il telaio complanare
   al retro del display.
6. Premi uniformemente a circa 15 N/cm² per qualche secondo su tutto il
   perimetro, usando un tampone di gomma.
7. **Attendi 72 ore** prima di sollecitare il giunto. Il VHB arriva a metà
   della sua tenuta in un'ora, ma al valore pieno solo dopo tre giorni.

## Fase 7 — Montaggio finale

1. Collega l'ethernet, già passato nel corrugato, lasciandolo lungo quanto
   serve a tenere il gruppo in mano davanti alla cassa.
2. Facoltativo: stendi un velo di grasso al silicone sulla faccia della
   battuta, dove appoggia il telaio, senza coprire perni e dischetti. Riduce la
   risalita dell'acqua nel gioco fra telaio e cassa; non serve a tenere niente.
3. Presenta il gruppo alla bocca, infila i due fori superiori sui perni della
   battuta e accompagna il basso: gli ultimi millimetri li fanno i magneti.
   Accompagna fino in fondo, non lasciarlo schioccare: il vetro è incollato a
   una piastra che sta per prendere un colpo magnetico.
4. Verifica che il vetro sia a filo della cornice e dell'intonaco e che la
   fessura d'ombra sia regolare sui quattro lati. Se il pannello balla,
   controlla che nessun cavo sia rimasto schiacciato fra telaio e battuta.
   **Non mettere silicone nella fessura d'ombra**, su nessun lato: è la via
   d'aria e lo scarico, e il pannello deve poter uscire con la ventosa.

## Fase 8 — Collaudo in opera

1. Ripeti le verifiche della fase 4, in particolare la lettura NFC, che ora
   avviene attraverso il vetro definitivo.
2. Fai una chiamata completa e ascolta il volume dall'esterno, di fronte e di
   lato: il suono esce dalle due feritoie laterali, attraverso la fessura
   d'ombra dei fianchi, e deve risultare chiaro a tre metri di fronte.
3. **Prova di pioggia.** Spegni il pannello dalla porta PoE dello switch. Con
   la canna da giardino sul getto a pioggia, da un paio di metri, bagna il
   pannello per cinque minuti dall'alto a 45°, poi cinque per lato e cinque di
   fronte: è grosso modo quello che la norma chiede per il secondo 4 di IP44.
   Aspetta dieci minuti, estrai il gruppo con la ventosa e guarda: dalla
   feritoia bassa deve essere uscita acqua, e non deve essercene sulla
   battuta, sul fondo del vano oltre una velatura, né sull'elettronica. Se ce
   n'è, la via è quasi sempre il gioco fra telaio e cassa: asciuga, metti il
   grasso al silicone del passo 2 della fase 7 e ripeti.
4. Lascia il sistema a regime e controlla la temperatura per qualche giorno con
   `sensor.videocitofono_temp_max_24h`. Deve restare entro il salto misurato
   nella prova termica della fase 4, sopra la temperatura esterna all'ombra; se
   lo supera di molto, prima di tutto guarda dalla fessura d'ombra che la rete
   delle feritoie non sia intasata di polvere o ragnatele.

## Smontaggio

Per la manutenzione: attacca la ventosa al centro del vetro e tira in avanti,
poi solleva il gruppo dai perni. Vetro, telaio ed elettronica escono come un
pezzo unico. Scollega prima ethernet e alimentazione se devi portarlo via.
Non c'è modo di separare il vetro dal telaio senza romperlo, ed è intenzionale:
è quello che permette di non avere nessuna vite in vista sul fronte.
