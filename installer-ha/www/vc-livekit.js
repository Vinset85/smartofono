/* Videocitofono - LiveKit publisher helper (lato browser HA).
 *
 * Espone window.vcLK con API:
 *   - vcLK.start({ stream, audioOnly }) -> Promise<void>
 *       Connette alla LiveKit room "videocitofono" come ha-<browser_id>
 *       e pubblica lo stream (cam+mic o solo mic).
 *
 *   - vcLK.stop() -> Promise<void>
 *       Unpublish + disconnect dalla room. Ferma anche le track del
 *       MediaStream gestito dal warmup (se shared).
 *
 *   - vcLK.isActive() -> bool
 *
 * Architettura:
 *   browser HA (HTTPS) ──livekit-client UMD SDK── wss://<HA-host>/livekit/rtc
 *                                                  ^
 *                                                  +── token issuer FastAPI
 *                                                       https://<HA-host>/livekit-token/token
 *
 *   subscribe lato Pi:
 *   livekit-rtc Python SDK -> AudioStream (s16/mono/48k) -> AudioBackchannel
 *                          -> VideoStream (RGB24)         -> Kivy texture
 *
 * Endpoint:
 *   - Stesso origin del frontend HA (Caddy edge unifica HA + LiveKit + token).
 *     Niente mixed-content quando HA serve in HTTPS, niente CORS, niente
 *     cert mismatch sull'IP nudo.
 *   - Override esplicito: window.vcLKConfig = { tokenUrl, wsUrl } prima
 *     dello script, oppure vcLK.configure({ tokenUrl, wsUrl }) prima di
 *     start().
 *
 * Diversamente dal vecchio path WHIP/go2rtc:
 *   - niente cookie ingress / session token (auth con JWT firmato)
 *   - niente race condition su getUserMedia (warmup gia' acquisita)
 *   - niente encoder stall: BWE/RTCP gestito da libwebrtc dentro l'SDK
 *   - riconnessione automatica su packet loss
 */
(function () {
  'use strict';

  // Endpoints di default: stesso origin del frontend (Caddy edge).
  // Quando HA gira su https://casa-esempio.duckdns.org, vengono usati:
  //   tokenUrl = https://casa-esempio.duckdns.org/livekit-token/token
  //   wsUrl    = wss://casa-esempio.duckdns.org/livekit/rtc
  //
  // Se HA e' aperto via http (LAN-only legacy) il browser non puo' fare
  // getUserMedia (mediaDevices undefined) -> blocco a monte. Forziamo
  // quindi sempre il dominio HTTPS per il token e ws, costringendo
  // l'utente a usare HTTPS davvero.
  function defaultTokenUrl() {
    if (location.protocol === 'https:') {
      return location.origin + '/livekit-token/token';
    }
    // Fallback HTTP-only: ipotesi LAN diretta senza Caddy. Sara'
    // comunque inutile perche' getUserMedia richiede secure context.
    return 'http://' + location.hostname + ':8081/token';
  }
  function defaultWsUrl() {
    // NB: senza `/rtc` finale. Il SDK livekit-client appende `/rtc` da
    // solo (vedi SignalClient: `${host}/rtc?access_token=...`). Se
    // mettessimo `/livekit/rtc` qui, il client tenterebbe
    // `wss://h/livekit/rtc/rtc?...` e Caddy/livekit-server 404.
    // Caddy strippa /livekit prefix -> upstream /rtc (signaling).
    if (location.protocol === 'https:') {
      return 'wss://' + location.host + '/livekit';
    }
    return 'ws://' + location.hostname + ':7880';
  }

  const cfg = Object.assign(
    {
      tokenUrl: defaultTokenUrl(),
      wsUrl: defaultWsUrl(),
      sdkUrl: '/local/livekit-client-2.19.1.umd.min.js',
      roomName: 'videocitofono',
    },
    window.vcLKConfig || {}
  );

  let sdkLoadPromise = null;
  let state = null; // { room, stream, identity, audioOnly }

  function log(...args) { console.log('[vcLK]', ...args); }
  function warn(...args) { console.warn('[vcLK]', ...args); }

  function configure(opts) {
    if (!opts) return;
    if (opts.tokenUrl) cfg.tokenUrl = opts.tokenUrl;
    if (opts.wsUrl) cfg.wsUrl = opts.wsUrl;
    if (opts.sdkUrl) cfg.sdkUrl = opts.sdkUrl;
    if (opts.roomName) cfg.roomName = opts.roomName;
  }

  function loadSdk() {
    if (window.LivekitClient || window.LiveKitClient) {
      return Promise.resolve(window.LivekitClient || window.LiveKitClient);
    }
    if (sdkLoadPromise) return sdkLoadPromise;
    sdkLoadPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = cfg.sdkUrl;
      s.async = true;
      s.onload = () => {
        const lk = window.LivekitClient || window.LiveKitClient;
        if (!lk) {
          reject(new Error('SDK livekit-client non esposto su window'));
          return;
        }
        log('SDK livekit-client caricato');
        resolve(lk);
      };
      s.onerror = () => reject(new Error('SDK livekit-client load error'));
      document.head.appendChild(s);
    });
    return sdkLoadPromise;
  }

  async function fetchToken(identity, audioOnly) {
    const body = JSON.stringify({
      identity: identity,
      room: cfg.roomName,
      name: identity,
      ttl_seconds: 7200,
      can_publish: true,
      can_subscribe: true,
      prefer_lan: false,
    });
    const resp = await fetch(cfg.tokenUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    });
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error('token issuer HTTP ' + resp.status + ' ' + txt.slice(0, 200));
    }
    const j = await resp.json();
    if (!j.token) throw new Error('token issuer payload invalido');
    // Override ws_url col valore configurato lato client. Il JWT non e'
    // legato al ws_url, e' solo metadata. Cosi' un eventuale mismatch
    // backend (es. issuer con env LIVEKIT_HOST stale) non rompe il
    // frontend: prevale sempre cfg.wsUrl che e' costruito dal location
    // del frontend stesso.
    j.ws_url = cfg.wsUrl;
    return j;
  }

  function generateIdentity() {
    let id = sessionStorage.getItem('vc-lk-identity');
    if (!id) {
      id = 'ha-' + Math.random().toString(36).slice(2, 10);
      sessionStorage.setItem('vc-lk-identity', id);
    }
    return id;
  }

  function preflightCheck() {
    if (!window.isSecureContext) {
      throw new Error(
        'Contesto non sicuro: HA deve essere aperto in HTTPS (es. ' +
        'https://casa-esempio.duckdns.org). In HTTP il browser non ' +
        'espone navigator.mediaDevices e LiveKit non puo' +
        ' acquisire camera/microfono.'
      );
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('navigator.mediaDevices.getUserMedia non disponibile in questo browser');
    }
  }

  async function start(opts) {
    opts = opts || {};
    const audioOnly = !!opts.audioOnly;
    const stream = opts.stream;
    if (!stream) throw new Error('stream MediaStream richiesto');
    if (state && state.room) {
      warn('start: gia attivo, ignoro');
      return;
    }
    preflightCheck();
    const lk = await loadSdk();
    const identity = generateIdentity();
    log('fetch token identity=', identity, 'audioOnly=', audioOnly,
        'token=', cfg.tokenUrl, 'ws=', cfg.wsUrl);
    const tk = await fetchToken(identity, audioOnly);

    const room = new lk.Room({
      adaptiveStream: true,
      dynacast: true,
      publishDefaults: {
        // Il Pi e' uno dei consumer e mostra solo 480x480, ma altri
        // tablet HA possono vedere lo stesso uplink: simulcast 2 layer
        // (SD+QVGA) per adattare automaticamente.
        simulcast: true,
        videoCodec: 'vp8',
        videoEncoding: {
          maxBitrate: 800_000,
          maxFramerate: 20,
        },
        audioPreset: { maxBitrate: 32_000 },
      },
    });

    room
      .on(lk.RoomEvent.ConnectionStateChanged, (s) => log('state=', s))
      .on(lk.RoomEvent.Disconnected, (reason) => log('disconnected', reason))
      .on(lk.RoomEvent.ParticipantConnected, (p) => log('participant connected', p.identity))
      .on(lk.RoomEvent.MediaDevicesError, (e) => warn('MediaDevicesError', e));

    await room.connect(tk.ws_url, tk.token);
    log('connected as', identity, 'in', cfg.roomName);

    const audioTracks = stream.getAudioTracks();
    if (audioTracks.length) {
      const at = audioTracks[0];
      await room.localParticipant.publishTrack(at, {
        source: lk.Track.Source.Microphone,
      });
      log('audio track pubblicato');
    } else {
      warn('nessun audio track nello stream');
    }
    if (!audioOnly) {
      const videoTracks = stream.getVideoTracks();
      if (videoTracks.length) {
        const vt = videoTracks[0];
        await room.localParticipant.publishTrack(vt, {
          source: lk.Track.Source.Camera,
        });
        log('video track pubblicato');
      } else {
        warn('nessun video track nello stream (audioOnly atteso: ' + audioOnly + ')');
      }
    }

    state = { room, stream, identity, audioOnly };
    log('publish completata');
  }

  async function stop() {
    if (!state) return;
    const { room, stream } = state;
    state = null;
    try {
      await room.disconnect(true);
      log('room disconnected');
    } catch (e) { warn('disconnect err', e); }
    try {
      stream.getTracks().forEach(t => { try { t.stop(); } catch (_) {} });
    } catch (e) { warn('stream stop err', e); }
  }

  function isActive() { return !!state; }

  function diagnostics() {
    return {
      secure: !!window.isSecureContext,
      proto: location.protocol,
      origin: location.origin,
      hasGUM: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
      tokenUrl: cfg.tokenUrl,
      wsUrl: cfg.wsUrl,
      sdkLoaded: !!(window.LivekitClient || window.LiveKitClient),
      active: !!state,
    };
  }

  window.vcLK = {
    start, stop, isActive, configure, loadSdk, diagnostics,
    get config() { return Object.assign({}, cfg); },
  };
  log('vc-livekit.js caricato', diagnostics());
})();
