#!/usr/bin/env python3
"""Quote del videocitofono da incasso: un unico posto dove cambiarle.

Tutte le misure sono in millimetri. Il sistema di riferimento del frontale ha
origine al centro in orizzontale (x = 0 e' l'asse del pannello) e in basso in
verticale (y = 0 e' il bordo inferiore del vetro), perche' il montaggio avviene
allineando il basso del pannello alla quota del muro.

Le quote marcate "VERIFICARE" dipendono da componenti che vanno misurati con un
calibro prima di mandare i file in produzione: il modulo del display, lo stack
Pi + HAT audio + adattatore NVMe e il lettore NFC. Il resto si ricava da queste.
"""
from __future__ import annotations

import math

# --------------------------------------------------------------------------
# Display: OLED 5,5" 1080x1920 verticale, touch integrato, in HDMI
# La scheda del prodotto dice OLED e poi anche "design IPS": il calibro
# risolve la contraddizione, perche' il pannello nudo misura 0,4 mm e un LCD
# non ci sta, gli servirebbe il backlight. Conta perche' su OLED la luminosita'
# si abbassa in software, mentre su LCD servirebbe un PWM sul backlight.
# --------------------------------------------------------------------------
# Area attiva ricavata dalla risoluzione reale (1080x1920 con passo 0,063 mm),
# coerente con il framebuffer letto sull'unita' esterna.
DISPLAY_ATTIVO_L = 68.04
DISPLAY_ATTIVO_H = 120.96

# Ingombro del modulo, MISURATO sul pezzo: 70,0 x 125,0. La cornice non e'
# uniforme, ed e' questo il dato utile: in larghezza resta un millimetro per
# lato, in altezza due. Sopra e sotto c'e' quindi il doppio di superficie per
# incollare, e il vincolo stretto del progetto resta solo sui fianchi.
DISPLAY_MODULO_L = 70.0
DISPLAY_MODULO_H = 125.0
# Spessore col flat ripiegato, MISURATO: 1,8 mm, contro i 3,0 che il progetto
# assumeva. Il pannello nudo e' 0,4 mm, cioe' una lastra di vetro: l'1,8 e'
# quasi tutto coda ripiegata. Il millimetro e due decimi guadagnati non vanno
# in profondita' della cassa, vanno via dallo spazio fra vetro e telaio, dove
# sta la basetta del microfono: vedi SPAZIO_MIC.
DISPLAY_MODULO_S = 1.8
DISPLAY_PANNELLO_S = 0.4
DISPLAY_CORNICE_X = (DISPLAY_MODULO_L - DISPLAY_ATTIVO_L) / 2
DISPLAY_CORNICE_Y = (DISPLAY_MODULO_H - DISPLAY_ATTIVO_H) / 2
DISPLAY_CORNICE = min(DISPLAY_CORNICE_X, DISPLAY_CORNICE_Y)

# Sotto il bordo inferiore del pannello c'e' una zona FPC rigida, MISURATA
# 70,0 x 28,0 x 0,5, che porta il chip del driver e il connettore del flat: e'
# larga quanto tutto il pannello. Si ripiega dietro, e ripiegata rientra
# nell'1,8 complessivo. Se non si ripiegasse scenderebbe nella fascia sotto il
# display, dove sta il lettore NFC.
DISPLAY_CODA_L = 70.0
DISPLAY_CODA_H = 28.0
DISPLAY_CODA_S = 0.5
DISPLAY_CODA_RIPIEGATA = True

# Scheda di ingresso del display, MISURATA: quadrata, 43 x 43, spessa 4,5 coi
# connettori, con quattro fori da 2,5 a interasse 39 x 39. Era assunta
# 60 x 35 x 10: e' piu' piccola in larghezza, piu' alta e meno di meta' in
# spessore. USB-C e HDMI-A NON sporgono oltre il bordo del PCB.
DRIVER_L = 43.0
DRIVER_H = 43.0
DRIVER_S = 4.5
DRIVER_FORI_X = 39.0
DRIVER_FORI_Y = 39.0
DRIVER_FORO_D = 2.5
DRIVER_SPORGENZA_CONNETTORI = 0.0
# Il plug HDMI-A che ci si innesta, pero', sporge: una ventina di millimetri di
# guscio piu' la curva del cavo. E' per questo che il connettore va girato
# verso l'interno del vano e non verso la parete.
HDMI_A_PLUG_SPORGENZA = 20.0

# Schedina terminale, in fondo al flat largo: porta il connettore del pannello.
# MISURATA 39 x 20 x 2,0 coi due flat innestati. Va in piedi sullo stesso
# fianco della scheda di ingresso, cinque centimetri piu' in basso: e' l'unico
# punto che i due flat raggiungono entrambi. In piano non esiste posto, perche'
# la fascia sotto il Pi e' occupata dall'ansa del flat PCIe e dal patch, e
# quella sopra il Pi e' troppo lontana dall'asola per i 100 mm del flat del
# pannello. Le due distanze le controlla verifica().
TERMINALE_L = 39.0
TERMINALE_H = 20.0
TERMINALE_S = 2.0
TERMINALE_X = -36.0
TERMINALE_Y = 100.0

# Flat largo fra le due schede, MISURATO 95 x 25 disteso. E' la liberta' del
# gruppo: 95 mm bastano a tenere la schedina terminale dietro il display e la
# scheda di ingresso sul fianco.
FLAT_DRIVER_L = 95.0
FLAT_DRIVER_W = 25.0

# Squadretta che tiene in piedi la scheda di ingresso. Serve un pezzo e non
# "biadesivo o una squadretta" come diceva la procedura: la scheda porta il
# plug HDMI-A, che si innesta e si disinnesta, e un adesivo su un PCB che
# prende quella leva prima o poi cede. Il pezzo e' una L di lamiera piegata:
# l'ala corta si avvita al retro del telaio, l'ala lunga sta in piedi contro
# il fianco e prende i quattro fori della scheda.
#
# L'ala lunga va dalla parte del fianco e non verso l'interno: da quel lato
# restano 5 mm fino alla parete della cassa, abbastanza per la lamiera e per
# le teste delle viti, mentre verso l'interno ce ne sono 11 e ci passa il Pi.
STAFFA_S = 1.5                     # lamiera di alluminio, piegata a 90 gradi
# L'ala corta non puo' essere piu' lunga di cosi': oltre i 12 mm va a finire
# sotto la base dell'NVMe, che comincia a x -25,5 e sta alla stessa quota.
STAFFA_ALA_BASE = 12.0             # quanto entra sotto, sul retro del telaio
STAFFA_ALA_H = 47.0                # altezza in z dell'ala verticale
STAFFA_L = 47.0                    # sviluppo in y: 43 della scheda piu' bordo
STAFFA_FORO_SCHEDA_D = 2.7         # passaggio per le M2.5 della scheda
# Due fori diversi che prima erano lo stesso numero: nell'ala la vite passa,
# nel telaio si avvita. E quelli nel telaio sono ciechi, quindi filettati per
# forza: un cieco da 2,7 profondo 2 non trattiene una M2.5, la lascia girare.
STAFFA_FORO_ALA_D = 2.7            # passaggio M2.5 nell'ala della squadretta
STAFFA_FORO_TELAIO_D = 2.05        # preforo M2.5 nel telaio, cieco
STAFFA_FORI_TELAIO_PASSO = 32.0    # interasse dei due fori sul telaio
# I due fori nel telaio cadono dietro il display, perche' l'ala corta entra
# nel vano e il display e' largo 70 su un telaio da 89: non esiste un punto
# comodo fuori dalla sua ombra. Vanno quindi filettati M2.5 **ciechi dal
# retro**, 2 mm su 3 di spessore: il fronte del telaio resta intatto e la
# punta della vite non ha modo di arrivare al pannello, che gli corre a 1 mm.
# Un foro passante qui e' il genere di errore che si paga col display rotto.
STAFFA_FORI_CIECHI = True
STAFFA_FORO_PROF = 2.0
# Lo stacco fra retro del telaio e primo foro della scheda: la scheda comincia
# 2 mm dietro il telaio e il suo primo foro altri 2 mm dopo.
STAFFA_Z0 = 8.0                    # il piano dell'ala base, cioe' il telaio
STAFFA_X = -39.7                   # piano dell'ala verticale


def posizioni_fori_staffa() -> list[tuple[float, float]]:
    """I due fori da filettare nel telaio per la squadretta del display.

    Cadono a meta' dell'ala corta, sopra la finestra del display e sotto
    l'altoparlante: e' la fascia di telaio pieno che resta su quel fianco.
    """
    x = STAFFA_X + STAFFA_S / 2 + STAFFA_ALA_BASE / 2
    return [(x, DRIVER_Y + sy * STAFFA_FORI_TELAIO_PASSO / 2)
            for sy in (-1, 1)]
# Sta in piedi sul fianco, col lato lungo in verticale: dietro il telaio non
# esiste nessuna fascia orizzontale libera alta 35 mm, perche' fra il Pi e la
# camera ne restano 27. Di lato invece ci sono 17,5 mm di luce e tutta
# l'altezza. Il fianco e' quello del lato GPIO del Pi, dove in orizzontale non
# esce nulla, e non quello dei micro-HDMI: da quel lato il cavo ha bisogno di
# tutti i 17,5 mm e fra bordo scheda e scheda video ne resterebbero 3.
DRIVER_X = -36.0
DRIVER_Y = 150.0
# Su quale fianco escono i micro-HDMI, nel riferimento del vetro. Il Pi si
# guarda dal lato saldature, perche' gli HAT crescono verso il fondo della
# cassa: l'immagine e' quindi specchiata rispetto alle foto dei cataloghi, e
# con l'RJ45 in basso i micro-HDMI finiscono a destra.
HDMI_LATO_X = 1

# --------------------------------------------------------------------------
# Vetro frontale
# --------------------------------------------------------------------------
# Le proporzioni (1:2,2) riprendono il pannello di riferimento; la larghezza
# nasce dal display: 68 mm di area attiva con 16 mm di margine per lato.
VETRO_L = 100.0
VETRO_H = 240.0
# Corning Gorilla Glass 3 da 2 mm, alluminosilicato rinforzato chimicamente.
# Lo spessore e' il motivo della scelta, non il marchio: il touch capacitivo
# deve leggere attraverso il vetro, e la sensibilita' di questo modulo non e'
# regolabile. Sotto i 3 mm il float non si tempra termicamente, quindi per
# scendere a 2 mm l'alluminosilicato e' l'unica strada.
VETRO_S = 2.0
VETRO_RAGGIO = 3.0

# Il modulo e' centrato sul pannello: da qui nascono tutte le quote in altezza
# della zona display.
DISPLAY_MODULO_Y0 = (VETRO_H - DISPLAY_MODULO_H) / 2

# Finestra trasparente del display: area attiva piu' mezzo millimetro per lato,
# cosi' la serigrafia non mangia pixel. Resta mezzo millimetro di cornice in
# vista, nera su nero e quindi invisibile.
FINESTRA_DISPLAY_L = DISPLAY_ATTIVO_L + 1.0
FINESTRA_DISPLAY_H = DISPLAY_ATTIVO_H + 1.0
FINESTRA_DISPLAY_Y = DISPLAY_MODULO_Y0 \
    + (DISPLAY_MODULO_H - FINESTRA_DISPLAY_H) / 2

# Finestra trasparente dell'obiettivo. Unica: la luminosita' del display e'
# gestita via software, quindi un sensore ambientale non c'e' e il foro sarebbe
# stato solo decorativo. Il diametro non e' estetico ma ottico, e lo calcola
# finestra_ottica_minima(): la finestra si comporta come un diaframma posto
# davanti all'obiettivo e se e' troppo piccola vignetta gli angoli.
OTTICA_D = 10.0
OTTICA_Y = 202.0

# Microfono: foro passante nel vetro, eseguito al CNC prima del rinforzo
# chimico. Sul vetro temperato il minimo era pari allo spessore; qui la
# lavorazione e' a controllo numerico sul crudo, quindi 3 mm sono comodi.
# Dietro va una membrana acustica.
MICROFONO_D = 3.0
MICROFONO_X = -32.0
MICROFONO_Y = 202.0

# Griglia dell'altoparlante: e' solo serigrafia. Il suono esce dalla fessura
# perimetrale superiore, perche' forare il vetro temperato con fessure strette
# non e' realizzabile e indebolirebbe il pannello.
GRIGLIA_L = 76.0
GRIGLIA_SPESSORE = 1.5
GRIGLIA_PASSO = 3.5
GRIGLIA_N = 3
# Quota della prima striscia. Essendo finestre, attraverso di loro si vede
# quello che c'e' dietro, e a 223 la terza finiva a 231,5: in pieno sulla
# fascia dei due magneti alti e dei due fori perno, che si sarebbero visti in
# trasparenza come quattro buchi. Da 215 le tre strisce stanno dentro la luce
# dell'altoparlante nel telaio, che va da 213 a 226, quindi si affacciano sul
# vano e non sul metallo forato.
GRIGLIA_Y = 215.0

# Zona di lettura NFC: icona serigrafata semitrasparente, retroilluminata.
# L'icona va dove legge l'antenna, e l'antenna non e' al centro della scheda:
# NFC_X viene percio' da NFC_ANTENNA_OFFSET_X, piu' in basso. Lasciarla al
# centro del pannello vorrebbe dire invitare ad appoggiare il tag dove la
# scheda ha il suo PN532 e il convertitore USB, non la spira.
NFC_D = 22.0
NFC_Y = 30.0

# --------------------------------------------------------------------------
# Cassa da incasso
# --------------------------------------------------------------------------
# Resta 3 mm piu' piccola del vetro per lato: il vetro la copre interamente e
# fra il suo bordo e l'intonaco resta una fessura d'ombra continua, che e' la
# via d'aria e allo stesso tempo l'unico dettaglio visibile del montaggio.
OMBRA_PERIMETRALE = 3.0
CASSA_L = VETRO_L - 2 * OMBRA_PERIMETRALE
CASSA_H = VETRO_H - 2 * OMBRA_PERIMETRALE
# Il muro e' in tufo, profondo 200 mm, e la nicchia puo' arrivare a 170, ma non serve
# andare oltre: quello che conta e' il canale d'aria che resta dietro i
# componenti, e perche' il canale non sia il collo di bottiglia basta che la
# sua sezione superi quella lorda di una feritoia, cioe' 13,2 mm su 91. Il
# conto vero lo fanno canale_aria() e gruppo_massimo(), e il riepilogo stampa
# quanti millimetri di gruppo del Pi restano prima che il canale diventi lui
# il collo di bottiglia: e' il margine per l'incertezza della misura.
CASSA_PROF = 75.0
CASSA_PARETE = 1.5

CASSA_INT_L = CASSA_L - 2 * CASSA_PARETE
CASSA_INT_H = CASSA_H - 2 * CASSA_PARETE

# Luce finita dell'intonaco: il vetro piu' la fessura d'ombra su ogni lato.
LUCE_INTONACO_L = VETRO_L + 2 * OMBRA_PERIMETRALE
LUCE_INTONACO_H = VETRO_H + 2 * OMBRA_PERIMETRALE

# Cornice d'intonaco: un anello che fa parte della cassa, col fronte sul piano
# dell'intonaco finito e la faccia interna sulla luce. Il vetro sta 5 mm
# davanti al fronte della cassa (Z_TELAIO), quindi a cassa "a filo
# dell'intonaco" il vetro sporgeva di 5 mm; e il bordo della luce, tirato a
# mano dal rasante, decideva da solo se la fessura d'ombra veniva di 3 mm.
# Con la cornice la posa ha un riscontro fisico - si rasa a filo della
# cornice - e la fessura la fa il modello. Fra cornice e fianchi della cassa
# resta un canale largo due volte l'ombra, chiuso in fondo dalla flangia: e'
# li' che si affacciano le feritoie, e la malta non ci puo' entrare.
CORNICE_S = CASSA_PARETE
CORNICE_L = LUCE_INTONACO_L + 2 * CORNICE_S
CORNICE_H = LUCE_INTONACO_H + 2 * CORNICE_S
CANALE_PERIMETRALE = (LUCE_INTONACO_L - CASSA_L) / 2

# Flangia di muratura: aletta che annega nella malta e chiude in fondo il
# canale perimetrale. Sta dietro le feritoie (FLANGIA_ARRETRAMENTO e' piu'
# sotto, insieme a loro) e sporge oltre la cornice quanto basta per i fori
# d'ancoraggio, che devono stare fuori dal canale.
FLANGIA_ALA = 10.0
FLANGIA = CANALE_PERIMETRALE + CORNICE_S + FLANGIA_ALA
FLANGIA_FORO_D = 5.0
FLANGIA_FORI_X = CASSA_L / 2 + CANALE_PERIMETRALE + CORNICE_S + FLANGIA_ALA / 2
FLANGIA_FORI_PASSO = 55.0          # quattro per fianco, centrati in altezza
FLANGIA_FORI_N = 4

# Nicchia da scavare. La profondita' si misura dal piano dell'intonaco
# finito, che sul muro esistente e' la sua superficie: e' l'unico riferimento
# che chi scava ha davanti, e il fondo della cassa ci sta a Z_TELAIO +
# CASSA_PROF.
FORO_MURO_L = CASSA_L + 2 * FLANGIA + 6.0
FORO_MURO_H = CASSA_H + 2 * FLANGIA + 6.0

# Passaggi per i cavi sul fondo. Con il PoE ne serve uno, quello di rete: il
# secondo resta come riserva con un filo pilota, perche' nel tufo murato tirare
# un cavo nuovo costa piu' che predisporlo.
CORRUGATO_D = 25.0
CORRUGATO_PASSO = 40.0

# --------------------------------------------------------------------------
# Telaio portante estraibile
# --------------------------------------------------------------------------
# Piastra in alluminio che porta display, Pi, camera, altoparlante e lettore.
# Entra nella cassa con 1 mm di gioco per lato e si fissa con quattro viti.
TELAIO_L = CASSA_INT_L - 2.0
TELAIO_H = CASSA_INT_H - 2.0
TELAIO_S = 3.0

# Dietro il display il telaio resta pieno, senza nessuna finestra. Serve per
# due motivi che si tengono: fa da appoggio continuo al pannello, che con un
# millimetro di cornice non puo' restare appeso al solo adesivo, e distribuisce
# la pressione invece di concentrarla su una cornice stretta, che lascerebbe
# aloni; e porta i quattro fori del Raspberry, che cadono in pieno nell'area
# del display e in una finestra non avrebbero materiale da filettare.
# Passa solo il flat, da un'asola a cavallo del bordo inferiore del modulo.
# Flat del pannello, MISURATO: largo 13,0, lungo circa 100 ma con curve, e
# l'asse cade esattamente in mezzo al bordo inferiore, come il progetto
# assumeva. Le due linguette rigide che si vedono sul percorso sono punti di
# ancoraggio e hanno lo stesso spessore del flat, quindi nell'asola passano:
# era l'unico dubbio che avrebbe costretto a fare l'asola piu' larga.
FLAT_PANNELLO_W = 13.0
FLAT_PANNELLO_LUNG = 100.0
FLAT_ASOLA_L = 18.0               # il flat misurato piu' gioco da ogni lato
FLAT_ASOLA_H = 8.0
FLAT_ASOLA_X = 0.0                # misurato: il flat esce centrato
FLAT_ASOLA_Y = DISPLAY_MODULO_Y0
# Quota del bordo inferiore del telaio nel sistema di riferimento del vetro.
# Tutti i disegni usano quello: il telaio e' centrato, quindi parte 5,5 mm
# sopra il bordo del vetro e non da zero.
TELAIO_Y0 = (VETRO_H - TELAIO_H) / 2

# Raspberry Pi 5: interasse dei fori di fissaggio e ingombro della scheda.
PI_L = 85.0
PI_H = 56.0
PI_FORI_X = 58.0
PI_FORI_Y = 49.0
# Preforo da filettare M2.5, non passaggio: la vite prende nei 3 mm del
# telaio e non c'e' nessun dado dietro. Con il 2,7 che c'era qui prima - che
# e' la misura del foro di passaggio - non restava materiale da filettare e
# le quattro viti del Raspberry non avrebbero avuto presa su niente.
PI_FORO_D = 2.05                   # preforo M2.5 (passo 0,45)
PI_MARGINE_FORI = 3.5              # distanza dei fori dal bordo scheda
# Altezza dello stack Pi 5 + adattatore NVMe + PoE HAT (F) + HAT audio
# Pi MIC V3 + ventola. MISURATO dal piano del telaio (MISURE.md, sezione 2):
# 40,5 mm alla cima dei pin liberi, 50,0 con i Dupont dell'NVMe innestati.
# Conta la seconda, perche' quei connettori non si possono togliere.
# Attenzione alla convenzione, perche' qui ci si sbaglia: PI_STACK_H parte dal
# PCB del Pi, che sta sui distanziali, e il gruppo e' la loro somma. Con 10 di
# distanziale e 40,5 qui il modello tiene 50,5, mezzo millimetro sopra la
# misura: e' a favore di sicurezza, e prima di scavare la nicchia il gruppo si
# rimisura comunque (ASSEMBLAGGIO.md, fase 5).
PI_STACK_H = 40.5
# Spazio fra il telaio e il PCB del Pi. Non e' aria: l'SSD NVMe sta su una
# base sotto il Pi, collegata con un flat PCIe che fa un'ansa oltre il bordo
# della scheda. Questo spazio e' quindi occupato, e l'aria che il progetto
# faceva passare qui sotto in realta' deve girare attorno alla base.
# La quota la fissa il distanziale, che e' un pezzo commerciale da 10, non
# l'ingombro che ci deve stare dentro: base piu' SSD montato misurano 9,5 e
# avanza mezzo millimetro. Tenere qui il 9,5 era comodo e sbagliato - diceva
# che il PCB del Pi appoggia a 9,5 dal telaio, mentre appoggia a 10 - e
# falsava di mezzo millimetro tutta la catena del gruppo, comprese le
# lunghezze delle viti.
PI_DISTANZIALI = 10.0
NVME_BASE_S = 9.5                  # MISURATO: base piu' SSD montato
# Altezza di tutto il gruppo dal piano del telaio alla cima dei pin: e' la sola
# quota che si misura direttamente, e quella da confrontare col calibro.
PI_GRUPPO_H = PI_DISTANZIALI + PI_STACK_H

# Ingombro in pianta della base NVMe sotto il Pi, misurato: sta dentro il
# profilo della scheda (56 x 85) e non e' lei a dettare la larghezza.
NVME_BASE_L = 51.0
NVME_BASE_H = 65.0

# Quanto sporgono, oltre il bordo del PCB, le tre cose che escono dal Pi. Sono
# misurate col cavo o col flat montati, che e' l'unica condizione che conta, e
# sono tutte piu' grandi dei 17,5 mm che restano ai fianchi: per questo
# l'orientamento della scheda nel vano non e' libero.
#
# Sul Pi 5 l'RJ45 e il connettore PCIe stanno sul bordo CORTO, da 56 mm, che
# qui e' orizzontale: sporgono quindi in verticale, dove c'e' posto fra il
# lettore NFC e la scheda. I micro-HDMI stanno sul bordo LUNGO, cioe' su un
# fianco, dove di millimetri ce ne sono 17,5 e non bastano.
PCIE_ANSA = 25.0                   # ansa del flat che torna alla base NVMe
RJ45_SPORGENZA = 34.0              # col patch inserito
HDMI_SPORGENZA = 20.0              # col cavo diritto inserito: non ci sta
# Dai 20 mm del cavo diritto si scende a 8 con un micro-HDMI a uscita
# angolata a 90 gradi, e diventa l'unico modo di stare nei 17,5 mm del fianco.
# Non e' un accessorio opzionale: senza, il cavo spinge contro la parete della
# cassa e il connettore del Pi lavora in leva.
HDMI_ANGOLATO_SPORGENZA = 8.0
# Il Pi si monta con i connettori di rete e PCIe verso il BASSO: li' l'aria
# entra dalla feritoia inferiore, i corrugati arrivano dal fondo e fra il
# lettore NFC e il bordo della scheda ci sono 27 mm liberi. Girarlo vorrebbe
# dire mandare il patch addosso alla camera e all'altoparlante.
PI_CONNETTORI_IN_BASSO = True
# Scheda centrata in altezza: l'aria entra dalla fessura in basso, lambisce il
# dissipatore a meta' altezza ed esce da quella in alto.
PI_Y0 = (VETRO_H - PI_L) / 2       # quota del bordo inferiore della scheda

# Camera Module 3 standard, variante confermata dal Raspberry: libcamera la
# riporta come "imx708" e non "imx708_wide". Quote dal product brief ufficiale
# di giugno 2024, tolleranza dichiarata 0,2 mm.
CAMERA_PCB_L = 25.0
CAMERA_PCB_H = 23.862
CAMERA_PCB_S = 1.12
CAMERA_X = 0.0
CAMERA_FORI_X = 21.0               # fori a 2,0 mm dai bordi laterali
CAMERA_FORI_Y = 12.5
# Quote primarie da cui nasce il decentramento, entrambe misurate dal bordo
# del PCB che porta il connettore. Sono quelle del disegno quotato e del
# modello STEP ufficiale, che su queste concordano.
CAMERA_ASSE_DAL_BORDO = 14.5
CAMERA_FORI_DAL_BORDO = 2.0
CAMERA_FORO_D = 1.6                # preforo M2 (passo 0,4)
CAMERA_FORO_RISPETTO_D = 4.75      # zona di rispetto attorno al foro
CAMERA_LENTE_D = 5.75              # barilotto; 6.95 sulla variante wide
CAMERA_LENTE_FRONTALE_D = 4.0       # VERIFICARE col calibro: la lente in vista
CAMERA_BASE_L = 10.8               # base quadrata del gruppo ottico
CAMERA_BASE_S = 2.75               # quanto la base sporge sopra il PCB
# Campo visivo della variante standard: 66 x 41 gradi, 75 in diagonale. E' la
# diagonale che conta per dimensionare una finestra tonda.
CAMERA_FOV_DIAGONALE = 75.0

# L'asse ottico non e' al centro dei quattro fori, e i quattro fori non sono
# centrati sul PCB: sono due decentramenti distinti e vanno tenuti separati.
# I fori stanno a 2,0 mm dal bordo del connettore e a 2,0 dai bordi laterali,
# con interasse 12,5 x 21; l'asse ottico cade a 14,5 dal bordo del connettore,
# cioe' in pratica sulla fila di fori opposta al connettore.
# Il primo valore serve per filettare il telaio, il secondo per sapere dove
# finisce il PCB. Scambiarli vuol dire montare la camera fuori dalla finestra.
CAMERA_ASSE_OFFSET = CAMERA_ASSE_DAL_BORDO \
    - (CAMERA_FORI_DAL_BORDO + CAMERA_FORI_Y / 2)
CAMERA_PCB_OFFSET = CAMERA_ASSE_DAL_BORDO - CAMERA_PCB_H / 2

# Il modulo si monta col connettore verso il basso, dove c'e' il Raspberry, e
# il flat scende senza torsioni. Da qui il segno degli offset: fori e PCB
# stanno sotto l'asse ottico.
CAMERA_FORI_Y0 = OTTICA_Y - CAMERA_ASSE_OFFSET
CAMERA_PCB_Y0 = OTTICA_Y - CAMERA_PCB_OFFSET

# Altezza totale, dal retro del PCB alla punta dell'obiettivo. E' la quota che
# ha imposto di arretrare il modulo: sporge piu' dello spazio che c'e' fra il
# retro del telaio e il vetro, quindi la scheda non puo' appoggiare al telaio.
CAMERA_ALTEZZA = 11.3              # 12.0 sulla variante wide
CAMERA_COLONNINE = 6.0             # distanziali fra telaio e PCB
# Dietro il PCB ci sono solo componenti bassi: nel modello STEP ufficiale
# arrivano a 2,6 mm e il connettore FPC sta sulla faccia dell'obiettivo, non
# su questa. Il flat si piega quindi nello spazio delle colonnine, non dietro.
CAMERA_CONNETTORE_S = 2.6          # VERIFICARE sul pezzo
# Quanto il modulo sporge dietro il telaio: e' la quota che decide di quanto
# arretrare l'altoparlante per scavalcarlo.
CAMERA_SPORGENZA = CAMERA_COLONNINE + CAMERA_PCB_S + CAMERA_CONNETTORE_S
# Il barilotto attraversa il telaio: il foro va largo quanto basta a infilarlo
# senza toccarlo, perche' un contatto rigido trasmette all'ottica le vibrazioni
# dell'altoparlante.
GIOCO_LENTE_TELAIO = 1.25


def posizioni_fori_camera() -> list[tuple[float, float]]:
    """I quattro fori M2 da filettare nel telaio per le colonnine.

    Sono centrati su CAMERA_FORI_Y0 e non sull'asse ottico: la differenza e' il
    decentramento dichiarato dal costruttore, che vale 6,25 mm. La fila
    superiore cade quindi in pratica sull'asse dell'obiettivo.
    """
    return [(CAMERA_X + sx * CAMERA_FORI_X / 2,
             CAMERA_FORI_Y0 + sy * CAMERA_FORI_Y / 2)
            for sx in (-1, 1) for sy in (-1, 1)]

# Microfono I2S su basetta separata. L'HAT MIC+ V3 lo collega con sei fili a
# passo 2,54 (3V3, GND, BCLK, DOUT, WB, SEL) e lo da' per prolungabile: il
# microfono si porta quindi dietro al foro del vetro, invece di restare in
# mezzo allo stack dove sentirebbe soltanto la ventola. Si incolla alla faccia
# interna del vetro, nello spessore che il display occupa piu' in basso.
# MISURATO: e' una strisciolina, non il quadrato che il progetto assumeva.
MIC_PCB_L = 15.5
MIC_PCB_H = 6.5
MIC_PCB_S = 1.5                    # solo PCB
MIC_INGOMBRO_S = 2.5               # col microfono sopra il PCB
# L'apertura acustica sta sulla faccia DEI PIN, non su quella delle saldature:
# e' quindi quella faccia che va incollata al vetro, girata rispetto a come il
# progetto la immaginava. Non cambia le quote, cambia il montaggio, e ne segue
# una prescrizione: i fili vanno saldati dal lato opposto, infilandoli nei fori
# del pettine dissaldato, perche' saldarli sulla faccia a vista vorrebbe dire
# mettere lo stagno fra la basetta e il vetro.
MIC_APERTURA_LATO_PIN = True
# Il pettine a sei pin va dissaldato e i fili saldati ai pad: da solo e' alto
# 8,5 mm e nello spazio fra vetro e telaio non ci sta. Nel telaio serve quindi
# un'asola per il passaggio dei fili.
MIC_ASOLA_L = 12.0
MIC_ASOLA_H = 4.0
MIC_ASOLA_Y = 190.0

# Lo spazio in cui deve starci e' quello fra vetro e telaio, che e' lo spessore
# del biadesivo del telaio: 3,0 mm, contro i 2,5 della basetta. Ci sta, con
# mezzo millimetro. La misura del display non lo ha cambiato, perche' quella
# distanza la fissa l'incollaggio del telaio e non il display.

# Altoparlante rettangolare con cono ovale e flangia a quattro fori, quello
# gia' disponibile, sui morsetti a vite dell'HAT audio. MISURATO col calibro.
SPEAKER_L = 69.5
SPEAKER_H = 30.5
SPEAKER_S = 16.5                   # spessore totale, magnete compreso
SPEAKER_FORI_X = 63.5              # interasse dei quattro fori di flangia
SPEAKER_FORI_Y = 24.0
SPEAKER_FORO_D = 2.5               # M3 da filettare nel telaio
# Foro nella flangia dell'altoparlante: 3,5 mm misurati, quindi una M3 passa
# con gioco e il filetto sta nel telaio, come previsto.
SPEAKER_FLANGIA_FORO_D = 3.5
# Non si affaccia al vetro: li' il vetro e' pieno e la griglia e' solo
# serigrafia. Sta quindi arretrato nel vano, montato su colonnine sul retro del
# telaio, abbastanza indietro da scavalcare la camera. Il cono guarda il
# telaio e carica la cavita' da cui si affaccia la feritoia d'uscita.
SPEAKER_X = 0.0
SPEAKER_Y = 211.0
SPEAKER_ARRETRAMENTO = 14.0        # dal retro del telaio alla flangia
# Luce nel telaio davanti al cono: non deve essere grande come il cono, perche'
# la cavita' non e' stagna, ma serve a non chiudergli il fronte. Sta sopra il
# microfono e la lente, che occupano la stessa fascia.
SPEAKER_LUCE_L = 40.0
SPEAKER_LUCE_H = 13.0
SPEAKER_LUCE_Y = 219.5


def posizioni_fori_speaker() -> list[tuple[float, float]]:
    """Fori della flangia da filettare M3 nel telaio.

    Se ne usano tre: il quarto cadrebbe dietro la basetta del microfono, dove
    la punta della vite arriverebbe a toccarla. Per trenta grammi di
    altoparlante tre viti bastano.
    """
    escluso = (1 if MICROFONO_X > 0 else -1, -1)
    return [(SPEAKER_X + sx * SPEAKER_FORI_X / 2,
             SPEAKER_Y + sy * SPEAKER_FORI_Y / 2)
            for sx in (-1, 1) for sy in (-1, 1)
            if (sx, sy) != escluso]

# Lettore NFC PN532 con adattatore USB-seriale. MISURATO, ed e' mezza scheda
# piu' grande di quanto il progetto assumeva: 60 x 38 invece di 43 x 41.
NFC_PCB_L = 60.0
NFC_PCB_H = 38.0
NFC_PCB_S = 5.0                    # spessore totale, connettore escluso
NFC_FORI_INTERASSE_X = 54.0        # i quattro fori stanno a 3 mm dai bordi
NFC_FORI_INTERASSE_Y = 32.0
NFC_FORO_D = 2.5                   # preforo M3 (passo 0,5)
# L'antenna non e' centrata sulla scheda: la spira occupa la metA sinistra,
# l'altra metA porta il PN532, il convertitore USB e il connettore. Misurata
# sulla foto, la spira sta fra 2,3 e 34,6 mm dal bordo sinistro, quindi il suo
# centro cade 11,5 mm a sinistra del centro della scheda.
# VERIFICARE col calibro: distanza della spira dai bordi.
NFC_ANTENNA_L = 32.3
NFC_ANTENNA_H = 35.0
NFC_ANTENNA_OFFSET_X = -11.5       # dal centro del PCB al centro della spira
# L'antenna non puo' avere l'alluminio del telaio alle spalle, lo schermo
# ucciderebbe la portata: il telaio e' aperto in questa zona e la scheda si
# monta sul retro, guardando il vetro attraverso l'apertura.
# L'apertura cade dentro la spira, non attorno: coprire d'alluminio i
# conduttori attenua poco, mentre l'area interna deve restare libera. Cosi'
# resta anche un appoggio continuo di 3 mm su tutto il perimetro del PCB.
NFC_APERTURA_L = 30.0
NFC_APERTURA_H = 32.0
# I fori di fissaggio stanno fuori dall'apertura, con abbastanza alluminio da
# reggere il filetto: a quattro millimetri dal bordo ne restavano meno di uno.
# Il PCB resta centrato sul pannello: spostarlo per centrare l'antenna lo
# porterebbe col connettore USB-C a filo del fianco della cassa, e li' il cavo
# non entra. Si sposta invece l'icona sul vetro.
NFC_PCB_X = 0.0
NFC_X = NFC_PCB_X + NFC_ANTENNA_OFFSET_X
# Dei quattro fori della scheda se ne usano due, quelli dal lato
# dell'elettronica: gli altri due cadono a mezzo millimetro dall'apertura e
# non lascerebbero alluminio da filettare. Dal lato dell'antenna il PCB
# appoggia sul perimetro dell'apertura, che basta a una scheda da dieci grammi.
NFC_FORI_USATI_X = 1               # +1 destra, -1 sinistra
# Il connettore USB-C sporge dal bordo della scheda e vuole il suo cavo. Con
# un'uscita angolata a 90 gradi sta nei millimetri che restano fino al fianco
# della cassa; con un cavo diritto, no.
NFC_USB_SPORGENZA = 2.3            # il connettore oltre il bordo del PCB
NFC_USB_CAVO_ANGOLATO = 9.0        # il guscio del cavo, angolato
def posizioni_fori_nfc() -> list[tuple[float, float]]:
    """I fori da filettare nel telaio per il lettore NFC.

    Sono due e non quattro, ed entrambi dal lato dell'elettronica: dal lato
    della spira i fori della scheda cadono a filo dell'apertura.
    """
    return [(NFC_PCB_X + NFC_FORI_USATI_X * NFC_FORI_INTERASSE_X / 2,
             NFC_Y + sy * NFC_FORI_INTERASSE_Y / 2) for sy in (-1, 1)]


# Distanza fra antenna e faccia interna del vetro: il lettore appoggia al retro
# del telaio, quindi e' Z_TELAIO + TELAIO_S e non un numero scelto. Con 2 mm di
# vetro piu' questi restano circa due centimetri di portata utile sul tag. Il
# valore e' ripetuto qui perche' Z_TELAIO e' definito piu' sotto, e un
# controllo in verifica() si accorge se i due si scollano: e' appunto quello
# che e' successo quando il display misurato ha portato il telaio piu' avanti.
NFC_DISTANZA_VETRO = 8.0

# Fissaggio del telaio nella cassa. Non puo' avvenire con viti: sul fronte
# finirebbero sotto il vetro incollato, e dal basso avrebbero la testa annegata
# nella malta. L'unico accesso dall'esterno e' la fessura d'ombra da 3 mm, che
# non lascia spazio a una chiave. Il gruppo si tiene quindi su sei magneti,
# centrato da due perni, e si estrae con una ventosa sul vetro. La sicurezza si
# risolve in software: un reed switch avverte Home Assistant se qualcuno lo
# stacca, e la camera e' gia' li'.
PERNO_D = 4.0                      # perni di centraggio sulla battuta
PERNO_FORO_D = 4.3                 # foro corrispondente nel telaio
PERNO_PASSO = 48.0
# Lunghezza del perno misurata dalla battuta in avanti, cioe' dal retro del
# telaio. A 6 mm attraversava i 3 mm di telaio e continuava per altri 3
# nell'intercapedine del biadesivo, arrivando a toccare il retro del vetro: la
# spinta con cui si accosta il gruppo sarebbe passata per due punte d'acciaio
# da 4 mm appoggiate al Gorilla, invece che per la schiuma del VHB. A filo del
# fronte del telaio il perno guida su tutto lo spessore e non tocca niente.
PERNO_SPORGENZA = 3.0
PERNO_MARGINE = 8.0                # distanza dei perni dal bordo superiore

# Magneti al neodimio N42 in sedi passanti nel telaio, incollati a filo della
# faccia posteriore. Il diametro e' vincolato due volte: la sede deve cadere
# nella striscia dove telaio e battuta si sovrappongono, larga appena 5 mm, e
# deve lasciare parete fra se' e il bordo del telaio. Un Ø5 a 2,5 mm dal bordo
# le soddisfa entrambe solo sulla carta: il suo raggio e' 2,5, quindi la sede
# nasce tangente al bordo e in taglio laser diventa una tacca aperta, senza
# nulla che trattenga il magnete di lato. Con Ø4 a 3,0 mm restano 1,0 mm di
# parete e la sede sta comunque tutta sopra la battuta. Si perde tiro: sei Ø4x3
# tengono circa 3 kg contro i 500 g del gruppo, sei volte il peso invece di
# otto, che e' ancora abbondante per non farlo vibrare.
MAGNETE_D = 4.0
MAGNETE_S = 3.0
MAGNETE_MARGINE = 3.0              # dal bordo del telaio al centro del magnete
# Quello che il laser taglia non e' il magnete ma la sua sede, un decimo piu'
# larga per farlo entrare. E' la sede a decidere quanta parete resta verso il
# bordo, quindi e' lei che va nei controlli: con il diametro del magnete la
# parete risultava 1,00 mm invece dei 0,95 reali.
MAGNETE_SEDE_D = MAGNETE_D + 0.1


def posizioni_magneti() -> list[tuple[float, float]]:
    """Quattro magneti agli angoli e due a meta' dei fianchi."""
    y_basso = TELAIO_Y0 + MAGNETE_MARGINE
    y_alto = TELAIO_Y0 + TELAIO_H - MAGNETE_MARGINE
    x_ang = 32.0
    x_lat = TELAIO_L / 2 - MAGNETE_MARGINE
    return [(sx * x_ang, y) for sx in (-1, 1) for y in (y_basso, y_alto)] \
        + [(sx * x_lat, VETRO_H / 2) for sx in (-1, 1)]

# Reed switch di antimanomissione, incollato sul retro del telaio in basso, con
# il suo magnete sulla battuta della cassa.
REED_X = -32.0
REED_L = 14.0
REED_H = 4.0

# Battuta interna sul fronte della cassa: il telaio si appoggia qui invece di
# cadere dentro. E' un gradino di pochi millimetri, non un restringimento per
# tutta la profondita': dietro serve il vano pieno.
BATTUTA = 6.0
BATTUTA_PROF = 4.0
# La squadretta della scheda di ingresso sta in piedi a 5 mm dal fianco e
# l'anello e' largo 6: la sua ala verticale ci cadeva sopra per quasi un
# millimetro e il telaio non arrivava in appoggio. Lungo la squadretta l'anello
# si restringe, con mezzo millimetro di gioco.
SCARICO_STAFFA_X = STAFFA_X - STAFFA_S / 2 - 0.5
SCARICO_STAFFA_Y0 = DRIVER_Y - STAFFA_L / 2 - 1.0
SCARICO_STAFFA_Y1 = DRIVER_Y + STAFFA_L / 2 + 1.0

# Riscontri ferrosi: il telaio e' alluminio, la cassa e' stampata in ASA, e i
# magneti hanno bisogno di qualcosa da attrarre. Vanno sei dischetti di acciaio
# dolce dietro ai sei magneti.
#
# Due cose che il progetto sbagliava, e che si vedono solo facendo i conti.
# La prima: un dischetto appoggiato sulla battuta si infila fra battuta e
# magnete e solleva tutto il gruppo del suo spessore, mentre il vetro deve
# restare a filo dell'intonaco. Quindi va annegato in una sede.
# La seconda: la sede non sta dove si sarebbe tentati di metterla, cioe'
# centrata sul magnete. L'anello di battuta e' largo 6 mm ma i magneti ne
# stanno a 4 dal bordo del vano, quindi dalla loro parte interna ne restano 2 e
# una sede centrata su di loro sborda dentro il vano. Allargare la battuta con
# un'isola di materiale sembra la via d'uscita e non lo e': appena si prova, il
# controllo di interferenza fa vedere che sotto, a mezzo millimetro dalla
# battuta, passa il lettore NFC.
#
# La sede va invece centrata sull'asse della battuta, non sul magnete. Un
# dischetto O6 cosi' posizionato copre interamente il magnete O4 (che e'
# l'unica cosa che conta, perche' serve ferro davanti al magnete) e resta tutto
# sull'anello, senza isole e senza toccare niente.
RISCONTRO_D = 6.0
RISCONTRO_S = 1.0
RISCONTRO_GIOCO = 0.4              # la sede va scavata un po' larga
RISCONTRO_SEDE_D = RISCONTRO_D + RISCONTRO_GIOCO
RISCONTRO_SEDE_PROF = RISCONTRO_S + 0.2
# Quanto la sede puo' sbordare dall'anello. Non e' zero perche' non puo'
# esserlo: la sede col suo gioco e' 6,4 su un anello di 6,0, e il magnete non si
# puo' spostare al centro dell'anello perche' nel telaio gli resterebbe meno di
# un millimetro di parete verso il bordo. Due decimi per lato non togliono
# appoggio al telaio, che poggia su cinque millimetri di anello, e non lasciano
# il dischetto a sbalzo, che e' comunque incollato.
RISCONTRO_SBORDO_MAX = 0.5


def posizioni_riscontri() -> list[tuple[float, float]]:
    """Dove cade ogni sede: sul magnete in un asse, sulla battuta nell'altro.

    Lungo il perimetro la sede segue il magnete, perche' da quella parte di
    anello ce n'e' quanto se ne vuole. Nell'altro asse si mette a metezza
    dell'anello, che e' l'unico modo di starci dentro tutta.
    """
    x0, x1 = -CASSA_INT_L / 2, CASSA_INT_L / 2
    y0 = VETRO_H / 2 - CASSA_INT_H / 2
    y1 = VETRO_H / 2 + CASSA_INT_H / 2
    sedi = []
    for mx, my in posizioni_magneti():
        # Su quale lato dell'anello sta questo magnete: quello da cui dista meno.
        if min(mx - x0, x1 - mx) < min(my - y0, y1 - my):
            bordo = x0 if mx < 0 else x1
            sedi.append((bordo + (BATTUTA / 2 if mx < 0 else -BATTUTA / 2), my))
        else:
            bordo = y0 if my < VETRO_H / 2 else y1
            sedi.append((mx, bordo + (BATTUTA / 2 if my < VETRO_H / 2
                                      else -BATTUTA / 2)))
    return sedi

# --------------------------------------------------------------------------
# Ventilazione
# --------------------------------------------------------------------------
# L'aria entra da una feritoia nella parete bassa ed esce da due feritoie nei
# fianchi, in alto. Nessuna sul fronte, che e' coperto dal vetro, e nessuna
# nella parete alta: li' guarderebbe in su, proprio sotto la fessura d'ombra,
# e l'acqua che entra dalla fessura ci cadrebbe dentro. Una feritoia rivolta in
# basso non riceve acqua per gravita' e scarica quella che entra; una
# verticale la riceve solo di striscio, e la rete la ferma (vedi sotto).
# Tutte si affacciano nel canale perimetrale fra cassa e cornice, che porta
# alla fessura d'ombra.
# L'altezza e' misurata nella direzione della profondita', non sul fronte:
# allargarla non si vede da fuori. Le quote sono quelle che, tolta la rete,
# lasciano 6,75 cm2 di passaggio vero per lato (il controllo e' in verifica()).
FESSURA_ALTEZZA = 15.0
FESSURA_LARGHEZZA = 80.0
FESSURA_LATO_L = 40.0              # lunghezza di ciascuna delle due laterali
# Distanza delle feritoie dal fronte della cassa. Devono cadere dietro la
# battuta, non a cavallo: quattro dei sei magneti stanno a x +-32, dentro la
# larghezza della feritoia bassa, e i loro riscontri appoggiano sulla battuta.
# Con la feritoia davanti, l'anello di appoggio restava tagliato dove il
# magnete deve tirare.
FESSURA_ARRETRAMENTO = TELAIO_S + BATTUTA_PROF + 1.0
# Le laterali finiscono 3 mm sotto il soffitto interno: l'aria calda si ferma
# li', e tutto quello che sta sopra il bordo della feritoia e' aria che non esce.
FESSURA_LATO_Y1 = VETRO_H / 2 + CASSA_INT_H / 2 - 3.0
FESSURA_LATO_Y0 = FESSURA_LATO_Y1 - FESSURA_LATO_L
# Gocciolatoio sopra ogni feritoia laterale: un dente sul fianco esterno, con
# la faccia superiore inclinata verso fuori. L'acqua che scende lungo il fianco
# ci arriva sopra e si stacca a 2,5 mm dalla parete, invece di passare
# davanti alla feritoia.
GOCCIOLATOIO = 2.5
# La flangia chiude il canale perimetrale dietro le feritoie. Davanti a esse
# chiudeva il passaggio: era a 10 mm dal fronte, con la feritoia fra 8 e 16, e
# verso fuori ne restavano due millimetri. I 5 mm dietro la feritoia servono ai
# canali laterali, che portano alla feritoia bassa l'aria entrata dai fianchi
# della fessura: con meno, la bocca d'ingresso diventa piu' stretta della
# feritoia.
FLANGIA_ARRETRAMENTO = FESSURA_ARRETRAMENTO + FESSURA_ALTEZZA + 5.0
# Rete inox contro gli insetti. Il filo conta quanto la maglia: con 0,6 di luce
# e filo da 0,2 l'area libera e' il 56%, con filo da 0,25 scende al 50%.
RETE_MAGLIA = 0.6
RETE_FILO = 0.2
RETE_AREA_LIBERA = (RETE_MAGLIA / (RETE_MAGLIA + RETE_FILO)) ** 2
# La rete va incollata dentro, sopra la feritoia, e per incollarla serve bordo
# su cui mettere l'adesivo: non basta il margine in lunghezza, perche' sono i
# due lati lunghi a tenerla.
RETE_SOVRAPPOSIZIONE = 5.0
RETE_L = FESSURA_LARGHEZZA + RETE_SOVRAPPOSIZIONE
RETE_H = FESSURA_ALTEZZA + RETE_SOVRAPPOSIZIONE
RETE_LATO_L = FESSURA_LATO_L + RETE_SOVRAPPOSIZIONE
# Smussi interni agli angoli bassi, fra la feritoia e i fianchi: l'acqua che
# dovesse scendere lungo l'interno dei fianchi arriva sul fondo fuori dalla
# feritoia, e senza smusso ristagnerebbe in quei 5,5 mm.
SMUSSO_SCARICO = (CASSA_INT_L - FESSURA_LARGHEZZA) / 2

# Il telaio non ha feritoie proprie: non servirebbero a niente. Davanti al
# telaio c'e' il vetro incollato, quindi quel volume e' chiuso; l'aria circola
# tutta nel vano dietro il telaio, dove le tre feritoie della cassa si
# affacciano direttamente.

# Nessun setto acustico: chiuderebbe l'uscita dell'aria calda. Il microfono non
# sente la ventola perche' la sua basetta e' staccata dall'HAT e sigillata
# dietro al foro del vetro con una membrana PTFE, quindi e' accoppiata all'aria
# esterna e non al vano. Suono e aria calda escono dalla stessa feritoia.

# --------------------------------------------------------------------------
# Guarnizioni e incollaggi
# --------------------------------------------------------------------------
# Il display si incolla al vetro con un adesivo ottico steso in pieno, non con
# una cornice perimetrale: il pannello e' touch capacitivo, e un'intercapedine
# d'aria anche di due decimi conta, in termini di accoppiamento, come un
# millimetro e mezzo di vetro in piu'. Oltre a questo, un'intercapedine
# aggiunge due interfacce vetro-aria che riflettono e sbiadiscono l'immagine.
BIADESIVO_DISPLAY_S = 0.35         # OCA in foglio, su tutta la superficie
# I 35 centesimi al posto dei 20 di prima sono il margine su questo gradino.
# Non costano niente: la quota del telaio la fissa il VHB da 3,0, e display piu
# adesivo arrivano a 2,15, quindi il pacchetto resta 0,85 mm sotto. In
# cambio il rapporto regge anche se il fornitore stampa sei passate invece di
# tre, che e' il caso in cui un OCA da 20 centesimi non ce la farebbe.

# Lo spessore della serigrafia non e' una rifinitura: l'OCA e' tagliato a
# misura del modulo (70 x 125) mentre la finestra trasparente e' 69,0 x 122,0,
# quindi la laminazione scavalca il bordo dell'inchiostro su tutto il perimetro
# - mezzo millimetro sui fianchi, un millimetro e mezzo sopra e sotto. Su quel
# gradino l'adesivo deve rifluire, e se non ce la fa resta un canale d'aria
# proprio lungo il bordo della finestra, cioe' un anello di bolle nel punto
# dove si vede di piu'. Un nero coprente in serigrafia UV sta sulle due o tre
# passate da 8-15 um, da cui i 30 um assunti qui: il numero va confermato dal
# fornitore nel preventivo, perche' e' lui a scegliere quante passate fare.
SERIGRAFIA_S = 0.030
# Rapporto minimo fra spessore dell'adesivo e gradino da assorbire. Il limite
# fisico di un OCA morbido ad alto flusso sta intorno a un terzo del proprio
# spessore, ma quello vale in autoclave: qui si lamina a mano, con un rullo, e
# cinque e' il margine che serve per non giocarsi un vetro da campione su un
# decimo di pressione in meno.
OCA_RAPPORTO_MIN = 5.0

# Il telaio si incolla al vetro con una schiuma da 3,0 mm. Era stata scelta per
# pareggiare display piu' adesivo, che il progetto assumeva spessi altrettanto;
# col display misurato in 1,8 quella somma fa 2,0 e il nastro e' piu' spesso di
# un millimetro. Resta il nastro da 3,0, e non e' un ripiego: un VHB da 2,0
# esiste, ma la schiuma piu' spessa assorbe meglio le ondulazioni del vetro
# temperato e le dilatazioni differenziali, e il millimetro che ne risulta non
# serve a nessun altro. Il display non appoggia dunque al telaio - e' incollato
# in pieno al vetro con l'adesivo ottico, che su un pannello da 0,4 mm basta e
# avanza - e la sua coda ripiegata resta libera invece di essere schiacciata
# dall'alluminio.
BIADESIVO_S = 3.0                  # 3M VHB 4959, cornice perimetrale

# --------------------------------------------------------------------------
# Viti che si avvitano nel telaio
# --------------------------------------------------------------------------
# Queste viti entrano tutte dal retro e il telaio e' spesso 3 mm, quindi la
# lunghezza non e' una scelta libera: quello che avanza oltre il filetto
# riemerge dal fronte, dove non c'e' il vuoto ma il display incollato al vetro.
# La minuteria dava M2.5 x 16 per il Raspberry: con 9,5 di distanziale e 1,6 di
# scheda l'impegno sarebbe 4,9 su 3 mm di telaio, cioe' 1,9 mm di vite in
# uscita contro 0,85 mm d'aria. Quattro punte che spingono sul retro di un OLED
# da 0,4 mm. La x14 impegna 2,9 su 3, che sono sei filetti, e non esce.
PI_PCB_S = 1.6                     # spessore della scheda del Raspberry
PI_VITE_L = 14.0                   # M2.5
# CAMERA_PCB_S resta quello del product brief, 1,12: riassegnarlo qui a 1,0
# (come era) congelava CAMERA_SPORGENZA al valore vecchio e mentiva al
# modello 3D e al controllo delle viti.
# A 12 la vite della camera impegnava 5 mm su 3 di telaio e riemergeva per 2
# nell'intercapedine, fermandosi a un millimetro dal vetro. A 10 impegna
# 2,88 mm di filetto e si ferma dentro.
CAMERA_VITE_L = 10.0               # M2
SPEAKER_VITE_L = 18.0              # M3, nelle colonnine di nylon
NFC_VITE_L = 6.0                   # M3, lettore appoggiato al telaio
# La vite attraversa il circuito stampato del lettore, non il suo ingombro:
# NFC_PCB_S e' 5 mm perche' comprende i componenti, ma sotto la testa della
# vite ci sono solo i 1,6 della basetta.
NFC_PCB_SOLO_S = 1.6

# Piano della faccia anteriore del telaio, misurato dalla faccia esterna del
# vetro: e' la quota da cui partono tutti i componenti. La distanza dal vetro
# la fissa il piu' spesso fra i due incollaggi, che e' quello del telaio: e'
# lui che tiene su il gruppo.
Z_TELAIO = VETRO_S + max(BIADESIVO_S, BIADESIVO_DISPLAY_S + DISPLAY_MODULO_S)
# Le quote della posa, che dipendono da Z_TELAIO: il fronte della cassa sta
# Z_TELAIO dietro il piano dell'intonaco, e da quel piano si misurano anche la
# flangia e la nicchia.
Z_FLANGIA = Z_TELAIO + FLANGIA_ARRETRAMENTO
FORO_MURO_PROF = Z_TELAIO + CASSA_PROF + 6.0
# Aria che resta fra il retro del display e il fronte del telaio.
DISPLAY_ARIA_TELAIO = (Z_TELAIO - VETRO_S
                       - BIADESIVO_DISPLAY_S - DISPLAY_MODULO_S)

# Distanza fra la punta dell'obiettivo e la faccia interna del vetro, una volta
# montato il modulo sulle sue colonnine. Non e' un parametro da scegliere ma il
# risultato della catena di quote, e va riempita con un anello di schiuma nera
# che fa anche da paraluce: senza, la luce del vano arriva sul sensore come
# velo. Il foro dell'anello sta fuori dal cono visivo.
CAMERA_GIOCO_VETRO = (Z_TELAIO + TELAIO_S + CAMERA_COLONNINE) \
    - CAMERA_ALTEZZA - VETRO_S


def finestra_ottica_minima() -> float:
    """Diametro minimo della finestra trasparente, in millimetri.

    La finestra nella serigrafia sta davanti all'obiettivo e lavora da
    diaframma: il cono visivo parte dalla lente in vista e si allarga fino alla
    faccia esterna del vetro, attraversando il gioco d'aria e lo spessore. Si
    usa il campo diagonale perche' la finestra e' tonda e deve contenere anche
    gli angoli del fotogramma.
    """
    distanza = CAMERA_GIOCO_VETRO + VETRO_S
    semiangolo = math.radians(CAMERA_FOV_DIAGONALE / 2)
    return CAMERA_LENTE_FRONTALE_D + 2 * distanza * math.tan(semiangolo)


def componenti() -> list[tuple[str, float, float, float, float, float, float]]:
    """I volumi occupati dai componenti, in coordinate del vetro.

    Ogni voce e' (nome, x1, y1, z1, x2, y2, z2) con z misurata dalla faccia
    esterna del vetro verso il fondo della cassa. La usano sia verifica(), per
    cercare le compenetrazioni, sia genera_dxf.py per disegnare la mappa dei
    componenti: devono guardare la stessa lista, altrimenti il disegno dice una
    cosa e il controllo un'altra.
    """
    z_retro = Z_TELAIO + TELAIO_S   # faccia posteriore del telaio

    def ingombro(nome, cx, cy, larghezza, altezza, z0=0.0, spessore=0.0):
        """Volume occupato da un componente, in coordinate del vetro.

        La z serve perche' i componenti stanno su piani diversi: la camera e
        l'altoparlante si sovrappongono in pianta e non si toccano, perche' il
        secondo e' montato quattordici millimetri piu' indietro.
        """
        return (nome, cx - larghezza / 2, cy - altezza / 2, z0,
                cx + larghezza / 2, cy + altezza / 2, z0 + spessore)

    componenti = [
        ingombro("lettore NFC", NFC_PCB_X, NFC_Y, NFC_PCB_L, NFC_PCB_H,
                 VETRO_S + NFC_DISTANZA_VETRO, NFC_PCB_S),
        ingombro("display", 0, DISPLAY_MODULO_Y0 + DISPLAY_MODULO_H / 2,
                 DISPLAY_MODULO_L, DISPLAY_MODULO_H,
                 VETRO_S + BIADESIVO_DISPLAY_S, DISPLAY_MODULO_S),
        # Il PCB della camera e' centrato sui propri fori, non sull'asse
        # ottico, ed e' arretrato sulle colonnine: l'obiettivo sporge in avanti
        # dentro il foro del telaio e non fa parte di questo ingombro.
        ingombro("camera", CAMERA_X, CAMERA_PCB_Y0,
                 CAMERA_PCB_L, CAMERA_PCB_H,
                 z_retro + CAMERA_COLONNINE - CAMERA_PCB_S,
                 CAMERA_PCB_S + CAMERA_CONNETTORE_S),
        ingombro("obiettivo", CAMERA_X, OTTICA_Y, CAMERA_BASE_L, CAMERA_BASE_L,
                 z_retro + CAMERA_COLONNINE - CAMERA_PCB_S - CAMERA_BASE_S,
                 CAMERA_BASE_S),
        ingombro("altoparlante", SPEAKER_X, SPEAKER_Y, SPEAKER_L, SPEAKER_H,
                 z_retro + SPEAKER_ARRETRAMENTO, SPEAKER_S),
        ingombro("basetta microfono", MICROFONO_X, MICROFONO_Y,
                 MIC_PCB_L, MIC_PCB_H, VETRO_S, MIC_INGOMBRO_S),
        ingombro("stack del Pi", 0, PI_Y0 + PI_L / 2, PI_H, PI_L,
                 z_retro + PI_DISTANZIALI, PI_STACK_H),
        ingombro("scheda di ingresso", DRIVER_X, DRIVER_Y, DRIVER_S, DRIVER_L,
                 z_retro + 2, DRIVER_H),
        ingombro("schedina terminale", TERMINALE_X, TERMINALE_Y, TERMINALE_S,
                 TERMINALE_H, z_retro + 2, TERMINALE_L),
        # Le due ali della squadretta, separate: come volume unico sarebbe un
        # parallelepipedo pieno che collide con la scheda che deve tenere.
        ingombro("staffa, ala verticale", STAFFA_X, DRIVER_Y, STAFFA_S,
                 STAFFA_L, STAFFA_Z0, STAFFA_ALA_H),
        ingombro("staffa, ala a telaio",
                 STAFFA_X + STAFFA_S / 2 + STAFFA_ALA_BASE / 2, DRIVER_Y,
                 STAFFA_ALA_BASE, STAFFA_L, STAFFA_Z0, STAFFA_S),
        # La base dell'SSD occupa lo spazio fra telaio e Pi. Non e' un volume
        # trascurabile: e' il disco di avvio, e sta nell'unico punto del vano
        # che il progetto considerava libero.
        # Lo spessore dichiarato e' quello dei distanziali e non i 9,5 della
        # base: quei 10 mm li tiene il Pi comunque, nessun altro componente
        # puo' usarli, e riservarli tutti e' piu' severo che riservare il pezzo.
        ingombro("base NVMe", 0, PI_Y0 + PI_L / 2, NVME_BASE_L, NVME_BASE_H,
                 z_retro, PI_DISTANZIALI),
    ]

    # Quello che esce dal bordo del Pi verso il basso: l'ansa del flat PCIe,
    # che gira attorno al gruppo per tornare alla base, e il connettore di
    # rete col suo patch. Il primo sta basso, fra telaio e scheda; il secondo
    # sta sul PCB e passa quindi sopra il lettore NFC, non dentro.
    componenti.append(
        ingombro("ansa del flat PCIe", 0, PI_Y0 - PCIE_ANSA / 2,
                 NVME_BASE_L, PCIE_ANSA, z_retro, PI_DISTANZIALI))
    componenti.append(
        ingombro("patch di rete", -18.0, PI_Y0 - RJ45_SPORGENZA / 2,
                 20.0, RJ45_SPORGENZA, z_retro + PI_DISTANZIALI, 14.0))
    return componenti


def fondo_interno() -> float:
    """Quota del fondo interno della cassa, misurata dalla faccia del vetro."""
    return Z_TELAIO + CASSA_PROF - CASSA_PARETE


def canale_aria() -> float:
    """Millimetri liberi fra il componente piu' profondo e il fondo cassa."""
    return fondo_interno() - max(c[6] for c in componenti())


def gruppo_massimo() -> float:
    """Altezza del gruppo del Pi oltre la quale il canale d'aria dietro i
    componenti diventa piu' stretto della feritoia lorda.

    Vale finche' il gruppo del Pi e' il componente piu' profondo, e verifica()
    controlla che lo sia.
    """
    canale_min = (max(sezioni_aria()[k] for k in ("ingresso", "uscita"))
                  * 100 / CASSA_INT_L)
    return PI_GRUPPO_H + canale_aria() - canale_min


def sezioni_aria() -> dict[str, float]:
    """Le sezioni in serie sul percorso dell'aria, in cm2.

    Per ciascun verso: la feritoia lorda, la stessa tolta la rete, e la bocca
    nella fessura d'ombra. La bocca d'ingresso e' la fessura bassa piu' la
    meta' bassa dei fianchi, che pero' arriva alla feritoia solo lungo i
    canali laterali e ne e' limitata; quella d'uscita e' la meta' alta dei
    fianchi, davanti alle feritoie laterali, piu' la fessura alta, che si
    raggiunge salendo oltre i gocciolatoi.
    """
    ombra = OMBRA_PERIMETRALE
    canale_lato = CANALE_PERIMETRALE * (Z_FLANGIA - VETRO_S)
    oltre_gocciolatoio = ((CANALE_PERIMETRALE - GOCCIOLATOIO)
                          * (Z_FLANGIA - Z_TELAIO)
                          + CANALE_PERIMETRALE * (Z_TELAIO - VETRO_S))
    ingresso = FESSURA_LARGHEZZA * FESSURA_ALTEZZA
    uscita = 2 * FESSURA_LATO_L * FESSURA_ALTEZZA
    sezioni = {
        "ingresso": ingresso,
        "ingresso_libera": ingresso * RETE_AREA_LIBERA,
        "uscita": uscita,
        "uscita_libera": uscita * RETE_AREA_LIBERA,
        "bocca_ingresso": ombra * LUCE_INTONACO_L
        + 2 * min(ombra * LUCE_INTONACO_H / 2, canale_lato),
        "bocca_uscita": 2 * min(ombra * LUCE_INTONACO_H / 2, 2 * canale_lato)
        + min(ombra * LUCE_INTONACO_L, 2 * oltre_gocciolatoio),
    }
    return {k: v / 100 for k, v in sezioni.items()}


# Coefficiente d'efflusso di un'apertura a spigolo vivo.
TIRAGGIO_CD = 0.6


def tiraggio(delta_t: float, t_esterna: float = 35.0) -> float:
    """Watt portati fuori dal solo tiraggio naturale.

    Effetto camino fra la feritoia bassa e il centro delle laterali, con
    l'aria interna delta_t gradi sopra quella esterna. Le sezioni in serie si
    compongono come resistenze idrauliche, 1/A^2. Non conta la ventola, che
    rimescola l'aria dentro la cassa ma non la cambia.
    """
    def serie(*aree):
        return sum(a ** -2 for a in aree) ** -0.5

    s = sezioni_aria()
    area = serie(serie(s["ingresso_libera"], s["bocca_ingresso"]),
                 serie(s["uscita_libera"], s["bocca_uscita"])) / 1e4
    salto = ((FESSURA_LATO_Y0 + FESSURA_LATO_Y1) / 2
             - (VETRO_H - CASSA_H) / 2) / 1000
    velocita = math.sqrt(2 * 9.81 * salto * delta_t / (t_esterna + 273.15))
    return 1.15 * 1005 * TIRAGGIO_CD * area * velocita * delta_t


# Bilancio termico. Le feritoie da sole non bastano: a 20 gradi di salto il
# tiraggio porta fuori meno di tre watt, e il resto deve passare per il vetro
# e per il muro. Questi coefficienti sono stime da manuale, non misure, e
# vanno trattati come tali: il numero che ne esce serve a sapere che cosa
# aspettarsi dalla prova in cassa chiusa, non a sostituirla.
POTENZA_RIPOSO = 5.0      # W in cassa: Pi a riposo, SSD, perdita PoE, display spento
POTENZA_PICCO = 11.5      # W in cassa: in chiamata, display acceso e Pi carico
H_ARIA_INTERNA = 5.0      # W/m2K, convezione naturale sulle pareti interne
H_VETRO_ESTERNO = 9.0     # W/m2K, convezione e irraggiamento, vetro all'ombra
K_TUFO = 0.3              # W/mK, tufo asciutto: 0,2-0,5 secondo la cava
TUFO_DIETRO = 0.11        # m, quanto muro resta dietro la cassa fino all'interno
K_VHB = 0.1               # W/mK, schiuma acrilica
VHB_LARGHEZZA = 12.0      # mm, il nastro della cornice


def conduttanze_pareti() -> dict[str, float]:
    """W/K fra l'aria interna e l'esterno, attraverso vetro e muro.

    Vetro: aria interna -> telaio -> VHB e intercapedine -> vetro -> fuori,
    tutto in serie. Muro: aria interna -> pareti della cassa -> tufo, con la
    parete di casa a fare da pozzo; e' la stima piu' incerta delle due.
    """
    a_telaio = TELAIO_L * TELAIO_H / 1e6
    a_vhb = VHB_LARGHEZZA * 2 * (TELAIO_L + TELAIO_H) / 1e6
    a_vetro = VETRO_L * VETRO_H / 1e6
    r_vetro = (1 / (H_ARIA_INTERNA * a_telaio)
               + 1 / (K_VHB * a_vhb / (BIADESIVO_S / 1000)
                      + 0.026 * (a_telaio - a_vhb) / (BIADESIVO_S / 1000))
               + 1 / (H_VETRO_ESTERNO * a_vetro))
    prof = (fondo_interno() - Z_TELAIO - TELAIO_S) / 1000
    a_cassa = (CASSA_INT_L * CASSA_INT_H / 1e6
               + 2 * (CASSA_INT_L + CASSA_INT_H) / 1000 * prof)
    r_muro = 1 / (H_ARIA_INTERNA * a_cassa) + TUFO_DIETRO / (K_TUFO * a_cassa)
    return {"vetro": 1 / r_vetro, "muro": 1 / r_muro}


def salto_termico(potenza: float, t_esterna: float = 35.0) -> float:
    """Gradi dell'aria interna sopra l'esterno, a regime, con potenza watt."""
    g = sum(conduttanze_pareti().values())
    basso, alto = 0.0, 200.0
    for _ in range(60):
        dt = (basso + alto) / 2
        if tiraggio(dt, t_esterna) + g * dt < potenza:
            basso = dt
        else:
            alto = dt
    return (basso + alto) / 2


def costanti_duplicate() -> list[str]:
    """Una costante maiuscola assegnata due volte: la seconda vince, le
    derivate calcolate in mezzo restano col valore vecchio."""
    import ast
    import pathlib

    albero = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    viste: dict[str, int] = {}
    problemi = []
    for nodo in albero.body:
        if not isinstance(nodo, ast.Assign):
            continue
        for t in nodo.targets:
            if isinstance(t, ast.Name) and t.id.isupper() and t.id in viste:
                problemi.append(
                    f"{t.id} e' assegnata due volte (righe {viste[t.id]}"
                    f" e {nodo.lineno})")
            if isinstance(t, ast.Name) and t.id.isupper():
                viste[t.id] = nodo.lineno
    return problemi


def verifica() -> list[str]:
    """Controlla che le zone non si sovrappongano e che tutto entri nella cassa.

    Serve dopo ogni modifica alle quote: una collisione fra altoparlante e
    camera o un componente piu' largo del vano interno si vedono qui, prima di
    mandare i file in produzione.
    """
    problemi: list[str] = []
    problemi += costanti_duplicate()
    if abs(CAMERA_SPORGENZA - (CAMERA_COLONNINE + CAMERA_PCB_S
                               + CAMERA_CONNETTORE_S)) > 0.01:
        problemi.append(
            f"CAMERA_SPORGENZA e' {CAMERA_SPORGENZA} ma colonnine + PCB +"
            f" connettore fanno {CAMERA_COLONNINE + CAMERA_PCB_S + CAMERA_CONNETTORE_S}:"
            " una delle quote e' stata riassegnata dopo il calcolo")

    componenti_lista = componenti()

    for i, (n1, x1, y1, z1, x2, y2, z2) in enumerate(componenti_lista):
        for n2, a1, b1, c1, a2, b2, c2 in componenti_lista[i + 1:]:
            dx = min(x2, a2) - max(x1, a1)
            dy = min(y2, b2) - max(y1, b1)
            dz = min(z2, c2) - max(z1, c1)
            if dx > 0 and dy > 0 and dz > 0:
                problemi.append(
                    f"{n1} e {n2} si compenetrano di "
                    f"{dx:.1f} x {dy:.1f} x {dz:.1f} mm")
        # Nessun componente deve sfondare il vano o arrivare al fondo cassa.
        if z2 > Z_TELAIO + CASSA_PROF - CASSA_PARETE - 3:
            problemi.append(
                f"{n1} arriva a {z2:.1f} mm dal vetro: tocca il fondo"
                f" della cassa")
        # Nessun componente deve arrivare a filo del bordo del vetro.
        if y1 < 4 or y2 > VETRO_H - 4 or x1 < -VETRO_L / 2 + 4 \
                or x2 > VETRO_L / 2 - 4:
            problemi.append(
                f"{n1} e' a meno di 4 mm dal bordo del vetro "
                f"(x {x1:.1f}..{x2:.1f}, y {y1:.1f}..{y2:.1f})")

    # L'interasse dei fori del Raspberry e' un dato del costruttore, 58 x 49, e
    # il disegno lo ricava dal margine invece di leggerlo: finche' i due modi
    # danno lo stesso numero va bene, ma se qualcuno tocca il margine il
    # disegno si sposta e questo parametro resta indietro senza dirlo.
    if abs((PI_H - 2 * PI_MARGINE_FORI) - PI_FORI_Y) > 0.01:
        problemi.append(
            f"l'interasse dei fori del Pi e' {PI_FORI_Y} ma dal margine"
            f" {PI_MARGINE_FORI} su una scheda da {PI_H} ne risultano"
            f" {PI_H - 2 * PI_MARGINE_FORI}")

    # Sotto il Pi i distanziali devono contenere la base dell'SSD.
    if NVME_BASE_S > PI_DISTANZIALI:
        problemi.append(
            f"la base dell'SSD e' alta {NVME_BASE_S} e i distanziali sono"
            f" {PI_DISTANZIALI}: il Pi ci appoggia sopra invece che sui"
            " distanziali")

    # Quanto esce dal fronte del telaio ogni vite avvitata da dietro, e cosa
    # trova quando esce. Sotto il display c'e' meno di un millimetro d'aria;
    # altrove c'e' l'intercapedine del biadesivo, e in fondo il vetro.
    for nome, lung, sotto, passo, davanti in (
            ("Raspberry", PI_VITE_L, PI_DISTANZIALI + PI_PCB_S, 0.45,
             DISPLAY_ARIA_TELAIO),
            ("camera", CAMERA_VITE_L, CAMERA_COLONNINE + CAMERA_PCB_S, 0.4,
             Z_TELAIO - VETRO_S),
            ("altoparlante", SPEAKER_VITE_L, SPEAKER_ARRETRAMENTO, 0.5,
             Z_TELAIO - VETRO_S),
            ("lettore NFC", NFC_VITE_L, NFC_PCB_SOLO_S, 0.5,
             Z_TELAIO - VETRO_S)):
        impegno = lung - sotto
        sporgenza = impegno - TELAIO_S
        if sporgenza > davanti - 0.3:
            problemi.append(
                f"la vite del {nome} e' lunga {lung:.0f} e sporge"
                f" {sporgenza:.1f} mm dal fronte del telaio, dove ce ne stanno"
                f" {davanti:.2f}: accorciala a"
                f" {sotto + TELAIO_S:.0f}")
        elif min(impegno, TELAIO_S) / passo < 3.0:
            problemi.append(
                f"la vite del {nome} impegna {impegno:.1f} mm di filetto,"
                f" meno di tre passi: non tiene")

    # Ogni foro che il disegno manda in filettatura deve avere la misura del
    # preforo, non quella di passaggio. E' una distinzione che costa un decimo
    # sul disegno e l'intero fissaggio in officina: un M2.5 vuole 2,05, e in un
    # foro da 2,7 non c'e' niente da filettare.
    PREFORI = {"M2": 1.6, "M2.5": 2.05, "M3": 2.5}
    for nome, diametro, vite in (
            ("Raspberry", PI_FORO_D, "M2.5"),
            ("camera", CAMERA_FORO_D, "M2"),
            ("altoparlante", SPEAKER_FORO_D, "M3"),
            ("lettore NFC", NFC_FORO_D, "M3"),
            ("squadretta nel telaio", STAFFA_FORO_TELAIO_D, "M2.5")):
        atteso = PREFORI[vite]
        if abs(diametro - atteso) > 0.06:
            problemi.append(
                f"il foro {nome} e' O{diametro:.2f} ma va filettato {vite},"
                f" che vuole un preforo O{atteso:.2f}"
                + (": cosi' la vite non ha presa"
                   if diametro > atteso else ": cosi' non entra il maschio"))

    # I perni di aggancio non devono cadere su un'apertura.
    perno_y = (VETRO_H + TELAIO_H) / 2 - PERNO_MARGINE / 2
    if (abs(PERNO_PASSO / 2) + PERNO_FORO_D / 2 > TELAIO_L / 2 - 3
            or perno_y > (VETRO_H + TELAIO_H) / 2 - 3):
        problemi.append("i perni di aggancio sono troppo vicini al bordo")
    # Oltre il fronte del telaio il perno entra nell'intercapedine del
    # biadesivo, e in fondo a quella c'e' il vetro. Non e' un'interferenza da
    # millimetri: il gruppo si accosta a mano premendo, e una punta d'acciaio
    # appoggiata al Gorilla e' un carico concentrato su un vetro da 2 mm.
    punta_perno = Z_TELAIO + TELAIO_S - PERNO_SPORGENZA
    if punta_perno < VETRO_S + 0.5:
        problemi.append(
            f"il perno di centraggio arriva a z {punta_perno:.1f} e il retro"
            f" del vetro sta a {VETRO_S:.1f}:"
            + (" ci batte contro" if punta_perno <= VETRO_S
               else f" restano {punta_perno - VETRO_S:.1f} mm")
            + f". La sporgenza non puo' superare"
            f" {Z_TELAIO + TELAIO_S - VETRO_S - 0.5:.1f}")
    # Il perno sporge dietro il telaio: se l'altoparlante fosse montato a
    # contatto, gli finirebbe addosso.
    if PERNO_SPORGENZA - TELAIO_S > SPEAKER_ARRETRAMENTO \
            and abs(PERNO_PASSO / 2) - PERNO_FORO_D / 2 < SPEAKER_L / 2 \
            and perno_y > SPEAKER_Y - SPEAKER_H / 2:
        problemi.append("un perno di aggancio batte sull'altoparlante")
    # Ogni magnete deve cadere nella striscia dove telaio e battuta si
    # sovrappongono, altrimenti non ha niente da attirare.
    for mx, my in posizioni_magneti():
        r = MAGNETE_SEDE_D / 2
        su_fianco = abs(mx) + r > TELAIO_L / 2 - BATTUTA
        su_bordo = (my - r < TELAIO_Y0 + BATTUTA
                    or my + r > TELAIO_Y0 + TELAIO_H - BATTUTA)
        if not (su_fianco or su_bordo):
            problemi.append(
                f"il magnete in ({mx}, {my}) non appoggia sulla battuta")
        if abs(mx) + r > TELAIO_L / 2 or my - r < TELAIO_Y0 \
                or my + r > TELAIO_Y0 + TELAIO_H:
            problemi.append(
                f"il magnete in ({mx}, {my}) esce dal profilo del telaio")

    # L'altoparlante deve restare dietro la griglia serigrafata, altrimenti il
    # suono non ha una via d'uscita.
    if abs(SPEAKER_X) + SPEAKER_L / 2 > GRIGLIA_L / 2:
        problemi.append(
            "l'altoparlante sporge oltre la griglia serigrafata")

    # Catena di quote dell'ottica. L'obiettivo sporge 11,3 mm dal retro del suo
    # PCB, molto piu' dei millimetri che ci sono fra telaio e vetro: se la
    # scheda appoggiasse al telaio la lente sfonderebbe il pannello. Da qui le
    # colonnine, la cui altezza va controllata in entrambi i versi.
    if CAMERA_GIOCO_VETRO < 0.3:
        problemi.append(
            f"l'obiettivo arriva a {CAMERA_GIOCO_VETRO:.1f} mm dal vetro:"
            f" con colonnine da {CAMERA_COLONNINE:.1f} mm "
            + ("ci batte contro" if CAMERA_GIOCO_VETRO < 0
               else "non c'e' spazio per l'anello paraluce"))
    elif CAMERA_GIOCO_VETRO > 1.5:
        problemi.append(
            f"l'obiettivo resta a {CAMERA_GIOCO_VETRO:.1f} mm dal vetro:"
            " troppo lontano, la finestra dovrebbe allargarsi")
    # La finestra trasparente lavora da diaframma: se e' piu' piccola del cono
    # visivo, gli angoli del fotogramma restano neri.
    minima = finestra_ottica_minima()
    if OTTICA_D < minima:
        problemi.append(
            f"la finestra dell'ottica e' {OTTICA_D:.1f} mm ma per "
            f"{CAMERA_FOV_DIAGONALE:.0f} gradi di campo a "
            f"{CAMERA_GIOCO_VETRO + VETRO_S:.1f} mm dalla lente ne servono "
            f"{minima:.1f}: vignetta gli angoli")
    # L'anello paraluce sta attorno al barilotto e non deve entrare nel campo.
    cono_r = CAMERA_LENTE_FRONTALE_D / 2 + CAMERA_GIOCO_VETRO \
        * math.tan(math.radians(CAMERA_FOV_DIAGONALE / 2))
    if cono_r > CAMERA_LENTE_D / 2:
        problemi.append(
            f"a {CAMERA_GIOCO_VETRO:.1f} mm dalla lente il cono visivo misura"
            f" {2 * cono_r:.1f} mm, piu' del barilotto: l'anello paraluce"
            " entrerebbe nell'inquadratura")

    # Aperture ricavate nel telaio: devono stare dentro la piastra con almeno
    # 3 mm di materiale intorno e lasciare fra loro un ponte di almeno 2 mm.
    # Due aperture che si intersecano sono il modo piu' facile di mandare al
    # laser un file ambiguo e ritrovarsi un anellino tagliato in piu'.
    telaio_y0 = (VETRO_H - TELAIO_H) / 2
    PONTE_MIN = 2.0
    aperture = [
        ("apertura NFC", NFC_X, NFC_Y, NFC_APERTURA_L, NFC_APERTURA_H),
        ("luce altoparlante", SPEAKER_X, SPEAKER_LUCE_Y,
         SPEAKER_LUCE_L, SPEAKER_LUCE_H),
        ("passaggio lente", CAMERA_X, OTTICA_Y,
         CAMERA_LENTE_D + GIOCO_LENTE_TELAIO,
         CAMERA_LENTE_D + GIOCO_LENTE_TELAIO),
        ("asola del microfono", MICROFONO_X, MIC_ASOLA_Y,
         MIC_ASOLA_L, MIC_ASOLA_H),
        ("asola del flat", FLAT_ASOLA_X, FLAT_ASOLA_Y,
         FLAT_ASOLA_L, FLAT_ASOLA_H),
    ]
    for nome, cx, cy, larghezza, altezza in aperture:
        x1, x2 = cx - larghezza / 2, cx + larghezza / 2
        y1, y2 = cy - altezza / 2, cy + altezza / 2
        if (y1 < telaio_y0 + 3 or y2 > telaio_y0 + TELAIO_H - 3
                or abs(x1) > TELAIO_L / 2 - 3 or abs(x2) > TELAIO_L / 2 - 3):
            problemi.append(
                f"{nome} troppo vicina al bordo del telaio "
                f"(x {x1:.1f}..{x2:.1f}, y {y1:.1f}..{y2:.1f}, "
                f"telaio y {telaio_y0:.1f}..{telaio_y0 + TELAIO_H:.1f})")
    # La sede del riscontro va scavata nella faccia di battuta, dove appoggia il
    # telaio, e dietro deve restare materiale: se la sede sfonda, il dischetto
    # cade nel vano. Vale solo per la cassa stampata, che e' la variante dove i
    # riscontri esistono.
    if RISCONTRO_SEDE_PROF > BATTUTA_PROF - 1.0:
        problemi.append(
            f"la sede del riscontro e' profonda {RISCONTRO_SEDE_PROF} su una"
            f" battuta di {BATTUTA_PROF}: dietro resta meno di 1 mm")

    # Ogni sede deve stare tutta sull'anello di battuta: se sborda verso il
    # vano, il dischetto resta a sbalzo sul vuoto; se sborda verso la bocca,
    # intacca la faccia su cui appoggia il telaio.
    x0, x1 = -CASSA_INT_L / 2, CASSA_INT_L / 2
    y0 = VETRO_H / 2 - CASSA_INT_H / 2
    y1 = VETRO_H / 2 + CASSA_INT_H / 2
    raggio = RISCONTRO_SEDE_D / 2
    for (sx, sy), (mx, my) in zip(posizioni_riscontri(), posizioni_magneti()):
        if min(sx - x0, x1 - sx) < min(sy - y0, y1 - sy):
            dal_bordo = min(sx - x0, x1 - sx)
        else:
            dal_bordo = min(sy - y0, y1 - sy)
        sbordo = max(raggio - dal_bordo, raggio - (BATTUTA - dal_bordo))
        if sbordo > RISCONTRO_SBORDO_MAX + 0.01:
            problemi.append(
                f"la sede del riscontro in ({sx:.1f}, {sy:.1f}) sborda"
                f" {sbordo:.1f} mm dall'anello di battuta da {BATTUTA}, il"
                f" massimo ammesso e' {RISCONTRO_SBORDO_MAX}")

        # E il dischetto deve coprire tutto il magnete, perche' e' ferro
        # davanti al magnete quello che serve: coprirlo a meta' dimezza la
        # forza, ed e' la forza che tiene su mezzo chilo di pannello.
        # La copertura risulta esattamente tangente, e non e' una scelta: con il
        # magnete dov'e' e l'anello larga 6 non si fa di meglio. Regge perche' a
        # guidare il dischetto c'e' la sede, quindi di sbagliato ha al massimo i
        # due decimi di gioco e non quelli di una posa a occhio.
        scarto = math.dist((sx, sy), (mx, my))
        if scarto + MAGNETE_D / 2 > RISCONTRO_D / 2 + 0.01:
            problemi.append(
                f"il riscontro O{RISCONTRO_D} in ({sx:.1f}, {sy:.1f}) non"
                f" copre tutto il magnete O{MAGNETE_D} in ({mx:.1f},"
                f" {my:.1f}): sono decentrati di {scarto:.1f} mm")

    # La sede e' un volume che sta nel vano, quindi va confrontata con i
    # componenti come qualsiasi altro pezzo. Il cilindro e' approssimato col
    # quadrato circoscritto, che e' piu' severo del vero.
    sede_z0 = Z_TELAIO + TELAIO_S
    sede_z1 = sede_z0 + RISCONTRO_SEDE_PROF
    for sx, sy in posizioni_riscontri():
        for nome, cx0, cy0, cz0, cx1, cy1, cz1 in componenti():
            sovr = (min(sx + raggio, cx1) - max(sx - raggio, cx0),
                    min(sy + raggio, cy1) - max(sy - raggio, cy0),
                    min(sede_z1, cz1) - max(sede_z0, cz0))
            if all(s > 0 for s in sovr):
                problemi.append(
                    f"la sede del riscontro in ({sx:.1f}, {sy:.1f}) entra in"
                    f" {nome} per {sovr[0]:.1f} x {sovr[1]:.1f} x"
                    f" {sovr[2]:.1f} mm")

    # Le finestre del vetro sono vetro nudo: attraverso ognuna si vede quello
    # che c'e' dietro. Dove dietro passa il display non e' un problema, perche'
    # lo copre lui; ma la griglia dell'altoparlante e la finestra dell'ottica
    # danno direttamente sul telaio, e la serigrafia nera esiste proprio per
    # nascondere sedi, fori e teste di vite. Questo controllo guarda la cosa da
    # un lato che gli altri non guardano: non l'interferenza fra i volumi, ma
    # cosa resta in vista.
    nascosti = ([(f"magnete in ({mx:.0f}, {my:.0f})", mx, my, MAGNETE_SEDE_D)
                 for mx, my in posizioni_magneti()]
                + [(f"foro perno in ({sx * PERNO_PASSO / 2:.0f}, {perno_y:.0f})",
                    sx * PERNO_PASSO / 2, perno_y, PERNO_FORO_D)
                   for sx in (-1, 1)])
    finestre = [(f"striscia {i + 1} della griglia", 0.0,
                 GRIGLIA_Y + i * GRIGLIA_PASSO + GRIGLIA_SPESSORE / 2,
                 GRIGLIA_L, GRIGLIA_SPESSORE) for i in range(GRIGLIA_N)]
    finestre.append(("finestra dell'ottica", CAMERA_X, OTTICA_Y,
                     OTTICA_D, OTTICA_D))
    # L'icona NFC non e' una finestra piena ma inchiostro al 15-20%: non ci si
    # vede attraverso come nel vetro nudo, pero' un foro dietro si intravede.
    finestre.append(("icona NFC", NFC_X, NFC_Y, NFC_D, NFC_D))
    for nome_f, fx, fy, fl, fh in finestre:
        for nome_o, ox, oy, od in nascosti:
            sovr_x = min(fx + fl / 2, ox + od / 2) - max(fx - fl / 2, ox - od / 2)
            sovr_y = min(fy + fh / 2, oy + od / 2) - max(fy - fh / 2, oy - od / 2)
            if sovr_x > 0 and sovr_y > 0:
                problemi.append(
                    f"la {nome_f} lascia vedere il {nome_o}:"
                    f" si sovrappongono per {sovr_x * sovr_y:.1f} mm2")

    # Ogni foro filettato del telaio deve cadere su materiale pieno: lontano
    # dalle aperture, dai magneti, dai perni e dal bordo. E' il controllo che
    # mancava quando i quattro fori del Raspberry finivano dentro la finestra
    # del display, cioe' nel vuoto.
    ostacoli = [(mx, my, MAGNETE_SEDE_D / 2) for mx, my in posizioni_magneti()] \
        + [(sx * PERNO_PASSO / 2, perno_y, PERNO_FORO_D / 2)
           for sx in (-1, 1)]
    pi_off_x = (PI_H - 2 * PI_MARGINE_FORI) / 2
    filettature = [
        (f"foro del Raspberry", sx * pi_off_x,
         PI_Y0 + PI_MARGINE_FORI + sy * PI_FORI_X, PI_FORO_D)
        for sx in (-1, 1) for sy in (0, 1)
    ] + [
        (f"foro della camera", fx, fy, CAMERA_FORO_D)
        for fx, fy in posizioni_fori_camera()
    ] + [
        (f"foro dell'altoparlante", fx, fy, SPEAKER_FORO_D)
        for fx, fy in posizioni_fori_speaker()
    ] + [
        (f"foro del lettore NFC", fx, fy, NFC_FORO_D)
        for fx, fy in posizioni_fori_nfc()
    ]
    for nome, fx, fy, d in filettature:
        if abs(fx) + d > TELAIO_L / 2 - 3 or fy - d < telaio_y0 + 3 \
                or fy + d > telaio_y0 + TELAIO_H - 3:
            problemi.append(
                f"il {nome} in ({fx:.1f}, {fy:.1f}) e' troppo vicino al bordo"
                " del telaio")
        for ox, oy, r in ostacoli:
            dist = ((fx - ox) ** 2 + (fy - oy) ** 2) ** 0.5 - r - d
            if dist < PONTE_MIN:
                problemi.append(
                    f"il {nome} in ({fx:.1f}, {fy:.1f}) lascia {dist:.1f} mm"
                    f" di alluminio verso ({ox:.0f}, {oy:.0f})")
        for apertura, cx, cy, larghezza, altezza in aperture:
            dx = abs(fx - cx) - larghezza / 2 - d
            dy = abs(fy - cy) - altezza / 2 - d
            if dx < PONTE_MIN and dy < PONTE_MIN:
                problemi.append(
                    f"il {nome} in ({fx:.1f}, {fy:.1f}) cade su {apertura}")

    for i, (n1, cx1, cy1, l1, h1) in enumerate(aperture):
        for n2, cx2, cy2, l2, h2 in aperture[i + 1:]:
            # Distanza fra i due rettangoli: negativa se si intersecano.
            dx = abs(cx1 - cx2) - (l1 + l2) / 2
            dy = abs(cy1 - cy2) - (h1 + h2) / 2
            if dx < PONTE_MIN and dy < PONTE_MIN:
                problemi.append(
                    f"fra {n1} e {n2} restano {max(dx, dy):.1f} mm di"
                    f" alluminio: ne servono almeno {PONTE_MIN:.0f}")

    # Larghezze: nessun componente piu' largo del vano interno.
    for nome, larghezza in (("display", DISPLAY_MODULO_L),
                            ("Raspberry", PI_H),
                            ("lettore NFC", NFC_PCB_L)):
        if larghezza > CASSA_INT_L - 4:
            problemi.append(
                f"{nome} largo {larghezza} mm: non entra nel vano da"
                f" {CASSA_INT_L} mm con 2 mm di gioco per lato")

    # I micro-HDMI stanno sul bordo lungo del Pi, cioe' su un fianco, e ai
    # fianchi restano 17,5 mm: un cavo diritto sfonda la parete della cassa.
    # E' il solo vincolo che le misure dei connettori hanno fatto emergere, e
    # non si risolve con la geometria, perche' la larghezza la detta il vetro.
    fianco = CASSA_INT_L / 2 - PI_H / 2
    if HDMI_ANGOLATO_SPORGENZA > fianco:
        problemi.append(
            f"il micro-HDMI sporge {HDMI_ANGOLATO_SPORGENZA:.0f} mm dal fianco"
            f" del Pi, dove ce ne sono {fianco:.1f}")
    # Il fianco dei micro-HDMI deve restare libero: se la scheda sta da
    # quel lato, fra il bordo del Pi e la scheda ci sono 3 mm e il cavo, pure
    # angolato, non entra. Per questo la scheda sta sull'altro fianco,
    # quello del lato GPIO, dove non esce niente in orizzontale.
    if HDMI_LATO_X * DRIVER_X > 0:
        problemi.append(
            f"la scheda di ingresso e il micro-HDMI sono sullo stesso fianco:"
            f" fra il bordo del Pi e la scheda restano"
            f" {abs(DRIVER_X) - DRIVER_S / 2 - PI_H / 2:.1f} mm")
    # L'RJ45 e l'ansa del flat PCIe escono dal bordo corto, verso il basso, e
    # finiscono nella fascia fra il lettore NFC e il Pi.
    luce_sotto = PI_Y0 - (NFC_Y + NFC_PCB_H / 2)
    if max(RJ45_SPORGENZA, PCIE_ANSA) > luce_sotto + NFC_PCB_H:
        problemi.append(
            f"sotto il Pi ci sono {luce_sotto:.1f} mm prima del lettore NFC e"
            f" il patch ne vuole {RJ45_SPORGENZA:.0f}: esce dal telaio")

    # La scheda di ingresso sta in piedi di fianco allo stack: va verificato
    # che non lo tocchi e che non sfondi la parete della cassa.
    if abs(DRIVER_X) - DRIVER_S / 2 < PI_H / 2 + 2:
        problemi.append(
            f"la scheda di ingresso a x={DRIVER_X} tocca lo stack del Pi "
            f"(largo {PI_H} mm)")
    if abs(DRIVER_X) + DRIVER_S / 2 > CASSA_INT_L / 2 - 2:
        problemi.append(
            f"la scheda di ingresso a x={DRIVER_X} non entra nel vano "
            f"(semiluce {CASSA_INT_L / 2} mm)")
    if DRIVER_H > CASSA_PROF - Z_TELAIO - TELAIO_S - 4:
        problemi.append(
            f"la scheda di ingresso e' larga {DRIVER_H} mm: non ci sta in"
            " profondita' dietro il telaio")
    if DRIVER_Y - DRIVER_L / 2 < 4 or DRIVER_Y + DRIVER_L / 2 > VETRO_H - 4:
        problemi.append(
            f"la scheda di ingresso a y={DRIVER_Y} esce dall'altezza"
            " del pannello")

    # Profondita'. Display e cornice di incollaggio stanno sullo stesso piano,
    # quindi vanno in parallelo e non in serie.
    usata = (VETRO_S + max(BIADESIVO_S, BIADESIVO_DISPLAY_S + DISPLAY_MODULO_S)
             + TELAIO_S + PI_DISTANZIALI + PI_STACK_H)
    if canale_aria() < 5:
        problemi.append(
            f"i componenti arrivano a {max(c[6] for c in componenti()):.1f} mm"
            f" dal vetro e il fondo interno della cassa sta a"
            f" {fondo_interno():.1f}: restano meno di 5 mm")

    # Raffreddamento. Il muro e' in tufo e non dissipa, quindi tutto passa per
    # le due feritoie e per il vetro. Il canale che resta dietro i componenti
    # non deve essere piu' stretto delle feritoie, altrimenti il collo di
    # bottiglia si sposta li' e allargare le feritoie non serve a nulla.
    # Il canale si misura fra il componente piu' profondo e il fondo interno
    # della cassa, non fra lo stack e CASSA_PROF: la cassa comincia al suo
    # fronte, che e' arretrato di Z_TELAIO rispetto alla faccia del vetro,
    # quindi i due riferimenti non coincidono e confonderli sottostima il
    # canale di qualche millimetro.
    sez = sezioni_aria()
    sez_canale = CASSA_INT_L * canale_aria() / 100
    if sez_canale < sez["ingresso"]:
        problemi.append(
            f"il canale d'aria dietro i componenti vale {sez_canale:.1f} cm2,"
            f" meno della feritoia ({sez['ingresso']:.1f} cm2): e' lui il collo"
            " di bottiglia, non serve allargare le feritoie")
    piu_profondo = max(componenti(), key=lambda c: c[6])
    if piu_profondo[0] != "stack del Pi":
        problemi.append(
            f"il componente piu' profondo e' {piu_profondo[0]}, non lo stack del"
            " Pi: gruppo_massimo() e la quota che ne citano i documenti non"
            " valgono piu'")
    # Quello che passa davvero e' la feritoia meno la rete: contare la
    # sezione lorda era l'errore che dava 6,4 cm2 dove ne passavano 3,2.
    for nome in ("ingresso", "uscita"):
        if sez[nome + "_libera"] < 6.4:
            problemi.append(
                f"la sezione libera d'{nome}, tolta la rete, e'"
                f" {sez[nome + '_libera']:.2f} cm2: ne servono 6,4")
    # Le feritoie sono in serie con la fessura d'ombra, che e' la bocca vera
    # verso l'esterno. Se la bocca e' piu' stretta, il collo di bottiglia e'
    # lei e le feritoie sono sovradimensionate per niente.
    for nome in ("ingresso", "uscita"):
        if sez["bocca_" + nome] < sez[nome + "_libera"]:
            problemi.append(
                f"la bocca d'{nome} nella fessura d'ombra vale"
                f" {sez['bocca_' + nome]:.2f} cm2, meno della feritoia"
                f" ({sez[nome + '_libera']:.2f}): il collo di bottiglia e' lei")
    # La flangia chiude il canale perimetrale e deve stare dietro le
    # feritoie: davanti, le chiude.
    # Si controlla Z_FLANGIA, che e' la quota esportata al modello 3D, e non
    # l'arretramento da cui nasce.
    if Z_FLANGIA - Z_TELAIO < FESSURA_ARRETRAMENTO + FESSURA_ALTEZZA + 1.0:
        problemi.append(
            f"la flangia sta a {Z_FLANGIA - Z_TELAIO:.1f} mm dal fronte e le"
            f" feritoie arrivano a"
            f" {FESSURA_ARRETRAMENTO + FESSURA_ALTEZZA:.1f}: le copre")
    # I fori d'ancoraggio della flangia devono stare fuori dalla cornice, o
    # la malta passa dal foro nel canale delle feritoie.
    dentro = FLANGIA_FORI_X - FLANGIA_FORO_D / 2 \
        - (CASSA_L / 2 + CANALE_PERIMETRALE + CORNICE_S)
    fuori = CASSA_L / 2 + FLANGIA - (FLANGIA_FORI_X + FLANGIA_FORO_D / 2)
    if min(dentro, fuori) < 1.5:
        problemi.append(
            f"i fori della flangia lasciano {dentro:.1f} mm verso la cornice"
            f" e {fuori:.1f} verso il bordo: servono 1,5 per parte")
    # Le feritoie laterali stanno sotto il soffitto interno, e il
    # gocciolatoio sopra di loro deve stare ancora sul fianco.
    tetto = VETRO_H / 2 + CASSA_H / 2
    if FESSURA_LATO_Y1 + 1.0 + GOCCIOLATOIO > tetto:
        problemi.append(
            f"il gocciolatoio sopra le feritoie laterali arriva a"
            f" {FESSURA_LATO_Y1 + 1.0 + GOCCIOLATOIO:.1f}, oltre il tetto della"
            f" cassa a {tetto:.1f}")
    if CANALE_PERIMETRALE - GOCCIOLATOIO < 3.0:
        problemi.append(
            f"il gocciolatoio sporge {GOCCIOLATOIO} mm in un canale largo"
            f" {CANALE_PERIMETRALE}: restano meno di 3 mm per l'aria")
    # Pioggia di striscio. Un getto che entra dalla fessura d'ombra raggiunge
    # una feritoia solo con un angolo radente sulla parete: al massimo quello
    # che va dallo spigolo della cornice, dietro il vetro, al bordo anteriore
    # della feritoia. Una rete tessuta e' spessa due fili, e sotto l'angolo
    # atan(2 filo / maglia) non lascia passare niente in linea retta: la goccia
    # trova un filo e scende lungo la rete.
    radente = math.degrees(math.atan2(
        CANALE_PERIMETRALE, Z_TELAIO + FESSURA_ARRETRAMENTO - VETRO_S))
    limite = math.degrees(math.atan2(2 * RETE_FILO, RETE_MAGLIA))
    if radente > limite - 3.0:
        problemi.append(
            f"un getto dalla fessura d'ombra arriva sulle feritoie a"
            f" {radente:.1f} gradi e la rete e' cieca solo sotto i"
            f" {limite:.1f}: non resta il margine di 3 gradi")
    # L'anello di battuta e' dove il telaio appoggia: niente di quello che sta
    # sul retro del telaio puo' scendere li' sopra, salvo nello scarico della
    # squadretta. Nessun controllo lo guardava, e la squadretta ci cadeva.
    zb0 = Z_TELAIO + TELAIO_S
    zb1 = zb0 + BATTUTA_PROF
    ox = CASSA_INT_L / 2 - BATTUTA
    oy0 = VETRO_H / 2 - CASSA_INT_H / 2 + BATTUTA
    oy1 = VETRO_H / 2 + CASSA_INT_H / 2 - BATTUTA
    for nome, x1, y1, z1, x2, y2, z2 in componenti_lista:
        if z2 <= zb0 or z1 >= zb1:
            continue
        fuori = x1 < -ox or x2 > ox or y1 < oy0 or y2 > oy1
        nello_scarico = (x1 >= SCARICO_STAFFA_X and x2 <= ox
                         and SCARICO_STAFFA_Y0 <= y1 and y2 <= SCARICO_STAFFA_Y1
                         and oy0 <= y1 and y2 <= oy1)
        if fuori and not nello_scarico:
            problemi.append(
                f"{nome} scende sull'anello di battuta (x {x1:.1f}..{x2:.1f},"
                f" y {y1:.1f}..{y2:.1f}): il telaio non arriva in appoggio")
    # Lo scarico lascia al telaio almeno 3 mm d'appoggio e sta lontano dalla
    # sede del riscontro laterale.
    if TELAIO_L / 2 - abs(SCARICO_STAFFA_X) < 3.0:
        problemi.append(
            f"lo scarico della squadretta lascia"
            f" {TELAIO_L / 2 - abs(SCARICO_STAFFA_X):.1f} mm d'appoggio al"
            f" telaio")
    for rx, ry in posizioni_riscontri():
        if rx < 0 and abs(rx) - RISCONTRO_SEDE_D / 2 < abs(SCARICO_STAFFA_X) \
                and ry + RISCONTRO_SEDE_D / 2 > SCARICO_STAFFA_Y0 - 1.0 \
                and ry - RISCONTRO_SEDE_D / 2 < SCARICO_STAFFA_Y1 + 1.0:
            problemi.append(
                f"lo scarico della squadretta tocca la sede del riscontro in"
                f" ({rx:.1f}, {ry:.1f})")
    # Nessun componente deve toccare l'interno dei fianchi nella fascia delle
    # feritoie e sotto di esse: e' la parete su cui scende l'acqua che dovesse
    # passare la rete, e un pezzo appoggiato la raccoglierebbe.
    z_a = Z_TELAIO + FESSURA_ARRETRAMENTO
    z_b = z_a + FESSURA_ALTEZZA
    for nome, x1, y1, z1, x2, y2, z2 in componenti_lista:
        if z2 <= z_a or z1 >= z_b or y1 >= FESSURA_LATO_Y1:
            continue
        if min(CASSA_INT_L / 2 - abs(x1), CASSA_INT_L / 2 - abs(x2)) < 2.0:
            problemi.append(
                f"{nome} sta a meno di 2 mm dall'interno del fianco, sotto le"
                f" feritoie laterali")
        # Gli smussi di scarico occupano gli angoli bassi.
        sm_y = VETRO_H / 2 - CASSA_INT_H / 2 + SMUSSO_SCARICO
        if y1 < sm_y and max(abs(x1), abs(x2)) > FESSURA_LARGHEZZA / 2:
            problemi.append(
                f"{nome} entra negli smussi di scarico agli angoli bassi")
    # La feritoia deve cadere dietro la battuta, non a cavallo: la battuta e'
    # l'anello su cui il telaio appoggia e su cui tirano i magneti, e quattro
    # dei sei cadono dentro la larghezza della feritoia.
    if FESSURA_ARRETRAMENTO < TELAIO_S + BATTUTA_PROF:
        in_mezzo = [(mx, my) for mx, my in posizioni_magneti()
                    if abs(mx) - MAGNETE_SEDE_D / 2 < FESSURA_LARGHEZZA / 2
                    and (my < TELAIO_Y0 + BATTUTA
                         or my > TELAIO_Y0 + TELAIO_H - BATTUTA)]
        problemi.append(
            f"la feritoia inizia a {FESSURA_ARRETRAMENTO:.0f} mm dal fronte e"
            f" taglia la battuta, che arriva a {TELAIO_S + BATTUTA_PROF:.0f}"
            + (f": i magneti in {in_mezzo} ci appoggiano sopra" if in_mezzo
               else ", dove il telaio appoggia"))

    # Il microfono si incolla al vetro e deve stare fra vetro e telaio, cioe'
    # nello spessore del biadesivo che tiene su il telaio.
    spazio_mic = Z_TELAIO - VETRO_S
    if MIC_INGOMBRO_S > spazio_mic:
        problemi.append(
            f"la basetta del microfono e' alta {MIC_INGOMBRO_S} mm: fra vetro"
            f" e telaio ce ne sono {spazio_mic:.1f}")
    if MIC_ASOLA_Y + MIC_ASOLA_H / 2 > MICROFONO_Y - MIC_PCB_H / 2:
        problemi.append(
            "l'asola dei fili del microfono finisce sotto la sua basetta")
    # Il biadesivo del telaio e quello del display sono indipendenti, ma il
    # primo non puo' essere piu' sottile del secondo piu' il display, o il
    # telaio spingerebbe sul pannello.
    if BIADESIVO_S < BIADESIVO_DISPLAY_S + DISPLAY_MODULO_S:
        problemi.append(
            f"il biadesivo del telaio e' {BIADESIVO_S} mm e display piu'"
            f" adesivo ottico fanno"
            f" {BIADESIVO_DISPLAY_S + DISPLAY_MODULO_S:.1f}: il telaio"
            f" spingerebbe sul pannello")

    # L'adesivo ottico scavalca il bordo della serigrafia, perche' e' tagliato
    # a misura del modulo e la finestra trasparente e' piu' piccola. Deve
    # quindi essere abbastanza spesso da rifluire su quel gradino, altrimenti
    # resta un anello d'aria lungo il bordo della finestra.
    if SERIGRAFIA_S > 0:
        rapporto = BIADESIVO_DISPLAY_S / SERIGRAFIA_S
        if rapporto < OCA_RAPPORTO_MIN:
            problemi.append(
                f"l'adesivo ottico e' {BIADESIVO_DISPLAY_S} mm su un gradino"
                f" di serigrafia da {SERIGRAFIA_S * 1000:.0f} um (rapporto"
                f" {rapporto:.1f}, minimo {OCA_RAPPORTO_MIN:.0f}): laminando a"
                f" mano resta un anello di bolle sul bordo della finestra."
                f" Serve un OCA da almeno"
                f" {SERIGRAFIA_S * OCA_RAPPORTO_MIN:.2f} mm")
    # Lo stesso gradino alza il modulo rispetto al vetro, perche' il suo bordo
    # appoggia sull'inchiostro e il centro no. Va speso dall'aria dietro.
    if DISPLAY_ARIA_TELAIO - SERIGRAFIA_S < 0.3:
        problemi.append(
            f"col gradino di serigrafia il display arriva a"
            f" {DISPLAY_ARIA_TELAIO - SERIGRAFIA_S:.2f} mm dal telaio")

    # Il telaio va dentro il vano della cassa e appoggia sulla battuta, quindi
    # la parete non e' libera di crescere: la misura esterna della cassa la
    # fissa la fessura d'ombra, e ogni decimo di parete in piu' lo paga il
    # vano. E' il controllo che boccia le "pareti 3 mm" che la nota del
    # disegno della cassa si portava dietro: con quelle il vano scende a
    # 88 x 228 e il telaio da 89 x 229 non entra.
    gioco_telaio = min((CASSA_INT_L - TELAIO_L) / 2,
                       (CASSA_INT_H - TELAIO_H) / 2)
    if gioco_telaio < 0.5:
        problemi.append(
            f"col vano da {CASSA_INT_L:.0f} x {CASSA_INT_H:.0f} restano"
            f" {gioco_telaio:+.2f} mm per lato attorno al telaio"
            f" {TELAIO_L:.0f} x {TELAIO_H:.0f}:"
            + (" non entra" if gioco_telaio < 0 else " troppo poco per"
               " le tolleranze di una cassa stampata")
            + f". La parete non puo' superare"
            f" {(CASSA_L - TELAIO_L - 1.0) / 2:.1f} mm")

    # Fra il modulo display e il bordo del telaio deve restare la cornice di
    # VHB che incolla il telaio al vetro.
    vhb = min((TELAIO_L - DISPLAY_MODULO_L) / 2,
              (TELAIO_H - DISPLAY_MODULO_H) / 2)
    if vhb < 5.0:
        problemi.append(
            f"restano {vhb:.1f} mm fra display e bordo del telaio: non ci sta"
            " la cornice di biadesivo")
    # La cornice misurata e' 0,98 sui fianchi e 2,02 sopra e sotto: su un
    # millimetro non si incolla un biadesivo perimetrale, e per questo
    # l'adesivo ottico in pieno e' una scelta obbligata, non una preferenza.
    # Quello che il controllo deve guardare e' che la finestra serigrafata
    # resti dentro la cornice: se sborda si vede il bordo del pannello, e su
    # 0,98 mm basta mezzo millimetro di troppo.
    for nome, finestra, modulo, attivo, cornice in (
            ("larghezza", FINESTRA_DISPLAY_L, DISPLAY_MODULO_L,
             DISPLAY_ATTIVO_L, DISPLAY_CORNICE_X),
            ("altezza", FINESTRA_DISPLAY_H, DISPLAY_MODULO_H,
             DISPLAY_ATTIVO_H, DISPLAY_CORNICE_Y)):
        if finestra > modulo:
            problemi.append(
                f"la finestra del vetro in {nome} e' {finestra:.1f} contro un"
                f" modulo da {modulo:.1f}: si vedrebbe oltre il pannello")
        elif (finestra - attivo) / 2 > cornice - 0.3:
            problemi.append(
                f"in {nome} la finestra sborda di"
                f" {(finestra - attivo) / 2:.2f} mm su una cornice da"
                f" {cornice:.2f}: non resta appoggio serigrafato")
    # L'asola del flat deve stare sotto il modulo, non in mezzo ai pixel.
    if FLAT_ASOLA_Y - FLAT_ASOLA_H / 2 > DISPLAY_MODULO_Y0 + DISPLAY_CORNICE:
        problemi.append(
            "l'asola del flat e' troppo alta: cade sotto l'area attiva")
    # I due flat del gruppo display devono arrivare dove le schede stanno. Il
    # percorso non e' diritto, quindi si lascia un quarto di margine.
    corsa_pannello = math.dist((FLAT_ASOLA_X, FLAT_ASOLA_Y),
                               (TERMINALE_X, TERMINALE_Y))
    if corsa_pannello > FLAT_PANNELLO_LUNG * 0.75:
        problemi.append(
            f"dall'asola alla schedina terminale ci sono"
            f" {corsa_pannello:.0f} mm in linea d'aria e il flat del pannello"
            f" e' lungo {FLAT_PANNELLO_LUNG:.0f}: col percorso curvo non ci"
            f" arriva")
    corsa_driver = math.dist((DRIVER_X, DRIVER_Y), (TERMINALE_X, TERMINALE_Y))
    if corsa_driver > FLAT_DRIVER_L * 0.75:
        problemi.append(
            f"fra le due schede ci sono {corsa_driver:.0f} mm e il flat largo"
            f" e' {FLAT_DRIVER_L:.0f}: non si raggiungono")
    # Le due schede stanno in piedi sullo stesso fianco, quindi il flat che le
    # unisce ha il suo piano parallelo al fianco: i 25 mm di larghezza si
    # sviluppano in profondita', non in larghezza, e il confronto e' con lo
    # spazio fra retro del telaio e fondo della cassa.
    profondo = CASSA_PROF - Z_TELAIO - TELAIO_S - CASSA_PARETE
    if FLAT_DRIVER_W > profondo:
        problemi.append(
            f"il flat largo e' {FLAT_DRIVER_W:.0f} mm e dietro il telaio ce"
            f" ne stanno {profondo:.1f}")

    # Le sedi dei magneti sono passanti e stanno in una striscia di 5 mm fra il
    # bordo del telaio e la luce della battuta. Due modi di sbagliarle, che
    # nessun altro controllo vede: la sede tangente al bordo, che in taglio
    # diventa una tacca aperta, e la sede che scavalca la battuta e affaccia
    # sul vuoto, dove non ha niente da attrarre.
    # I quattro magneti d'angolo affacciano sulla battuta orizzontale e i due
    # laterali su quella verticale, quindi il confronto si fa sul bordo piu'
    # vicino a ciascuno, non su una formula sola.
    vano_x = (CASSA_L - 2 * CASSA_PARETE) / 2
    vano_y0 = (VETRO_H - (CASSA_H - 2 * CASSA_PARETE)) / 2
    for mx, my in posizioni_magneti():
        # distanza della sede dal bordo del telaio, sui due assi
        parete = min(TELAIO_L / 2 - abs(mx), my - TELAIO_Y0,
                     TELAIO_Y0 + TELAIO_H - my) - MAGNETE_SEDE_D / 2
        if parete < 0.8:
            problemi.append(
                f"la sede del magnete in ({mx:+.0f},{my:.0f}) lascia"
                f" {parete:.1f} mm di parete verso il bordo del telaio:"
                f" serve almeno 0,8")
        # La battuta e' una cornice larga BATTUTA lungo il bordo del vano: la
        # sede ci sta dentro se la sua distanza dal bordo piu' vicino, piu' il
        # raggio, non la supera. Oltre quella riga il magnete affaccia sul
        # vuoto e non ha ferro da attrarre.
        dal_vano = min(vano_x - abs(mx), my - vano_y0, (VETRO_H - vano_y0) - my)
        if dal_vano + MAGNETE_SEDE_D / 2 > BATTUTA + 0.1:
            problemi.append(
                f"il magnete in ({mx:+.0f},{my:.0f}) sporge"
                f" {dal_vano + MAGNETE_SEDE_D / 2 - BATTUTA:.1f} mm oltre la"
                f" battuta larga {BATTUTA:.0f}: quella parte non ha ferro"
                f" davanti")

    # I fori della squadretta cadono nell'ombra del display: se non sono
    # ciechi, la vite affiora sul fronte del telaio e trova il pannello a
    # un millimetro.
    for sx, sy in posizioni_fori_staffa():
        dentro_display = (abs(sx) <= DISPLAY_MODULO_L / 2
                          and DISPLAY_MODULO_Y0 <= sy
                          <= DISPLAY_MODULO_Y0 + DISPLAY_MODULO_H)
        if dentro_display and not STAFFA_FORI_CIECHI:
            problemi.append(
                f"il foro della staffa in ({sx:+.1f},{sy:.0f}) e' passante e"
                f" cade dietro il display: la vite lo tocca")
        if STAFFA_FORI_CIECHI and STAFFA_FORO_PROF >= TELAIO_S:
            problemi.append(
                f"i fori ciechi della staffa sono profondi"
                f" {STAFFA_FORO_PROF} su {TELAIO_S} di telaio: non sono ciechi")
    # La squadretta deve stare fra il fianco della cassa e la scheda, e la
    # scheda fra la squadretta e il Pi: e' il punto piu' affollato del vano.
    gioco_fianco = (CASSA_L / 2 - CASSA_PARETE) - abs(STAFFA_X - STAFFA_S / 2)
    if gioco_fianco < 2.0:
        problemi.append(
            f"fra la squadretta e il fianco della cassa restano"
            f" {gioco_fianco:.1f} mm: non ci passano le teste delle viti")

    # Il lettore NFC appoggia al retro del telaio: se la quota si scolla, sono
    # millimetri che spariscono dalla fascia sotto il Pi senza che si veda.
    if abs(NFC_DISTANZA_VETRO - (Z_TELAIO + TELAIO_S)) > 0.1:
        problemi.append(
            f"NFC_DISTANZA_VETRO e' {NFC_DISTANZA_VETRO} ma il retro del"
            f" telaio sta a {Z_TELAIO + TELAIO_S:.1f}: il lettore o galleggia"
            f" o affonda nell'alluminio")
    # Il patch di rete scende dal Pi e passa sopra il lettore NFC: il margine
    # e' fra i piu' stretti del progetto e non e' sorvegliato da nient'altro.
    margine_patch = (Z_TELAIO + TELAIO_S + PI_DISTANZIALI
                     - VETRO_S - NFC_DISTANZA_VETRO - NFC_PCB_S - 1.0)
    if margine_patch < 1.0:
        problemi.append(
            f"fra il lettore NFC e il patch di rete che gli passa sopra"
            f" restano {margine_patch:.1f} mm")

    # La coda del pannello, se non si ripiega, scende nella fascia fra il
    # display e il lettore NFC, che e' stretta.
    if not DISPLAY_CODA_RIPIEGATA:
        luce = DISPLAY_MODULO_Y0 - (NFC_Y + NFC_PCB_H / 2)
        if DISPLAY_CODA_H > luce:
            problemi.append(
                f"la coda del pannello resta in piano e sporge"
                f" {DISPLAY_CODA_H:.1f} mm sotto il display, dove fino al"
                f" lettore NFC ce ne sono {luce:.1f}")
    # Se invece si ripiega, passa dietro il pannello e non dall'asola: deve
    # starci nello spessore dichiarato, perche' lo spazio dietro il display e'
    # proprio DISPLAY_MODULO_S e il telaio comincia subito dopo.
    elif DISPLAY_CODA_H > DISPLAY_MODULO_H:
        problemi.append(
            f"la coda e' piu' lunga del pannello ({DISPLAY_CODA_H:.1f} mm):"
            " ripiegata gli sporgerebbe oltre il bordo opposto")
    # Ripiegata, la coda sta fra pannello e telaio: il totale e' DISPLAY_MODULO_S
    # e quel numero e' misurato, ma le due parti devono tornare.
    if DISPLAY_CODA_RIPIEGATA \
            and DISPLAY_PANNELLO_S + DISPLAY_CODA_S > DISPLAY_MODULO_S:
        problemi.append(
            f"pannello {DISPLAY_PANNELLO_S} piu' coda {DISPLAY_CODA_S} fanno"
            f" piu' dell'1,8 misurato sul gruppo ripiegato: una delle tre"
            f" quote e' sbagliata")
    # Dall'asola passa solo il flat del pannello, non la coda.
    if FLAT_PANNELLO_W > FLAT_ASOLA_L - 2:
        problemi.append(
            f"il flat del pannello e' largo {FLAT_PANNELLO_W} mm e l'asola"
            f" {FLAT_ASOLA_L}: non resta un millimetro di gioco per lato")

    # L'antenna NFC non deve avere metallo alle spalle. Il confronto e' con la
    # spira, non col PCB: la scheda e' mezza elettronica, e pretendere
    # un'apertura grande quanto lei vorrebbe dire togliere al telaio alluminio
    # che serve, compreso quello dove si filetta.
    if (NFC_APERTURA_L < NFC_ANTENNA_L - 4
            or NFC_APERTURA_H < NFC_ANTENNA_H - 4):
        problemi.append(
            f"l'apertura del telaio nella zona NFC e'"
            f" {NFC_APERTURA_L:.0f} x {NFC_APERTURA_H:.0f} contro una spira da"
            f" {NFC_ANTENNA_L:.0f} x {NFC_ANTENNA_H:.0f}: l'alluminio"
            f" schermerebbe l'antenna")
    # L'apertura deve stare dentro il PCB, altrimenti si vede il vano dal
    # fronte e la scheda non ha dove appoggiare.
    for nome, a_c, a_dim, p_c, p_dim in (
            ("in larghezza", NFC_X, NFC_APERTURA_L, NFC_PCB_X, NFC_PCB_L),
            ("in altezza", NFC_Y, NFC_APERTURA_H, NFC_Y, NFC_PCB_H)):
        appoggio = min(a_c - a_dim / 2 - (p_c - p_dim / 2),
                       (p_c + p_dim / 2) - (a_c + a_dim / 2))
        if appoggio < 2.0:
            problemi.append(
                f"{nome} fra l'apertura NFC e il bordo del lettore restano"
                f" {appoggio:.1f} mm: la scheda non ha dove appoggiare")
    # L'icona sul vetro deve cadere sulla spira, o si invita ad appoggiare il
    # tag dove la scheda ha il convertitore USB.
    if abs(NFC_X - (NFC_PCB_X + NFC_ANTENNA_OFFSET_X)) > 2.0:
        problemi.append(
            f"l'icona NFC e' a x={NFC_X:.1f} ma la spira e' centrata a"
            f" x={NFC_PCB_X + NFC_ANTENNA_OFFSET_X:.1f}")
    # Il cavo dell'USB-C del lettore esce verso il fianco della cassa.
    usb_x = NFC_PCB_X + NFC_PCB_L / 2 + NFC_USB_SPORGENZA \
        + NFC_USB_CAVO_ANGOLATO
    if usb_x > CASSA_INT_L / 2:
        problemi.append(
            f"il cavo USB-C del lettore arriva a {usb_x:.1f} mm dall'asse e"
            f" sfonda il fianco della cassa, che e' a {CASSA_INT_L / 2:.1f}")

    return problemi


def esporta_scad(percorso) -> None:
    """Riversa le quote in un file .scad, cosi' il 3D e il 2D non divergono."""
    import pathlib

    righe = ["// Generato da parametri.py: non modificare a mano.", ""]
    for nome, valore in sorted(globals().items()):
        if nome.startswith("_") or not nome.isupper():
            continue
        if isinstance(valore, (int, float)):
            righe.append(f"{nome} = {valore};")

    punti = ", ".join(f"[{x}, {y}]" for x, y in posizioni_magneti())
    righe += ["", f"MAGNETI = [{punti}];"]
    punti = ", ".join(f"[{x}, {y}]" for x, y in posizioni_riscontri())
    righe += [f"RISCONTRI = [{punti}];"]
    punti = ", ".join(f"[{x}, {y}]" for x, y in posizioni_fori_speaker())
    righe += [f"FORI_SPEAKER = [{punti}];"]
    punti = ", ".join(f"[{x}, {y}]" for x, y in posizioni_fori_camera())
    righe += [f"FORI_CAMERA = [{punti}];"]
    pathlib.Path(percorso).write_text("\n".join(righe) + "\n",
                                      encoding="utf-8")


def riepilogo() -> str:
    """Stampa le quote principali, utile come controllo prima di produrre."""
    righe = [
        f"vetro            {VETRO_L} x {VETRO_H} x {VETRO_S}",
        f"finestra display {FINESTRA_DISPLAY_L:.1f} x {FINESTRA_DISPLAY_H:.1f}"
        f" a y={FINESTRA_DISPLAY_Y}",
        f"cassa esterna    {CASSA_L} x {CASSA_H} x {CASSA_PROF}",
        f"cassa interna    {CASSA_INT_L} x {CASSA_INT_H}",
        f"telaio           {TELAIO_L} x {TELAIO_H} x {TELAIO_S}",
        f"profondita' usata {max(c[6] for c in componenti()):.1f} dalla faccia"
        f" del vetro, su {fondo_interno():.1f} fino al fondo interno",
        f"gruppo del Pi    {PI_GRUPPO_H:.1f} dal telaio alla cima dei pin"
        f" (e' la quota da prendere col calibro)",
        f"canale d'aria    {canale_aria():.1f} mm fra il componente piu'"
        f" profondo e il fondo cassa ({CASSA_INT_L * canale_aria() / 100:.1f} cm2)",
        f"feritoie         bassa {FESSURA_LARGHEZZA:.0f} x {FESSURA_ALTEZZA:.0f},"
        f" laterali 2 x {FESSURA_LATO_L:.0f} x {FESSURA_ALTEZZA:.0f}:"
        f" {sezioni_aria()['ingresso']:.1f} cm2 per verso, tolta la rete"
        f" {sezioni_aria()['ingresso_libera']:.2f}",
        f"bocche           ingresso {sezioni_aria()['bocca_ingresso']:.2f} cm2,"
        f" uscita {sezioni_aria()['bocca_uscita']:.2f}",
        f"tiraggio         {tiraggio(20):.1f} W con l'aria interna 20 gradi"
        f" sopra l'esterno, {tiraggio(30):.1f} W a 30",
        f"pareti           vetro {conduttanze_pareti()['vetro']:.3f} W/K,"
        f" muro {conduttanze_pareti()['muro']:.3f} W/K (stime)",
        f"aria in cassa    +{salto_termico(POTENZA_RIPOSO):.0f} K a riposo"
        f" ({POTENZA_RIPOSO:.1f} W), +{salto_termico(POTENZA_PICCO):.0f} K a"
        f" pieno carico continuo ({POTENZA_PICCO:.1f} W)",
        f"posa             cornice a filo dell'intonaco finito, flangia a"
        f" {Z_FLANGIA:.0f} mm, nicchia {FORO_MURO_L:.0f} x {FORO_MURO_H:.0f}"
        f" x {FORO_MURO_PROF:.0f}",
        f"sotto il Pi      l'ansa del flat PCIe si ferma a"
        f" {PI_Y0 - PCIE_ANSA - (NFC_Y + NFC_PCB_H / 2):.1f} mm dal lettore"
        f" NFC, il patch gli passa sopra a"
        f" {Z_TELAIO + TELAIO_S + PI_DISTANZIALI - VETRO_S - NFC_DISTANZA_VETRO - NFC_PCB_S - 1.0:.1f} mm",
    ]
    return "\n".join("  " + r for r in righe)


if __name__ == "__main__":
    import pathlib

    destinazione = pathlib.Path(__file__).parent / "cad" / "parametri.scad"
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    esporta_scad(destinazione)
    print(riepilogo())
    print(f"\n  quote esportate in {destinazione.name}")

    problemi = verifica()
    print()
    if problemi:
        print("  INTERFERENZE DA RISOLVERE:")
        for x in problemi:
            print("   -", x)
        raise SystemExit(1)
    print("  verifica interferenze: nessun problema")
