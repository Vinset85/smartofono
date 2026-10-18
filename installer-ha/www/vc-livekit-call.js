/* Videocitofono - LiveKit call card per Home Assistant Lovelace.
 *
 * Custom card che renderizza una "videochiamata" piena tra il browser HA
 * (rispondente: tablet di casa o telefono via Companion app) e l'unita'
 * esterna RPi (visitatore al citofono).
 *
 * Architettura:
 *   browser HA  ──publish cam+mic──▶  LiveKit room "videocitofono"
 *                                           │
 *                ──subscribe video──◀───────┤
 *                                           │
 *                          RPi  ──publish camera+mic──┘
 *
 *   Caddy edge davanti: same-origin HTTPS, niente mixed-content, niente CORS.
 *   Token JWT firmato dal token-issuer (FastAPI) via /livekit-token/token.
 *   Signaling LiveKit via /livekit/rtc.
 *
 * Uso in dashboard (vista "Conversazione" fullscreen):
 *
 *   type: custom:vc-livekit-call
 *   audio_only: false               # opzionale, default false
 *   room: videocitofono             # opzionale
 *   identity_prefix: ha             # opzionale
 *   open_door_script: script.videocitofono_apri_porta   # opzionale
 *   hangup_script: script.videocitofono_chiudi          # opzionale
 *
 * Lifecycle:
 *   - connectedCallback (la view e' aperta): preflight secure context →
 *     getUserMedia → fetch token → connect Room → publish cam+mic.
 *   - disconnectedCallback (la view e' chiusa o navigata via): room.disconnect
 *     + stop di tutte le track del MediaStream locale.
 *
 * Diversamente dal vecchio approccio popup browser_mod + custom:webrtc-camera:
 *   - niente IntersectionObserver hack (la card vive in una view normale,
 *     non in un dialog modal: nessuna shadow-overlay che nasconde l'elemento)
 *   - niente vc-kick: il subscribe LiveKit e' nativo, non serve forzare
 *     reconnect manuale
 *   - niente warmup pre-emptivo: il pubblisher si avvia in <800ms (LK SDK
 *     ottimizzato), e l'audio comunque non parla finche' non c'e' un
 *     subscriber.
 */

(function () {
  'use strict';

  // ---- ICE candidate IP blacklist ----------------------------------------
  // Sulla LAN dell'utente esiste un conflitto di IP: il Pi videocitofono
  // (MAC 2c:cf:67:ec:93:a0) risponde a 192.168.1.185 (wlan0) E a
  // 192.168.1.52 (eth0). Un secondo Pi (MAC ...:a1) risponde anche a
  // 192.168.1.52. Quando il browser del tablet (che ha un'interfaccia
  // virtuale, hotspot mobile o cache stale) annuncia 192.168.1.185 o
  // 192.168.1.52 come ICE host candidate suo, il LiveKit server invia
  // DTLS verso quegli IP -> ARP risolve sul MAC del Pi -> i pacchetti
  // finiscono al Pi che non ha la sessione DTLS -> handshake timeout
  // -> schermo verde lato tablet (ICE connesso ma media mai decodificato).
  //
  // Mitigazione: filtriamo questi IP dalle candidate sia outgoing
  // (onicecandidate trickle) sia inline nelle SDP locali. Cosi' il
  // server vede solo candidate validi per il client e DTLS handshake
  // raggiunge il tablet vero.
  const VC_BLOCKED_IPS = new Set(['192.168.1.185', '192.168.1.52']);
  const mdi = (name) => `<ha-icon icon="${name}"></ha-icon>`;
  function vcCandidateBlocked(candStr) {
    if (!candStr) return false;
    // candidate string format: "candidate:foundation 1 udp prio IP port typ host ..."
    const parts = String(candStr).split(/\s+/);
    if (parts.length < 5) return false;
    const ip = parts[4];
    return VC_BLOCKED_IPS.has(ip);
  }
  function vcStripBlockedFromSdp(sdp) {
    if (!sdp) return sdp;
    return sdp
      .split(/\r?\n/)
      .filter((line) => {
        if (!line.startsWith('a=candidate:')) return true;
        return !vcCandidateBlocked(line.slice(2));
      })
      .join('\r\n');
  }
  if (!window.__vcRtcPatched && typeof window.RTCPeerConnection === 'function') {
    window.__vcRtcPatched = true;
    const OrigPC = window.RTCPeerConnection;
    const origAdd = OrigPC.prototype.addEventListener;
    OrigPC.prototype.addEventListener = function (type, listener, opts) {
      if (type === 'icecandidate' && typeof listener === 'function') {
        const wrapped = function (ev) {
          if (ev && ev.candidate && vcCandidateBlocked(ev.candidate.candidate)) {
            console.log('[vc-livekit-call] block local candidate:', ev.candidate.candidate);
            return;
          }
          return listener.call(this, ev);
        };
        return origAdd.call(this, type, wrapped, opts);
      }
      return origAdd.call(this, type, listener, opts);
    };
    const oicDesc = Object.getOwnPropertyDescriptor(OrigPC.prototype, 'onicecandidate');
    if (oicDesc && oicDesc.set) {
      Object.defineProperty(OrigPC.prototype, 'onicecandidate', {
        configurable: true,
        get: oicDesc.get,
        set: function (fn) {
          if (typeof fn !== 'function') return oicDesc.set.call(this, fn);
          const wrapped = function (ev) {
            if (ev && ev.candidate && vcCandidateBlocked(ev.candidate.candidate)) {
              console.log('[vc-livekit-call] block local candidate (oic):', ev.candidate.candidate);
              return;
            }
            return fn.call(this, ev);
          };
          return oicDesc.set.call(this, wrapped);
        },
      });
    }
    const origSetLocal = OrigPC.prototype.setLocalDescription;
    OrigPC.prototype.setLocalDescription = function (desc) {
      if (desc && desc.sdp) {
        const stripped = vcStripBlockedFromSdp(desc.sdp);
        if (stripped !== desc.sdp) {
          desc = { type: desc.type, sdp: stripped };
        }
      }
      return origSetLocal.call(this, desc);
    };
    console.log('[vc-livekit-call] RTCPeerConnection ICE filter installed:', Array.from(VC_BLOCKED_IPS));
  }
  // -------------------------------------------------------------------------

  // SDK self-hosted in /config/www/ (HA /local/): niente dipendenza da
  // internet/CDN per far partire le videochiamate (critico per un
  // citofono). Aggiornato a livekit-client 2.23.0 (nessun breaking change)
  // dal 2.5.10, solo fix riconnessione/ICE/memory-leak Room).
  const SDK_URL = '/local/livekit-client-2.23.0.umd.min.js';

  let sdkLoadPromise = null;
  function loadSdk() {
    const win = window;
    if (win.LivekitClient || win.LiveKitClient) {
      return Promise.resolve(win.LivekitClient || win.LiveKitClient);
    }
    if (sdkLoadPromise) return sdkLoadPromise;
    sdkLoadPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = SDK_URL;
      s.async = true;
      s.onload = () => {
        const lk = win.LivekitClient || win.LiveKitClient;
        if (!lk) return reject(new Error('SDK livekit-client non esposto su window'));
        resolve(lk);
      };
      s.onerror = () => reject(new Error('SDK livekit-client load error'));
      document.head.appendChild(s);
    });
    return sdkLoadPromise;
  }

  // Caddy edge espone /livekit-token/* e /livekit/* SOLO sulla porta
  // standard 443 (HTTPS). Se il tablet apre HA su una porta diversa
  // (es. Fully Kiosk con URL https://duckdns:8191 che e' un port-forward
  // diretto al core HA :8123), `location.origin` include quella porta
  // -> /livekit-token/token finisce sul core HA che non sa cosa farsene
  // -> 404 "Not found". Soluzione: se la porta corrente non e' quella
  // standard del protocollo, dropparla cosi' la fetch va al Caddy edge.
  function edgeOrigin() {
    if (location.protocol === 'https:') {
      const std = !location.port || location.port === '443';
      return std ? location.origin : ('https://' + location.hostname);
    }
    return location.origin;
  }
  function defaultTokenUrl() {
    if (location.protocol === 'https:') return edgeOrigin() + '/livekit-token/token';
    return 'http://' + location.hostname + ':8081/token';
  }

  // ---- LAN detection ------------------------------------------------------
  // Chiede a Caddy di rivelarci l'IP da cui ci vede. Se l'IP appartiene
  // alle tre RFC1918 (10/8, 172.16/12, 192.168/16) o e' loopback, siamo in
  // LAN: Caddy e il client sono sulla stessa rete privata e il NAT del
  // router non ha SNAT-tato la sorgente. Cached per la sessione perche' il
  // risultato non cambia mid-call.
  let _lanCache = null;
  function detectLan() {
    if (_lanCache !== null) return Promise.resolve(_lanCache);
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const url = (location.protocol === 'https:' ? edgeOrigin() : 'http://' + location.hostname) + '/lan-check';
    return fetch(url, { signal: ctrl.signal, cache: 'no-store' })
      .then((r) => r.ok ? r.text() : '')
      .then((ip) => {
        clearTimeout(t);
        const v = (ip || '').trim();
        const isPriv = /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.|::1$)/.test(v);
        _lanCache = isPriv;
        return isPriv;
      })
      .catch(() => {
        clearTimeout(t);
        _lanCache = false;
        return false;
      });
  }
  function defaultWsUrl() {
    // NB: senza `/rtc` finale. Il SDK livekit-client 2.x appende `/rtc` da
    // solo a wsUrl (`${host}/rtc?access_token=...`). Se mettessimo qui
    // `/livekit/rtc`, il client farebbe `wss://h/livekit/rtc/rtc?...` e
    // il server risponderebbe 404 ("could not establish signal
    // connection: 404 page not found"). Caddy `handle_path /livekit/*`
    // strippa /livekit, quindi /livekit/rtc -> upstream /rtc (signaling
    // endpoint corretto di livekit-server).
    // Stesso trattamento porta non-standard di edgeOrigin(): il signaling
    // LiveKit e' esposto solo dal Caddy edge :443. Se l'utente apre HA su
    // :8191/altra-porta, dobbiamo comunque connettere il websocket al
    // Caddy 443 (location.host SENZA porta).
    if (location.protocol === 'https:') {
      const std = !location.port || location.port === '443';
      const host = std ? location.host : location.hostname;
      return 'wss://' + host + '/livekit';
    }
    return 'ws://' + location.hostname + ':7880';
  }

  function generateIdentity(prefix) {
    const key = 'vc-lk-identity-' + (prefix || 'ha');
    let id = sessionStorage.getItem(key);
    if (!id) {
      id = (prefix || 'ha') + '-' + Math.random().toString(36).slice(2, 10);
      sessionStorage.setItem(key, id);
    }
    return id;
  }

  // ---------------------------------------------------------------------------

  class VcLivekitCall extends HTMLElement {
    constructor() {
      super();
      this._cfg = {};
      this._hass = null;
      this._room = null;
      this._localStream = null;
      this._identity = null;
      this._lk = null;
      this._status = 'init';
      this._error = null;
      this._micEnabled = true;
      this._camEnabled = true;
      this._remoteAttached = false;
      this._intentionalClose = false;
      this._retryAttempt = 0;
      this._retryTimer = null;
      // Flusso "ring -> answer": all'apertura della view la card si
      // collega alla Room, sottoscrive i track del Pi e mostra il video
      // del visitatore SENZA audio e senza pubblicare nulla. Solo dopo
      // tap su "Rispondi" il browser HA fa getUserMedia, pubblica
      // cam+mic e sblocca l'audio remoto.
      this._answered = false;
      this._answering = false;
      this._answerMode = null;
      this._dismissed = false;
      this._lastRawStatus = undefined;
      this._renderRoot = this.attachShadow({ mode: 'open' });
      this._render();
    }

    setConfig(cfg) {
      this._cfg = Object.assign(
        {
          room: 'videocitofono',
          identity_prefix: 'ha',
          audio_only: false,
          token_url: defaultTokenUrl(),
          ws_url: defaultWsUrl(),
          open_door_script: 'script.videocitofono_apri_porta',
          hangup_script: 'script.videocitofono_chiudi',
        },
        cfg || {}
      );
      this._micEnabled = true;
      this._camEnabled = !this._cfg.audio_only;
    }

    set hass(hass) {
      this._hass = hass;
      // Dismiss deterministico via stato HA: indipendente dalla room
      // LiveKit (funziona anche sui dispositivi che mostrano la maschera
      // ma non si sono connessi al WebRTC). Quando lo stato chiamata passa
      // a 'risposto*' e NON e' questo dispositivo ad aver risposto, esci.
      try { this._checkAnsweredViaState(hass); } catch (_) {}
    }

    _checkAnsweredViaState(hass) {
      if (!hass || !hass.states) return;
      // Build-report one-shot al primo hass (indipendente da LiveKit):
      // serve a sapere quale versione della card gira su OGNI dispositivo
      // che mostra la maschera, anche se non si connette alla room.
      if (!this._buildReported) {
        this._buildReported = true;
        try {
          hass.callService('mqtt', 'publish', {
            topic: 'videocitofono/ha_card_build',
            payload: VC_BUILD + ' hass id=' + (this._identity || 'pre'),
            qos: 0, retain: false,
          });
        } catch (_) {}
      }
      const st = hass.states['sensor.videocitofono_stato_chiamata_raw'];
      const cur = st ? st.state : null;
      const prev = this._lastRawStatus;
      this._lastRawStatus = cur;
      if (this._answered || this._answering || this._dismissed) return;
      // Primo campione = baseline: non scattare su valore gia' presente
      // all'apertura (es. 'risposto_*' residuo di una chiamata precedente).
      if (prev === undefined) return;
      if (!cur || cur === 'unknown' || cur === 'unavailable') return;
      const isRisposto = cur.indexOf('risposto') === 0;
      const prevRisposto = (typeof prev === 'string') && prev.indexOf('risposto') === 0;
      // Solo sulla TRANSIZIONE fresca a 'risposto*'.
      if (isRisposto && !prevRisposto) {
        this._answeredElsewhere('state:' + cur);
      }
    }

    getCardSize() { return 8; }

    // --- lifecycle Lovelace -------------------------------------------------

    connectedCallback() {
      // Lovelace puo' riciclare la stessa istanza del custom element quando
      // l'utente naviga via dalla view "Conversazione" e poi torna (seconda
      // chiamata consecutiva). In quel caso disconnectedCallback() ha gia'
      // chiuso room+stream, e dobbiamo ripartire da zero. Quindi NON usare
      // un flag "_connectStarted" che blocca il re-connect: meglio
      // proteggere il re-entry con _connectInFlight basato sul fatto che
      // _room sia gia' presente o no.
      if (this._room || this._connectInFlight) return;
      this._connectInFlight = true;
      this._intentionalClose = false;
      this._retryAttempt = 0;
      this._connect()
        .catch((e) => this._fail(e))
        .finally(() => { this._connectInFlight = false; });
    }

    disconnectedCallback() {
      this._intentionalClose = true;
      if (this._retryTimer) { clearTimeout(this._retryTimer); this._retryTimer = null; }
      this._teardown().catch(() => {});
    }

    _scheduleRetry(reason) {
      if (this._intentionalClose) return;
      if (this._retryTimer) return;
      this._retryAttempt += 1;
      const max = 20;
      if (this._retryAttempt > max) {
        this._status = 'disconnected';
        this._error = 'connessione persa: troppi tentativi';
        this._render();
        return;
      }
      const delay = Math.min(15000, 1000 * Math.pow(1.5, this._retryAttempt - 1));
      this._status = 'reconnecting';
      this._render();
      this._retryTimer = setTimeout(async () => {
        this._retryTimer = null;
        try {
          const room = this._room;
          this._room = null;
          if (room) { try { await room.disconnect(true); } catch (_) {} }
        } catch (_) {}
        this._connect().catch((e) => this._fail(e));
      }, delay);
    }

    // --- connection logic ---------------------------------------------------

    async _connect() {
      try {
        if (this._localStream) {
          this._localStream.getTracks().forEach((t) => { try { t.stop(); } catch (_) {} });
        }
      } catch (_) {}
      this._localStream = null;
      this._remoteAttached = false;
      this._error = null;
      this._answered = false;
      this._answering = false;
      this._answerMode = null;
      this._dismissed = false;
      this._lastRawStatus = undefined;
      this._status = 'preflight';
      this._render();
      if (!window.isSecureContext) {
        throw new Error(
          'HA non e\' aperto in HTTPS. La videochiamata richiede contesto sicuro. ' +
          'Apri https://' + location.hostname + ' invece di http://...'
        );
      }
      // NB: getUserMedia spostato in _answer(). Durante il "ringing"
      // non serve permesso camera/mic; cosi' anche browser/kiosk con
      // permessi mancanti vedono almeno il video del visitatore.

      this._status = 'token';
      this._render();
      this._lk = await loadSdk();
      this._identity = generateIdentity(this._cfg.identity_prefix);

      const tkHdr = { 'Content-Type': 'application/json' };
      const lkSecret = this._hass && this._hass.states['input_text.videocitofono_lk_token']
        ? String(this._hass.states['input_text.videocitofono_lk_token'].state || '').trim()
        : '';
      if (lkSecret && lkSecret !== 'unavailable' && lkSecret !== 'unknown') {
        tkHdr['X-VC-Token'] = lkSecret;
      }

      const tkResp = await fetch(this._cfg.token_url, {
        method: 'POST',
        headers: tkHdr,
        body: JSON.stringify({
          identity: this._identity,
          name: this._identity,
          room: this._cfg.room,
          ttl_seconds: 7200,
          can_publish: true,
          can_subscribe: true,
          prefer_lan: false,
        }),
      });
      if (!tkResp.ok) {
        const txt = await tkResp.text();
        throw new Error('token issuer HTTP ' + tkResp.status + ': ' + txt.slice(0, 200));
      }
      const tk = await tkResp.json();
      if (!tk.token) throw new Error('token issuer payload invalido');

      this._status = 'connect';
      this._render();
      const lk = this._lk;

      // LAN detection: se Caddy ci vede da un IP privato (split-DNS o accesso
      // diretto via IP LAN), siamo in LAN -> rtcConfig.iceServers vuoti =
      // niente STUN/srflx, ICE risolve solo su host candidates.
      // Vantaggi: ICE setup ~300ms piu' rapido, niente request DNS verso
      // stun.l.google.com, niente candidate srflx pubblici da hairpin.
      const isLan = await detectLan();
      const rtcConfig = isLan
        ? { iceServers: [], iceTransportPolicy: 'all' }
        : undefined;
      console.log('[vc-livekit-call] mode:', isLan ? 'LAN (no STUN)' : 'WAN (STUN+TURN)');

      // simulcast=false + dynacast=false: il SDK Python livekit-rtc 1.1.5
      // non espone API per scegliere quality/dimensions sul subscriber,
      // quindi il server gli inoltra il layer piu' alto. Single-layer
      // 640x480@15fps sta sotto 600kbps, decode <30% CPU su Pi5.
      //
      // videoCodec=vp8: il SDK Python 1.1.5 supporta H264 nei simboli
      // libwebrtc, ma quando il browser pubblica H264 con backupCodec
      // abilitato (default LiveKit per H264/AV1/VP9) il server segna
      // il track con codecs=[H264, vp8] e il subscriber Python non
      // riceve frame (probabile bug di selezione codec nel binding
      // FFI, recv=0 fps in 10s). Restiamo su VP8 single-layer: con
      // simulcast=false la decode VP8 sul Pi5 sta sotto 30% CPU e
      // non causa il freeze visto in 720p+simulcast.
      // Il publisher Pi resta su H264 (Chrome decoda in HW).
      const room = new lk.Room({
        adaptiveStream: true,
        dynacast: false,
        rtcConfig,
        publishDefaults: {
          simulcast: false,
          videoCodec: 'vp8',
          backupCodec: false,
          videoEncoding: { maxBitrate: 600_000, maxFramerate: 15 },
          audioPreset: { maxBitrate: 32_000 },
        },
      });
      this._room = room;

      room
        .on(lk.RoomEvent.ConnectionStateChanged, (s) => {
          this._status = 'state:' + s;
          this._render();
        })
        .on(lk.RoomEvent.Disconnected, (reason) => {
          this._status = 'disconnected';
          this._render();
          this._scheduleRetry(reason);
        })
        .on(lk.RoomEvent.ParticipantConnected, (p) => {
          // niente da fare: i track arrivano via TrackSubscribed
        })
        .on(lk.RoomEvent.TrackSubscribed, (track, pub, participant) => {
          // Se a pubblicare e' un ALTRO rispondente (identity 'ha-*'), vuol
          // dire che la chiamata e' stata presa altrove: questa view va
          // chiusa (resta attiva solo sul dispositivo che ha risposto).
          if (this._maybeAnsweredElsewhere(participant)) return;
          this._attachRemoteTrack(track, participant);
        })
        .on(lk.RoomEvent.TrackUnsubscribed, (track) => {
          try { track.detach().forEach((el) => el.remove()); } catch (_) {}
        });

      await room.connect(this._cfg.ws_url, tk.token);

      // Subscribe a track gia' presenti (se il visitatore RPi e' arrivato prima).
      for (const p of room.remoteParticipants.values()) {
        // Gia' risposto da un altro rispondente prima che aprissimo? chiudi.
        const hasTrack = Array.from(p.trackPublications.values())
          .some((pub) => pub.track);
        if (hasTrack && this._maybeAnsweredElsewhere(p)) return;
        for (const pub of p.trackPublications.values()) {
          if (pub.track) this._attachRemoteTrack(pub.track, p);
        }
      }

      // Stato "ringing": video del visitatore visibile, audio del
      // visitatore mutato (vedi _attachRemoteTrack), nessun publish
      // locale. L'utente HA preme "Rispondi" e si entra in "live".
      this._status = 'ringing';
      this._retryAttempt = 0;
      this._render();
      // Build-report diagnostico: pubblica build+identity su MQTT, cosi'
      // e' verificabile quale versione della card gira su ogni dispositivo
      // (serve a distinguere "card vecchia in cache" da "bug logico").
      try {
        if (this._hass) {
          this._hass.callService('mqtt', 'publish', {
            topic: 'videocitofono/ha_card_build',
            payload: VC_BUILD + ' id=' + (this._identity || '?'),
            qos: 0, retain: false,
          });
        }
      } catch (_) {}
    }

    async _answer(mode) {
      if (this._answered || this._answering) return;
      if (!this._room) return;
      const answerMode = mode === 'audio' ? 'audio' : 'video';
      this._answering = true;
      this._answerError = null;

      // Stop suoneria IMMEDIATO al click "Rispondi", prima ancora del
      // getUserMedia (che impiega 200-800ms in Fully Kiosk e farebbe
      // sovrapporre la suoneria con il pickup). Doppio path:
      //   1) ferma il window._vcRing locale di QUESTO tab (suoneria
      //      avviata dal browser_mod.javascript dell'automation HA).
      //   2) chiama lo script videocitofono_stop_ringtone che fa
      //      browser_mod.javascript per fermare il ring su TUTTI i
      //      frontend (es. se la suoneria sta suonando anche su un
      //      altro tablet/companion app).
      try {
        if (window._vcRing) {
          try { window._vcRing.pause(); } catch (_) {}
          try { window._vcRing.currentTime = 0; } catch (_) {}
          window._vcRing = null;
        }
        if (window._vcRingTimer) {
          clearTimeout(window._vcRingTimer);
          window._vcRingTimer = null;
        }
      } catch (_) {}
      try {
        if (this._hass) {
          this._hass.callService('script', 'videocitofono_stop_ringtone', {});
        }
      } catch (e) { console.warn('stop_ringtone callService err:', e); }

      this._status = 'gum';
      this._render();
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error('navigator.mediaDevices.getUserMedia non disponibile.');
        }
        const constraints = {
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
            channelCount: 1,
            sampleRate: 48000,
          },
          // Vedi commento sul publishDefaults: 640x480@15fps single-layer
          // per non saturare il decoder libwebrtc Python sul Pi5.
          video: answerMode === 'video' ? {
            width: { ideal: 640 },
            height: { ideal: 480 },
            frameRate: { ideal: 15, max: 20 },
            facingMode: 'user',
          } : false,
        };
        this._localStream = await navigator.mediaDevices.getUserMedia(constraints);
        if (answerMode === 'video') {
          this._renderLocalPreview();
        }

        this._status = 'publishing';
        this._render();
        const lk = this._lk;
        const room = this._room;

        // Audio uplink HA -> Pi
        const aTracks = this._localStream.getAudioTracks();
        if (aTracks.length) {
          await room.localParticipant.publishTrack(aTracks[0], {
            source: lk.Track.Source.Microphone,
          });
        }
        // Video uplink HA -> Pi (solo risposta audio+video)
        if (answerMode === 'video') {
          const vTracks = this._localStream.getVideoTracks();
          if (vTracks.length) {
            await room.localParticipant.publishTrack(vTracks[0], {
              source: lk.Track.Source.Camera,
            });
          }
        }

        this._answered = true;
        this._answerMode = answerMode;
        this._camEnabled = answerMode === 'video';
        this._answering = false;
        this._unmuteRemoteAudio();
        this._status = 'live';
        this._render();

        // Notifica al Pi: modalita' risposta (audio-only vs video).
        try {
          if (this._hass) {
            this._hass.callService('mqtt', 'publish', {
              topic: 'videocitofono/chiamata',
              payload: answerMode === 'audio' ? 'risposto_audio' : 'risposto_video',
              qos: 0,
              retain: false,
            });
          }
        } catch (e) { console.warn('mqtt risposto err:', e); }
      } catch (err) {
        // Errore in _answer NON deve buttare giu' la Room: il video
        // del visitatore continua, l'utente puo' ritentare. Tipico
        // caso: NotReadableError "camera in uso da un'altra app"
        // (Fully Motion Detection / Snapshot abilitati). Pulizia
        // parziale: stop tracks gia' acquisite, niente teardown.
        this._answering = false;
        this._answered = false;
        try {
          if (this._localStream) {
            this._localStream.getTracks().forEach((t) => { try { t.stop(); } catch (_) {} });
          }
        } catch (_) {}
        this._localStream = null;
        let msg = err && err.message ? err.message : String(err);
        const name = err && err.name ? String(err.name) : '';
        if (name === 'NotReadableError' || /in use|busy|in uso/i.test(msg)) {
          msg = 'Camera/microfono occupati da un\'altra app del tablet ' +
                '(Fully Motion Detection? Webcam Snapshot?). Disabilitarli ' +
                'in Settings di Fully e riprovare.';
        } else if (name === 'NotAllowedError') {
          msg = 'Permesso camera/microfono negato. Verifica i permessi ' +
                'di Fully Kiosk (Motion Detection sospeso, microfono ON).';
        } else if (name === 'NotFoundError') {
          msg = 'Camera o microfono non trovati sul dispositivo.';
        }
        this._answerError = msg;
        console.warn('[vc-livekit-call] answer failed:', err, '->', msg);
        this._status = 'ringing';
        this._render();
      }
    }

    _unmuteRemoteAudio() {
      const root = this._renderRoot;
      const audios = root.querySelectorAll('audio[data-vc-remote]');
      audios.forEach((a) => {
        try {
          a.muted = false;
          a.volume = 1.0;
          a.play().catch(() => {});
        } catch (_) {}
      });
    }

    _isForeignResponder(identity) {
      // Rispondenti HA = identity con prefisso 'ha-' (vedi generateIdentity).
      // Il visitatore RPi pubblica con identity 'rpi' -> NON e' un rispondente.
      const prefix = (this._cfg && this._cfg.identity_prefix) || 'ha';
      return !!identity && identity !== this._identity &&
        identity.indexOf(prefix) === 0;
    }

    _maybeAnsweredElsewhere(participant) {
      try {
        if (this._answered || this._answering || this._dismissed) return false;
        const id = participant && participant.identity;
        if (!this._isForeignResponder(id)) return false;
        this._answeredElsewhere(id);
        return true;
      } catch (_) { return false; }
    }

    async _answeredElsewhere(id) {
      if (this._dismissed) return;
      this._dismissed = true;
      console.info('[vc-livekit-call] risposto da altro dispositivo (%s), chiudo questa view', id);
      // Ferma SOLO la suoneria locale: NON chiamo stop_ringtone globale ne'
      // hangup_script, perche' la chiamata prosegue sul dispositivo che ha
      // risposto e non va chiusa.
      try {
        if (window._vcRing) {
          try { window._vcRing.pause(); } catch (_) {}
          window._vcRing = null;
        }
        if (window._vcRingTimer) {
          clearTimeout(window._vcRingTimer);
          window._vcRingTimer = null;
        }
      } catch (_) {}
      // Diagnostica: segnala su MQTT che il dismiss e' partito (per
      // distinguere "detection non scatta" da "nav non funziona").
      try {
        if (this._hass) {
          this._hass.callService('mqtt', 'publish', {
            topic: 'videocitofono/ha_card_build',
            payload: 'DISMISS by=' + id + ' self=' + (this._identity || '?'),
            qos: 0, retain: false,
          });
        }
      } catch (_) {}
      this._status = 'answered_elsewhere';
      this._render();
      await this._teardown().catch(() => {});
      this._navigateOut();
    }

    _navigateOut() {
      // Navigazione robusta fuori dalla view conversazione. history.back()
      // e' inaffidabile su kiosk (Fully Kiosk avviato direttamente sulla
      // view => nessuna cronologia => no-op). Usiamo l'evento HA SPA
      // `location-changed` su window (come fa il router del frontend HA);
      // fallback su location.assign.
      try {
        const target = '/lovelace';
        window.history.pushState(null, '', target);
        const ev = new CustomEvent('location-changed', {
          detail: { replace: true }, bubbles: true, composed: true,
        });
        window.dispatchEvent(ev);
      } catch (_) {
        try { window.location.assign('/lovelace'); } catch (__) {}
      }
    }

    async _teardown() {
      const room = this._room;
      const stream = this._localStream;
      this._room = null;
      this._localStream = null;
      this._remoteAttached = false;
      this._status = 'closed';
      try { if (room) await room.disconnect(true); } catch (_) {}
      try {
        if (stream) stream.getTracks().forEach((t) => { try { t.stop(); } catch (_) {} });
      } catch (_) {}
    }

    _fail(err) {
      console.error('[vc-livekit-call]', err);
      this._error = err && err.message ? err.message : String(err);
      this._status = 'error';
      this._render();
      const msg = String(this._error || '').toLowerCase();
      const isPermanent =
        msg.includes('getusermedia') ||
        msg.includes('https') ||
        msg.includes('securecontext') ||
        msg.includes('permission');
      if (!isPermanent) this._scheduleRetry('error');
    }

    // --- rendering ----------------------------------------------------------

    _render() {
      const root = this._renderRoot;
      if (!root.firstChild) {
        root.innerHTML = `
<style>
  :host { display: block; width: 100%; height: 100%; }
  .wrap {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 70vh;
    background: #000;
    color: #fff;
    overflow: hidden;
    font-family: var(--primary-font-family, system-ui, sans-serif);
  }
  .remote {
    position: absolute; inset: 0;
    width: 100%; height: 100%;
    display: flex; align-items: center; justify-content: center;
    background: #000;
  }
  .remote video {
    width: 100%; height: 100%;
    object-fit: contain;
    background: #000;
  }
  .remote-placeholder {
    color: #ccc; font-size: 1.1rem; text-align: center;
    padding: 2rem;
  }
  .self {
    position: absolute;
    right: 16px; bottom: 96px;
    width: 22vw; max-width: 240px; min-width: 120px;
    aspect-ratio: 4/3;
    border-radius: 12px;
    overflow: hidden;
    background: #222;
    box-shadow: 0 4px 16px rgba(0,0,0,0.6);
    border: 2px solid rgba(255,255,255,0.15);
  }
  .self video {
    width: 100%; height: 100%;
    object-fit: cover;
    transform: scaleX(-1); /* mirror per chi si vede in self-view */
  }
  .controls {
    position: absolute; left: 0; right: 0; bottom: 0;
    display: flex; justify-content: center; gap: 18px;
    padding: 16px;
    background: linear-gradient(transparent, rgba(0,0,0,0.55));
  }
  .btn {
    width: 64px; height: 64px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    display: inline-flex;
    align-items: center; justify-content: center;
    color: #fff;
    background: #2c3034;
    transition: transform 0.1s ease, background 0.15s ease;
    box-shadow: 0 2px 6px rgba(0,0,0,0.4);
    --mdc-icon-size: 28px;
  }
  .btn ha-icon, .btn-answer ha-icon {
    pointer-events: none;
    color: inherit;
    display: flex;
  }
  .btn:hover { background: #3a4046; }
  .btn:active { transform: scale(0.95); }
  .btn.off { background: #5a3a3a; }
  .btn.danger { background: #d33; }
  .btn.danger:hover { background: #e44; }
  .btn.primary { background: #2e7d32; }
  .btn.primary:hover { background: #388e3c; }
  .ring-overlay {
    position: absolute;
    left: 0; right: 0; bottom: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    padding: 24px 16px 28px;
    background: linear-gradient(transparent, rgba(0,0,0,0.7));
    pointer-events: auto;
  }
  .ring-caller {
    font-size: 1.15rem;
    color: #fff;
    text-shadow: 0 1px 3px rgba(0,0,0,0.7);
    margin-bottom: 4px;
    text-align: center;
  }
  .ring-caller small { display:block; font-size: 0.85rem; opacity: 0.85; margin-top: 2px; }
  .ring-actions {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 28px;
  }
  .ring-action {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }
  .ring-action-label {
    font-size: 0.82rem;
    color: rgba(255,255,255,0.92);
    text-shadow: 0 1px 2px rgba(0,0,0,0.6);
  }
  .btn-answer {
    width: 88px; height: 88px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    display: inline-flex;
    align-items: center; justify-content: center;
    color: #fff;
    --mdc-icon-size: 42px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
    transition: transform 0.1s ease, background 0.15s ease, opacity 0.15s ease;
  }
  .btn-answer-audio {
    background: #1565c0;
    animation: ringPulseAudio 1.6s ease-out infinite;
  }
  .btn-answer-audio:hover { background: #1976d2; }
  .btn-answer-video {
    background: #2e7d32;
    animation: ringPulseVideo 1.6s ease-out infinite;
  }
  .btn-answer-video:hover { background: #388e3c; }
  .btn-answer-door {
    background: #e65100;
    animation: ringPulseDoor 1.6s ease-out infinite;
  }
  .btn-answer-door:hover { background: #ef6c00; }
  .btn-answer:active { transform: scale(0.95); animation: none; }
  @keyframes ringPulseAudio {
    0%   { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 0 rgba(21,101,192,0.55); }
    70%  { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 22px rgba(21,101,192,0); }
    100% { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 0 rgba(21,101,192,0); }
  }
  @keyframes ringPulseVideo {
    0%   { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 0 rgba(46,125,50,0.55); }
    70%  { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 22px rgba(46,125,50,0); }
    100% { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 0 rgba(46,125,50,0); }
  }
  @keyframes ringPulseDoor {
    0%   { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 0 rgba(230,81,0,0.55); }
    70%  { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 22px rgba(230,81,0,0); }
    100% { box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 0 rgba(230,81,0,0); }
  }
  .ring-error {
    max-width: 90%;
    margin-top: 4px;
    padding: 10px 14px;
    border-radius: 10px;
    background: rgba(180, 50, 50, 0.85);
    color: #fff;
    font-size: 0.9rem;
    line-height: 1.35;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
    display: none;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  .status {
    position: absolute; top: 12px; left: 12px;
    padding: 6px 12px;
    background: rgba(0,0,0,0.5);
    border-radius: 999px;
    font-size: 0.85rem;
    backdrop-filter: blur(6px);
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .status ha-icon, .error ha-icon, .ring-error ha-icon {
    --mdc-icon-size: 18px;
    color: inherit;
  }
  .error {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    padding: 2rem;
    text-align: center;
    background: rgba(80,0,0,0.85);
    color: #fff;
    font-size: 1rem;
    line-height: 1.5;
    gap: 10px;
  }
  .badge-rec { color: #ff5252; margin-right: 6px; }
</style>
<div class="wrap">
  <div class="remote" id="remote">
    <div class="remote-placeholder" id="remote-placeholder">In attesa del visitatore…</div>
  </div>
  <div class="self" id="self">
    <video id="self-video" autoplay muted playsinline></video>
  </div>
  <div class="status" id="status"></div>
  <div class="controls" id="controls">
    <button class="btn" id="btn-mic"  title="Mic on/off">${mdi('mdi:microphone')}</button>
    <button class="btn" id="btn-cam"  title="Camera on/off">${mdi('mdi:video')}</button>
    <button class="btn primary" id="btn-door" title="Apri porta">${mdi('mdi:door-open')}</button>
    <button class="btn danger"  id="btn-end"  title="Chiudi">${mdi('mdi:phone-hangup')}</button>
  </div>
  <div class="ring-overlay" id="ring-overlay" style="display:none">
    <div class="ring-caller" id="ring-caller">Chiamata in arrivo<small>…</small></div>
    <div class="ring-actions">
      <div class="ring-action">
        <button class="btn-answer btn-answer-audio" id="btn-answer-audio" title="Rispondi solo audio">${mdi('mdi:phone')}</button>
        <span class="ring-action-label">Solo audio</span>
      </div>
      <div class="ring-action">
        <button class="btn-answer btn-answer-video" id="btn-answer-video" title="Rispondi audio e video">${mdi('mdi:video')}</button>
        <span class="ring-action-label">Audio + video</span>
      </div>
      <div class="ring-action">
        <button class="btn-answer btn-answer-door" id="btn-answer-door" title="Apri porta senza rispondere">${mdi('mdi:door-open')}</button>
        <span class="ring-action-label">Apri porta</span>
      </div>
    </div>
    <div class="ring-error" id="ring-error" style="display:none"></div>
  </div>
  <div class="error" id="error" style="display:none"></div>
</div>`;
        root.getElementById('btn-mic').addEventListener('click', () => this._toggleMic());
        root.getElementById('btn-cam').addEventListener('click', () => this._toggleCam());
        root.getElementById('btn-door').addEventListener('click', () => this._openDoor());
        root.getElementById('btn-end').addEventListener('click', () => this._hangup());
        root.getElementById('btn-answer-audio').addEventListener('click', () => this._answer('audio'));
        root.getElementById('btn-answer-video').addEventListener('click', () => this._answer('video'));
        root.getElementById('btn-answer-door').addEventListener('click', () => this._openDoor());
      }

      const status = root.getElementById('status');
      const errBox = root.getElementById('error');
      const btnMic = root.getElementById('btn-mic');
      const btnCam = root.getElementById('btn-cam');
      const camWrap = root.getElementById('self');

      if (this._status === 'error') {
        errBox.style.display = 'flex';
        errBox.innerHTML = mdi('mdi:alert-circle-outline') + ' ' + (this._error || 'errore sconosciuto');
      } else {
        errBox.style.display = 'none';
      }

      const labels = {
        init: mdi('mdi:dots-horizontal') + ' …',
        preflight: mdi('mdi:shield-check-outline') + ' verifica…',
        token: mdi('mdi:key-variant') + ' autenticazione…',
        connect: mdi('mdi:lan-connect') + ' connessione…',
        ringing: mdi('mdi:phone-ring') + ' chiamata in arrivo',
        gum: mdi('mdi:video-account') + ' attivazione camera/microfono…',
        publishing: mdi('mdi:upload') + ' invio video…',
        live: mdi('mdi:record-circle') + ' in chiamata',
        reconnecting: mdi('mdi:reload') + ' riconnessione in corso…',
        disconnected: mdi('mdi:lan-disconnect') + ' connessione persa, ritento…',
        answered_elsewhere: mdi('mdi:phone-forward') + ' risposto da un altro dispositivo',
        closed: mdi('mdi:phone-hangup') + ' chiusa',
        error: mdi('mdi:alert-circle-outline') + ' errore',
      };
      const label = labels[this._status] || this._status;
      status.innerHTML = label;

      btnMic.classList.toggle('off', !this._micEnabled);
      btnMic.innerHTML = mdi(this._micEnabled ? 'mdi:microphone' : 'mdi:microphone-off');
      btnCam.classList.toggle('off', !this._camEnabled);
      btnCam.innerHTML = mdi(this._camEnabled ? 'mdi:video' : 'mdi:video-off');

      // Ringing UI: bottone "Rispondi" enorme + nome campanello.
      // L'overlay e' visibile in TUTTI gli stati pre-answered
      // (init/preflight/token/connect/ringing/gum/publishing) per
      // evitare il "limbo nero con testo di stato" che si vedeva tra
      // l'apertura della view e la connessione Room (~500-1500ms).
      // Il bottone Rispondi e' visualmente disabilitato (opacity +
      // pointer-events none) finche' lo stato non e' 'ringing': cosi'
      // l'utente non puo' premerlo prima che la Room abbia subscribed
      // il video del Pi, ma vede comunque la schermata corretta da
      // subito.
      const ringOverlay = root.getElementById('ring-overlay');
      const controls = root.getElementById('controls');
      const btnAnswerAudio = root.getElementById('btn-answer-audio');
      const btnAnswerVideo = root.getElementById('btn-answer-video');
      const btnAnswerDoor = root.getElementById('btn-answer-door');
      const preLive = !this._answered && !this._dismissed &&
                      this._status !== 'live' &&
                      this._status !== 'answered_elsewhere' &&
                      this._status !== 'closed' && this._status !== 'error';
      const ringing = preLive;
      const answerReady = this._status === 'ringing' || this._status === 'gum' || this._status === 'publishing';
      if (ringOverlay) ringOverlay.style.display = ringing ? 'flex' : 'none';
      if (controls) controls.style.display = ringing ? 'none' : 'flex';
      [btnAnswerAudio, btnAnswerVideo, btnAnswerDoor].forEach((btn) => {
        if (!btn) return;
        btn.style.opacity = answerReady ? '1' : '0.45';
        btn.style.pointerEvents = answerReady ? 'auto' : 'none';
      });
      const hideSelf = ringing || this._answerMode === 'audio' || this._cfg.audio_only;
      camWrap.style.display = hideSelf ? 'none' : '';

      // Errore non-fatale (es. camera busy in Fully) mostrato sotto il
      // bottone Rispondi senza chiudere la Room.
      const ringErr = root.getElementById('ring-error');
      if (ringErr) {
        if (ringing && this._answerError) {
          ringErr.style.display = 'flex';
          ringErr.innerHTML = mdi('mdi:alert-circle-outline') + ' ' + this._answerError;
        } else {
          ringErr.style.display = 'none';
        }
      }

      // Nome campanello dal sensor MQTT.
      const ringCaller = root.getElementById('ring-caller');
      if (ringCaller && ringing) {
        let who = '';
        try {
          const st = this._hass && this._hass.states &&
            this._hass.states['sensor.videocitofono_ultimo_campanello'];
          if (st && st.state && st.state !== 'unknown' && st.state !== 'unavailable') {
            who = String(st.state).replace(/_/g, ' ');
          }
        } catch (_) {}
        // Sub-label per stato:
        //  init/preflight/token/connect: "preparazione…" (Room non
        //    ancora pronta, bottone disabilitato).
        //  ringing: nome campanello (chiamata pronta a essere risposta).
        //  gum/publishing: stato post-click "Rispondi".
        let sub;
        if (this._status === 'gum') sub = 'attivazione camera/mic…';
        else if (this._status === 'publishing') sub = 'connessione audio/video…';
        else if (this._status === 'ringing') sub = (who ? who : '…');
        else sub = 'preparazione…';
        ringCaller.innerHTML = 'Chiamata in arrivo<small>' + sub + '</small>';
      }
    }

    _renderLocalPreview() {
      const v = this._renderRoot.getElementById('self-video');
      if (v && this._localStream) {
        try {
          // Solo video: attaccare anche l'audio locale al <video> fa
          // sentire la propria voce in cuffia/speaker (sidetone), anche
          // se l'elemento e' muted su alcuni browser.
          const vids = this._localStream.getVideoTracks();
          v.srcObject = vids.length ? new MediaStream(vids) : null;
          v.muted = true;
          v.volume = 0;
          v.play().catch(() => {});
        } catch (_) {}
      }
    }

    _attachRemoteTrack(track, participant) {
      const lk = this._lk;
      if (!lk) return;
      const remote = this._renderRoot.getElementById('remote');
      const placeholder = this._renderRoot.getElementById('remote-placeholder');
      if (placeholder) placeholder.style.display = 'none';

      if (track.kind === 'video') {
        const el = track.attach();
        el.style.width = '100%';
        el.style.height = '100%';
        el.style.objectFit = 'contain';
        el.setAttribute('playsinline', '');
        el.setAttribute('autoplay', '');
        el.id = 'remote-video-' + participant.identity;
        // rimuovi eventuale video precedente dello stesso participant
        const prev = this._renderRoot.getElementById(el.id);
        if (prev) prev.remove();
        remote.appendChild(el);
        el.play().catch(() => {});
      } else if (track.kind === 'audio') {
        const el = track.attach();
        el.id = 'remote-audio-' + participant.identity;
        el.setAttribute('data-vc-remote', '1');
        const prev = this._renderRoot.getElementById(el.id);
        if (prev) prev.remove();
        el.setAttribute('autoplay', '');
        // Stato "ringing": audio del visitatore silenziato finche'
        // il rispondente non preme "Rispondi". track.attach() crea
        // un <audio> con muted=false di default; lo zittiamo qui.
        if (!this._answered) {
          el.muted = true;
          el.volume = 0;
        }
        remote.appendChild(el);
      }
      this._remoteAttached = true;
    }

    // --- controls -----------------------------------------------------------

    async _toggleMic() {
      if (!this._room) return;
      this._micEnabled = !this._micEnabled;
      try {
        await this._room.localParticipant.setMicrophoneEnabled(this._micEnabled);
      } catch (e) { console.warn('toggle mic err', e); }
      this._render();
    }

    async _toggleCam() {
      if (!this._room || this._cfg.audio_only) return;
      const enabling = !this._camEnabled;
      if (enabling && this._answerMode === 'audio') {
        await this._upgradeToVideo();
        return;
      }
      this._camEnabled = !this._camEnabled;
      try {
        await this._room.localParticipant.setCameraEnabled(this._camEnabled);
      } catch (e) { console.warn('toggle cam err', e); }
      this._render();
    }

    async _upgradeToVideo() {
      if (!this._room || this._answerMode === 'video') return;
      const lk = this._lk;
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error('getUserMedia non disponibile');
        }
        const vStream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 640 },
            height: { ideal: 480 },
            frameRate: { ideal: 15, max: 20 },
            facingMode: 'user',
          },
        });
        const vTrack = vStream.getVideoTracks()[0];
        if (!vTrack) throw new Error('Nessuna track video');
        if (this._localStream) {
          this._localStream.addTrack(vTrack);
        } else {
          this._localStream = vStream;
        }
        await this._room.localParticipant.publishTrack(vTrack, {
          source: lk.Track.Source.Camera,
        });
        this._answerMode = 'video';
        this._camEnabled = true;
        this._renderLocalPreview();
        this._render();
        try {
          if (this._hass) {
            this._hass.callService('mqtt', 'publish', {
              topic: 'videocitofono/chiamata',
              payload: 'risposto_video',
              qos: 0,
              retain: false,
            });
          }
        } catch (e) { console.warn('mqtt risposto_video upgrade err:', e); }
      } catch (e) {
        console.warn('upgrade to video err', e);
      }
    }

    _openDoor() {
      const target = this._cfg.open_door_script;
      if (!target || !this._hass) return;
      const [domain, service] = String(target).split('.');
      if (!domain || !service) return;
      try { this._hass.callService(domain, service, {}); } catch (e) { console.warn(e); }
    }

    async _hangup() {
      const target = this._cfg.hangup_script;
      if (target && this._hass) {
        const [domain, service] = String(target).split('.');
        try { this._hass.callService(domain, service, {}); } catch (_) {}
      }
      await this._teardown();
      // navigazione fuori: se la view e' /lovelace/conversazione torna alla home.
      try {
        if (location.pathname.includes('/conversazione')) {
          history.back();
        }
      } catch (_) {}
    }
  }

  // v3: nome custom element nuovo per forzare i kiosk Fully Browser
  // a usare la nuova classe. Fully cacha aggressivamente la classe
  // gia' definita per `vc-livekit-call-v2`; cambiando nome il browser
  // e' costretto a fetchare e registrare ex novo. v2 resta come alias
  // di compatibilita' su altre dashboard non migrate.
  if (!customElements.get('vc-livekit-call-v3')) {
    customElements.define('vc-livekit-call-v3', VcLivekitCall);
  }
  if (!customElements.get('vc-livekit-call-v2')) {
    class VcLivekitCallAliasV2 extends VcLivekitCall {}
    customElements.define('vc-livekit-call-v2', VcLivekitCallAliasV2);
  }
  if (!customElements.get('vc-livekit-call')) {
    class VcLivekitCallAlias extends VcLivekitCall {}
    customElements.define('vc-livekit-call', VcLivekitCallAlias);
  }

  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === 'vc-livekit-call-v3')) {
    window.customCards.push({
      type: 'vc-livekit-call-v3',
      name: 'Videocitofono LiveKit Call (v3)',
      description: 'Videochiamata bidirezionale (LiveKit) tra rispondente e visitatore.',
      preview: false,
    });
  }

  const VC_BUILD = '2026-10-18.mdi-call';
  console.log('[vc-livekit-call-v3] custom card registrata, build=' + VC_BUILD);
})();
