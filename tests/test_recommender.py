import numpy as np
from supabase_client import _mmr_rerank, _parse_pgvector, _strip_embedding


def _unit(v):
    a = np.asarray(v, dtype=np.float32)
    return a / np.linalg.norm(a)


def _cand(sim, vec):
    return {'similarity': sim, 'embedding': _unit(vec)}


# --- _parse_pgvector ---

def test_parse_pgvector_string():
    out = _parse_pgvector('[0.1, -0.2, 0.3]')
    assert out is not None
    np.testing.assert_allclose(out, [0.1, -0.2, 0.3], rtol=1e-6)


def test_parse_pgvector_list_and_tuple():
    np.testing.assert_allclose(_parse_pgvector([1.0, 2.0]), [1.0, 2.0])
    np.testing.assert_allclose(_parse_pgvector((1.0, 2.0)), [1.0, 2.0])


def test_parse_pgvector_ndarray_passthrough():
    arr = np.array([1.0, 2.0], dtype=np.float64)
    out = _parse_pgvector(arr)
    assert out.dtype == np.float32


def test_parse_pgvector_garbage_returns_none():
    assert _parse_pgvector('kein json') is None
    assert _parse_pgvector(None) is None
    assert _parse_pgvector(42) is None


# --- _mmr_rerank ---

def test_mmr_empty_input():
    assert _mmr_rerank([], k=5) == []


def test_mmr_returns_at_most_k():
    cands = [_cand(0.9 - i * 0.01, [1, i, 0]) for i in range(10)]
    assert len(_mmr_rerank(cands, k=3)) == 3


def test_mmr_skips_near_duplicates():
    # Zwei fast identische Vektoren, ein orthogonaler: bei k=2 muss der
    # orthogonale gewählt werden, nicht das Duplikat.
    a = _cand(0.99, [1, 0, 0])
    dup = _cand(0.98, [1, 0.001, 0])
    ortho = _cand(0.50, [0, 1, 0])
    out = _mmr_rerank([a, dup, ortho], k=2)
    assert out[0] is a
    assert out[1] is ortho


def test_mmr_relaxes_cap_when_k_unreachable():
    # Alle Kandidaten sind fast identisch: die harte Kappung würde nur 1
    # zulassen, die stufenweise Lockerung muss trotzdem k liefern.
    cands = [_cand(0.9, [1, 0.0001 * i, 0]) for i in range(4)]
    out = _mmr_rerank(cands, k=3)
    assert len(out) == 3


def test_mmr_candidates_without_embedding_fallback():
    cands = [{'similarity': 0.9, 'embedding': None} for _ in range(5)]
    out = _mmr_rerank(cands, k=2)
    assert len(out) == 2  # Fallback: candidates[:k]


def test_strip_embedding():
    rec = {'id': 1, 'embedding': np.array([1.0]), 'title': 'x'}
    out = _strip_embedding(rec)
    assert 'embedding' not in out
    assert out['id'] == 1 and out['title'] == 'x'
