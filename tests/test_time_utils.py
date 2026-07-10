from datetime import UTC, datetime, timedelta

from supabase_client import calculate_time_ago, clean_html


def _iso(delta: timedelta) -> str:
    return (datetime.now(UTC) - delta).isoformat()


def test_time_ago_just_now():
    assert calculate_time_ago(_iso(timedelta(seconds=10))) == 'Gerade eben'


def test_time_ago_minutes():
    assert calculate_time_ago(_iso(timedelta(minutes=5))) == 'vor 5 Min.'


def test_time_ago_hours():
    assert calculate_time_ago(_iso(timedelta(hours=3))) == 'vor 3 Std.'


def test_time_ago_yesterday():
    assert calculate_time_ago(_iso(timedelta(days=1, minutes=5))) == 'Gestern'


def test_time_ago_days():
    assert calculate_time_ago(_iso(timedelta(days=3))) == 'vor 3 Tagen'


def test_time_ago_weeks():
    assert calculate_time_ago(_iso(timedelta(days=14))) == 'vor 2 Wo.'


def test_time_ago_old_date_formats_as_date():
    out = calculate_time_ago('2020-01-15T00:00:00+00:00')
    assert out == '15.01.2020'


def test_time_ago_empty_and_garbage():
    assert calculate_time_ago('') == ''
    assert calculate_time_ago(None) == ''
    assert calculate_time_ago('kein datum') == ''


def test_clean_html_strips_tags():
    assert clean_html('<p>Hallo <b>Welt</b>&nbsp;!</p>') == 'Hallo Welt !'


def test_clean_html_empty():
    assert clean_html('') == ''
    assert clean_html(None) == ''
