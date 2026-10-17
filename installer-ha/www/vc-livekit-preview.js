/* Videocitofono - Anteprima live dell'ingresso (LiveKit), sola ricezione.
 *
 * Card da dashboard: mostra cosa vede la telecamera del citofono FUORI da una
 * chiamata. Non parte da sola, si avvia con un tocco e si spegne da sola.
 *
 * Perche' "a richiesta" e non un flusso sempre attivo
 * ---------------------------------------------------
 * Sul Pi libcamera e' esclusiva: mentre LiveKit pubblica, il rilevamento
 * movimento e il riconoscimento volti locali non possono usare il sensore (e
 * go2rtc/rpicam-vid resta fermo). Un'anteprima permanente significherebbe
 * rinunciare a quelle funzioni 24 ore al giorno. Quindi:
 *
 *   tap "Guarda ora"
 *     -> MQTT videocitofono/cmd {"action":"livekit_preview","on":true,"ttl":N}
 *     -> il Pi libera la camera, entra nella room e pubblica video+audio
 *     -> questa card, con un token SENZA diritto di pubblicare, si iscrive
 *   scadenza / "Chiudi" / uscita dalla pagina
 *     -> {"on":false} e il citofono torna alle sue funzioni
 *
 * Il timeout lato Pi e' la garanzia che la camera venga restituita anche se il
 * browser sparisce senza chiudere nulla (kiosk che si riavvia, tab uccisa).
 *
 * Differenze rispetto a vc-livekit-call
 * -------------------------------------
 * Quella card e' una videochiamata: chiede camera e microfono al browser,
 * pubblica, gestisce squillo, risposta e apertura porta. Questa non pubblica
 * niente (`can_publish: false` nel token) e non ha nulla a che vedere con il
 * ciclo della chiamata: se una chiamata e' in corso non si avvia affatto e
 * rimanda alla scheda della videochiamata, perche' in quel caso il video del
 * visitatore e' gia' nella room e una seconda sessione del Pi con la stessa
 * identita' espellerebbe la prima.
 *
 * Uso in Lovelace:
 *   type: custom:vc-livekit-preview
 *   title: Ingresso dal vivo      # opzionale
 *   ttl: 120                      # opzionale, secondi di anteprima
 *   room: videocitofono           # opzionale
 */

(function () {
  'use strict';

  const VC_PREV_BUILD = 'vc-livekit-preview 2026.08.18-2';
  const SDK_URL = '/local/livekit-client-2.23.0.umd.min.js';
  // Entita' opzionali: token del token-issuer (i comandi MQTT passano
  // da pyscript.videocitofono_mqtt_cmd, senza esporre il secret al browser).
  const LK_TOKEN_ENTITY = 'input_text.videocitofono_lk_token';
  const CALL_ENTITY = 'binary_sensor.stato_chiamata_videocitofono';
  // Quanto attendere il primo fotogramma prima di dire che non arriva: il Pi
  // deve fermare rpicam-vid, riaprire il sensore e negoziare WebRTC.
  const ATTESA_VIDEO_MS = 15000;

  /* --- Filtro ICE ---------------------------------------------------------
   * Sulla LAN due Pi rispondono a 192.168.1.52 e uno risponde anche a
   * 192.168.1.185: se il browser annuncia quegli IP come propri host
   * candidate, il DTLS del server finisce sul Pi sbagliato e il video resta
   * verde. La patch e' la stessa di vc-livekit-call.js (dove e' documentata per
   * esteso) e usa il medesimo flag globale, quindi si applica una volta sola
   * indipendentemente da quale delle due card viene caricata per prima. */
  const VC_BLOCKED_IPS = new Set(['192.168.1.185', '192.168.1.52']);
  function vcCandBlocked(c) {
    if (!c) return false;
    const p = String(c).split(/\s+/);
    return p.length >= 5 && VC_BLOCKED_IPS.has(p[4]);
  }
  if (!window.__vcRtcPatched && typeof window.RTCPeerConnection === 'function') {
    window.__vcRtcPatched = true;
    const PC = window.RTCPeerConnection;
    const origAdd = PC.prototype.addEventListener;
    PC.prototype.addEventListener = function (type, listener, opts) {
      if (type === 'icecandidate' && typeof listener === 'function') {
        return origAdd.call(this, type, function (ev) {
          if (ev && ev.candidate && vcCandBlocked(ev.candidate.candidate)) return;
          return listener.call(this, ev);
        }, opts);
      }
      return origAdd.call(this, type, listener, opts);
    };
    const origSetLocal = PC.prototype.setLocalDescription;
    PC.prototype.setLocalDescription = function (desc) {
      if (desc && desc.sdp) {
        const sdp = desc.sdp.split(/\r?\n/)
          .filter((l) => !l.startsWith('a=candidate:') || !vcCandBlocked(l.slice(2)))
          .join('\r\n');
        if (sdp !== desc.sdp) desc = { type: desc.type, sdp };
      }
      return origSetLocal.call(this, desc);
    };
  }

  /* --- SDK e URL: stessa logica di vc-livekit-call ------------------------
   * Caddy espone /livekit-token e /livekit solo sulla 443, quindi se HA e'
   * aperto su una porta diversa (port-forward diretto al core) la porta va
   * scartata, altrimenti la richiesta finisce sul core che non sa cosa farne. */
  let sdkPromise = null;
  function loadSdk() {
    const w = window;
    if (w.LivekitClient || w.LiveKitClient) {
      return Promise.resolve(w.LivekitClient || w.LiveKitClient);
    }
    if (sdkPromise) return sdkPromise;
    sdkPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = SDK_URL;
      s.async = true;
      s.onload = () => {
        const lk = w.LivekitClient || w.LiveKitClient;
        lk ? resolve(lk) : reject(new Error('SDK livekit-client non esposto'));
      };
      s.onerror = () => reject(new Error('SDK livekit-client non caricato'));
      document.head.appendChild(s);
    });
    return sdkPromise;
  }

  function edgeOrigin() {
    if (location.protocol === 'https:') {
      const std = !location.port || location.port === '443';
      return std ? location.origin : 'https://' + location.hostname;
    }
    return location.origin;
  }
  function defaultTokenUrl() {
    if (location.protocol === 'https:') return edgeOrigin() + '/livekit-token/token';
    return 'http://' + location.hostname + ':8081/token';
  }
  function defaultWsUrl() {
    // Senza `/rtc`: il SDK lo appende da solo.
    if (location.protocol === 'https:') {
      const std = !location.port || location.port === '443';
      return 'wss://' + (std ? location.host : location.hostname) + '/livekit';
    }
    return 'ws://' + location.hostname + ':7880';
  }

  function statoEntita(hass, entity) {
    const st = hass && hass.states ? hass.states[entity] : null;
    if (!st) return '';
    const v = String(st.state || '').trim();
    return (v === 'unknown' || v === 'unavailable') ? '' : v;
  }

  function mmss(ms) {
    const s = Math.max(0, Math.round(ms / 1000));
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  // -------------------------------------------------------------------------

  class VcLivekitPreview extends HTMLElement {
    static getStubConfig() { return { title: 'Ingresso dal vivo', ttl: 120 }; }

    constructor() {
      super();
      this._cfg = {};
      this._hass = null;
      this._room = null;
      this._lk = null;
      // idle | avvio | attesa | live | scaduta | errore | in_chiamata
      this._stato = 'idle';
      this._errore = '';
      this._audioOn = false;
      this._deadline = 0;
      this._tick = null;
      this._attesaTimer = null;
      this._root = this.attachShadow({ mode: 'open' });
      this._renderShell();
    }

    setConfig(cfg) {
      this._cfg = Object.assign({
        title: 'Ingresso dal vivo',
        ttl: 120,
        room: 'videocitofono',
        // Non 'ha' come la card chiamata: quella riconosce gli altri
        // rispondenti dal prefisso dell'identita' e un giorno potrebbe
        // scambiare uno spettatore per qualcuno che ha risposto.
        identity_prefix: 'viewer',
        token_url: defaultTokenUrl(),
        ws_url: defaultWsUrl(),
      }, cfg || {});
      this._ttl = Math.max(15, Math.min(600, parseInt(this._cfg.ttl, 10) || 120));
      // Il contenuto va disegnato qui: `set hass` ridisegna solo quando lo stato
      // cambia, quindi a riposo la card resterebbe un rettangolo vuoto senza il
      // pulsante di avvio.
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      // In chiamata l'anteprima non si puo' avviare: si mostra il rimando alla
      // videochiamata, dove il video del visitatore c'e' gia'.
      const inCall = statoEntita(hass, CALL_ENTITY) === 'on';
      if (inCall && (this._stato === 'idle' || this._stato === 'scaduta')) {
        this._stato = 'in_chiamata';
        this._render();
      } else if (!inCall && this._stato === 'in_chiamata') {
        this._stato = 'idle';
        this._render();
      }
    }

    getCardSize() { return 6; }

    // --- ciclo di vita ----------------------------------------------------

    connectedCallback() {
      // Lovelace puo' spostare la card nel DOM (cambio di colonne, ritorno sulla
      // vista): dopo un `disconnectedCallback` che ha chiuso la sessione serve
      // ridisegnare, altrimenti resta il messaggio dello stato precedente.
      if (this._cfg && !this._root.getElementById('msg')) this._render();
    }

    disconnectedCallback() {
      // La pagina e' stata cambiata o la card rimossa: si chiude tutto, cosi'
      // il citofono non resta a pubblicare per il resto del timeout.
      if (this._stato !== 'idle') this._ferma('uscita dalla pagina');
    }

    // --- comandi al Pi ----------------------------------------------------

    _comando(on) {
      if (!this._hass) return;
      const data = { action: 'livekit_preview', on: !!on };
      if (on) data.ttl = this._ttl;
      try {
        this._hass.callService('pyscript', 'videocitofono_mqtt_cmd', data);
      } catch (e) {
        console.warn('[vc-livekit-preview] comando MQTT fallito:', e);
      }
    }

    async _avvia() {
      if (this._stato === 'avvio' || this._stato === 'attesa'
          || this._stato === 'live') return;
      if (statoEntita(this._hass, CALL_ENTITY) === 'on') {
        this._stato = 'in_chiamata';
        this._render();
        return;
      }
      this._errore = '';
      this._audioOn = false;
      this._stato = 'avvio';
      this._render();

      this._comando(true);

      try {
        const lk = await loadSdk();
        this._lk = lk;
        const token = await this._chiediToken();
        // Nessun publishDefaults: questa card non pubblica nulla.
        const room = new lk.Room({ adaptiveStream: true, dynacast: false });
        this._room = room;
        room
          .on(lk.RoomEvent.TrackSubscribed, (track) => this._attacca(track))
          .on(lk.RoomEvent.TrackUnsubscribed, (track) => {
            try { track.detach().forEach((el) => el.remove()); } catch (_) {}
            // Il Pi ha smesso di pubblicare mentre guardavamo: succede se
            // suona il campanello (la chiamata ha la precedenza sulla camera)
            // o se il timeout e' scaduto lato Pi prima che scadesse qui. In
            // entrambi i casi la card non deve restare a mostrare "in diretta"
            // su un fotogramma congelato; `set hass` la portera' poi su
            // "chiamata in corso" se e' quello il motivo.
            if (track.kind === 'video' && this._stato === 'live') {
              this._chiudiSessione();
              this._stato = 'scaduta';
              this._render();
            }
          })
          .on(lk.RoomEvent.Disconnected, () => {
            if (this._stato === 'live' || this._stato === 'attesa') {
              this._stato = 'scaduta';
              this._render();
            }
          });
        await room.connect(this._cfg.ws_url, token);
        for (const p of room.remoteParticipants.values()) {
          for (const pub of p.trackPublications.values()) {
            if (pub.track) this._attacca(pub.track);
          }
        }
        if (this._stato === 'avvio') {
          this._stato = 'attesa';
          this._render();
        }
        // Se il Pi non arriva, non lasciare la card in attesa perenne: il caso
        // tipico e' la camera occupata da un'altra funzione locale.
        this._attesaTimer = setTimeout(() => {
          if (this._stato === 'attesa') {
            this._errore = 'Il citofono non ha inviato immagini. '
              + 'Puo' + '\u2019' + ' essere occupato dal riconoscimento del volto '
              + 'o da una chiamata appena conclusa: riprova tra qualche secondo.';
            this._stato = 'errore';
            this._render();
            this._chiudiSessione();
            this._comando(false);
          }
        }, ATTESA_VIDEO_MS);
      } catch (e) {
        console.warn('[vc-livekit-preview] avvio fallito:', e);
        this._errore = String((e && e.message) || e).slice(0, 200);
        this._stato = 'errore';
        this._render();
        this._chiudiSessione();
        this._comando(false);
      }
    }

    async _chiediToken() {
      const headers = { 'Content-Type': 'application/json' };
      const secret = statoEntita(this._hass, LK_TOKEN_ENTITY);
      if (secret) headers['X-VC-Token'] = secret;
      const identita = (this._cfg.identity_prefix || 'ha') + '-view-'
        + Math.random().toString(36).slice(2, 8);
      const r = await fetch(this._cfg.token_url, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          identity: identita,
          name: identita,
          room: this._cfg.room,
          ttl_seconds: 3600,
          // Il punto della card: guardare senza poter pubblicare. Cosi' il Pi
          // non riceve tracce da riprodurre sull'altoparlante dell'ingresso.
          can_publish: false,
          can_subscribe: true,
          prefer_lan: false,
        }),
      });
      if (!r.ok) {
        throw new Error('token issuer HTTP ' + r.status + ': '
          + (await r.text()).slice(0, 160));
      }
      const j = await r.json();
      if (!j.token) throw new Error('token issuer: risposta senza token');
      return j.token;
    }

    _attacca(track) {
      const box = this._root.getElementById('video');
      if (!box) return;
      if (track.kind === 'video') {
        const el = track.attach();
        el.setAttribute('playsinline', '');
        el.setAttribute('autoplay', '');
        el.id = 'v-live';
        const prec = this._root.getElementById('v-live');
        if (prec) prec.remove();
        box.appendChild(el);
        el.play().catch(() => {});
        if (this._attesaTimer) {
          clearTimeout(this._attesaTimer);
          this._attesaTimer = null;
        }
        this._stato = 'live';
        this._deadline = Date.now() + this._ttl * 1000;
        this._avviaConto();
        this._render();
      } else if (track.kind === 'audio') {
        const el = track.attach();
        el.id = 'a-live';
        el.setAttribute('autoplay', '');
        // Muto all'apertura: l'ascolto dell'ingresso si attiva con un tocco.
        el.muted = !this._audioOn;
        el.volume = this._audioOn ? 1 : 0;
        const prec = this._root.getElementById('a-live');
        if (prec) prec.remove();
        box.appendChild(el);
      }
    }

    _avviaConto() {
      if (this._tick) clearInterval(this._tick);
      this._tick = setInterval(() => {
        const resto = this._deadline - Date.now();
        if (resto <= 0) {
          // Il Pi si ferma da solo allo scadere: qui si allinea la card.
          this._stato = 'scaduta';
          this._chiudiSessione();
          this._render();
          return;
        }
        const el = this._root.getElementById('conto');
        if (el) el.textContent = mmss(resto);
      }, 1000);
    }

    _prolunga() {
      this._comando(true);
      this._deadline = Date.now() + this._ttl * 1000;
      this._render();
    }

    _toggleAudio() {
      this._audioOn = !this._audioOn;
      const a = this._root.getElementById('a-live');
      if (a) {
        a.muted = !this._audioOn;
        a.volume = this._audioOn ? 1 : 0;
        if (this._audioOn) a.play().catch(() => {});
      }
      this._render();
    }

    _chiudiSessione() {
      if (this._tick) { clearInterval(this._tick); this._tick = null; }
      if (this._attesaTimer) { clearTimeout(this._attesaTimer); this._attesaTimer = null; }
      const room = this._room;
      this._room = null;
      if (room) { try { room.disconnect(); } catch (_) {} }
      const v = this._root.getElementById('v-live');
      if (v) v.remove();
      const a = this._root.getElementById('a-live');
      if (a) a.remove();
    }

    _ferma(motivo) {
      this._chiudiSessione();
      this._comando(false);
      this._stato = 'idle';
      this._render();
      if (motivo) console.log('[vc-livekit-preview] chiusa:', motivo);
    }

    // --- interfaccia ------------------------------------------------------

    _renderShell() {
      this._root.innerHTML = `
<style>
  ha-card { overflow: hidden; }
  .hdr {
    display: flex; align-items: center; gap: 8px;
    padding: 12px 16px 8px;
  }
  .tit {
    flex: 1; font-size: 1rem; font-weight: 600;
    color: var(--primary-text-color);
  }
  .stato {
    font-size: 0.72rem; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; color: var(--secondary-text-color);
  }
  .stato.live { color: #e53935; }
  .box {
    position: relative; width: 100%; aspect-ratio: 4 / 3;
    background: #10141a; display: flex;
    align-items: center; justify-content: center;
  }
  .box video { width: 100%; height: 100%; object-fit: contain; display: block; }
  .msg {
    position: absolute; inset: 0; display: flex; gap: 10px;
    flex-direction: column; align-items: center; justify-content: center;
    padding: 18px; box-sizing: border-box; text-align: center;
    color: rgba(255,255,255,.86); font-size: 0.86rem; line-height: 1.45;
  }
  .msg ha-icon { --mdc-icon-size: 34px; opacity: .75; }
  .avvia {
    display: inline-flex; align-items: center; gap: 8px;
    border: none; border-radius: 999px; cursor: pointer;
    padding: 11px 20px; font: inherit; font-weight: 600; font-size: 0.9rem;
    background: #2f7d4f; color: #fff;
  }
  .avvia:hover { background: #276a43; }
  .avvia.grigio { background: rgba(255,255,255,.16); }
  .barra {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 12px;
  }
  .conto {
    font-variant-numeric: tabular-nums; font-size: 0.85rem; font-weight: 600;
    color: var(--secondary-text-color); margin-right: auto; padding-left: 4px;
  }
  .tondo {
    width: 40px; height: 40px; border-radius: 50%; border: none;
    cursor: pointer; display: inline-flex;
    align-items: center; justify-content: center;
    background: var(--secondary-background-color, rgba(0,0,0,.06));
    color: var(--primary-text-color); --mdc-icon-size: 20px;
  }
  .tondo.on { background: #2f7d4f; color: #fff; }
  .tondo.stop { background: #c62828; color: #fff; }
  .tondo:hover { filter: brightness(.94); }
  .nota {
    padding: 0 16px 12px; font-size: 0.74rem; line-height: 1.4;
    color: var(--secondary-text-color);
  }
  .vai {
    color: var(--primary-color); font-weight: 600;
    text-decoration: none; cursor: pointer;
  }
</style>
<ha-card>
  <div class="hdr">
    <div class="tit" id="tit"></div>
    <div class="stato" id="badge"></div>
  </div>
  <div class="box" id="video"></div>
  <div id="sotto"></div>
</ha-card>`;
      this._root.getElementById('video').addEventListener('click', (e) => {
        const b = e.target.closest && e.target.closest('button[data-act]');
        if (b) this._azione(b.dataset.act);
      });
      this._root.getElementById('sotto').addEventListener('click', (e) => {
        const b = e.target.closest && e.target.closest('[data-act]');
        if (b) this._azione(b.dataset.act);
      });
    }

    _azione(act) {
      if (act === 'avvia') this._avvia();
      else if (act === 'ferma') this._ferma('richiesta utente');
      else if (act === 'audio') this._toggleAudio();
      else if (act === 'prolunga') this._prolunga();
      else if (act === 'chiamata') {
        history.pushState(null, '', '/lovelace/conversazione');
        window.dispatchEvent(new CustomEvent('location-changed'));
      }
    }

    _render() {
      const tit = this._root.getElementById('tit');
      const badge = this._root.getElementById('badge');
      const box = this._root.getElementById('video');
      const sotto = this._root.getElementById('sotto');
      if (!tit) return;
      tit.textContent = this._cfg.title || 'Ingresso dal vivo';

      const etichette = {
        idle: '', avvio: 'avvio…', attesa: 'in attesa',
        live: 'in diretta', scaduta: 'terminata', errore: 'errore',
        in_chiamata: 'chiamata in corso',
      };
      badge.textContent = etichette[this._stato] || '';
      badge.className = 'stato' + (this._stato === 'live' ? ' live' : '');

      // Il video resta appeso al box: si sostituisce solo il messaggio sopra.
      const vecchio = this._root.getElementById('msg');
      if (vecchio) vecchio.remove();
      const msg = (html) => {
        const d = document.createElement('div');
        d.className = 'msg';
        d.id = 'msg';
        d.innerHTML = html;
        box.appendChild(d);
      };

      if (this._stato === 'idle') {
        msg(`<ha-icon icon="mdi:cctv"></ha-icon>
             <div>Guarda cosa vede il citofono in questo momento.</div>
             <button class="avvia" data-act="avvia">
               <ha-icon icon="mdi:play"></ha-icon>Guarda ora
             </button>`);
      } else if (this._stato === 'avvio' || this._stato === 'attesa') {
        msg(`<ha-icon icon="mdi:video-wireless-outline"></ha-icon>
             <div>Sto accendendo la telecamera dell${'\u2019'}ingresso…</div>`);
      } else if (this._stato === 'scaduta') {
        msg(`<ha-icon icon="mdi:timer-off-outline"></ha-icon>
             <div>Anteprima terminata. La telecamera è tornata alle sue
             funzioni.</div>
             <button class="avvia" data-act="avvia">
               <ha-icon icon="mdi:replay"></ha-icon>Guarda ancora
             </button>`);
      } else if (this._stato === 'errore') {
        msg(`<ha-icon icon="mdi:alert-circle-outline"></ha-icon>
             <div>${this._errore || 'Anteprima non disponibile.'}</div>
             <button class="avvia grigio" data-act="avvia">
               <ha-icon icon="mdi:replay"></ha-icon>Riprova
             </button>`);
      } else if (this._stato === 'in_chiamata') {
        msg(`<ha-icon icon="mdi:phone-in-talk"></ha-icon>
             <div>C${'\u2019'}è una chiamata in corso: le immagini sono nella
             videochiamata.</div>
             <button class="avvia" data-act="chiamata">
               <ha-icon icon="mdi:video"></ha-icon>Apri la videochiamata
             </button>`);
      }

      if (this._stato === 'live') {
        const resto = mmss(Math.max(0, this._deadline - Date.now()));
        sotto.innerHTML = `
<div class="barra">
  <span class="conto" id="conto">${resto}</span>
  <button class="tondo ${this._audioOn ? 'on' : ''}" data-act="audio"
          title="${this._audioOn ? 'Disattiva l\u2019ascolto' : 'Ascolta l\u2019ingresso'}">
    <ha-icon icon="${this._audioOn ? 'mdi:volume-high' : 'mdi:volume-off'}"></ha-icon>
  </button>
  <button class="tondo" data-act="prolunga" title="Aggiungi tempo">
    <ha-icon icon="mdi:timer-plus-outline"></ha-icon>
  </button>
  <button class="tondo stop" data-act="ferma" title="Chiudi l\u2019anteprima">
    <ha-icon icon="mdi:stop"></ha-icon>
  </button>
</div>`;
      } else if (this._stato === 'idle' || this._stato === 'scaduta') {
        sotto.innerHTML = `<div class="nota">Mentre l${'\u2019'}anteprima è attiva
          il citofono non usa la telecamera per il rilevamento del movimento e
          per il riconoscimento dei volti. Si spegne da sola dopo
          ${Math.round(this._ttl / 60) >= 1
            ? Math.round(this._ttl / 60) + ' minuti'
            : this._ttl + ' secondi'}.</div>`;
      } else {
        sotto.innerHTML = '';
      }
    }
  }

  if (!customElements.get('vc-livekit-preview')) {
    customElements.define('vc-livekit-preview', VcLivekitPreview);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: 'vc-livekit-preview',
      name: 'Videocitofono - Anteprima live',
      description: 'Immagini dal vivo della telecamera del citofono, a richiesta',
    });
    console.info(`%c ${VC_PREV_BUILD} `, 'background:#2f7d4f;color:#fff');
  }
})();
