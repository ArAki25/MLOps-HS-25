from embeddings.dicts import (
    bkp_label,
    canton_label,
    cpv_label,
    order_type_label,
    pub_type_label,
)


def test_cpv_label_known_code():
    label = cpv_label('45000000')
    assert label
    assert 'Bau' in label


def test_cpv_label_unknown_and_none():
    assert cpv_label('99999999') is None
    assert cpv_label(None) is None
    assert cpv_label('') is None


def test_canton_label():
    assert canton_label('ZH') == 'Zürich'
    assert canton_label('zh') == 'Zürich'
    assert canton_label('XX') is None


def test_bkp_label_none():
    assert bkp_label(None) is None


def test_order_type_label_unknown_passthrough_or_none():
    # Unbekannte Codes dürfen keinen Crash auslösen
    order_type_label('unbekannt-xyz')


def test_pub_type_label_none():
    assert pub_type_label(None) is None
