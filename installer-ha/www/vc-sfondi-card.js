/* Videocitofono - Card libreria sfondi
 *
 * Custom card vanilla (no LitElement) per:
 *  - caricare nuovi sfondi (drag&drop o file picker, multi)
 *  - mostrare galleria (thumbnail) degli sfondi presenti in /config/www/vc-sfondi/
 *  - selezionare lo sfondo corrente (aggiorna input_select.videocitofono_sfondo)
 *  - eliminare uno sfondo
 *
 * Backend: pyscript service
 *  - pyscript.videocitofono_upload_sfondo (filename, content_b64)
 *  - pyscript.videocitofono_delete_sfondo (filename)
 *  - pyscript.videocitofono_refresh_sfondi
 *
 * Le opzioni di input_select.videocitofono_sfondo sono la fonte di verità
 * per la lista; il pyscript le ripopola dopo ogni upload/delete.
 *
 * Uso in Lovelace:
 *   - type: custom:vc-sfondi-card
 *     entity: input_select.videocitofono_sfondo
 *     title: "Libreria sfondi"
 */

const ENTITY = 'input_select.videocitofono_sfondo';
const BASE_URL = '/local/vc-sfondi/';
const ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_BYTES = 8 * 1024 * 1024;

class VcSfondiCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._rendered = false;
    this._lastOptions = null;
    this._lastState = null;
    this._busy = false;
  }

  setConfig(config) {
    this._config = Object.assign({ entity: ENTITY, title: 'Libreria sfondi' }, config || {});
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) this._render();
    this._refreshIfChanged();
  }

  getCardSize() { return 5; }

  _refreshIfChanged() {
    if (!this._hass) return;
    const st = this._hass.states[this._config.entity];
    if (!st) return;
    const opts = (st.attributes && st.attributes.options) || ['default'];
    const cur = st.state || 'default';
    const key = JSON.stringify(opts) + '|' + cur;
    if (key === this._lastKey) return;
    this._lastKey = key;
    this._lastOptions = opts;
    this._lastState = cur;
    this._renderGallery();
  }

  _render() {
    this._rendered = true;
    const r = this.shadowRoot;
    r.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 12px; }
        h3 { margin: 0 0 8px 0; font-size: 16px; font-weight: 500; color: var(--primary-text-color); }
        .hint { color: var(--secondary-text-color); font-size: 12px; margin-bottom: 10px; }
        .drop {
          border: 2px dashed var(--divider-color);
          border-radius: 12px;
          padding: 18px;
          text-align: center;
          color: var(--secondary-text-color);
          cursor: pointer;
          transition: background .15s, border-color .15s;
          margin-bottom: 12px;
        }
        .drop.over { border-color: var(--primary-color); background: var(--secondary-background-color); }
        .drop input { display: none; }
        .drop b { color: var(--primary-color); }
        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
          gap: 10px;
        }
        .tile {
          position: relative;
          border-radius: 10px;
          overflow: hidden;
          background: var(--secondary-background-color);
          aspect-ratio: 1 / 1;
          cursor: pointer;
          border: 2px solid transparent;
          transition: border-color .15s, transform .15s;
        }
        .tile:hover { transform: scale(1.02); }
        .tile.selected { border-color: var(--primary-color); }
        .tile.default {
          display: flex; align-items: center; justify-content: center;
          color: var(--secondary-text-color); font-size: 13px;
          background: linear-gradient(135deg, #1f2235 0%, #2a2f4a 100%);
          color: #cfd2dc;
        }
        .tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
        .tile .name {
          position: absolute; left: 0; right: 0; bottom: 0;
          background: linear-gradient(to top, rgba(0,0,0,.7), rgba(0,0,0,0));
          color: white; font-size: 11px; padding: 12px 6px 4px;
          text-overflow: ellipsis; white-space: nowrap; overflow: hidden;
        }
        .tile .badge {
          position: absolute; top: 4px; left: 4px;
          background: var(--primary-color); color: white;
          font-size: 10px; padding: 2px 6px; border-radius: 8px;
          font-weight: 600;
        }
        .tile button.del {
          position: absolute; top: 4px; right: 4px;
          background: rgba(0,0,0,.55); color: white;
          border: none; border-radius: 50%;
          width: 24px; height: 24px; cursor: pointer;
          font-size: 14px; line-height: 1;
        }
        .tile button.del:hover { background: #c0392b; }
        .empty { color: var(--secondary-text-color); font-style: italic; padding: 8px 0; }
        .toast {
          position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
          background: var(--primary-color); color: white;
          padding: 10px 18px; border-radius: 8px; z-index: 9999;
          box-shadow: 0 4px 12px rgba(0,0,0,.2); font-size: 14px;
          opacity: 0; transition: opacity .2s;
        }
        .toast.show { opacity: 1; }
        .toast.error { background: #c0392b; }
      </style>
      <ha-card>
        <h3 id="title"></h3>
        <div class="hint">JPG/PNG/WEBP, max 8 MB. Lo sfondo selezionato è mostrato sullo screensaver dell'unità esterna.</div>
        <label class="drop" id="drop">
          <input type="file" id="file" accept="image/jpeg,image/png,image/webp" multiple />
          <div>Trascina i file qui oppure <b>clicca per scegliere</b></div>
        </label>
        <div id="grid" class="grid"></div>
        <div class="toast" id="toast"></div>
      </ha-card>
    `;
    r.getElementById('title').textContent = this._config.title || 'Libreria sfondi';
    const drop = r.getElementById('drop');
    const fi = r.getElementById('file');
    fi.addEventListener('change', (e) => this._handleFiles(e.target.files));
    ['dragenter', 'dragover'].forEach(ev =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', (e) => {
      const files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) this._handleFiles(files);
    });
  }

  _renderGallery() {
    const grid = this.shadowRoot.getElementById('grid');
    if (!grid) return;
    const opts = this._lastOptions || ['default'];
    const cur = this._lastState || 'default';
    if (!opts.length) {
      grid.innerHTML = '<div class="empty">Nessuno sfondo caricato.</div>';
      return;
    }
    grid.innerHTML = '';
    for (const name of opts) {
      const tile = document.createElement('div');
      const isDefault = (name === 'default');
      tile.className = 'tile' + (name === cur ? ' selected' : '') + (isDefault ? ' default' : '');
      tile.title = name;
      tile.addEventListener('click', () => this._selectSfondo(name));
      if (!isDefault) {
        const img = document.createElement('img');
        img.loading = 'lazy';
        img.src = BASE_URL + encodeURIComponent(name) + '?t=' + Date.now();
        img.onerror = () => { tile.textContent = name; };
        tile.appendChild(img);
        const del = document.createElement('button');
        del.className = 'del';
        del.title = 'Elimina';
        del.textContent = '×';
        del.addEventListener('click', (e) => { e.stopPropagation(); this._delete(name); });
        tile.appendChild(del);
      } else {
        tile.textContent = 'Default (nessun sfondo)';
      }
      const lab = document.createElement('div');
      lab.className = 'name';
      lab.textContent = isDefault ? 'default' : name;
      tile.appendChild(lab);
      if (name === cur) {
        const b = document.createElement('div');
        b.className = 'badge';
        b.textContent = 'IN USO';
        tile.appendChild(b);
      }
      grid.appendChild(tile);
    }
  }

  async _selectSfondo(name) {
    if (!this._hass) return;
    try {
      await this._hass.callService('input_select', 'select_option', {
        entity_id: this._config.entity, option: name,
      });
      this._toast(`Selezionato: ${name}`);
    } catch (e) {
      this._toast('Errore selezione: ' + (e.message || e), true);
    }
  }

  async _delete(name) {
    if (!this._hass) return;
    if (!confirm(`Eliminare lo sfondo "${name}"?`)) return;
    try {
      await this._hass.callService('pyscript', 'videocitofono_delete_sfondo', { filename: name });
      this._toast(`Eliminato: ${name}`);
    } catch (e) {
      this._toast('Errore eliminazione: ' + (e.message || e), true);
    }
  }

  async _handleFiles(files) {
    if (!this._hass || !files || !files.length) return;
    if (this._busy) { this._toast('Upload in corso, attendi...', true); return; }
    this._busy = true;
    let ok = 0, errs = [];
    let lastUploaded = null;
    for (const f of Array.from(files)) {
      if (!ALLOWED.includes(f.type)) { errs.push(`${f.name}: formato non valido`); continue; }
      if (f.size > MAX_BYTES) { errs.push(`${f.name}: troppo grande (>8MB)`); continue; }
      try {
        const b64 = await this._readAsB64(f);
        await this._hass.callService('pyscript', 'videocitofono_upload_sfondo', {
          filename: f.name, content_b64: b64,
        });
        ok++;
        lastUploaded = f.name;
      } catch (e) {
        errs.push(`${f.name}: ${e.message || e}`);
      }
    }
    this._busy = false;
    this.shadowRoot.getElementById('file').value = '';
    if (errs.length) this._toast(errs.join(' | '), true);
    // Auto-seleziona l'ultimo sfondo caricato (replica della sanitize del pyscript)
    if (lastUploaded) {
      const safe = this._sanitize(lastUploaded);
      // ritardo: HA propaga le nuove options via state event
      setTimeout(() => {
        const st = this._hass.states[this._config.entity];
        const opts = (st && st.attributes && st.attributes.options) || [];
        const match = opts.find(o => o === safe) || opts.find(o => o !== 'default' && o !== st.state);
        if (match) {
          this._selectSfondo(match);
          if (ok) this._toast(`Caricato e selezionato: ${match}`);
        } else if (ok) {
          this._toast(`Caricati ${ok} sfondi (clicca per selezionare)`);
        }
      }, 1800);
    } else if (ok) {
      this._toast(`Caricati ${ok} sfondi`);
    }
  }

  _sanitize(filename) {
    let base = (filename || '').split('/').pop().split('\\').pop();
    base = base.replace(/ /g, '_').replace(/[^A-Za-z0-9._\-]/g, '');
    if (!base) return '';
    const i = base.lastIndexOf('.');
    if (i < 0) return base;
    const name = base.slice(0, i).slice(0, 60);
    const ext = base.slice(i).toLowerCase();
    return name + ext;
  }

  _readAsB64(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => {
        const s = String(r.result || '');
        const i = s.indexOf(',');
        resolve(i >= 0 ? s.slice(i + 1) : s);
      };
      r.onerror = () => reject(new Error('read error'));
      r.readAsDataURL(file);
    });
  }

  _toast(msg, isErr) {
    const t = this.shadowRoot.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'toast show' + (isErr ? ' error' : '');
    clearTimeout(this._toastTo);
    this._toastTo = setTimeout(() => { t.className = 'toast'; }, 3500);
  }
}

if (!customElements.get('vc-sfondi-card')) {
  customElements.define('vc-sfondi-card', VcSfondiCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'vc-sfondi-card',
  name: 'Videocitofono Sfondi',
  description: 'Galleria + uploader sfondi screensaver videocitofono',
});
