from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from baseop.account import (
    AbstractAccount,
    AccountClosedError,
    AccountCurrency,
    AccountFrozenError,
    BankAccount,
    InsufficientFundsError,
    InvalidOperationError,
)
from baseop.account.base import AccountStatus
from baseop.client import ClientStatus
from baseop.uuid import AccountId

_TIMEZONE = UTC


class TransactionError(Exception):
    pass


class TransactionStatusError(TransactionError):
    pass


class InvalidTransactionError(TransactionError):
    pass


class TransactionType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    TRANSFER = "transfer"


class TransactionStatus(StrEnum):
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransactionTarget(BaseModel):
    client_id: UUID | None = None
    account_id: AccountId | None = None


def account_currency(account: AbstractAccount) -> AccountCurrency:
    return account.currency if isinstance(account, BankAccount) else AccountCurrency.RUB


class Transaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    type: TransactionType
    amount: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    currency: AccountCurrency
    fee: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    from_client_id: UUID | None = None
    from_account_id: AccountId | None = None
    to_client_id: UUID | None = None
    to_account_id: AccountId | None = None
    external_destination: str | None = None
    status: TransactionStatus = TransactionStatus.QUEUED
    errors: list[str] = Field(default_factory=list)
    attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(_TIMEZONE))
    scheduled_at: datetime = Field(default_factory=lambda: datetime.now(_TIMEZONE))
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _check_withdraw_valid(self):
        if self.type == TransactionType.WITHDRAW and (
            (not self.from_account_id) or self.to_account_id
        ):
            raise InvalidTransactionError("Invalid transaction")
        return self

    @model_validator(mode="after")
    def _check_deposit_valid(self):
        if self.type == TransactionType.DEPOSIT and (
            (not self.to_account_id) or self.from_account_id
        ):
            raise InvalidTransactionError("Invalid transaction")
        return self

    @model_validator(mode="after")
    def _check_transfer_valid(self):
        if self.type == TransactionType.TRANSFER:
            has_internal = bool(self.to_account_id)
            has_external = bool(self.external_destination)
            if not self.from_account_id or has_external == has_internal:
                raise InvalidTransactionError("Invalid transaction")
        return self

    @property
    def fail_reason(self) -> str | None:
        return self.errors[-1] if len(self.errors) else None

    @property
    def is_external(self) -> bool:
        return (
            self.type == TransactionType.TRANSFER
            and self.to_account_id is None
            and bool(self.external_destination)
        )

    def complete(self) -> None:
        if self.status != TransactionStatus.QUEUED:
            raise TransactionStatusError("Invalid transaction status")
        self.status = TransactionStatus.COMPLETED
        self.finished_at = datetime.now(_TIMEZONE)

    def cancel(self) -> None:
        if self.status != TransactionStatus.QUEUED:
            raise TransactionStatusError("Invalid transaction status")
        self.status = TransactionStatus.CANCELLED
        self.finished_at = datetime.now(_TIMEZONE)

    def fail(self) -> None:
        if self.status != TransactionStatus.QUEUED:
            raise TransactionStatusError("Invalid transaction status")
        self.status = TransactionStatus.FAILED
        self.finished_at = datetime.now(_TIMEZONE)


class TransactionQueueInvalidStatusError(TransactionError):
    pass


class TransactionQueueTxNotFoundError(TransactionError):
    pass


class TransactionPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TransactionQueue:
    def __init__(self) -> None:
        self._queue: dict[TransactionPriority, list[Transaction]] = {
            priority: [] for priority in TransactionPriority
        }

    def add(
        self,
        tx: Transaction,
        priority: TransactionPriority,
    ) -> None:
        if tx.status != TransactionStatus.QUEUED:
            raise TransactionQueueInvalidStatusError("Invalid transaction status")

        for queue in self._queue.values():
            if any(txx for txx in queue if tx.id == txx.id):
                raise TransactionRejected("Invalid transaction id")
        self._queue[priority].append(tx)

    def get(self, tx_id: UUID) -> Transaction | None:
        for queue in self._queue.values():
            for transaction in queue:
                if transaction.id == tx_id:
                    return transaction
        return None

    def cancel(self, tx_id: UUID) -> None:
        transaction = None
        for queue in self._queue.values():
            (idx, transaction) = next(
                ((idx, tx) for (idx, tx) in enumerate(queue) if tx.id == tx_id),
                (-1, None),
            )
            if transaction and transaction.status == TransactionStatus.QUEUED:
                transaction.cancel()
                queue.pop(idx)
                return
        if not transaction:
            raise TransactionQueueTxNotFoundError("Invalid transaction id")
        if transaction.status != TransactionStatus.QUEUED:
            raise TransactionQueueInvalidStatusError("Invalid transacion statsu")

    def pop_ready(self) -> Transaction | None:
        priority_order = (
            TransactionPriority.HIGH,
            TransactionPriority.MEDIUM,
            TransactionPriority.LOW,
        )

        for priority in priority_order:
            (idx, transaction) = next(
                (
                    (idx, tx)
                    for idx, tx in enumerate(self._queue[priority])
                    if datetime.now(_TIMEZONE) >= tx.scheduled_at
                    and tx.status == TransactionStatus.QUEUED
                ),
                (-1, None),
            )

            if transaction:
                self._queue[priority].pop(idx)
                return transaction


class TransactionProcessorInvalidStatusError(TransactionError):
    pass


class TransactionProcessorAccountNotFound(TransactionError):
    pass


class TransactionRejected(TransactionError):
    pass


class TransactionRetryableError(TransactionError):
    pass


class TransactionCompensationError(TransactionError):
    pass


_RETRYABLE_ERRORS = (TransactionRetryableError,)
_TERMINAL_ERRORS = (
    TransactionError,
    AccountFrozenError,
    AccountClosedError,
    InsufficientFundsError,
    InvalidOperationError,
    ValueError,
    KeyError,
)


_RATES_TO_RUB = {
    AccountCurrency.RUB: 1.0,
    AccountCurrency.USD: 90.0,
    AccountCurrency.EUR: 100.0,
    AccountCurrency.KZT: 0.20,
    AccountCurrency.CNY: 12.0,
}


def round_money(amount: float) -> float:
    return round(amount, 2)


def convert(amount: float, source: AccountCurrency, target: AccountCurrency) -> float:
    """Converts source currency to target"""
    rate_to_rub = amount * _RATES_TO_RUB[source]
    return rate_to_rub / _RATES_TO_RUB[target]


class TransactionProcessor:
    def __init__(self, external_fee: float | None = None) -> None:
        self._EXTERNAL_TRANSFER_FEE: float = (
            external_fee if external_fee is not None else 0.03
        )
        self._RETRY_COUNT: int = 3

    def run_pending(
        self, queue: TransactionQueue, accounts: dict[AccountId, AbstractAccount]
    ) -> list[Transaction]:
        """Executes available pending transactions from queue"""
        processing = []
        while (tx := queue.pop_ready()) is not None:
            processing.append(self.process_one(tx, accounts))
        return processing

    def process_one(
        self, tx: Transaction, accounts: dict[AccountId, AbstractAccount]
    ) -> Transaction:
        """Executes one transaction"""
        if tx.status != TransactionStatus.QUEUED:
            raise TransactionRejected("Invalid transaction status")

        while tx.attempts < self._RETRY_COUNT:
            tx.attempts += 1
            try:
                self._execute_transaction(tx, accounts)
            except _RETRYABLE_ERRORS as exc:
                tx.errors.append(str(exc))
                if tx.attempts == self._RETRY_COUNT:
                    tx.fail()
                    return tx
                continue
            except _TERMINAL_ERRORS as exc:
                tx.errors.append(str(exc))
                tx.fail()
                return tx

            tx.complete()
            return tx

        message = "max retry count exceeded"
        tx.errors.append(message)
        tx.fail()
        return tx

    def _account(
        self, accounts: dict[AccountId, AbstractAccount], account_id: AccountId | None
    ) -> AbstractAccount:
        if account_id is None or ((account := accounts.get(account_id, None)) is None):
            raise TransactionRejected("Acount not found")
        return account

    def _is_active(self, account: AbstractAccount) -> None:
        if account.account_status is not AccountStatus.ACTIVE:
            raise TransactionRejected("Account status is invalid")
        if account.user.status is not ClientStatus.ACTIVE:
            raise TransactionRejected("Client status is invalid")

    def _execute_transaction(
        self, tx: Transaction, accounts: dict[AccountId, AbstractAccount]
    ) -> None:
        if tx.type == TransactionType.DEPOSIT:
            recipient = self._account(accounts, tx.to_account_id)
            self._is_active(recipient)
            amount_to_deposit = tx.amount
            if recipient.currency is not tx.currency:
                amount_to_deposit = convert(tx.amount, tx.currency, recipient.currency)
            recipient.deposit(round_money(amount_to_deposit))
            return

        sender = self._account(accounts, tx.from_account_id)
        self._is_active(sender)
        if tx.type == TransactionType.WITHDRAW:
            amount_to_withdraw = tx.amount
            if sender.currency is not tx.currency:
                amount_to_withdraw = convert(tx.amount, tx.currency, sender.currency)
            sender.withdraw(round_money(amount_to_withdraw))
            return

        if tx.is_external:
            """Intentional simplifying of external logic"""
            fee = round_money(tx.amount * self._EXTERNAL_TRANSFER_FEE)
            tx.fee = fee
            total = round_money(tx.amount + fee)
            sender.withdraw(convert(total, tx.currency, sender.currency))
            # transfer to self.external_destination somehow
            return

        if tx.type == TransactionType.TRANSFER:
            recipient = self._account(accounts, tx.to_account_id)
            self._is_active(recipient)

            debit = round_money(convert(tx.amount, tx.currency, sender.currency))
            credit = round_money(convert(tx.amount, tx.currency, recipient.currency))
            balance_before = sender.balance
            sender.withdraw(debit)
            credited = False
            try:
                recipient.deposit(credit)
                credited = True
            finally:
                if not credited:
                    sender.deposit(balance_before - sender.balance)
                    if sender.balance != balance_before:
                        raise TransactionCompensationError("Balance compensation error")
