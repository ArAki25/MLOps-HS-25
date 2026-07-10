import pytest

from embeddings.text_builder import build_text

PROJECT_ROW = {
    'id': 'abc-123',
    'title_de': 'Sanierung Kantonsstrasse',
    'description_de': '<p>Belagsersatz auf 2&nbsp;km.</p>',
    'canton': 'ZH',
    'city': 'Zürich',
    'proc_office_name_de': 'Tiefbauamt Kanton Zürich',
    'cpv_code_main': '45233120',
}


def test_build_text_project_contains_content():
    bt = build_text(PROJECT_ROW, 'project')
    assert 'Sanierung Kantonsstrasse' in bt.raw_text
    assert bt.text_hash
    assert bt.language == 'de'


def test_build_text_strips_html():
    bt = build_text(PROJECT_ROW, 'project')
    assert '<p>' not in bt.raw_text
    assert '&nbsp;' not in bt.raw_text


def test_build_text_hash_is_deterministic():
    a = build_text(PROJECT_ROW, 'project')
    b = build_text(dict(PROJECT_ROW), 'project')
    assert a.text_hash == b.text_hash


def test_build_text_hash_changes_with_content():
    changed = {**PROJECT_ROW, 'title_de': 'Neubau Schulhaus'}
    assert build_text(PROJECT_ROW, 'project').text_hash != build_text(changed, 'project').text_hash


def test_build_text_empty_row_falls_back_to_id():
    bt = build_text({'id': 'xyz-9'}, 'archive')
    assert 'xyz-9' in bt.raw_text
    assert bt.text_hash


def test_build_text_language_cascade():
    row_fr = {'id': '1', 'title_fr': 'Assainissement route'}
    assert build_text(row_fr, 'project').language == 'fr'
    row_explicit = {'id': '1', 'creation_language': 'IT', 'title_de': 'x'}
    assert build_text(row_explicit, 'project').language == 'it'


def test_build_text_unknown_source_raises():
    with pytest.raises(ValueError):
        build_text(PROJECT_ROW, 'weird')


def test_preview_is_capped():
    row = {**PROJECT_ROW, 'description_de': 'x' * 2000}
    assert len(build_text(row, 'project').preview) <= 500
