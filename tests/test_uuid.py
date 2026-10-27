from baseop.uuid import account_uuid


def test_account_uuid_init_as_string():
    assert isinstance(account_uuid(), str)


def test_account_uuid_init_non_empty():
    assert len(account_uuid()) > 0


def test_account_uuid_init_8_symbol():
    assert len(account_uuid()) == 8


def test_account_uuid_is_uniq():
    assert account_uuid() != account_uuid()
