/* Videocitofono - Card libreria icone (avatar campanelli)
 *
 * Custom card vanilla (no LitElement) per:
 *  - caricare nuove icone (drag&drop o file picker, multi)
 *  - mostrare galleria delle icone presenti in /config/www/vc-icone/
 *  - assegnare un'icona a uno dei 4 campanelli (input_select.videocitofono_campanelloN_icona)
 *  - eliminare un'icona
 *
 * Backend pyscript service:
 *  - pyscript.videocitofono_upload_icona (filename, content_b64)
 *  - pyscript.videocitofono_delete_icona (filename)
 *  - pyscript.videocitofono_refresh_icone
 *
 * Le opzioni dei 4 input_select.videocitofono_campanelloN_icona sono allineate
 * dal pyscript dopo ogni upload/delete; la fonte di verita' dei file disponibili
 * e' input_select.videocitofono_campanello1_icona (tutti e 4 condividono la
 * stessa lista).
 *
 * Uso in Lovelace:
 *   - type: custom:vc-icone-card
 *     title: "Libreria icone"
 *     targets:
 *       - entity: input_select.videocitofono_campanello1_icona
 *         label: "Campanello 1"
 *       - entity: input_select.videocitofono_campanello2_icona
 *         label: "Campanello 2"
 *       - entity: input_select.videocitofono_campanello3_icona
 *         label: "Campanello 3"
 *       - entity: input_select.videocitofono_campanello4_icona
 *         label: "Campanello 4"
 */

const BASE_URL = '/local/vc-icone/';
const ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_BYTES = 4 * 1024 * 1024;

class VcIconeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._rendered = false;
    this._busy = false;
    this._activeTarget = 0;
  }

  setConfig(config) {
    const defaultTargets = [1, 2, 3, 4].map(n => ({
      entity: `input_select.videocitofono_campanello${n}_icona`,
      label: `Campanello ${n}`,
    }));
    this._config = Object.assign(
      { title: 'Libreria icone', targets: defaultTargets },
      config || {}
    );
    if (!Array.isArray(this._config.targets) || !this._config.targets.length) {
      this._config.targets = defaultTargets;
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) this._render();
    this._refreshIfChanged();
  }

  getCardSize() { return 6; }

  _refreshIfChanged() {
    if (!this._hass) return;
    const targets = this._config.targets;
    const states = targets.map(t => {
      const st = this._hass.states[t.entity];
      return st ? st.state : '';
    });
    const opts = (() => {
      for (const t of targets) {
        const st = this._hass.states[t.entity];
        if (st && st.attributes && st.attributes.options) return st.attributes.options;
      }
      return ['default'];
    })();
    const key = JSON.stringify(opts) + '|' + states.join(',') + '|' + this._activeTarget;
    if (key === this._lastKey) return;
    this._lastKey = key;
    this._lastOptions = opts;
    this._lastStates = states;
    this._renderTargets();
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
        .targets {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 6px;
          margin-bottom: 12px;
        }
        .target-btn {
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          border: 2px solid transparent;
          border-radius: 10px;
          padding: 8px 10px;
          cursor: pointer;
          font-size: 13px;
          display: flex;
          align-items: center;
          gap: 8px;
          text-align: left;
          transition: border-color .15s, background .15s;
        }
        .target-btn.active { border-color: var(--primary-color); background: var(--card-background-color); }
        .target-btn .preview {
          width: 32px; height: 32px; flex: 0 0 32px;
          border-radius: 50%; background: var(--divider-color);
          overflow: hidden; display: flex; align-items: center; justify-content: center;
          font-size: 11px; color: var(--secondary-text-color);
        }
        .target-btn .preview img { width: 100%; height: 100%; object-fit: cover; }
        .target-btn .meta { display: flex; flex-direction: column; line-height: 1.15; min-width: 0; }
        .target-btn .meta .lbl { font-weight: 600; }
        .target-btn .meta .cur { font-size: 11px; color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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
          grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
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
          color: #cfd2dc; font-size: 13px;
          background: linear-gradient(135deg, #2a2f4a 0%, #1f2235 100%);
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
        <div class="hint">Seleziona prima il campanello da aggiornare, poi clicca un'icona per assegnarla. JPG/PNG/WEBP, max 4 MB.</div>
        <div class="targets" id="targets"></div>
        <label class="drop" id="drop">
          <input type="file" id="file" accept="image/jpeg,image/png,image/webp" multiple />
          <div>Trascina i file qui oppure <b>clicca per scegliere</b></div>
        </label>
        <div id="grid" class="grid"></div>
        <div class="toast" id="toast"></div>
      </ha-card>
    `;
    r.getElementById('title').textContent = this._config.title || 'Libreria icone';
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

  _renderTargets() {
    const root = this.shadowRoot.getElementById('targets');
    if (!root) return;
    const targets = this._config.targets;
    root.innerHTML = '';
    targets.forEach((t, idx) => {
      const cur = (this._lastStates && this._lastStates[idx]) || 'default';
      const btn = document.createElement('button');
      btn.className = 'target-btn' + (idx === this._activeTarget ? ' active' : '');
      btn.type = 'button';
      btn.addEventListener('click', () => {
        this._activeTarget = idx;
        this._lastKey = null;
        this._refreshIfChanged();
      });
      const preview = document.createElement('div');
      preview.className = 'preview';
      if (cur && cur !== 'default') {
        const img = document.createElement('img');
        img.loading = 'lazy';
        img.src = BASE_URL + encodeURIComponent(cur) + '?t=' + Date.now();
        img.onerror = () => { preview.textContent = '?'; };
        preview.appendChild(img);
      } else {
        preview.textContent = '–';
      }
      const meta = document.createElement('div');
      meta.className = 'meta';
      const lbl = document.createElement('span');
      lbl.className = 'lbl';
      lbl.textContent = t.label || t.entity;
      const sub = document.createElement('span');
      sub.className = 'cur';
      sub.textContent = cur && cur !== 'default' ? cur : 'nessuna icona';
      meta.appendChild(lbl);
      meta.appendChild(sub);
      btn.appendChild(preview);
      btn.appendChild(meta);
      root.appendChild(btn);
    });
  }

  _renderGallery() {
    const grid = this.shadowRoot.getElementById('grid');
    if (!grid) return;
    const opts = this._lastOptions || ['default'];
    const targets = this._config.targets;
    const cur = (this._lastStates && this._lastStates[this._activeTarget]) || 'default';
    if (!opts.length) {
      grid.innerHTML = '<div class="empty">Nessuna icona caricata.</div>';
      return;
    }
    grid.innerHTML = '';
    for (const name of opts) {
      const tile = document.createElement('div');
      const isDefault = (name === 'default');
      tile.className = 'tile' + (name === cur ? ' selected' : '') + (isDefault ? ' default' : '');
      tile.title = name;
      tile.addEventListener('click', () => this._selectIcona(name));
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
        tile.textContent = 'Default (iniziali)';
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

  async _selectIcona(name) {
    if (!this._hass) return;
    const target = this._config.targets[this._activeTarget];
    if (!target) return;
    try {
      await this._hass.callService('input_select', 'select_option', {
        entity_id: target.entity, option: name,
      });
      this._toast(`${target.label}: ${name}`);
    } catch (e) {
      this._toast('Errore selezione: ' + (e.message || e), true);
    }
  }

  async _delete(name) {
    if (!this._hass) return;
    if (!confirm(`Eliminare l'icona "${name}"?`)) return;
    try {
      await this._hass.callService('pyscript', 'videocitofono_delete_icona', { filename: name });
      this._toast(`Eliminata: ${name}`);
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
      if (f.size > MAX_BYTES) { errs.push(`${f.name}: troppo grande (>4MB)`); continue; }
      try {
        const b64 = await this._readAsB64(f);
        await this._hass.callService('pyscript', 'videocitofono_upload_icona', {
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
    if (lastUploaded) {
      const safe = this._sanitize(lastUploaded);
      setTimeout(() => {
        const target = this._config.targets[this._activeTarget];
        const st = target ? this._hass.states[target.entity] : null;
        const opts = (st && st.attributes && st.attributes.options) || [];
        const match = opts.find(o => o === safe);
        if (match) {
          this._selectIcona(match);
          if (ok) this._toast(`Caricata e assegnata: ${match}`);
        } else if (ok) {
          this._toast(`Caricate ${ok} icone (clicca per assegnare)`);
        }
      }, 1800);
    } else if (ok) {
      this._toast(`Caricate ${ok} icone`);
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

if (!customElements.get('vc-icone-card')) {
  customElements.define('vc-icone-card', VcIconeCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'vc-icone-card',
  name: 'Videocitofono Icone',
  description: 'Galleria + uploader icone avatar campanelli videocitofono',
});
