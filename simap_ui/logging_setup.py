"""
logging_setup.py - Zentrale Logging-Konfiguration

Einmalig beim App-Start aufrufen. Level via LOG_LEVEL-Env steuerbar
(Default INFO). Module holen sich ihren Logger selbst per
logging.getLogger(__name__), damit sie auch standalone importierbar bleiben.
"""

import logging
import os
import sys


def setup_logging() -> None:
    level = os.getenv('LOG_LEVEL', 'INFO').upper()
    # Windows-Konsolen sind oft cp1252; Log-Meldungen enthalten Emojis
    stream = sys.stderr
    try:
        stream.reconfigure(errors='replace')
    except AttributeError:
        pass
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        stream=stream,
    )
