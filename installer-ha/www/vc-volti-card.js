/* Videocitofono - Card gestione volti riconoscimento facciale.
 *
 * Custom card vanilla per:
 *  - caricare una nuova foto + nome + genere (M/F)
 *  - vedere la lista delle persone registrate (con conteggio foto e genere)
 *  - modificare il genere di una persona registrata (Bentornato/Bentornata)
 *  - aggiungere altre foto a una persona esistente
 *  - eliminare una persona (rimuove tutte le sue foto + meta)
 *
 * Storage: i volti sono memorizzati sul RPi (data/faces/<nome>/), NON su HA.
 * La card pubblica le richieste via service pyscript -> MQTT verso il RPi.
 *
 * Stato letto da sensor.videocitofono_volti
 *   attributi: { volti: [{nome, foto, genere}, ...] }
 * popolato dal topic MQTT retain videocitofono/volti/library.
 *
 * Service pyscript:
 *  - pyscript.videocitofono_enroll_volto(nome, content_b64, ext, genere)
 *  - pyscript.videocitofono_update_volto(nome, genere)
 *  - pyscript.videocitofono_delete_volto(nome)
 *  - pyscript.videocitofono_refresh_volti
 */

const ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_BYTES = 8 * 1024 * 1024;
const RESIZE_MAX = 640;
const RESIZE_QUALITY = 0.82;
const SENSOR = 'sensor.videocitofono_volti';

function _g(label) {
  // Etichetta human-friendly del genere.
  if (label === 'M') return 'Maschile';
  if (label === 'F') return 'Femminile';
  return 'Non specificato';
}

class VcVoltiCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._rendered = false;
    this._busy = false;
    this._lastKey = '';
    this._editing = null;  // nome utente in editing inline (o null)
  }

  setConfig(config) {
    this._config = Object.assign({ title: 'Riconoscimento facciale' }, config || {});
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) this._render();
    this._refreshIfChanged();
  }

  getCardSize() { return 6; }

  _voltiList() {
    if (!this._hass) return [];
    const st = this._hass.states[SENSOR];
    if (!st) return [];
    const v = st.attributes && st.attributes.volti;
    return Array.isArray(v) ? v : [];
  }

  _refreshIfChanged() {
    const list = this._voltiList();
    const key = JSON.stringify(list) + '|' + this._busy + '|' + (this._editing || '');
    if (key === this._lastKey) return;
    this._lastKey = key;
    this._renderList();
  }

  _render() {
    this._rendered = true;
    const r = this.shadowRoot;
    r.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 14px; }
        h3 { margin: 0 0 6px 0; font-size: 16px; font-weight: 500; color: var(--primary-text-color); }
        .hint { color: var(--secondary-text-color); font-size: 12px; margin-bottom: 12px; line-height: 1.4; }
        .form { display: grid; gap: 10px; grid-template-columns: 1fr; margin-bottom: 14px; }
        @media (min-width: 640px) { .form { grid-template-columns: 1fr 140px 160px; align-items: end; } }
        label { display: block; font-size: 12px; color: var(--secondary-text-color); margin-bottom: 4px; }
        input[type=text], select {
          width: 100%; box-sizing: border-box; padding: 10px 12px; border-radius: 8px;
          border: 1px solid var(--divider-color); background: var(--card-background-color);
          color: var(--primary-text-color); font-size: 14px;
        }
        .file-row { display: flex; gap: 8px; align-items: center; }
        .pick-btn, .add-btn, .save-btn, .cancel-btn {
          padding: 10px 14px; border: none; border-radius: 8px; cursor: pointer;
          font-size: 13px; font-weight: 500;
        }
        .pick-btn { background: var(--secondary-background-color); color: var(--primary-text-color); }
        .add-btn { background: var(--primary-color); color: var(--text-primary-color, #fff); width: 100%; }
        .add-btn[disabled] { opacity: .5; cursor: not-allowed; }
        .file-name { color: var(--secondary-text-color); font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .status { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 10px; min-height: 18px; }
        .status.error { color: var(--error-color, #c00); }
        .status.success { color: var(--success-color, #2a7); }
        .list { display: grid; gap: 6px; }
        .row { display: flex; align-items: center; gap: 10px; padding: 10px 12px;
               background: var(--secondary-background-color); border-radius: 8px;
               flex-wrap: wrap; }
        .row .name { flex: 1 1 160px; font-weight: 500; color: var(--primary-text-color); font-size: 14px; }
        .row .meta { color: var(--secondary-text-color); font-size: 12px; flex: 0 0 auto; }
        .row .meta.f { color: var(--success-color, #c4a); }
        .row .meta.m { color: var(--info-color, #2a7); }
        .row button { background: transparent; border: 1px solid var(--divider-color); color: var(--primary-text-color);
                       padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; }
        .row button.del { color: var(--error-color, #c00); border-color: var(--error-color, #c00); }
        .row button.edit { color: var(--primary-color); border-color: var(--primary-color); }
        .row .edit-form { flex: 1 1 100%; display: flex; gap: 8px; align-items: center; padding-top: 8px; flex-wrap: wrap; }
        .row .edit-form input[type=text] { flex: 1; min-width: 140px; }
        .row .edit-form select { flex: 1; min-width: 140px; max-width: 220px; }
        .row .edit-form .edit-pin { max-width: 180px; }
        .row .edit-form label.cb { font-size: 12px; color: var(--secondary-text-color);
                                    display: flex; align-items: center; gap: 4px; }
        .save-btn { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        .cancel-btn { background: var(--secondary-background-color); color: var(--primary-text-color); }
        .empty { color: var(--secondary-text-color); font-size: 13px; padding: 8px 4px; }
        input[type=file] { display: none; }
      </style>
      <ha-card>
        <h3>${this._config.title}</h3>
        <div class="hint">Carica foto frontali ben illuminate, un solo volto per immagine. Indica il genere per personalizzare il saluto (Bentornato / Bentornata). Per maggiore accuratezza registra 3-5 foto per persona da angolazioni leggermente diverse.</div>

        <div class="form">
          <div>
            <label>Nome persona</label>
            <input id="nome" type="text" placeholder="es. Anna" maxlength="64" />
          </div>
          <div>
            <label>Genere</label>
            <select id="genere">
              <option value="">— non specificato —</option>
              <option value="F">Femminile</option>
              <option value="M">Maschile</option>
            </select>
          </div>
          <div>
            <label>Foto</label>
            <div class="file-row">
              <button class="pick-btn" id="pick">Scegli...</button>
              <span class="file-name" id="filename">nessuna selezionata</span>
            </div>
            <input type="file" id="file" accept="image/jpeg,image/png,image/webp" />
          </div>
        </div>
        <button class="add-btn" id="add">Aggiungi volto</button>
        <div class="status" id="status"></div>

        <h3 style="margin-top:14px">Persone registrate</h3>
        <div class="list" id="list"></div>
      </ha-card>
    `;
    const $ = sel => r.querySelector(sel);
    $('#pick').addEventListener('click', e => { e.preventDefault(); $('#file').click(); });
    $('#file').addEventListener('change', () => {
      const f = $('#file').files[0];
      $('#filename').textContent = f ? f.name : 'nessuna selezionata';
    });
    $('#add').addEventListener('click', () => this._onAdd());
    this._renderList();
  }

  _renderList() {
    if (!this.shadowRoot) return;
    const list = this._voltiList();
    const el = this.shadowRoot.getElementById('list');
    if (!el) return;
    if (!list.length) {
      el.innerHTML = `<div class="empty">Nessun volto registrato.</div>`;
      return;
    }
    el.innerHTML = list.map(v => {
      const g = (v.genere || '').toUpperCase();
      const nomeClean = v.nome.replace(/_/g, ' ');
      const nomeCleanEsc = this._escape(nomeClean);
      const pinSet = !!v.pin_set;
      const meta = `${v.foto} foto • ${_g(g)} • ${pinSet ? 'PIN impostato' : 'senza PIN'}`;
      const cls = g === 'F' ? 'f' : g === 'M' ? 'm' : '';
      const editing = this._editing === v.nome;
      const editForm = editing ? `
        <div class="edit-form">
          <input class="edit-nome" type="text" value="${nomeCleanEsc}" placeholder="Nome" maxlength="64" />
          <select class="edit-genere">
            <option value="" ${g === '' ? 'selected' : ''}>— non specificato —</option>
            <option value="F" ${g === 'F' ? 'selected' : ''}>Femminile</option>
            <option value="M" ${g === 'M' ? 'selected' : ''}>Maschile</option>
          </select>
          <input class="edit-pin" type="text" inputmode="numeric" pattern="[0-9]*"
                 placeholder="${pinSet ? 'lascia vuoto per non cambiare' : 'PIN 4-8 cifre (opz.)'}"
                 maxlength="8" />
          ${pinSet ? '<label class="cb"><input type="checkbox" class="edit-clear-pin"> rimuovi PIN</label>' : ''}
          <button class="save-btn save">Salva</button>
          <button class="cancel-btn cancel">Annulla</button>
        </div>` : '';
      return `
        <div class="row" data-nome="${this._escape(v.nome)}">
          <span class="name">${nomeCleanEsc}</span>
          <span class="meta ${cls}">${this._escape(meta)}</span>
          ${editing ? '' : `<button class="edit">Modifica</button><button class="del">Elimina</button>`}
          ${editForm}
        </div>
      `;
    }).join('');
    el.querySelectorAll('.row').forEach(row => {
      const nome = row.getAttribute('data-nome');
      const editBtn = row.querySelector('.edit');
      const delBtn = row.querySelector('.del');
      const saveBtn = row.querySelector('.save');
      const cancelBtn = row.querySelector('.cancel');
      if (editBtn) editBtn.addEventListener('click', () => { this._editing = nome; this._lastKey = ''; this._renderList(); });
      if (delBtn) delBtn.addEventListener('click', () => this._onDelete(nome));
      if (saveBtn) {
        saveBtn.addEventListener('click', () => {
          const inp = row.querySelector('.edit-nome');
          const sel = row.querySelector('.edit-genere');
          const pinInp = row.querySelector('.edit-pin');
          const clearCb = row.querySelector('.edit-clear-pin');
          const newName = inp ? inp.value.trim() : '';
          const g = sel ? sel.value : '';
          const pin = pinInp ? pinInp.value.replace(/\D/g, '') : '';
          const clearPin = !!(clearCb && clearCb.checked);
          this._onSaveEdit(nome, newName, g, pin, clearPin);
        });
      }
      if (cancelBtn) cancelBtn.addEventListener('click', () => { this._editing = null; this._lastKey = ''; this._renderList(); });
    });
  }

  _escape(s) {
    return String(s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  }

  _setStatus(msg, kind = '') {
    const el = this.shadowRoot.getElementById('status');
    if (!el) return;
    el.textContent = msg || '';
    el.className = 'status' + (kind ? ' ' + kind : '');
  }

  async _onAdd() {
    if (this._busy) return;
    const r = this.shadowRoot;
    const nome = (r.getElementById('nome').value || '').trim();
    const file = r.getElementById('file').files[0];
    const genere = (r.getElementById('genere').value || '').trim();
    if (!nome) { this._setStatus('Inserisci il nome della persona', 'error'); return; }
    if (!file) { this._setStatus('Seleziona una foto', 'error'); return; }
    if (!ALLOWED.includes(file.type)) { this._setStatus('Formato non supportato (JPEG/PNG/WEBP)', 'error'); return; }
    if (file.size > MAX_BYTES) { this._setStatus(`File troppo grande (max ${(MAX_BYTES / 1024 / 1024).toFixed(0)} MB)`, 'error'); return; }
    this._busy = true;
    this._setStatus('Ridimensiono e carico...');
    try {
      const { b64, ext } = await this._resizeToBase64(file);
      const sizeKB = Math.round(b64.length * 0.75 / 1024);
      this._setStatus(`Caricamento (${sizeKB} KB)...`);
      const args = { nome, content_b64: b64, ext };
      if (genere) args.genere = genere;
      try {
        await this._hass.callService('pyscript', 'videocitofono_enroll_volto', args);
      } catch (wsErr) {
        console.warn('vc-volti: WS fallita, fallback HTTP', wsErr);
        const resp = await fetch('/api/services/pyscript/videocitofono_enroll_volto', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this._hass.auth?.data?.access_token || ''}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(args),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      }
      this._setStatus('Richiesta inviata. La foto verra\' aggiunta a breve.', 'success');
      r.getElementById('nome').value = '';
      r.getElementById('genere').value = '';
      r.getElementById('file').value = '';
      r.getElementById('filename').textContent = 'nessuna selezionata';
      setTimeout(() => {
        try { this._hass.callService('pyscript', 'videocitofono_refresh_volti', {}); } catch (e) {}
      }, 2500);
    } catch (e) {
      this._setStatus('Errore: ' + (e && e.message ? e.message : e), 'error');
    } finally {
      this._busy = false;
    }
  }

  async _onSaveEdit(nome, newName, genere, pin, clearPin) {
    if (this._busy) return;
    if (pin && (pin.length < 4 || pin.length > 8)) {
      this._setStatus('PIN: 4-8 cifre numeriche', 'error');
      return;
    }
    this._busy = true;
    this._setStatus('Salvataggio...');
    try {
      // 1) Se il nome e' cambiato, fai prima il rename (sposta cartella).
      const safeNew = (newName || '').replace(/\s+/g, '_').replace(/[^A-Za-z0-9_\-]/g, '');
      const renaming = safeNew && safeNew !== nome;
      let currentName = nome;
      if (renaming) {
        await this._hass.callService('pyscript', 'videocitofono_rename_volto', {
          nome,
          nuovo_nome: safeNew,
        });
        currentName = safeNew;
        await new Promise(r => setTimeout(r, 600));
      }
      // 2) Aggiorna il genere (sul nome eventualmente nuovo).
      await this._hass.callService('pyscript', 'videocitofono_update_volto', {
        nome: currentName,
        genere,
      });
      // 3) Gestione PIN: rimozione esplicita ha priorita'; altrimenti se
      // il PIN e' stato digitato lo impostiamo. Se il campo e' vuoto e
      // non c'e' clearPin -> nessuna modifica al PIN esistente.
      if (clearPin) {
        await this._hass.callService('pyscript', 'videocitofono_set_volto_pin', {
          nome: currentName, pin: '',
        });
      } else if (pin) {
        await this._hass.callService('pyscript', 'videocitofono_set_volto_pin', {
          nome: currentName, pin,
        });
      }
      this._editing = null;
      this._setStatus(renaming ? 'Salvato (con rinomina)' : 'Salvato', 'success');
      setTimeout(() => {
        try { this._hass.callService('pyscript', 'videocitofono_refresh_volti', {}); } catch (e) {}
      }, 800);
    } catch (e) {
      this._setStatus('Errore: ' + (e && e.message ? e.message : e), 'error');
    } finally {
      this._busy = false;
      this._lastKey = '';
      this._renderList();
    }
  }

  async _onDelete(nome) {
    if (this._busy) return;
    if (!confirm(`Eliminare tutte le foto di "${nome.replace(/_/g, ' ')}"?`)) return;
    this._busy = true;
    this._setStatus('Eliminazione in corso...');
    try {
      await this._hass.callService('pyscript', 'videocitofono_delete_volto', { nome });
      this._setStatus('Eliminato', 'success');
      setTimeout(() => {
        try { this._hass.callService('pyscript', 'videocitofono_refresh_volti', {}); } catch (e) {}
      }, 1500);
    } catch (e) {
      this._setStatus('Errore: ' + (e && e.message ? e.message : e), 'error');
    } finally {
      this._busy = false;
    }
  }

  _toBase64(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => {
        const s = r.result || '';
        const i = s.indexOf(',');
        resolve(i >= 0 ? s.substring(i + 1) : s);
      };
      r.onerror = () => reject(r.error);
      r.readAsDataURL(file);
    });
  }

  _resizeToBase64(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        try {
          const w0 = img.naturalWidth, h0 = img.naturalHeight;
          const longest = Math.max(w0, h0);
          const scale = longest > RESIZE_MAX ? RESIZE_MAX / longest : 1;
          const w = Math.round(w0 * scale), h = Math.round(h0 * scale);
          const canvas = document.createElement('canvas');
          canvas.width = w; canvas.height = h;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, w, h);
          URL.revokeObjectURL(url);
          canvas.toBlob(async (blob) => {
            if (!blob) { reject(new Error('toBlob fallito')); return; }
            const r = new FileReader();
            r.onload = () => {
              const s = r.result || '';
              const i = s.indexOf(',');
              resolve({ b64: i >= 0 ? s.substring(i + 1) : s, ext: '.jpg' });
            };
            r.onerror = () => reject(r.error);
            r.readAsDataURL(blob);
          }, 'image/jpeg', RESIZE_QUALITY);
        } catch (e) {
          URL.revokeObjectURL(url);
          reject(e);
        }
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decodifica immagine fallita')); };
      img.src = url;
    });
  }
}

customElements.define('vc-volti-card', VcVoltiCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'vc-volti-card',
  name: 'VC Volti Card',
  description: 'Gestione volti riconoscimento facciale (RPi)',
});
