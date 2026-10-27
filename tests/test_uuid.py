from baseop.uuid import accout_uuid


def test_account_uuid_init_as_string():
    assert isinstance(accout_uuid(), str)


def test_account_uuid_init_non_empty():
    assert len(accout_uuid()) > 0


def test_account_uuid_init_8_symbol():
    assert len(accout_uuid()) == 8


def test_account_uuid_is_uniq():
    assert accout_uuid() != accout_uuid()
