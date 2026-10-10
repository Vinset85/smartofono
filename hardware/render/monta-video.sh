#!/bin/bash
# Monta i fotogrammi dei render in due brevi filmati, uno per l'installazione e
# uno per il funzionamento di giorno e di notte. Ogni fotogramma sta in campo tre
# secondi con una lenta carrellata di zoom, e passa al successivo in dissolvenza.
#
# Questo ffmpeg e' compilato senza libfreetype, quindi il filtro drawtext non
# c'e' e i filmati non possono portare didascalie sovrimpresse: i titoli delle
# fasi stanno nel README accanto alle immagini.
set -euo pipefail
cd "$(dirname "$0")"

DURATA=3.0        # secondi in campo per ogni fotogramma
DISSOLVENZA=0.8   # durata della dissolvenza fra due fotogrammi
FPS=30

# monta <uscita> <larghezza> <altezza> <fotogramma>...
monta() {
    local uscita=$1 w=$2 h=$3; shift 3
    local frame=("$@")
    local n=${#frame[@]}
    local durata_frame=$(echo "$DURATA * $FPS" | bc)
    local passo=$(echo "$DURATA - $DISSOLVENZA" | bc)

    local ingressi=() filtri=() i
    for ((i = 0; i < n; i++)); do
        # Niente -loop qui: zoompan espande da se' il fotogramma in d immagini,
        # e se gliene si danno 90 in ingresso ne produce 90 per ciascuna.
        ingressi+=(-i "${frame[i]}")
        # Lo zoom alterna avvicinamento e allontanamento, altrimenti la
        # sequenza respira sempre nello stesso verso e si nota il trucco.
        local z
        if ((i % 2 == 0)); then
            z="z='1+0.06*on/$durata_frame'"
        else
            z="z='1.06-0.06*on/$durata_frame'"
        fi
        # L'ingrandimento a monte di zoompan evita che il filtro lavori sui
        # pixel originali e sgrani l'immagine mentre stringe.
        filtri+=("[$i:v]scale=$((w * 2)):$((h * 2)):flags=lanczos,setsar=1,\
zoompan=$z:d=$durata_frame:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':\
s=${w}x${h}:fps=$FPS,trim=duration=$DURATA,format=yuv420p[v$i]")
    done

    local catena="[v0]" offset
    for ((i = 1; i < n; i++)); do
        offset=$(echo "$passo * $i" | bc)
        if ((i == n - 1)); then
            filtri+=("${catena}[v$i]xfade=transition=fade:\
duration=$DISSOLVENZA:offset=$offset[out]")
        else
            filtri+=("${catena}[v$i]xfade=transition=fade:\
duration=$DISSOLVENZA:offset=$offset[x$i]")
            catena="[x$i]"
        fi
    done

    local fc
    fc=$(IFS=';'; echo "${filtri[*]}")
    ffmpeg -y -hide_banner -loglevel error "${ingressi[@]}" \
        -filter_complex "$fc" -map '[out]' \
        -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
        -movflags +faststart "$uscita"
    echo "  $uscita  $(du -h "$uscita" | cut -f1)"
}

echo "monto i filmati:"
monta installazione.mp4 1440 1080 \
    inst-1-nicchia.jpg inst-2-cassa.jpg inst-3-telaio.jpg \
    inst-4-vetro.jpg inst-5-finito.jpg

monta giorno-notte.mp4 1080 1920 \
    func-1-giorno-riposo.jpg func-2-giorno-chiamata.jpg \
    func-3-notte-piena.jpg func-4-notte-attenuata.jpg func-5-notte-volto.jpg

# Dallo stesso montaggio ricavo una GIF ridotta per ciascun filmato: serve solo
# per l'anteprima dove un mp4 non si puo' riprodurre, la qualita' sta nell'mp4.
echo "ricavo le anteprime animate:"
for v in installazione giorno-notte; do
    ffmpeg -y -hide_banner -loglevel error -i "$v.mp4" \
        -vf "fps=10,scale=360:-1:flags=lanczos,split[a][b];\
[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" \
        "$v.gif"
    echo "  $v.gif  $(du -h "$v.gif" | cut -f1)"
done
