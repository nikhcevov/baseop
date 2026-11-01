from baseop.uuid import create_account_id


def test_create_account_id_is_str():
    assert isinstance(create_account_id(), str)


def test_create_account_id_is_8_symbols():
    assert len(create_account_id()) == 8


def test_create_account_id_is_unique():
    assert create_account_id() != create_account_id()
