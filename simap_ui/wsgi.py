"""
wsgi.py - Produktions-Entrypoint

    gunicorn --chdir simap_ui wsgi:app -w 2 -b 0.0.0.0:$PORT
"""

from app import app  # noqa: F401
