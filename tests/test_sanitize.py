from supabase_client import _sanitize_filter_value


def test_injection_payload_becomes_inert():
    assert _sanitize_filter_value('x,id.eq.1') == 'x id eq 1'


def test_parens_and_quotes_stripped():
    assert _sanitize_filter_value('a(b)"c"\\d') == 'a b  c  d'


def test_normal_search_untouched():
    assert _sanitize_filter_value('Brücke Sanierung Zürich') == 'Brücke Sanierung Zürich'


def test_empty_and_none():
    assert _sanitize_filter_value('') == ''
    assert _sanitize_filter_value(None) == ''


def test_whitespace_trimmed():
    assert _sanitize_filter_value('  ,,  ') == ''
