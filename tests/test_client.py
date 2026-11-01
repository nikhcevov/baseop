from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from baseop.client import Client, ClientStatus

REQUIRED: dict[str, Any] = {"first_name": "John", "last_name": "Doe", "age": 30}

NAMES = ["first_name", "middle_name", "last_name"]


def make_client(**overrides: Any) -> Client:
    return Client(**{**REQUIRED, **overrides})


def test_generates_fresh_id_per_client():
    first, second = make_client(), make_client()

    assert isinstance(first.id, UUID)
    assert first.id != second.id


def test_keeps_explicit_id():
    fixed = uuid4()

    assert make_client(id=fixed).id == fixed


def test_optionals_default():
    client = make_client()

    assert client.status is ClientStatus.ACTIVE
    assert client.middle_name is None
    assert client.account_ids == []
    assert client.contacts == []


def test_mutable_defaults_are_not_shared():
    first, second = make_client(), make_client()

    first.account_ids.append("abcdefgh")
    first.contacts.append("+7916123456")

    assert second.account_ids == []
    assert second.contacts == []


@pytest.mark.parametrize("field", NAMES)
@pytest.mark.parametrize("value", ["Jo", "J" * 50])
def test_name_accepts_boundary_lengths(field: str, value: str):
    assert getattr(make_client(**{field: value}), field) == value


@pytest.mark.parametrize("field", NAMES)
@pytest.mark.parametrize("value", ["J", "J" * 51])
def test_name_rejects_out_of_range_lengths(field: str, value: str):
    with pytest.raises(ValidationError):
        make_client(**{field: value})


@pytest.mark.parametrize("age", [18, 99])
def test_age_accepts_adults(age: int):
    assert make_client(age=age).age == age


@pytest.mark.parametrize("age", [17, -1, True, 18.0, "18"])
def test_age_rejects_non_adults_and_non_strict_ints(age: Any):
    with pytest.raises(ValidationError):
        make_client(age=age)


@pytest.mark.parametrize("status", ["blocked", ClientStatus.BLOCKED])
def test_status_accepts_member_or_value(status: Any):
    client = make_client(status=status)

    assert client.status is ClientStatus.BLOCKED
    assert client.model_dump(mode="json")["status"] == "blocked"


def test_status_rejects_unknown_value():
    with pytest.raises(ValidationError):
        make_client(status="frozen")


@pytest.mark.parametrize("value", ["abcdefgh", "12345678"])
def test_account_id_accepts_8_symbols(value: str):
    assert make_client(account_ids=[value]).account_ids == [value]


@pytest.mark.parametrize("value", ["abcdefg", "abcdefghi", "", 12345678, None])
def test_account_id_rejects_wrong_shape(value: Any):
    with pytest.raises(ValidationError):
        make_client(account_ids=[value])


@pytest.mark.parametrize("value", ["1234567", "12345678901"])
def test_contact_accepts_boundary_lengths(value: str):
    assert make_client(contacts=[value]).contacts == [value]


@pytest.mark.parametrize("value", ["123456", "123456789012", "", 1234567890])
def test_contact_rejects_wrong_shape(value: Any):
    with pytest.raises(ValidationError):
        make_client(contacts=[value])


@pytest.mark.parametrize("field", ["first_name", "last_name", "age"])
def test_required_fields_have_no_default(field: str):
    payload = {key: value for key, value in REQUIRED.items() if key != field}

    with pytest.raises(ValidationError):
        Client(**payload)


def test_rejects_unknown_field():
    with pytest.raises(ValidationError):
        make_client(nickname="johnny")


def test_rejects_attribute_assignment():
    client = make_client()

    with pytest.raises(ValidationError):
        client.age = 40  # pyright: ignore[reportAttributeAccessIssue]
