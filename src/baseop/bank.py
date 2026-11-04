from datetime import UTC, datetime, time
from enum import StrEnum
from math import isclose
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import Field, validate_call

from baseop.account import (
    AbstractAccount,
    AccountCurrency,
    AccountInfo,
    AccountStatus,
    BankAccount,
    InvalidOperationError,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)
from baseop.client import Client, ClientStatus
from baseop.transaction import (
    Transaction,
    TransactionPriority,
    TransactionProcessor,
    TransactionQueue,
    TransactionType,
)
from baseop.uuid import AccountId, create_account_id

_TIMEZONE = UTC
"""Intentional assumption"""


class AccountKind(StrEnum):
    BANK = "bank"
    INVESTMENT = "investment"
    PREMIUM = "premium"
    SAVING = "saving"


_ACCOUNT_KIND_FACTORY: dict[AccountKind, type[AbstractAccount]] = {
    AccountKind.BANK: BankAccount,
    AccountKind.INVESTMENT: InvestmentAccount,
    AccountKind.PREMIUM: PremiumAccount,
    AccountKind.SAVING: SavingsAccount,
}


class BankError(Exception):
    pass


class AccountNotFoundError(BankError):
    pass


class ClientNotFoundError(BankError):
    pass


class DuplicateIdError(BankError):
    pass


class AuthenticationError(BankError):
    pass


class WorkingHoursError(BankError):
    pass


class ClientInactiveError(BankError):
    pass


class Bank:
    def __init__(self) -> None:
        self._clients: dict[UUID, Client] = {}
        self._accounts: dict[AccountId, AbstractAccount] = {}
        self._account_kind: dict[AccountId, AccountKind] = {}
        self._credentials: dict[UUID, str] = {}
        """Keep creds as strings, its intentional simplifying"""
        self._authenticated: set[UUID] = set()
        self._auth_tries: dict[UUID, int] = {}
        self._queue = TransactionQueue()
        self._processor = TransactionProcessor()

    def _validate_op_time(self) -> None:
        bank_start = time(5, 0, 0)
        now = datetime.now(_TIMEZONE).astimezone(_TIMEZONE).time()
        if now < bank_start:
            raise WorkingHoursError("Bank working hours 05:00 to 00:00")

    def _require_client(self, client_id: UUID) -> Client:
        client = self._clients.get(client_id)
        if client is None:
            raise ClientNotFoundError("Client not found")
        return client

    def _validate_client_status(self, client_id: UUID):
        client = self._require_client(client_id)
        if client.status != ClientStatus.ACTIVE:
            raise ClientInactiveError("Client inactive")

    @validate_call
    def _set_status(self, client_id: UUID, status: ClientStatus) -> None:
        client = self._require_client(client_id)
        if status != client.status:
            object.__setattr__(client, "status", status)

    def _mark_suspicious(self, client_id: UUID) -> None:
        object.__setattr__(self._require_client(client_id), "suspicious", True)

    @validate_call
    def _add_account_id(self, client_id: UUID, account_id: AccountId) -> None:
        client = self._require_client(client_id)
        if account_id not in client.account_ids:
            client.account_ids.append(account_id)

    def _remove_account_id(self, client: Client, account_id: AccountId) -> None:
        if account_id in client.account_ids:
            client.account_ids.remove(account_id)

    def _require_own_account(
        self, client_id: UUID, account_id: AccountId
    ) -> AbstractAccount:
        account = self._accounts.get(account_id)
        if account is None or account.user.id != client_id:
            raise AccountNotFoundError("Account not found")
        return account

    @validate_call
    def add_client(
        self, *, first_name, last_name, age, middle_name=None, contacts=(), secret: str
    ) -> Client:
        self._validate_op_time()
        client_id = uuid4()
        if client_id in self._clients:
            raise DuplicateIdError("Duplicate client uuid")

        client = Client(
            id=client_id,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            age=age,
            contacts=contacts,
        )

        self._credentials[client_id] = secret
        self._clients[client_id] = client
        return client

    @validate_call
    def open_account(
        self,
        client_id: UUID,
        kind: AccountKind,
        currency: AccountCurrency = AccountCurrency.RUB,
    ) -> AccountInfo:
        self._validate_op_time()
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        client = self._require_client(client_id)

        account_factory = _ACCOUNT_KIND_FACTORY[kind]
        if not account_factory:
            raise ValueError("Account kind is invalid")

        account_id = create_account_id()
        if account_id in self._accounts:
            raise DuplicateIdError("Duplicate account id")

        extra_params = {"currency": currency} if kind == AccountKind.BANK else {}
        account = account_factory(
            account_id=account_id,
            user=client,
            account_status=AccountStatus.ACTIVE,
            balance=0,
            **extra_params,
        )
        self._accounts[account_id] = account
        self._account_kind[account_id] = kind
        self._add_account_id(client_id, account_id)
        return account.get_account_info()

    @validate_call
    def deposit(
        self,
        client_id: UUID,
        account_id: AccountId,
        amount: Annotated[float, Field(strict=True)],
    ) -> AccountInfo:
        self._validate_op_time()
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        account = self._require_own_account(client_id, account_id)
        account.deposit(amount)
        return account.get_account_info()

    @validate_call
    def withdraw(
        self,
        client_id: UUID,
        account_id: AccountId,
        amount: Annotated[float, Field(strict=True)],
    ) -> AccountInfo:
        self._validate_op_time()
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        account = self._require_own_account(client_id, account_id)
        account.withdraw(amount)
        return account.get_account_info()

    @validate_call
    def submit_transfer(
        self,
        client_id: UUID,
        from_account_id: AccountId,
        amount: Annotated[float, Field(strict=True, gt=0)],
        *,
        to_account_id: AccountId | None = None,
        external_destination: str | None = None,
    ) -> Transaction:
        self._validate_op_time()
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        sender = self._require_own_account(client_id, from_account_id)
        recipient = None
        if to_account_id is not None:
            recipient = self._accounts.get(to_account_id)
            if recipient is None:
                raise AccountNotFoundError("Account not found")

        tx = Transaction(
            type=TransactionType.TRANSFER,
            amount=amount,
            currency=sender.currency,
            from_client_id=client_id,
            from_account_id=sender.account_id,
            to_account_id=recipient.account_id if recipient else None,
            to_client_id=recipient.user.id if recipient else None,
            external_destination=external_destination,
        )
        self._queue.add(tx, TransactionPriority.MEDIUM)
        return tx

    @validate_call
    def cancel_transaction(self, client_id: UUID, tx_id: UUID) -> bool:
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        tx = self._queue.get(tx_id)
        if tx is None or tx.from_client_id != client_id:
            return False
        self._queue.cancel(tx_id)
        return True

    def run_transactions(self) -> list[Transaction]:
        return self._processor.run_pending(self._queue, self._accounts)

    @validate_call
    def close_account(self, client_id: UUID, account_id: AccountId) -> None:
        self._validate_op_time()
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        account = self._require_own_account(client_id, account_id)
        if not isclose(account.total_value, 0.0, abs_tol=0.001):
            raise InvalidOperationError("Account total value different from 0")
        account.close()

    @validate_call
    def freeze_account(self, client_id: UUID, account_id: AccountId) -> None:
        self._validate_op_time()
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        self._require_own_account(client_id, account_id).freeze()

    @validate_call
    def unfreeze_account(self, client_id: UUID, account_id: AccountId) -> None:
        self._validate_op_time()
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        self._require_own_account(client_id, account_id).unfreeze()

    def _validate_auth(self, client_id: UUID | None) -> None:
        if client_id not in self._authenticated:
            raise AuthenticationError("Operation is not permitted")

    @validate_call
    def authenticate_client(self, client_id: UUID, secret: str):
        client = self._require_client(client_id)
        if client.status != ClientStatus.ACTIVE:
            raise AuthenticationError("Client status in invalid")

        if not self._auth_tries.get(client_id, 0):
            self._auth_tries[client_id] = 0
        if self._auth_tries[client_id] > 2:
            raise AuthenticationError("Invalid credentials limit exceeded")
        if secret != self._credentials[client_id]:
            self._mark_suspicious(client_id)
            self._auth_tries[client_id] += 1
            if self._auth_tries[client_id] == 3:
                self._set_status(client_id, ClientStatus.BLOCKED)
                self._authenticated.discard(client_id)
                self._auth_tries[client_id] = 0
            raise AuthenticationError("Invalid credentials")

        self._auth_tries[client_id] = 0
        self._authenticated.add(client.id)

    @validate_call
    def search_accounts(
        self,
        client_id: UUID,
        *,
        status: AccountStatus | None = None,
        kind: AccountKind | None = None,
    ) -> list[AccountInfo]:
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        return [
            account.get_account_info()
            for account in self._accounts.values()
            if (client_id is None or account.user.id == client_id)
            and (status is None or account.account_status == status)
            and (kind is None or self._account_kind[account.account_id] == kind)
        ]

    def get_total_balance(self) -> float:
        return sum(
            account.total_value
            for account in self._accounts.values()
            if account.account_status != AccountStatus.CLOSED
        )

    def get_clients_ranking(self) -> dict[UUID, float]:
        """Returns clients with balances dict, sorted by balance, DESC"""
        ranking = {}

        for client in self._clients.values():
            total_balance = sum(
                account.total_value
                for account in self._accounts.values()
                if account.user.id == client.id
                and account.account_status != AccountStatus.CLOSED
            )
            ranking[client.id] = total_balance

        return dict(sorted(ranking.items(), reverse=True, key=lambda x: x[1]))
