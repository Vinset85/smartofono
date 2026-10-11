// Videocitofono da incasso: modello 3D parametrico dell'assieme.
//
// Le quote arrivano da parametri.scad, generato da parametri.py: per cambiare
// una misura si modifica il file Python e si rilancia, cosi' il 2D e il 3D
// restano allineati.
//
// Viste disponibili (variabile VISTA):
//   "assieme"   tutti i pezzi montati
//   "esploso"   stessi pezzi distanziati, per capire l'ordine di montaggio
//   "cassa"     solo la cassa da incasso          -> STL per stampa/lamiera
//   "telaio"    solo il telaio portante           -> STL
//   "vetro"     solo il vetro frontale            -> riferimento per la vetreria
//   "sezione"   assieme tagliato a meta', mostra il canale d'aria
//
// Export da riga di comando:
//   openscad -D 'VISTA="cassa"' -o cassa.stl videocitofono.scad

include <parametri.scad>

VISTA = "assieme";
$fn = 48;

// Il riferimento e' lo stesso dei disegni 2D: x = 0 al centro del pannello,
// y = 0 al bordo inferiore del vetro, z = 0 sulla faccia esterna del vetro
// con la profondita' che cresce entrando nel muro.

// ---------------------------------------------------------------- utilita'

// Centrata nei tre assi, come cube(center = true) e come foro(): tutti i
// richiami la posizionano scrivendo il piano di mezzeria, z0 + s / 2, e con
// un'estrusione che partiva da zero ogni piastra finiva mezzo spessore piu'
// avanti del suo posto - il vetro a 1..3 invece di 0..2, il telaio a 6,5..9,5
// invece di 5..8. Non si vedeva nei controlli, che stanno in parametri.py e
// non guardano questo file, ma falsava la sezione e i render.
module piastra_raccordata(l, h, s, r) {
    translate([0, 0, -s / 2])
    linear_extrude(height = s)
        offset(r = r) offset(delta = -r)
            square([l, h], center = true);
}

module foro(d, h) {
    cylinder(d = d, h = h, center = true);
}

// ---------------------------------------------------------------- vetro

module vetro() {
    color("#1a1a1aEE", 0.55)
    difference() {
        translate([0, VETRO_H / 2, VETRO_S / 2])
            piastra_raccordata(VETRO_L, VETRO_H, VETRO_S, VETRO_RAGGIO);
        // Unico foro passante: il microfono.
        translate([MICROFONO_X, MICROFONO_Y, VETRO_S / 2])
            foro(MICROFONO_D, VETRO_S * 3);
    }
    // Finestre trasparenti nella serigrafia, rese come lastre chiare. Stanno
    // dentro lo spessore, non lo scavalcano: se sporgessero di mezzo decimo per
    // evitare le facce complanari, vetro.stl misurerebbe 2,1 invece di 2,0 e
    // chiunque lo quotasse leggerebbe una quota falsa.
    color("#90c8ff", 0.35) {
        translate([0, FINESTRA_DISPLAY_Y + FINESTRA_DISPLAY_H / 2, VETRO_S / 2])
            cube([FINESTRA_DISPLAY_L, FINESTRA_DISPLAY_H, VETRO_S - 0.1], center = true);
        translate([CAMERA_X, OTTICA_Y, VETRO_S / 2])
            foro(OTTICA_D, VETRO_S - 0.1);
    }
    color("#4060a0", 0.3)
        translate([NFC_X, NFC_Y, VETRO_S / 2]) foro(NFC_D, VETRO_S - 0.1);
}

// ---------------------------------------------------------------- telaio

module telaio() {
    z0 = Z_TELAIO;   // complanare al retro del display
    color("#3c3c40")
    difference() {
        translate([0, VETRO_H / 2, z0 + TELAIO_S / 2])
            piastra_raccordata(TELAIO_L, TELAIO_H, TELAIO_S, 2);

        // Dietro il display il telaio e' pieno: passa solo il flat.
        translate([FLAT_ASOLA_X, FLAT_ASOLA_Y, z0 + TELAIO_S / 2])
            cube([FLAT_ASOLA_L, FLAT_ASOLA_H, TELAIO_S * 3], center = true);

        // Passaggio della lente della camera: il barilotto lo attraversa per
        // arrivare a sfiorare il vetro, quindi vuole gioco.
        translate([CAMERA_X, OTTICA_Y, z0 + TELAIO_S / 2])
            foro(CAMERA_LENTE_D + GIOCO_LENTE_TELAIO, TELAIO_S * 3);

        // Fori filettati delle colonnine della camera, decentrati rispetto
        // all'asse ottico.
        for (f = FORI_CAMERA)
            translate([f[0], f[1], z0 + TELAIO_S / 2])
                foro(CAMERA_FORO_D, TELAIO_S * 3);

        // Luce davanti al cono dell'altoparlante, sopra la lente.
        translate([SPEAKER_X, SPEAKER_LUCE_Y, z0 + TELAIO_S / 2])
            cube([SPEAKER_LUCE_L, SPEAKER_LUCE_H, TELAIO_S * 3],
                 center = true);

        // Apertura per l'antenna NFC: qui il telaio non deve avere metallo,
        // altrimenti la bobina non legge.
        translate([NFC_X, NFC_Y, z0 + TELAIO_S / 2])
            cube([NFC_APERTURA_L, NFC_APERTURA_H, TELAIO_S * 3],
                 center = true);

        // Asola per i fili del microfono, la cui basetta sta davanti al
        // telaio, incollata al vetro.
        translate([MICROFONO_X, MIC_ASOLA_Y, z0 + TELAIO_S / 2])
            cube([MIC_ASOLA_L, MIC_ASOLA_H, TELAIO_S * 3],
                 center = true);

        // Fori filettati dell'altoparlante: tre, non quattro.
        for (f = FORI_SPEAKER)
            translate([f[0], f[1], z0 + TELAIO_S / 2])
                foro(SPEAKER_FORO_D, TELAIO_S * 3);

        // Fori di aggancio ai due perni della cassa, in alto.
        for (sx = [-1, 1])
            translate([sx * PERNO_PASSO / 2,
                       (VETRO_H + TELAIO_H) / 2 - PERNO_MARGINE / 2,
                       z0 + TELAIO_S / 2])
                foro(PERNO_FORO_D, TELAIO_S * 3);

        // Sedi passanti dei magneti.
        for (m = MAGNETI)
            translate([m[0], m[1], z0 + TELAIO_S / 2])
                foro(MAGNETE_SEDE_D, TELAIO_S * 3);
    }
}

// ---------------------------------------------------------------- componenti

module display() {
    color("#101014")
        translate([0, DISPLAY_MODULO_Y0 + DISPLAY_MODULO_H / 2,
                   VETRO_S + BIADESIVO_DISPLAY_S + DISPLAY_MODULO_S / 2])
            cube([DISPLAY_MODULO_L, DISPLAY_MODULO_H, DISPLAY_MODULO_S],
                 center = true);
    // Coda del pannello, ripiegata dietro: e' larga quanto tutto il pannello
    // e il suo spessore e' compreso in DISPLAY_MODULO_S.
    color("#8a5a2a")
        translate([0, DISPLAY_MODULO_Y0 + DISPLAY_CODA_H / 2,
                   VETRO_S + BIADESIVO_DISPLAY_S + DISPLAY_MODULO_S
                   - DISPLAY_CODA_S / 2])
            cube([DISPLAY_CODA_L, DISPLAY_CODA_H, DISPLAY_CODA_S],
                 center = true);
    // Le due schede, in piedi sullo stesso fianco: quella di ingresso in alto
    // con HDMI-A e USB-C, la schedina terminale cinquanta millimetri sotto.
    color("#1a6a2a")
        translate([DRIVER_X, DRIVER_Y,
                   Z_TELAIO + TELAIO_S + 2 + DRIVER_H / 2])
            cube([DRIVER_S, DRIVER_L, DRIVER_H], center = true);
    color("#1a6a2a")
        translate([TERMINALE_X, TERMINALE_Y,
                   Z_TELAIO + TELAIO_S + 2 + TERMINALE_L / 2])
            cube([TERMINALE_S, TERMINALE_H, TERMINALE_L], center = true);
    // La squadretta che tiene in piedi la scheda di ingresso: ala lunga
    // contro il fianco, ala corta avvitata al retro del telaio.
    color("#9a9aa0") {
        translate([STAFFA_X, DRIVER_Y, STAFFA_Z0 + STAFFA_ALA_H / 2])
            cube([STAFFA_S, STAFFA_L, STAFFA_ALA_H], center = true);
        translate([STAFFA_X + STAFFA_S / 2 + STAFFA_ALA_BASE / 2, DRIVER_Y,
                   STAFFA_Z0 + STAFFA_S / 2])
            cube([STAFFA_ALA_BASE, STAFFA_L, STAFFA_S], center = true);
    }
}

module raspberry() {
    z0 = Z_TELAIO + TELAIO_S + PI_DISTANZIALI;
    // Scheda col lato lungo in verticale, connettori verso destra.
    color("#1a6a2a")
        translate([0, PI_Y0 + PI_L / 2, z0 + 0.8])
            cube([PI_H, PI_L, 1.6], center = true);
    // Stack di dissipatore, adattatore NVMe, HAT audio e ventola.
    color("#6a6a70", 0.9)
        translate([0, PI_Y0 + PI_L / 2, z0 + 1.6 + (PI_STACK_H - 1.6) / 2])
            cube([PI_H - 4, PI_L - 10, PI_STACK_H - 1.6], center = true);
}

module camera_modulo() {
    // La scheda e' arretrata sulle colonnine e centrata sui propri fori, che
    // non stanno sull'asse ottico. Il PCB e' quotato sulla faccia posteriore.
    z_pcb = Z_TELAIO + TELAIO_S + CAMERA_COLONNINE;
    color("#6a6a70")   // colonnine fra telaio e scheda
        for (f = FORI_CAMERA)
            translate([f[0], f[1], Z_TELAIO + TELAIO_S + CAMERA_COLONNINE / 2])
                foro(4, CAMERA_COLONNINE);
    color("#204020")
        translate([CAMERA_X, CAMERA_PCB_Y0, z_pcb - CAMERA_PCB_S / 2])
            cube([CAMERA_PCB_L, CAMERA_PCB_H, CAMERA_PCB_S], center = true);
    // Base quadrata del gruppo ottico, appoggiata al PCB.
    color("#15151a")
        translate([CAMERA_X, OTTICA_Y,
                   z_pcb - CAMERA_PCB_S - CAMERA_BASE_S / 2])
            cube([CAMERA_BASE_L, CAMERA_BASE_L, CAMERA_BASE_S],
                 center = true);
    // Barilotto: attraversa il telaio e si ferma a filo del vetro.
    color("#15151a")
        translate([CAMERA_X, OTTICA_Y,
                   VETRO_S + CAMERA_GIOCO_VETRO
                   + (z_pcb - CAMERA_PCB_S - CAMERA_BASE_S
                      - VETRO_S - CAMERA_GIOCO_VETRO) / 2])
            foro(CAMERA_LENTE_D, z_pcb - CAMERA_PCB_S - CAMERA_BASE_S
                                 - VETRO_S - CAMERA_GIOCO_VETRO);
}

module microfono() {
    // Basetta staccata dall'HAT e incollata al vetro, dietro al suo foro:
    // sta nello spessore che il display occupa piu' in basso.
    color("#204020")
        translate([MICROFONO_X, MICROFONO_Y,
                   VETRO_S + MIC_INGOMBRO_S / 2])
            cube([MIC_PCB_L, MIC_PCB_H, MIC_INGOMBRO_S], center = true);
}

module altoparlante() {
    color("#2a2a2e")
        translate([SPEAKER_X, SPEAKER_Y,
                   Z_TELAIO + TELAIO_S + SPEAKER_ARRETRAMENTO
                     + SPEAKER_S / 2])
            cube([SPEAKER_L, SPEAKER_H, SPEAKER_S], center = true);
}

module lettore_nfc() {
    // Montato sul retro del telaio, con l'antenna che guarda il vetro
    // attraverso l'apertura.
    color("#8a1a1a")
        translate([NFC_PCB_X, NFC_Y, VETRO_S + NFC_DISTANZA_VETRO + 0.8])
            cube([NFC_PCB_L, NFC_PCB_H, 1.6], center = true);
}

// ---------------------------------------------------------------- cassa

module cassa() {
    // La cassa parte dietro il vetro e si sviluppa in profondita' nel muro.
    z0 = Z_TELAIO;
    color("#9a9aa0")
    difference() {
        union() {
            // Corpo scatolato.
            translate([0, VETRO_H / 2, z0 + CASSA_PROF / 2])
                cube([CASSA_L, CASSA_H, CASSA_PROF], center = true);
            // Flangia di muratura, arretrata per restare sotto l'intonaco.
            translate([0, VETRO_H / 2,
                       z0 + FLANGIA_ARRETRAMENTO + CASSA_PARETE / 2])
                piastra_raccordata(CASSA_L + 2 * FLANGIA,
                                   CASSA_H + 2 * FLANGIA, CASSA_PARETE, 4);
        }

        // Vano interno: aperto sul fronte, chiuso in fondo dalla parete.
        translate([0, VETRO_H / 2,
                   z0 + (CASSA_PROF - CASSA_PARETE) / 2])
            cube([CASSA_INT_L, CASSA_INT_H, CASSA_PROF - CASSA_PARETE],
                 center = true);

        // Feritoie nelle pareti orizzontali: ingresso in basso, uscita in alto.
        // Guardano verso la fessura d'ombra, non verso chi sta davanti.
        for (sy = [-1, 1])
            translate([0, VETRO_H / 2 + sy * CASSA_H / 2,
                       z0 + FESSURA_ARRETRAMENTO + FESSURA_ALTEZZA / 2])
                cube([FESSURA_LARGHEZZA, CASSA_PARETE * 4, FESSURA_ALTEZZA],
                     center = true);

        // Bocca anteriore: il telaio entra fino alla battuta, quindi davanti
        // resta solo l'anello di appoggio.
        translate([0, VETRO_H / 2, z0 + TELAIO_S / 2 - 0.1])
            cube([CASSA_INT_L, CASSA_INT_H, TELAIO_S], center = true);
        // Oltre la battuta il vano torna pieno: la battuta e' un gradino di
        // pochi millimetri, non un restringimento per tutta la profondita'.
        translate([0, VETRO_H / 2,
                   z0 + TELAIO_S + BATTUTA_PROF
                     + (CASSA_PROF - TELAIO_S - BATTUTA_PROF) / 2])
            cube([CASSA_INT_L, CASSA_INT_H,
                  CASSA_PROF - TELAIO_S - BATTUTA_PROF], center = true);
        translate([0, VETRO_H / 2, z0 + TELAIO_S + BATTUTA_PROF / 2])
            cube([CASSA_INT_L - 2 * BATTUTA, CASSA_INT_H - 2 * BATTUTA,
                  BATTUTA_PROF + 0.1], center = true);

        // Passaggi dei corrugati sul fondo.
        for (sx = [-1, 1])
            translate([sx * CORRUGATO_PASSO / 2, 26, z0 + CASSA_PROF])
                foro(CORRUGATO_D, CASSA_PARETE * 6);

        // Fori nella flangia per l'ancoraggio.
        for (sx = [-1, 1])
            for (i = [0 : 3])
                translate([sx * (CASSA_L / 2 + FLANGIA / 2),
                           20 + i * 55,
                           z0 + FLANGIA_ARRETRAMENTO + CASSA_PARETE / 2])
                    foro(FLANGIA_FORO_D, CASSA_PARETE * 4);

        // Sedi dei riscontri ferrosi, scavate nella faccia su cui appoggia il
        // telaio: il dischetto ci sta dentro a filo e non solleva il gruppo.
        // Non sono centrate sui magneti ma sull'asse dell'anello di battuta,
        // che e' l'unico modo di starci dentro.
        for (r = RISCONTRI)
            translate([r[0], r[1],
                       z0 + TELAIO_S + RISCONTRO_SEDE_PROF / 2])
                foro(RISCONTRO_SEDE_D, RISCONTRO_SEDE_PROF);
    }

    // Perni di centraggio in alto: il telaio si aggancia qui e poi scende in
    // posizione, cosi' il fissaggio si riduce a due viti raggiungibili.
    color("#8a8a90")
        for (sx = [-1, 1])
            translate([sx * PERNO_PASSO / 2,
                       (VETRO_H + TELAIO_H) / 2 - PERNO_MARGINE / 2,
                       z0 + TELAIO_S - PERNO_SPORGENZA / 2])
                foro(PERNO_D, PERNO_SPORGENZA);
}

// ---------------------------------------------------------------- assiemi

module componenti() {
    display();
    raspberry();
    camera_modulo();
    microfono();
    altoparlante();
    lettore_nfc();
}

module assieme() {
    cassa();
    telaio();
    componenti();
    vetro();
}

module esploso() {
    d = 45;
    cassa();
    translate([0, 0, -d * 0.6]) telaio();
    translate([0, 0, -d * 0.9]) componenti();
    translate([0, 0, -d * 1.6]) vetro();
}

module sezione() {
    difference() {
        assieme();
        translate([CASSA_L, 0, 0])
            cube([CASSA_L * 2, VETRO_H * 3, CASSA_PROF * 4], center = true);
    }
}

// Il modello e' costruito con z = profondita' per restare coerente con i
// disegni 2D. Questa rotazione lo rimette in piedi come sta sul muro, cosi'
// le viste e gli STL hanno l'orientamento che uno si aspetta.
// Porta il modello nell'orientamento di montaggio: altezza lungo z e faccia
// esterna del vetro verso -y, cioe' verso chi guarda il citofono. Il mirror
// sulla profondita' serve perche' nei disegni 2D la x cresce verso destra
// guardando il pannello da fuori: senza di esso la vista 3D del fronte
// risulterebbe speculare, con il microfono dal lato sbagliato.
module montato() { rotate([90, 0, 0]) mirror([0, 0, 1]) children(); }

if (VISTA == "assieme") montato() assieme();
else if (VISTA == "esploso") montato() esploso();
else if (VISTA == "cassa") montato() cassa();
else if (VISTA == "telaio") montato() telaio();
else if (VISTA == "vetro") montato() vetro();
else if (VISTA == "sezione") montato() sezione();
else montato() assieme();
