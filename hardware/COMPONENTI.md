# Componenti elettronici

Distinta dei pezzi usati sul pannello, con specifiche ricavate dai datasheet
ufficiali e dai link di acquisto. I prezzi sono **indicativi** (IVA inclusa
dove il negozio la applica), riferiti a ottobre 2026: i listini si muovono.

Non c'è l'SSD NVMe (l'adattatore N05 lo richiede a parte), né vetro, telaio,
cassa o minuteria: quelli stanno in [PRODUZIONE.md](PRODUZIONE.md) e nella
tabella Minuteria del [README](README.md).

| Componente | Acquisto | Costo indicativo |
|---|---|---|
| Raspberry Pi 5 8 GB | [Reichelt RASP PI 5 B 8GB](https://www.reichelt.com/it/it/shop/prodotto/raspberry_pi_5_b_4x_2_4_ghz_8_gb_ram_wlan_bt-359846) | € 97,00 |
| Telecamera Camera Module 3 | [Amazon B0BRY6MVXL](https://www.amazon.it/dp/B0BRY6MVXL) | € 30,00 |
| Schermo AMOLED 5,5" | [AliExpress 1005004285318699](https://it.aliexpress.com/item/1005004285318699.html) | € 92,95 |
| Scheda audio Mic+ V3 | [Raspiaudio Mic+](https://raspiaudio.com/product/mic/) | € 28,00 |
| Casse 3 W 8 Ω (kit 2 pz) | [AZ-Delivery](https://www.az-delivery.de/it/products/2-stuck-dfplayer-mini-3-watt-8-ohm-mini-lautsprecher-mit-jst-ph2-0-mm-pin-schnittstelle-fur-arduino-raspberry-pi-und-elektronische-diy-projekte-inklusive-e-book) | € 8,00 |
| Lettore NFC PN532 | [Amazon B0FKH38Z6H](https://www.amazon.it/dp/B0FKH38Z6H) | € 15,99 |
| PoE HAT (F) | [Waveshare PoE HAT (F)](https://www.waveshare.com/product/raspberry-pi/hats/interface-power/poe-hat-f.htm) | € 20,00 |
| Scheda NVMe N05 | [Amazon B0CTLT39Y3](https://www.amazon.it/GeeekPi-N05-Raspberry-periferica-Superiore/dp/B0CTLT39Y3) | € 14,00 |
| **Totale elettronica (senza SSD)** | | **€ 305,94** |

Al 18 ottobre 2026 Reichelt elenca lo stesso Pi 5 8 GB a 200,33 €: il
€ 97,00 è il riferimento d'acquisto di questo impianto, non il listino odierno.

---

## Raspberry Pi 5, 8 GB

| | |
|---|---|
| Acquisto | [Reichelt, art. RASP PI 5 B 8GB](https://www.reichelt.com/it/it/shop/prodotto/raspberry_pi_5_b_4x_2_4_ghz_8_gb_ram_wlan_bt-359846) |
| Costo indicativo | € 97,00 |
| Produttore | Raspberry Pi Ltd, `PI5 MODEL B/8GB` |
| EAN | 5056561803326 |
| Datasheet | [Product brief](https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-product-brief.pdf) · [scheda prodotto](https://www.raspberrypi.com/products/raspberry-pi-5/) |

Dal product brief ufficiale (ottobre 2026):

- SoC Broadcom **BCM2712**, quad-core Arm Cortex-A76 64 bit a **2,4 GHz**, 512 KB L2 per core, 2 MB L3
- GPU VideoCore VII, OpenGL ES 3.1, Vulkan 1.2, HEVC 4Kp60
- **8 GB** LPDDR4X-4267 (varianti 1 / 2 / 4 / 8 / 16 GB)
- 2 × micro-HDMI 4Kp60 HDR; 2 × USB 3.0 (5 Gbit/s contemporanei), 2 × USB 2.0
- Gigabit Ethernet con PoE+ (serve HAT dedicato); Wi-Fi 802.11ac, Bluetooth 5.0 / BLE
- **PCIe 2.0 x1** (adattatore M.2 a parte); 2 transceiver MIPI a 4 lane (camera/display)
- Header GPIO 40 pin, RTC, pulsante di accensione, slot microSD SDR104
- Alimentazione 5 V / 5 A USB-C con USB-PD; 0–70 °C; produzione almeno fino a gennaio 2036
- Ingombro Reichelt: 85 × 56 × 17 mm

In questo progetto il Wi-Fi non si usa, l'avvio è da NVMe, l'alimentazione arriva
dal PoE HAT. Prima di staccare l'USB-C: `PSU_MAX_CURRENT=5000` in EEPROM.

---

## Telecamera — Raspberry Pi Camera Module 3 (standard)

| | |
|---|---|
| Acquisto | [Amazon, Camera Module 3](https://www.amazon.it/dp/B0BRY6MVXL) |
| Costo indicativo | € 30,00 |
| Datasheet | [Product brief giugno 2024](https://datasheets.raspberrypi.com/camera/camera-module-3-product-brief.pdf) · [scheda prodotto](https://www.raspberrypi.com/products/camera-module-3/) |

Dal brief ufficiale, variante **standard** (non Wide, non NoIR):

- Sensore Sony **IMX708**, stacked back-illuminated, **11,9 MP** (4608 × 2592), pixel 1,4 µm, diagonale 7,4 mm
- Autofocus a rilevamento di fase (PDAF), HDR fino a 3 MP
- Campo visivo **66° × 41°** (75° in diagonale), focale 4,74 mm, F1.8, fuoco 10 cm–∞
- Video tipici 1080p50 / 720p100 / 480p120, uscita RAW10 su CSI-2
- Filtro IR integrato (assente sulle NoIR)
- PCB 25 × 24 × 11,5 mm (altezza totale 11,3 mm dal brief), flat 200 mm, connettore FPC 15 × 1 mm
- 0–50 °C; produzione almeno fino a gennaio 2030

`libcamera` su questo impianto la vede come `imx708`, non `imx708_wide`. Il flat
in dotazione è corto per la cassa: in posa serve uno da **200 mm**.

---

## Schermo — AMOLED 5,5" 1080 × 1920 HDMI + touch

| | |
|---|---|
| Acquisto | [AliExpress 1005004285318699](https://it.aliexpress.com/item/1005004285318699.html) |
| Costo indicativo | € 92,95 |
| Equivalente ufficiale | Waveshare **5.5inch HDMI AMOLED**, SKU 16103 |
| Datasheet | [scheda Waveshare](https://www.waveshare.com/product/5.5inch-hdmi-amoled.htm) · [wiki](https://www.waveshare.com/wiki/5.5inch_HDMI_AMOLED) |

Dalla scheda e dalla wiki Waveshare (il listino ufficiale è ~119 $; l'acquisto
di questo impianto è AliExpress):

- Pannello **AMOLED** 5,5", **1080 × 1920** ritratto, 60 Hz, angolo 170°, ~90 % NTSC
- Luminosità a pieno bianco ~500 lux; cinque gradini 75 / 140 / 210 / 260 / 310 cd/m²
- Touch capacitivo **5 punti**, vetro temperato fino a 6H, porta USB; su questo Pi
  il bridge è `1a86:e5e3 USB2IIC_CTP_CONTROL`
- Video HDMI, audio jack 3,5 mm (non usato: l'audio passa dall'HAT)
- A 5 V: ~650 mA schermo bianco, ~250 mA nero
- Spessore AMOLED + PCB 4,8 mm (11 mm col supporto HDMI); viti M2.5 non oltre 4 mm
  o si spacca il pannello
- CE; burn-in se un'immagine fissa resta troppo a lungo — mitigato in software

Il rilievo col calibro sul pezzo reale: pannello **70,0 × 125,0 mm**, spessore
nudo **0,4 mm**. Quello spessore è la prova che è OLED, non IPS con backlight.

---

## Scheda audio — Raspiaudio Mic+ (Pi MIC V3)

| | |
|---|---|
| Acquisto | [raspiaudio.com/product/mic](https://raspiaudio.com/product/mic/) |
| Costo indicativo | € 28,00 (listino produttore 27,99 €) |
| Guida | [installazione MIC+ V3](https://forum.raspiaudio.com/t/mic-installation-guide/17) |
| DAC (datasheet TI) | [PCM5102A](https://www.ti.com/product/PCM5102A) |

Dalla scheda produttore e dalla guida V3:

- HAT I2S, compatibile Raspberry Pi 5 / 4 / 3 / Zero
- DAC 32 bit / 384 kHz **PCM5102A**, overlay `googlevoicehat-soundcard` (si
  presenta come Google voiceHAT)
- Amplificatore 2 × 5 W su morsetti per casse passive **2–8 Ω**; speaker di
  bordo disattivabili con microswitch (in cassa **vanno spenti**)
- Microfono I2S ad alta sensibilità su basetta staccabile, passo 2,54 mm:
  3V3, GND, BCLK, DOUT, WB, SEL
- EEPROM plug-and-play, header lungo per impilare un altro HAT sopra (qui il
  PoE sta sotto, l'audio sopra)
- GPIO25 occupato dal LED della scheda

Il jack 3,5 mm c'è; il citofono usa i morsetti e il microfono staccato, incollato
dietro il foro del vetro.

---

## Casse — mini altoparlante 3 W 8 Ω (kit 2 pezzi)

| | |
|---|---|
| Acquisto | [AZ-Delivery, kit 2 pz](https://www.az-delivery.de/it/products/2-stuck-dfplayer-mini-3-watt-8-ohm-mini-lautsprecher-mit-jst-ph2-0-mm-pin-schnittstelle-fur-arduino-raspberry-pi-und-elektronische-diy-projekte-inklusive-e-book) |
| Costo indicativo | € 8,00 (listino negozio al 18/10/2026: 5,11 €) |

Dalla scheda AZ-Delivery:

- Potenza **3 W** max, impedenza **8 Ω**
- Forma rettangolare, membrana in carta, magnete; connettore **JST-PH 2,0 mm**,
  cavo 420 mm
- Dimensioni dichiarate nel testo **70 × 30 × 15 mm** (la tabella del negozio
  riporta 3,1 × 2,8 × 1,5 cm, incoerente: in cassa si usa l'ovale ~70 × 32 del
  rilievo)
- Peso 23 g; adatto ad amplificatori classe D (MAX98306, TS2012, TPA2016) e
  quindi ai morsetti 2–8 Ω dell'HAT

Il kit è da due pezzi; nel pannello ne entra **uno**, arretrato su colonnine
nylon, lontano dalla camera.

---

## Lettore NFC — modulo PN532 V2 (chip NXP)

| | |
|---|---|
| Acquisto | [Amazon, AYWHP PN532 NFC RFID Module V2 Kit](https://www.amazon.it/dp/B0FKH38Z6H) |
| Costo indicativo | € 15,99 |
| Chip | NXP **PN532/C1** |
| Datasheet | [PN532 product data sheet, rev. 3.6](https://www.nxp.com/docs/en/nxp/data-sheets/PN532_C1.pdf) |

Dal datasheet NXP (28 novembre 2017) e dalla scheda del kit:

- Transceiver 13,56 MHz su core 80C51, 40 KB ROM, 1 KB RAM
- ISO/IEC 14443A/MIFARE, 14443B, FeliCa, NFCIP-1 (ISO/IEC 18092) fino a **424 kbit/s**
- Host **SPI**, **I2C**, **HSU** (UART); alimentazione 2,7–5,5 V
- Portata tipica in reader/writer **fino a 50 mm** (antenna e taratura)
- Kit: interfacce I2C / SPI / HSU, level shifter, portata dichiarata fino a 7 cm

In questo impianto il chip parla in **HSU** tramite adattatore USB-UART
**CH340** (`1a86:7523` → `/dev/ttyUSB0`), non in I2C. L'antenna **non è
centrata** sul PCB: le quote del telaio partono da lì, vedi
[MISURE.md](MISURE.md).

---

## PoE HAT (F) — Waveshare

| | |
|---|---|
| Acquisto | [Waveshare PoE HAT (F)](https://www.waveshare.com/product/raspberry-pi/hats/interface-power/poe-hat-f.htm) |
| Costo indicativo | € 20,00 (listino produttore ~19,19 $) |
| Datasheet | [wiki PoE HAT (F)](https://www.waveshare.com/wiki/PoE_HAT_(F)) |

Dalla scheda e dalla wiki ufficiale:

- Solo **Raspberry Pi 5 / CM5** (non Pi 4 / 3)
- IEEE **802.3af/at**, ingresso 37–57 V DC, SMPS **isolato**
- Uscite: header GPIO **5 V / 4,5 A**; header 2 pin **12 V / 2 A**; tetto **25 W**
  totali fra 5 V e 12 V
- 56,5 × 70,0 mm; ventola e dissipatore in metallo in dotazione
- La ventola va sul connettore **FAN a 4 pin del Pi**, non sui 5 V dell'HAT

I 12 V commutati da GPIO12 possono alimentare l'elettroserratura sotto UPS:
[SCHEMA-SERRATURA.md](SCHEMA-SERRATURA.md). Serve uno switch **PoE+ 802.3at**,
non 802.3af.

---

## Scheda memoria — GeeekPi / 52Pi N05 (M.2 NVMe)

| | |
|---|---|
| Acquisto | [Amazon, GeeekPi N05](https://www.amazon.it/GeeekPi-N05-Raspberry-periferica-Superiore/dp/B0CTLT39Y3) |
| Costo indicativo | € 14,00 (listino Amazon 13,99 €) |
| Datasheet | [52Pi wiki EP-0209](https://wiki.52pi.com/index.php?title=EP-0209) |

Dalla wiki 52Pi e dalla scheda Amazon (SSD e Pi **non** inclusi):

- Adattatore PCIe → M.2 **M-key NVMe**, formati **2230 e 2242**, solo Pi 5
- PCIe x1 Gen2 (certificato) / Gen3 (forzabile, non certificato dal Pi 5)
- Regolatore 3,3 V fino a **3 A** sul rail M.2; LED attività
- Formato HAT 65 × 56,5 mm, asole per i flat CSI/DSI, PCB traforato per l'aria
- In confezione: FFC PCIe 40 mm, distanziali, viti, vite CNC per l'SSD

In cassa l'adattatore sta **sotto** il Pi, alimentato dai 5 V dell'header con
fili volanti: è il punto fragile descritto nel [README](README.md). L'SSD
(Phison PS5021-E21 su questo impianto) si compra a parte.
