from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from baseop.account import (
    AbstractAccount,
    AccountCurrency,
    BankAccount,
    PremiumAccount,
)
from baseop.client import Client
from baseop.transaction import (
    InvalidTransactionError,
    Transaction,
    TransactionPriority,
    TransactionProcessor,
    TransactionQueue,
    TransactionStatus,
    TransactionType,
)


@pytest.fixture
def client() -> Client:
    return Client(id=uuid4(), first_name="John", last_name="Doe", age=30)


@pytest.fixture
def account(client: Client) -> BankAccount:
    return BankAccount(client, balance=1000)


@pytest.fixture
def recipient(client: Client) -> BankAccount:
    return BankAccount(client)


@pytest.fixture
def processor() -> TransactionProcessor:
    return TransactionProcessor()


def deposit(account: AbstractAccount, amount: float) -> Transaction:
    return Transaction(
        type=TransactionType.DEPOSIT,
        amount=amount,
        currency=account.currency,
        to_account_id=account.account_id,
    )


def withdraw(account: AbstractAccount, amount: float) -> Transaction:
    return Transaction(
        type=TransactionType.WITHDRAW,
        amount=amount,
        currency=account.currency,
        from_account_id=account.account_id,
    )


def transfer(
    sender: AbstractAccount,
    receiver: AbstractAccount | None,
    amount: float,
    *,
    currency: AccountCurrency | None = None,
    destination: str | None = None,
) -> Transaction:
    return Transaction(
        type=TransactionType.TRANSFER,
        amount=amount,
        currency=currency or sender.currency,
        from_account_id=sender.account_id,
        to_account_id=receiver.account_id if receiver else None,
        external_destination=destination,
    )


def test_deposit_and_withdraw(
    processor: TransactionProcessor, recipient: BankAccount
) -> None:
    incoming = deposit(recipient, 100)

    assert processor.process_one(incoming, {recipient.account_id: recipient}).status is (
        TransactionStatus.COMPLETED
    )
    assert incoming.finished_at is not None
    assert recipient.balance == 100

    outgoing = withdraw(recipient, 40)

    assert processor.process_one(outgoing, {recipient.account_id: recipient}).status is (
        TransactionStatus.COMPLETED
    )
    assert recipient.balance == 60


def test_internal_transfer(
    processor: TransactionProcessor, account: BankAccount, recipient: BankAccount
) -> None:
    tx = transfer(account, recipient, 100)

    assert processor.process_one(
        tx, {account.account_id: account, recipient.account_id: recipient}
    ).status is TransactionStatus.COMPLETED
    assert account.balance == 900
    assert recipient.balance == 100


def test_external_transfer_charges_fee(
    processor: TransactionProcessor, account: BankAccount
) -> None:
    tx = transfer(account, None, 100, destination="EXTERNAL-ACCOUNT")

    assert processor.process_one(tx, {account.account_id: account}).status is (
        TransactionStatus.COMPLETED
    )
    assert tx.fee == 3.0
    assert account.balance == 897


def test_fx_transfer_converts_credit(
    processor: TransactionProcessor, client: Client
) -> None:
    usd = BankAccount(client, balance=1000, currency=AccountCurrency.USD)
    rub = BankAccount(client, balance=0, currency=AccountCurrency.RUB)
    tx = transfer(usd, rub, 100, currency=AccountCurrency.RUB)

    assert processor.process_one(
        tx, {usd.account_id: usd, rub.account_id: rub}
    ).status is TransactionStatus.COMPLETED
    assert usd.balance == pytest.approx(998.89)
    assert rub.balance == 100


@pytest.mark.parametrize(
    ("from_account_id", "to_account_id", "destination"),
    [
        ("abcdefgh", None, None),
        (None, "abcdefgh", None),
        ("abcdefgh", "ijklmnop", "EXTERNAL-ACCOUNT"),
    ],
)
def test_transfer_requires_exactly_one_recipient(
    from_account_id: str | None,
    to_account_id: str | None,
    destination: str | None,
) -> None:
    with pytest.raises(InvalidTransactionError):
        Transaction(
            type=TransactionType.TRANSFER,
            amount=10,
            currency=AccountCurrency.RUB,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            external_destination=destination,
        )


def test_queue_priority_and_fifo(recipient: BankAccount) -> None:
    queue = TransactionQueue()
    low_first = deposit(recipient, 1)
    low_second = deposit(recipient, 2)
    high = deposit(recipient, 3)

    queue.add(low_first, TransactionPriority.LOW)
    queue.add(low_second, TransactionPriority.LOW)
    queue.add(high, TransactionPriority.HIGH)

    assert queue.pop_ready() is high
    assert queue.pop_ready() is low_first
    assert queue.pop_ready() is low_second
    assert queue.pop_ready() is None


def test_delayed_transaction_is_not_ready(recipient: BankAccount) -> None:
    queue = TransactionQueue()
    delayed = deposit(recipient, 1)
    delayed.scheduled_at = datetime.now(UTC) + timedelta(hours=1)
    ready = deposit(recipient, 2)

    queue.add(delayed, TransactionPriority.HIGH)
    queue.add(ready, TransactionPriority.LOW)

    assert queue.pop_ready() is ready
    assert queue.pop_ready() is None


def test_cancel_removes_queued_transaction(recipient: BankAccount) -> None:
    queue = TransactionQueue()
    tx = deposit(recipient, 10)
    queue.add(tx, TransactionPriority.HIGH)

    queue.cancel(tx.id)

    assert tx.status is TransactionStatus.CANCELLED
    assert queue.pop_ready() is None


def test_retry_then_success(
    processor: TransactionProcessor,
    recipient: BankAccount,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def flaky(_tx: Transaction, _accounts: dict[str, AbstractAccount]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")

    monkeypatch.setattr(processor, "_execute_transaction", flaky)
    tx = deposit(recipient, 10)

    result = processor.process_one(tx, {recipient.account_id: recipient})

    assert result.status is TransactionStatus.COMPLETED
    assert result.attempts == 2
    assert calls == 2


def test_retry_exhaustion(
    processor: TransactionProcessor,
    recipient: BankAccount,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_fails(_tx: Transaction, _accounts: dict[str, AbstractAccount]) -> None:
        raise RuntimeError("transient")

    monkeypatch.setattr(processor, "_execute_transaction", always_fails)
    tx = deposit(recipient, 10)

    result = processor.process_one(tx, {recipient.account_id: recipient})

    assert result.status is TransactionStatus.FAILED
    assert result.attempts == 3
    assert len(result.errors) == 3


def test_frozen_account_is_rejected(
    processor: TransactionProcessor, account: BankAccount, recipient: BankAccount
) -> None:
    account.freeze()
    tx = transfer(account, recipient, 100)

    result = processor.process_one(
        tx, {account.account_id: account, recipient.account_id: recipient}
    )

    assert result.status is TransactionStatus.FAILED
    assert account.balance == 1000
    assert recipient.balance == 0


def test_insufficient_funds_are_rejected(
    processor: TransactionProcessor, client: Client, recipient: BankAccount
) -> None:
    poor = BankAccount(client, balance=50)
    tx = transfer(poor, recipient, 100)

    result = processor.process_one(
        tx, {poor.account_id: poor, recipient.account_id: recipient}
    )

    assert result.status is TransactionStatus.FAILED
    assert poor.balance == 50
    assert recipient.balance == 0


def test_premium_account_may_go_negative(
    processor: TransactionProcessor, client: Client
) -> None:
    premium = PremiumAccount(
        client,
        balance=100,
        overdraft_limit=500,
        fixed_fee=0,
    )
    tx = withdraw(premium, 300)

    assert processor.process_one(
        tx, {premium.account_id: premium}
    ).status is TransactionStatus.COMPLETED
    assert premium.balance == -200
