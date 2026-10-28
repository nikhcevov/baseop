from uuid import uuid4

from baseop.user import User


def test_user_init():
    id = uuid4()
    name = "John"
    user = User(id, name)
    assert user.id == id and user.name == name
