#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import requests
from dotenv import load_dotenv

from ML.embedding_text import build_archive_embedding_text


# Defaults auf den aktuellen unified-Embedding-Stack (siehe embeddings/build_embeddings.py)
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

PAGE_SIZE = 1000
SUPABASE_TIMEOUT = 60
SOURCE_TABLE = "archive"

SELECT_COLUMNS = ",".join(
    [
        "simap_project_id",
        "simap_publication_id",
        "publication_date",
        "creation_language",
        "pub_type",
        "title_de",
        "title_fr",
        "description_de",
        "description_fr",
        "order_type",
        "process_type",
        "cpv_code_main",
        "cpv_codes",
        "bkp_codes",
        "canton",
    ]
)


@dataclass
class Supa:
    url: str
    key: str

    @classmethod
    def from_env(cls) -> "Supa":
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()

        url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_SERVICE_KEY")
            or os.getenv("SUPABASE_KEY")
            or ""
        )
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL und SUPABASE_SERVICE_ROLE_KEY (oder *_KEY) fehlen."
            )
        return cls(url=url, key=key)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def iter_archive_rows(self, limit: int) -> Iterable[dict[str, Any]]:
        emitted = 0
        offset = 0
        while emitted < limit:
            page_size = min(PAGE_SIZE, limit - emitted)
            url = (
                f"{self.url}/rest/v1/{SOURCE_TABLE}"
                f"?select={SELECT_COLUMNS}"
                f"&order=simap_project_id.asc,publication_date.asc"
            )
            headers = self._headers()
            headers["Range-Unit"] = "items"
            headers["Range"] = f"{offset}-{offset + page_size - 1}"
            r = requests.get(url, headers=headers, timeout=SUPABASE_TIMEOUT)
            if r.status_code not in (200, 206):
                raise RuntimeError(
                    f"Archive-Fetch fehlgeschlagen: {r.status_code} {r.text[:300]}"
                )
            batch = r.json()
            if not batch:
                return
            for row in batch:
                yield row
                emitted += 1
                if emitted >= limit:
                    return
            if len(batch) < page_size:
                return
            offset += page_size


def _synthetic_texts(n: int, *, seed: int, title_len: int, desc_len: int) -> list[str]:
    rnd = random.Random(seed)
    base_words = (
        "projekt ausschreibung vergabe baudienstleistung lieferung kanton "
        "planung architektur ingenieur leistung beschreibung frist "
        "angebot unterlagen kriterium sicherheit umwelt "
    ).split()

    texts: list[str] = []
    for _ in range(n):
        t_words = [rnd.choice(base_words) for _ in range(max(5, title_len // 7))]
        d_words = [rnd.choice(base_words) for _ in range(max(20, desc_len // 7))]
        title = " ".join(t_words)[:title_len]
        desc = " ".join(d_words)[:desc_len]
        cpv = f"CPV {rnd.choice(['45', '71', '72', '79'])}{rnd.randint(10,99)}00000"
        order = rnd.choice(["Bauauftrag", "Dienstleistungsauftrag", "Lieferauftrag"])
        texts.append(f"{order}. {cpv}. {title}. {desc}")
    return texts


def _bench_encode(
    model: Any,
    texts_prefixed: list[str],
    *,
    batch_size: int,
    repeats: int,
    warmup: int,
) -> dict[str, Any]:
    times: list[float] = []

    for i in range(warmup):
        _ = model.encode(
            texts_prefixed[: min(len(texts_prefixed), batch_size)],
            batch_size=min(batch_size, len(texts_prefixed)),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        if i == 0:
            # Grobe Synchronisation für CUDA, falls vorhanden
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.synchronize()
            except Exception:
                pass

    for _ in range(repeats):
        t0 = time.perf_counter()
        emb = model.encode(
            texts_prefixed,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
        except Exception:
            pass
        dt = time.perf_counter() - t0
        if isinstance(emb, np.ndarray) and emb.shape != (len(texts_prefixed), EMBEDDING_DIM):
            raise RuntimeError(f"Unerwartete Embedding-Shape: {emb.shape}")
        times.append(dt)

    return {
        "n": len(texts_prefixed),
        "batch_size": batch_size,
        "repeats": repeats,
        "warmup": warmup,
        "times_s": times,
        "median_s": statistics.median(times),
        "mean_s": statistics.mean(times),
        "stdev_s": statistics.pstdev(times) if len(times) > 1 else 0.0,
        "throughput_txt_s_median": (len(texts_prefixed) / statistics.median(times)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark: Archive embeddings (E5-small)")
    ap.add_argument("-n", "--num", type=int, default=500, help="Anzahl Texte (Default 500)")
    ap.add_argument("-b", "--batch-size", type=int, default=64, help="Encode batch size")
    ap.add_argument(
        "--max-seq",
        type=int,
        default=int(os.environ.get("EMBED_MAX_SEQ", "2048")),
        help="max_seq_length (Default 2048 oder EMBED_MAX_SEQ)",
    )
    ap.add_argument("--repeats", type=int, default=3, help="Messwiederholungen")
    ap.add_argument("--warmup", type=int, default=1, help="Warmup-Runs")
    ap.add_argument("--seed", type=int, default=42, help="Seed für synthetische Texte")
    ap.add_argument(
        "--from-supabase",
        action="store_true",
        help="Echte Archive-Texte via Supabase laden (SUPABASE_URL + KEY nötig).",
    )
    ap.add_argument("--title-len", type=int, default=120, help="Synthetischer Titel (chars)")
    ap.add_argument(
        "--desc-len", type=int, default=900, help="Synthetische Beschreibung (chars)"
    )
    args = ap.parse_args()

    # Texte vorbereiten
    source = "synthetisch"
    texts: list[str] = []

    if args.from_supabase:
        source = "supabase"
        supa = Supa.from_env()
        for row in supa.iter_archive_rows(args.num):
            text, _lang = build_archive_embedding_text(row)
            if text:
                texts.append(text)
        if len(texts) < args.num:
            print(
                f"Warnung: nur {len(texts)}/{args.num} Texte hatten nutzbaren Inhalt; "
                "Bench läuft mit der kleineren Menge.",
                file=sys.stderr,
            )
    else:
        texts = _synthetic_texts(
            args.num, seed=args.seed, title_len=args.title_len, desc_len=args.desc_len
        )
    # bge-m3 braucht (anders als e5) keinen "passage:"-Prefix.
    texts_prefixed = list(texts)

    # Modell laden
    t_load0 = time.perf_counter()
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    try:
        # bge-m3 default ist 8192; für unsere Textlängen ist 2048 i.d.R. schneller
        model.max_seq_length = min(getattr(model, "max_seq_length", args.max_seq), args.max_seq)
    except Exception:
        pass
    device = "cpu"
    try:
        import torch

        if torch.cuda.is_available():
            model = model.to("cuda")
            device = "cuda"
    except Exception:
        pass
    t_load = time.perf_counter() - t_load0

    # Encode bench
    res = _bench_encode(
        model,
        texts_prefixed,
        batch_size=args.batch_size,
        repeats=args.repeats,
        warmup=args.warmup,
    )

    # Ausgabe (kurz + copy/paste-freundlich)
    print("=== archive embedding benchmark ===")
    print(f"model={EMBEDDING_MODEL_NAME} dim={EMBEDDING_DIM} device={device}")
    print(f"source={source} n={res['n']} batch_size={res['batch_size']}")
    print(f"model_load_s={t_load:.3f}")
    print(
        "encode_median_s={:.3f} encode_mean_s={:.3f} stdev_s={:.3f}".format(
            res["median_s"], res["mean_s"], res["stdev_s"]
        )
    )
    print("throughput_txt_s_median={:.2f}".format(res["throughput_txt_s_median"]))
    print("times_s=" + ",".join("{:.3f}".format(t) for t in res["times_s"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

