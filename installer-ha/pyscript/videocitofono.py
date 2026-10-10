# /config/pyscripts/videocitofono.py

import json

@service
def segna_come_letta(timestamp=None):
    """Aggiunge un timestamp alla lista delle chiamate lette."""
    if timestamp is None:
        return

    read_helper = hass.states.get('input_text.chiamate_lette')
    read_timestamps_str = read_helper.state if read_helper else "[]"

    try:
        read_list = json.loads(read_timestamps_str)
    except (json.JSONDecodeError, TypeError):
        read_list = []

    if timestamp not in read_list:
        read_list.append(timestamp)
        hass.states.set('input_text.chiamate_lette', json.dumps(read_list))
        log.info(f"Chiamata segnata come letta: {timestamp}")