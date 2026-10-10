/* Videocitofono - Card gestione tag NFC (associa tag → utente sul RPi). */

const SENSOR = 'sensor.videocitofono_nfc';
const SENSOR_EVENTO = 'sensor.videocitofono_evento';
const SENSOR_VOLTI = 'sensor.videocitofono_volti';

function _fmtDate(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts * 1000);
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch (_e) { return ''; }
}

function _scopeLabel(s) {
  if (s === 'cancello') return 'Cancello';
  return 'Porta';
}

class VcNfcCard extends HTMLElement {
  static getStubConfig() {
    return {};
  }

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._rendered = false;
    this._busy = false;
    this._lastKey = '';
    this._enrollMsg = '';
    this._lastEvento = '';
    this._config = { title: 'Tag NFC' };
  }

  setConfig(config) {
    this._config = { title: 'Tag NFC' };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) this._render();
    this._handleEvento(hass);
    this._refreshIfChanged();
  }

  getCardSize() { return 5; }

  _items() {
    if (!this._hass) return [];
    const st = this._hass.states[SENSOR];
    if (!st) return [];
    const v = st.attributes && st.attributes.items;
    return Array.isArray(v) ? v : [];
  }

  _userNames() {
    if (!this._hass) return [];
    const st = this._hass.states[SENSOR_VOLTI];
    const volti = st && st.attributes && st.attributes.volti;
    if (!Array.isArray(volti)) return [];
    return volti.map((v) => (v && v.nome) ? String(v.nome).trim() : '')
      .filter(Boolean);
  }

  _handleEvento(hass) {
    const st = hass.states[SENSOR_EVENTO];
    if (!st) return;
    const tipo = st.state || '';
    const dati = st.attributes && st.attributes.dati;
    const key = tipo + JSON.stringify(dati || {});
    if (key === this._lastEvento) return;
    this._lastEvento = key;
    if (tipo === 'nfc_enroll_started') {
      const n = (dati && dati.nome) || '';
      this._showMsg(`Iscrizione avviata${n ? ` (${n})` : ''}: avvicina il tag al lettore`, 'info');
    } else if (tipo === 'nfc_enroll_done') {
      const uid = (dati && dati.uid) || '';
      const n = (dati && dati.nome) || '';
      this._showMsg(`Tag associato a ${n}${uid ? ` [${uid}]` : ''}`, 'info');
      this._busy = false;
      this._hass.callService('pyscript', 'videocitofono_nfc_refresh').catch(() => {});
    } else if (tipo === 'nfc_enroll_error') {
      const err = (dati && (dati.error || dati.motivo)) || 'errore';
      this._showMsg(`Iscrizione fallita: ${err}`, 'warn');
      this._busy = false;
    }
  }

  _refreshIfChanged() {
    const list = this._items();
    const ev = this._lastEvento;
    const key = JSON.stringify(list) + '|' + this._busy + '|' + this._enrollMsg + '|' + ev;
    if (key === this._lastKey) return;
    this._lastKey = key;
    this._fillUserSelect();
    this._renderList();
  }

  _fillUserSelect() {
    if (!this._rendered) return;
    const sel = this.shadowRoot.getElementById('nome');
    if (!sel || sel.tagName !== 'SELECT') return;
    const cur = sel.value;
    const names = this._userNames();
    sel.innerHTML = '<option value="">— Seleziona utente —</option>';
    for (const n of names) {
      const o = document.createElement('option');
      o.value = n;
      o.textContent = n;
      sel.appendChild(o);
    }
    const oAlt = document.createElement('option');
    oAlt.value = '__custom__';
    oAlt.textContent = 'Altro (digita sotto)';
    sel.appendChild(oAlt);
    if (cur) sel.value = cur;
  }

  _render() {
    this._rendered = true;
    const r = this.shadowRoot;
    r.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 14px; }
        h3 { margin: 0 0 8px 0; font-size: 16px; font-weight: 500; }
        .hint { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 12px; }
        .form {
          display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
          margin-bottom: 12px;
        }
        .form .full { grid-column: 1 / -1; }
        input, select {
          width: 100%; box-sizing: border-box; padding: 8px 10px;
          border-radius: 8px;
          border: 1px solid var(--divider-color, #444);
          background: var(--secondary-background-color);
          color: var(--primary-text-color); font-size: 0.95em;
        }
        button {
          padding: 10px 14px; border-radius: 8px; border: none;
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          font-weight: 600; cursor: pointer; font-size: 0.95em;
        }
        button.secondary {
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, #555);
        }
        button.danger { background: var(--error-color, #d33); }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        .toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
        .msg {
          padding: 8px 10px; border-radius: 6px; margin-bottom: 12px;
          font-size: 0.9em;
        }
        .msg.info  { background: rgba(33,150,243,0.15); color: #58a6ff; }
        .msg.warn  { background: rgba(255,160,0,0.15); color: #ffa000; }
        .msg.ok    { background: rgba(76,175,80,0.15); color: #4caf50; }
        .list {
          display: flex; flex-direction: column; gap: 8px;
          max-height: 380px; overflow-y: auto;
        }
        .row {
          display: flex; align-items: center; gap: 10px; padding: 10px;
          background: var(--secondary-background-color); border-radius: 8px;
        }
        .row .meta { flex: 1; min-width: 0; }
        .row .nome {
          font-weight: 600; overflow: hidden; text-overflow: ellipsis;
          white-space: nowrap;
        }
        .row .sub {
          font-size: 0.85em; color: var(--secondary-text-color);
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .pill {
          font-size: 0.75em; padding: 2px 8px; border-radius: 999px;
          background: rgba(255,255,255,0.1);
        }
        .pill.cancello { background: rgba(255,160,0,0.2); color: #ffa000; }
        .pill.porta    { background: rgba(76,175,80,0.2); color: #4caf50; }
        .empty {
          text-align: center; color: var(--secondary-text-color);
          padding: 20px; font-style: italic;
        }
        .actions { display: flex; gap: 6px; }
        .actions button { padding: 6px 10px; font-size: 0.85em; }
      </style>
      <ha-card>
        <h3 id="title">Tag NFC</h3>
        <div class="hint">Associa un badge al nome utente (salvato sul videocitofono).</div>
        <div class="toolbar">
          <button id="btn_refresh" class="secondary">Aggiorna lista</button>
        </div>
        <div class="form">
          <select id="nome" class="full"></select>
          <input id="nome_custom" class="full" type="text"
                 placeholder="Nome utente (se Altro)" style="display:none" />
          <select id="scope">
            <option value="porta">Porta (default)</option>
            <option value="cancello">Cancello</option>
          </select>
          <input id="label" class="full" type="text"
                 placeholder="Etichetta (es. Portachiavi)" />
          <button id="btn_enroll" class="full">Associa prossimo tag (30s)</button>
        </div>
        <div id="msg"></div>
        <div class="list" id="list"></div>
      </ha-card>
    `;
    r.getElementById('title').textContent = this._config.title;
    r.getElementById('btn_enroll').addEventListener('click',
      (e) => { e.stopPropagation(); this._onEnroll(); });
    r.getElementById('btn_refresh').addEventListener('click',
      (e) => { e.stopPropagation(); this._onRefresh(); });
    r.getElementById('nome').addEventListener('change', () => {
      const custom = r.getElementById('nome_custom');
      custom.style.display =
        r.getElementById('nome').value === '__custom__' ? 'block' : 'none';
    });
    this._fillUserSelect();
    if (this._hass) {
      this._hass.callService('pyscript', 'videocitofono_nfc_refresh').catch(() => {});
    }
  }

  _showMsg(text, level) {
    this._enrollMsg = JSON.stringify({ text, level });
    this._lastKey = '';
    this._renderList();
    setTimeout(() => {
      if (this._enrollMsg === JSON.stringify({ text, level })) {
        this._enrollMsg = '';
        this._lastKey = '';
        this._renderList();
      }
    }, 12000);
  }

  _resolveNome() {
    const r = this.shadowRoot;
    const sel = r.getElementById('nome').value;
    if (sel === '__custom__') {
      return (r.getElementById('nome_custom').value || '').trim();
    }
    return (sel || '').trim();
  }

  async _onRefresh() {
    if (!this._hass) return;
    try {
      await this._hass.callService('pyscript', 'videocitofono_nfc_refresh');
      this._showMsg('Lista aggiornata dal videocitofono', 'info');
    } catch (e) {
      this._showMsg('Errore refresh: ' + e.message, 'warn');
    }
  }

  async _onEnroll() {
    if (!this._hass || this._busy) return;
    const r = this.shadowRoot;
    const nome = this._resolveNome();
    const scope = r.getElementById('scope').value || 'porta';
    const label = (r.getElementById('label').value || '').trim();
    if (!nome) {
      this._showMsg('Seleziona o inserisci un nome utente', 'warn');
      return;
    }
    this._busy = true;
    this._showMsg(`Avvicina il tag al lettore PN532 (${nome})...`, 'info');
    try {
      await this._hass.callService('pyscript',
        'videocitofono_nfc_enroll',
        { nome, scope, label, timeout_sec: 30 });
    } catch (e) {
      this._showMsg('Errore invio: ' + e.message, 'warn');
      this._busy = false;
    }
  }

  async _onDelete(uid, nome) {
    if (!this._hass || this._busy) return;
    if (!confirm(`Eliminare il tag di ${nome}?`)) return;
    this._busy = true;
    try {
      await this._hass.callService('pyscript',
        'videocitofono_nfc_delete', { uid });
      this._showMsg('Tag rimosso', 'ok');
      await this._hass.callService('pyscript', 'videocitofono_nfc_refresh');
    } catch (e) {
      this._showMsg('Errore: ' + e.message, 'warn');
    } finally {
      this._busy = false;
    }
  }

  _renderList() {
    if (!this._rendered) return;
    const list = this._items();
    const r = this.shadowRoot;
    const cont = r.getElementById('list');
    const msg = r.getElementById('msg');
    msg.innerHTML = '';
    if (this._enrollMsg) {
      try {
        const o = JSON.parse(this._enrollMsg);
        msg.innerHTML = `<div class="msg ${o.level}">${o.text}</div>`;
      } catch (_e) { /* noop */ }
    }
    cont.innerHTML = '';
    r.getElementById('btn_enroll').disabled = !!this._busy;
    r.getElementById('btn_refresh').disabled = !!this._busy;
    if (!list.length) {
      cont.innerHTML = '<div class="empty">Nessun tag registrato — associa un tag a un utente sopra</div>';
      return;
    }
    for (const item of list) {
      const row = document.createElement('div');
      row.className = 'row';
      const sc = item.scope || 'porta';
      const pillCls = sc === 'cancello' ? 'pill cancello' : 'pill porta';
      const sub = [
        `UID ${item.uid}`,
        item.label ? `"${item.label}"` : '',
        item.added_ts ? _fmtDate(item.added_ts) : '',
      ].filter(Boolean).join(' • ');
      row.innerHTML = `
        <div class="meta">
          <div class="nome">${item.nome || '(senza nome)'}
            <span class="${pillCls}">${_scopeLabel(sc)}</span>
          </div>
          <div class="sub">${sub}</div>
        </div>
        <div class="actions">
          <button class="danger" data-uid="${item.uid}"
                  data-nome="${item.nome || ''}">Elimina</button>
        </div>
      `;
      row.querySelector('button.danger').addEventListener('click', (e) => {
        e.stopPropagation();
        this._onDelete(e.target.dataset.uid, e.target.dataset.nome);
      });
      cont.appendChild(row);
    }
  }
}

customElements.define('vc-nfc-card', VcNfcCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'vc-nfc-card',
  name: 'Videocitofono - Tag NFC',
  description: 'Associa tag NFC a utenti (volti/PIN) del videocitofono',
});
