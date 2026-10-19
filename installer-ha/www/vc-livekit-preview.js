/* Videocitofono - Anteprima ingresso.
 *
 * WebRTC (LiveKit, player isolato) nel tab di Lovelace ricarica
 * il frontend. Qui il video e l'audio arrivano come stream HTTP (fMP4)
 * in un <video> nella card: niente ICE nel browser.
 */

(function () {
  'use strict';

  const VC_PREV_BUILD = 'vc-livekit-preview 2026.10.18-28';
  const CALL_ENTITY = 'binary_sensor.stato_chiamata_videocitofono';
  const STREAM = '/go2rtc/api/stream.mp4?src=pi5cam_h264';
  const ATTESA_VIDEO_MS = 25000;
  const RETRY_MS = 1200;

  const SESS = {
    stato: 'idle', deadline: 0, liveDa: 0,
    ttl: 120, tentativo: 0,
    voglio: false, bootId: 0, tick: null,
    attesaTimer: null, retryTimer: null, video: null, audio: false,
  };
  let _card = null;
  let _cmdLast = { on: null, t: 0 };

  function eCopiaLovelace(el) {
    if (!el || !el.isConnected) return true;
    let n = el;
    for (let i = 0; i < 14 && n; i++) {
      if (n.nodeType === 1) {
        const st = n.getAttribute('style') || '';
        if (/left:\s*-\d{3,}/.test(st) || /top:\s*-\d{3,}/.test(st)) return true;
      }
      n = n.parentNode;
      if (n && n.nodeType === 11) n = n.host || n.parentNode;
    }
    return false;
  }

  function adottaSessione(c) {
    if (!c || !SESS.voglio) return false;
    if (SESS.stato !== 'live' && SESS.stato !== 'attesa' && SESS.stato !== 'avvio') {
      return false;
    }
    c._stato = SESS.stato === 'avvio' ? 'attesa' : SESS.stato;
    c._deadline = SESS.deadline;
    c._liveDa = SESS.liveDa;
    c._ttl = SESS.ttl;
    c._tentativo = SESS.tentativo;
    return true;
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

  function edgeOrigin() {
    if (location.protocol === 'https:') {
      const std = !location.port || location.port === '443';
      return std ? location.origin : ('https://' + location.hostname);
    }
    return location.origin;
  }

  function streamUrl() {
    return edgeOrigin() + STREAM + '&t=' + Date.now();
  }

  class VcLivekitPreview extends HTMLElement {
    static getStubConfig() { return { title: 'Ingresso dal vivo', ttl: 120 }; }

    constructor() {
      super();
      this._cfg = {};
      this._hass = null;
      this._stato = 'idle';
      this._errore = '';
      this._deadline = 0;
      this._liveDa = 0;
      this._tentativo = 0;
      this._ttl = 120;
      this._lockClick = 0;
      this._root = this.attachShadow({ mode: 'open' });
      this._onPlaying = () => this._segnaLive();
      this._onError = () => this._retryStream();
      this._renderShell();
    }

    setConfig(cfg) {
      this._cfg = Object.assign({ title: 'Ingresso dal vivo', ttl: 120 }, cfg || {});
      this._ttl = Math.max(15, Math.min(600, parseInt(this._cfg.ttl, 10) || 120));
      if (this._stato === 'live' || this._stato === 'attesa' || this._stato === 'avvio') {
        return;
      }
      if (adottaSessione(this)) this._riaggancia();
      else this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this._stato === 'live' || this._stato === 'attesa' || this._stato === 'avvio') {
        return;
      }
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
    getGridOptions() {
      return { columns: 'full', rows: 6, min_rows: 6, max_rows: 6 };
    }

    connectedCallback() {
      if (eCopiaLovelace(this)) return;
      if (_card && _card !== this && _card.isConnected && !eCopiaLovelace(_card)) {
        return;
      }
      const riprendi = adottaSessione(this)
        || this._stato === 'live' || this._stato === 'attesa' || this._stato === 'avvio';
      _card = this;
      if (riprendi) this._riaggancia();
      else if (this._cfg && !this._root.getElementById('msg')) this._render();
    }

    disconnectedCallback() {
      if (_card !== this) return;
      _card = null;
    }

    _riaggancia() {
      if (eCopiaLovelace(this)) return;
      _card = this;
      this._render();
      if (SESS.voglio && (this._stato === 'live' || this._stato === 'attesa'
          || this._stato === 'avvio')) {
        this._agganciaStream();
        if (this._stato === 'live' && !SESS.tick) this._avviaConto();
      }
    }

    _comando(on) {
      if (!this._hass) return;
      on = !!on;
      if (on && !SESS.voglio) return;
      if (!on && SESS.voglio) return;
      const now = Date.now();
      if (_cmdLast.on === on && (now - _cmdLast.t) < (on ? 8000 : 1500)) return;
      _cmdLast = { on: on, t: now };
      const data = { action: 'livekit_preview', on: on, enabled: on };
      if (on) data.ttl = this._ttl;
      try {
        const conn = this._hass.connection;
        const p = (conn && conn.sendMessagePromise)
          ? conn.sendMessagePromise({
              type: 'call_service',
              domain: 'pyscript',
              service: 'videocitofono_mqtt_cmd',
              service_data: data,
            })
          : this._hass.callService('pyscript', 'videocitofono_mqtt_cmd', data);
        if (p && typeof p.then === 'function') {
          p.catch((e) => console.warn('[vc-livekit-preview] comando MQTT fallito:', e));
        }
      } catch (e) {
        console.warn('[vc-livekit-preview] comando MQTT fallito:', e);
      }
    }

    _montaVideo() {
      const box = this._root.getElementById('video');
      if (!box) return null;
      let v = this._root.getElementById('player');
      if (v && v.tagName === 'VIDEO' && v.isConnected) {
        SESS.video = v;
        return v;
      }
      v = document.createElement('video');
      v.id = 'player';
      v.setAttribute('playsinline', '');
      v.setAttribute('autoplay', '');
      v.playsInline = true;
      v.autoplay = true;
      v.muted = !SESS.audio;
      v.controls = false;
      v.disablePictureInPicture = true;
      v.addEventListener('playing', this._onPlaying);
      v.addEventListener('canplay', this._onPlaying);
      v.addEventListener('error', this._onError);
      box.appendChild(v);
      SESS.video = v;
      return v;
    }

    _chiudiVideo() {
      if (SESS.retryTimer) {
        clearTimeout(SESS.retryTimer);
        SESS.retryTimer = null;
      }
      const v = SESS.video || (this._root && this._root.getElementById('player'));
      SESS.video = null;
      SESS.audio = false;
      if (!v) return;
      try { v.removeEventListener('playing', this._onPlaying); } catch (_) {}
      try { v.removeEventListener('canplay', this._onPlaying); } catch (_) {}
      try { v.removeEventListener('error', this._onError); } catch (_) {}
      try { v.pause(); } catch (_) {}
      try { v.removeAttribute('src'); v.load(); } catch (_) {}
      try { v.remove(); } catch (_) {}
    }

    _agganciaStream() {
      const v = this._montaVideo();
      if (!v || !SESS.voglio) return;
      try {
        v.muted = !SESS.audio;
        v.src = streamUrl();
        v.play().catch(function () {});
      } catch (e) {
        console.warn('[vc-livekit-preview] stream:', e);
      }
    }

    _retryStream() {
      if (!SESS.voglio) return;
      if (SESS.stato === 'live') return;
      if (SESS.retryTimer) return;
      SESS.retryTimer = setTimeout(() => {
        SESS.retryTimer = null;
        if (!SESS.voglio || SESS.stato === 'live') return;
        this._agganciaStream();
      }, RETRY_MS);
    }

    _segnaLive() {
      if (!SESS.voglio) return;
      if (SESS.attesaTimer) {
        clearTimeout(SESS.attesaTimer);
        SESS.attesaTimer = null;
      }
      if (SESS.retryTimer) {
        clearTimeout(SESS.retryTimer);
        SESS.retryTimer = null;
      }
      const giaLive = this._stato === 'live' && this._deadline > Date.now();
      this._stato = 'live';
      SESS.stato = 'live';
      if (!giaLive) {
        this._liveDa = Date.now();
        this._deadline = Date.now() + this._ttl * 1000;
        SESS.deadline = this._deadline;
        this._avviaConto();
        this._render();
      } else {
        this._nascondiMsg();
      }
    }

    _nascondiMsg() {
      const msg = this._root.getElementById('msg');
      if (msg) msg.classList.add('off');
    }

    _avvia(riprova) {
      if (!riprova && this._lockClick && Date.now() < this._lockClick) return;
      if (!riprova && SESS.voglio
          && (SESS.stato === 'live' || SESS.stato === 'attesa' || SESS.stato === 'avvio')) {
        this._agganciaStream();
        if (adottaSessione(this)) this._riaggancia();
        return;
      }
      if (!riprova && (this._stato === 'avvio' || this._stato === 'attesa'
          || this._stato === 'live')) {
        this._agganciaStream();
        return;
      }
      if (statoEntita(this._hass, CALL_ENTITY) === 'on') {
        this._stato = 'in_chiamata';
        this._render();
        return;
      }
      this._errore = '';
      this._stato = 'avvio';
      SESS.voglio = true;
      SESS.stato = 'avvio';
      SESS.audio = false;
      this._render();
      this._comando(true);
      this._tentativo += 1;
      SESS.bootId = (SESS.bootId || 0) + 1;
      this._stato = 'attesa';
      SESS.stato = 'attesa';
      this._render();
      this._agganciaStream();
      if (SESS.attesaTimer) clearTimeout(SESS.attesaTimer);
      SESS.attesaTimer = setTimeout(() => {
        if (SESS.stato === 'live' || !SESS.voglio) return;
        const c = _card || this;
        c._errore = 'Il citofono non ha inviato il video. '
          + 'Puo\u2019 essere occupato dal riconoscimento del volto '
          + 'o da una chiamata appena conclusa: riprova tra qualche secondo.';
        c._stato = 'errore';
        SESS.voglio = false;
        SESS.stato = 'errore';
        c._comando(false);
        c._chiudiVideo();
        c._render();
      }, ATTESA_VIDEO_MS);
    }

    _avviaConto() {
      if (SESS.tick) return;
      SESS.tick = setInterval(() => {
        if (!SESS.voglio) return;
        const deadline = SESS.deadline;
        if (!deadline) return;
        const resto = deadline - Date.now();
        const c = _card;
        if (resto <= 0) {
          if (c) c._ferma('tempo scaduto');
          return;
        }
        if (!c) return;
        c._deadline = deadline;
        const el = c._root && c._root.getElementById('conto');
        if (el) el.textContent = mmss(resto);
      }, 1000);
    }

    _prolunga() {
      SESS.voglio = true;
      this._comando(true);
      this._deadline = Date.now() + this._ttl * 1000;
      SESS.deadline = this._deadline;
      const el = this._root.getElementById('conto');
      if (el) el.textContent = mmss(this._ttl * 1000);
    }

    _audio() {
      SESS.audio = !SESS.audio;
      const v = SESS.video || (this._root && this._root.getElementById('player'));
      if (v) {
        v.muted = !SESS.audio;
        v.volume = SESS.audio ? 1 : 0;
        if (SESS.audio) v.play().catch(function () {});
      }
      const b = this._root.getElementById('btn-audio');
      if (b) b.setAttribute('title', SESS.audio ? 'Muto' : 'Audio');
      const ic = b && b.querySelector('ha-icon');
      if (ic) ic.setAttribute('icon', SESS.audio ? 'mdi:volume-high' : 'mdi:volume-off');
    }

    _ferma(motivo) {
      SESS.voglio = false;
      SESS.bootId = (SESS.bootId || 0) + 1;
      this._lockClick = Date.now() + 1000;
      this._comando(false);
      this._stato = 'idle';
      this._tentativo = 0;
      if (SESS.tick) { clearInterval(SESS.tick); SESS.tick = null; }
      if (SESS.attesaTimer) { clearTimeout(SESS.attesaTimer); SESS.attesaTimer = null; }
      this._chiudiVideo();
      this._render();
      if (motivo) console.log('[vc-livekit-preview] chiusa:', motivo);
    }

    _renderShell() {
      this._root.innerHTML = `
<style>
  ha-card { overflow: hidden; }
  .hdr { display: flex; align-items: center; gap: 8px; padding: 12px 16px 8px; }
  .tit { flex: 1; font-size: 1rem; font-weight: 600; color: var(--primary-text-color); }
  .stato { font-size: 0.72rem; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; color: var(--secondary-text-color); }
  .stato.live { color: #e53935; }
  .box { position: relative; width: 100%; aspect-ratio: 4 / 3;
    background: #10141a; display: flex; align-items: center; justify-content: center; }
  .box video { position: absolute; inset: 0; width: 100%; height: 100%;
    object-fit: contain; background: #000; z-index: 0; }
  .msg { position: absolute; inset: 0; z-index: 1; display: flex; gap: 10px;
    flex-direction: column; align-items: center; justify-content: center;
    padding: 18px; box-sizing: border-box; text-align: center;
    color: rgba(255,255,255,.86); font-size: 0.86rem; line-height: 1.45;
    background: #10141a; }
  .msg.off { display: none; }
  .msg ha-icon { --mdc-icon-size: 34px; opacity: .75; }
  .avvia { display: inline-flex; align-items: center; gap: 8px; border: none;
    border-radius: 999px; cursor: pointer; padding: 11px 20px; font: inherit;
    font-weight: 600; font-size: 0.9rem; background: #2f7d4f; color: #fff; }
  .avvia:hover { background: #276a43; }
  .avvia.grigio { background: rgba(255,255,255,.16); }
  .sotto { min-height: 60px; box-sizing: border-box; }
  .barra { display: flex; align-items: center; gap: 8px; padding: 10px 12px;
    min-height: 60px; box-sizing: border-box; }
  .conto { font-variant-numeric: tabular-nums; font-size: 0.85rem; font-weight: 600;
    color: var(--secondary-text-color); margin-right: auto; padding-left: 4px; }
  .tondo { width: 40px; height: 40px; border-radius: 50%; border: none; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
    background: var(--secondary-background-color, rgba(0,0,0,.06));
    color: var(--primary-text-color); --mdc-icon-size: 20px; }
  .tondo.stop { background: #c62828; color: #fff; }
  .tondo:hover { filter: brightness(.94); }
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
      else if (act === 'prolunga') this._prolunga();
      else if (act === 'audio') this._audio();
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

      const vecchio = this._root.getElementById('msg');
      if (vecchio) vecchio.remove();
      const msg = (html, cls) => {
        const d = document.createElement('div');
        d.className = 'msg' + (cls ? ' ' + cls : '');
        d.id = 'msg';
        d.innerHTML = html;
        box.appendChild(d);
      };

      if (this._stato === 'idle') {
        msg(`<ha-icon icon="mdi:cctv"></ha-icon>
             <div>Guarda e ascolta cosa vede il citofono.</div>
             <button class="avvia" data-act="avvia">
               <ha-icon icon="mdi:play"></ha-icon>Guarda ora
             </button>`);
      } else if (this._stato === 'avvio' || this._stato === 'attesa') {
        msg(`<ha-icon icon="mdi:video-wireless-outline"></ha-icon>
             <div>Sto accendendo la telecamera.</div>`);
      } else if (this._stato === 'live') {
        msg('', 'off');
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
             <div>C\u2019è una chiamata in corso: le immagini sono nella
             videochiamata.</div>
             <button class="avvia" data-act="chiamata">
               <ha-icon icon="mdi:video"></ha-icon>Apri la videochiamata
             </button>`);
      }

      if (this._stato === 'live' || this._stato === 'attesa' || this._stato === 'avvio') {
        const resto = this._stato === 'live'
          ? mmss(Math.max(0, this._deadline - Date.now())) : '';
        const icAudio = SESS.audio ? 'mdi:volume-high' : 'mdi:volume-off';
        sotto.innerHTML = `
<div class="barra">
  <span class="conto" id="conto">${resto}</span>
  <button class="tondo" id="btn-audio" data-act="audio" title="${SESS.audio ? 'Muto' : 'Audio'}">
    <ha-icon icon="${icAudio}"></ha-icon>
  </button>
  <button class="tondo" data-act="prolunga" title="Aggiungi tempo">
    <ha-icon icon="mdi:timer-plus-outline"></ha-icon>
  </button>
  <button class="tondo stop" data-act="ferma" title="Chiudi l\u2019anteprima">
    <ha-icon icon="mdi:stop"></ha-icon>
  </button>
</div>`;
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
