# Legacy

Ausgemusterter Code, der aus dem aktiven Projekt verschoben wurde.
Nichts hier wird von der laufenden App importiert oder deployed.

## ml/

Ältere/parallele ML-Arbeiten, ersetzt durch die aktive Pipeline in `embeddings/`:

- **`ml_aki.py`** — "ProjektKlassifikator v5" (GradientBoosting + MLflow/DagsHub).
  Nicht lauffähig: importiert `supabase_api_loader`, dessen Quellcode nicht
  (mehr) im Repo liegt.
- **`generate_archive_embeddings.py`** / **`embedding_text.py`** /
  **`benchmark_archive_embeddings.py`** — alte Embedding-Pipeline mit
  intfloat/multilingual-e5-small (384-dim). Ersetzt durch
  `embeddings/build_embeddings.py` (BAAI/bge-m3, 1024-dim), die nächtlich
  per GitHub Action läuft.

## webapp_oauth_demo/

Eigenständiges FastAPI-MVP für den SIMAP-OAuth/OIDC-Flow (In-Memory-Sessions).
Hat mit der laufenden Flask-App (`simap_ui/`) nichts zu tun.

## templates/

Von keiner Route mehr gerenderte Jinja2-Templates aus `simap_ui/templates/`:
`index.html` (Duplikat von `landing.html` — die Route `/` rendert
`landing.html`), `pro_dashboard.html`, `pro_recommended.html`,
`pro_favorites.html`, `pro_bkp_calculator.html`, `change_password.html`.

## archive.ipynb

641-KB-Explorationsnotebook zur SIMAP-Archiv-Migration.
