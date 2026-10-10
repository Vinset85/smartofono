/* Videocitofono - Registro chiamate con riproduzione della registrazione.
 *
 * Sostituisce la markdown card "Chiamate recenti": ogni voce con una
 * registrazione e' toccabile e apre il player a schermo pieno.
 *
 * Sorgente dati: attributo `all` di sensor.registro_videocitofono, cioe' il
 * file /config/www/registro_videocitofono.json scritto dal pyscript
 * update_registro_videocitofono. Il campo `video` e' un URL /local/... quindi
 * gia' servito da HA senza autenticazione aggiuntiva.
 *
 * Hanno un video solo le chiamate NON risposte: la retention (vedi
 * pyscript applica_retention_video_videocitofono) cancella la registrazione
 * appena risulta che qualcuno ha risposto o aperto. Le voci senza video non
 * sono toccabili.
 *
 * Uso in Lovelace:
 *   type: custom:vc-registro-card
 *   title: Chiamate recenti    # opzionale
 *   max: 10                    # opzionale, voci mostrate
 */

const VC_REG_BUILD = 'vc-registro-card 2026.08.17-1';
const VC_REG_SENSOR = 'sensor.registro_videocitofono';

const VC_REG_NOMI = {
  mario_rossi: 'Vincenzo Q.',
  giulia_bianchi: 'Stefania R.',
  famiglia_rossi: 'Fam. Rossi',
  famiglia_bianchi: 'Fam. Bianchi',
};

function vcRegNome(cid) {
  if (!cid) return 'Sconosciuto';
  if (VC_REG_NOMI[cid]) return VC_REG_NOMI[cid];
  return String(cid).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/* I timestamp del registro sono ISO senza timezone (datetime.now().isoformat(),
 * con microsecondi): Safari rifiuta le 6 cifre decimali, quindi si troncano ai
 * millisecondi. Senza suffisso Z la stringa e' interpretata come ora locale,
 * che e' quella con cui HA l'ha scritta. */
function vcRegDate(ts) {
  if (!ts) return null;
  const d = new Date(String(ts).trim().slice(0, 23));
  return isNaN(d.getTime()) ? null : d;
}

function vcRegQuando(d) {
  if (!d) return { ora: '--:--', giorno: '' };
  const pad = (n) => String(n).padStart(2, '0');
  const ora = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const oggi = new Date();
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const ieri = new Date(oggi.getTime() - 86400000);
  let giorno;
  if (sameDay(d, oggi)) giorno = 'oggi';
  else if (sameDay(d, ieri)) giorno = 'ieri';
  else giorno = `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
  return { ora, giorno };
}

function vcRegStato(rec) {
  const st = (rec.stato || '').trim();
  const az = (rec.azione || '').trim();
  if (st === 'risposto' && az === 'apertura') {
    return { label: 'Apertura', icon: 'mdi:door-open', tone: 'ok' };
  }
  if (st === 'risposto') {
    return {
      label: az === 'risposta_video' ? 'Risposto (video)' : 'Risposto',
      icon: 'mdi:phone-in-talk',
      tone: 'ok',
    };
  }
  if (st === 'persa') return { label: 'Persa', icon: 'mdi:phone-missed', tone: 'alert' };
  if (st === 'rifiutata') return { label: 'Rifiutata', icon: 'mdi:phone-cancel', tone: 'warn' };
  if (st === 'in_corso') return { label: 'In corso', icon: 'mdi:phone-ring', tone: 'live' };
  return { label: st || 'n/d', icon: 'mdi:phone', tone: 'warn' };
}

/* ---------------------------------------------------------------------------
 * Player: montato su document.body e non nello shadow root della card, cosi'
 * il position:fixed copre davvero il viewport anche quando la view Lovelace
 * crea un containing block (transform/contain sulle sezioni). Shadow root
 * dedicato per non ereditare il CSS del tema.
 * ------------------------------------------------------------------------- */
class VcRegPlayer {
  static open(url, titolo) {
    if (!VcRegPlayer._inst) VcRegPlayer._inst = new VcRegPlayer();
    VcRegPlayer._inst.show(url, titolo);
  }

  constructor() {
    this._host = document.createElement('div');
    this._host.id = 'vc-registro-player';
    this._root = this._host.attachShadow({ mode: 'open' });
    this._root.innerHTML = `
<style>
  .wrap {
    position: fixed; inset: 0; z-index: 99999;
    background: rgba(0,0,0,0.92);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 16px; box-sizing: border-box;
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
  }
  .bar {
    width: 100%; max-width: 900px;
    display: flex; align-items: center; gap: 12px;
    color: #fff; margin-bottom: 10px;
  }
  .tit { font-size: 1rem; font-weight: 600; flex: 1; }
  .x {
    width: 44px; height: 44px; border-radius: 50%;
    border: none; cursor: pointer; flex: none;
    background: rgba(255,255,255,0.16); color: #fff; font-size: 26px;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .x:hover { background: rgba(255,255,255,0.28); }
  video {
    width: 100%; max-width: 900px; max-height: 78vh;
    background: #000; border-radius: 12px;
    box-shadow: 0 8px 40px rgba(0,0,0,0.6);
  }
  .err {
    color: #fff; text-align: center; max-width: 520px;
    line-height: 1.5; font-size: 0.95rem;
  }
  .err small { display: block; opacity: 0.7; margin-top: 8px; }
  .hint {
    color: rgba(255,255,255,0.85); font-size: 0.85rem; margin-top: 10px;
    min-height: 1.2em;
  }
</style>
<div class="wrap" id="wrap">
  <div class="bar">
    <div class="tit" id="tit"></div>
    <button class="x" id="x" title="Chiudi">&times;</button>
  </div>
  <video id="video" controls playsinline preload="auto"></video>
  <div class="err" id="err" style="display:none"></div>
  <div class="hint" id="hint"></div>
</div>`;
    this._wrap = this._root.getElementById('wrap');
    this._video = this._root.getElementById('video');
    this._err = this._root.getElementById('err');
    this._hint = this._root.getElementById('hint');
    this._tit = this._root.getElementById('tit');
    this._root.getElementById('x').addEventListener('click', () => this.close());
    // Solo il click sul fondo scuro chiude: un click sul video (play/pause,
    // seek) non deve far sparire il player.
    this._wrap.addEventListener('click', (e) => {
      if (e.target === this._wrap) this.close();
    });
    this._onKey = (e) => { if (e.key === 'Escape') this.close(); };
    this._video.addEventListener('error', () => this._mostraErrore());
  }

  show(url, titolo) {
    if (!this._host.isConnected) document.body.appendChild(this._host);
    this._tit.textContent = titolo || 'Registrazione';
    this._err.style.display = 'none';
    this._hint.textContent = '';
    this._video.style.display = '';
    this._video.muted = false;
    this._video.src = url;
    document.addEventListener('keydown', this._onKey);
    // Il tap sulla voce e' un gesto utente, quindi l'autoplay con audio e'
    // permesso; su Fully Kiosk e webview restrittive puo' comunque essere
    // negato, allora si riprova muto invece di lasciare il player fermo.
    const p = this._video.play();
    if (p && typeof p.catch === 'function') {
      p.catch(() => {
        this._video.muted = true;
        this._video.play().then(() => {
          this._hint.textContent = 'Audio disattivato dal browser: attivalo dai comandi del video.';
        }).catch(() => {
          this._hint.textContent = 'Premi play per avviare la riproduzione.';
        });
      });
    }
  }

  _mostraErrore() {
    // Tipico: registrazione gia' rimossa dal purge a 7 giorni, o file mai
    // prodotto perche' l'egress era giu' quando la chiamata e' arrivata.
    this._video.style.display = 'none';
    this._err.style.display = '';
    this._err.innerHTML = 'Registrazione non disponibile.'
      + '<small>Il file potrebbe essere stato rimosso dalla pulizia automatica '
      + 'del registro.</small>';
  }

  close() {
    document.removeEventListener('keydown', this._onKey);
    try {
      this._video.pause();
      this._video.removeAttribute('src');
      this._video.load();
    } catch (_) { /* niente da fare */ }
    if (this._host.isConnected) document.body.removeChild(this._host);
  }
}

class VcRegistroCard extends HTMLElement {
  static getStubConfig() { return { title: 'Chiamate recenti', max: 10 }; }

  constructor() {
    super();
    this._root = this.attachShadow({ mode: 'open' });
    this._cfg = { title: 'Chiamate recenti', max: 10 };
    this._rendered = false;
    this._sig = '';
  }

  setConfig(config) {
    this._cfg = Object.assign({ title: 'Chiamate recenti', max: 10 }, config || {});
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) this._renderShell();
    this._refresh();
  }

  getCardSize() { return 6; }

  _records() {
    const st = this._hass && this._hass.states[VC_REG_SENSOR];
    if (!st) return null;
    if (st.state === 'unavailable' || st.state === 'unknown') return null;
    const all = st.attributes && st.attributes.all;
    return Array.isArray(all) ? all : null;
  }

  _renderShell() {
    this._rendered = true;
    this._root.innerHTML = `
<style>
  ha-card { padding: 8px 0 4px; overflow: hidden; }
  .hdr {
    padding: 12px 16px 8px; font-size: 1.1rem; font-weight: 500;
    color: var(--primary-text-color);
  }
  .empty {
    padding: 8px 16px 16px; color: var(--secondary-text-color);
    font-size: 0.9rem;
  }
  .row {
    display: flex; align-items: center; gap: 12px; width: 100%;
    padding: 10px 16px; border: none; background: none; text-align: left;
    font: inherit; color: var(--primary-text-color);
    border-top: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  }
  .row.play { cursor: pointer; }
  .row.play:hover { background: var(--secondary-background-color, rgba(0,0,0,0.04)); }
  .row.play:active { background: var(--divider-color, rgba(0,0,0,0.1)); }
  .ico { flex: none; --mdc-icon-size: 24px; }
  .ico.ok { color: var(--success-color, #2e7d32); }
  .ico.alert { color: var(--error-color, #c62828); }
  .ico.warn { color: var(--secondary-text-color); }
  .ico.live { color: var(--warning-color, #ef6c00); }
  .when { flex: none; width: 58px; line-height: 1.15; }
  .when b { font-size: 0.98rem; font-weight: 600; }
  .when small { display: block; font-size: 0.72rem; color: var(--secondary-text-color); }
  .mid { flex: 1; min-width: 0; line-height: 1.2; }
  .who {
    font-size: 0.95rem; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
  }
  .st { font-size: 0.78rem; color: var(--secondary-text-color); }
  .cta {
    flex: none; display: inline-flex; align-items: center; gap: 4px;
    color: var(--primary-color); font-size: 0.78rem; font-weight: 600;
    --mdc-icon-size: 20px;
  }
  .cta.none { color: var(--disabled-text-color, rgba(0,0,0,0.38)); font-weight: 400; }
</style>
<ha-card>
  <div class="hdr" id="hdr"></div>
  <div id="list"></div>
</ha-card>`;
    this._list = this._root.getElementById('list');
    this._hdr = this._root.getElementById('hdr');
  }

  _refresh() {
    const recs = this._records();
    const max = Math.max(1, parseInt(this._cfg.max, 10) || 10);
    const rows = recs ? recs.slice(-max).reverse() : [];
    // Ridisegno solo quando i dati cambiano davvero: `set hass` arriva a ogni
    // aggiornamento di stato dell'intera istanza HA.
    const sig = JSON.stringify([this._cfg.title, max, recs === null, rows]);
    if (sig === this._sig) return;
    this._sig = sig;

    this._hdr.textContent = this._cfg.title || '';
    if (recs === null) {
      this._list.innerHTML = '<div class="empty">Registro non disponibile: '
        + 'verifica il sensore <code>sensor.registro_videocitofono</code>.</div>';
      return;
    }
    if (!rows.length) {
      this._list.innerHTML = '<div class="empty">Nessuna chiamata registrata.</div>';
      return;
    }

    this._list.innerHTML = '';
    rows.forEach((rec) => {
      const info = vcRegStato(rec);
      const d = vcRegDate(rec.timestamp);
      const q = vcRegQuando(d);
      const video = (rec.video || '').trim();
      const nome = vcRegNome(rec.campanello);

      const row = document.createElement(video ? 'button' : 'div');
      row.className = 'row' + (video ? ' play' : '');
      row.innerHTML = `
  <ha-icon class="ico ${info.tone}" icon="${info.icon}"></ha-icon>
  <div class="when"><b>${q.ora}</b><small>${q.giorno}</small></div>
  <div class="mid">
    <div class="who">${nome}</div>
    <div class="st">${info.label}</div>
  </div>
  ${video
    ? '<span class="cta"><ha-icon icon="mdi:play-circle"></ha-icon>Video</span>'
    : '<span class="cta none">—</span>'}`;
      if (video) {
        const titolo = `${nome} — ${info.label} — ${q.giorno} ${q.ora}`;
        row.addEventListener('click', () => VcRegPlayer.open(video, titolo));
      }
      this._list.appendChild(row);
    });
  }
}

if (!customElements.get('vc-registro-card')) {
  customElements.define('vc-registro-card', VcRegistroCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'vc-registro-card',
    name: 'Videocitofono - Registro chiamate',
    description: 'Cronologia chiamate con riproduzione della registrazione',
  });
  console.info(`%c ${VC_REG_BUILD} `, 'background:#f97316;color:#fff');
}
