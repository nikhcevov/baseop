from collections import Counter
from datetime import time
from enum import StrEnum
from math import isclose
from typing import Annotated, TypedDict
from uuid import UUID, uuid4

from pydantic import Field, validate_call

from baseop.account import (
    AbstractAccount,
    AccountInfo,
    AccountStatus,
    BankAccount,
    InvalidOperationError,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)
from baseop.audit import AuditLog, AuditLogSeverity, LogEntry, RiscAnalyzer
from baseop.client import Client, ClientRisk, ClientStatus
from baseop.clock import Clock, system_now
from baseop.config import APP_TIMEZONE, Currency, is_within_window
from baseop.transaction import (
    Transaction,
    TransactionPriority,
    TransactionProcessor,
    TransactionQueue,
    TransactionStatus,
    TransactionType,
)
from baseop.uuid import AccountId, create_account_id


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


_CLOSED_FROM = time(0, tzinfo=APP_TIMEZONE)
_CLOSED_TO = time(5, tzinfo=APP_TIMEZONE)


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


class SuspiciousOperationError(BankError):
    def __init__(self, message: str, entries: list[LogEntry]) -> None:
        super().__init__(message)
        self.entries = entries


class ClientRiskReport(TypedDict):
    risk_profile: ClientRisk | None
    suspicious: bool
    findings: dict[AuditLogSeverity, int]


_SEVERITY_TO_RISK: dict[AuditLogSeverity, ClientRisk | None] = {
    AuditLogSeverity.NONE: None,
    AuditLogSeverity.LOW: "LOW",
    AuditLogSeverity.MEDIUM: "MEDIUM",
    AuditLogSeverity.HIGH: "HIGH",
}
_RISK_ORDER: dict[ClientRisk, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
_HIGH_RISK_BLOCK_LIMIT = 3
"""High severity findings a client may collect before being blocked"""


class Bank:
    def __init__(self, *, clock: Clock = system_now) -> None:
        self._clock = clock
        self._clients: dict[UUID, Client] = {}
        self._accounts: dict[AccountId, AbstractAccount] = {}
        self._account_kind: dict[AccountId, AccountKind] = {}
        self._credentials: dict[UUID, str] = {}
        """Keep creds as strings, its intentional simplifying"""
        self._authenticated: set[UUID] = set()
        self._auth_tries: dict[UUID, int] = {}
        self._queue = TransactionQueue(clock=clock)
        self._processor = TransactionProcessor(clock=clock)
        self._audit_log = AuditLog()
        self._risk_analyzer = RiscAnalyzer(clock=clock)
        self._error_stats: Counter[str] = Counter()
        self._high_risk_counts: Counter[UUID] = Counter()

    def _validate_op_time(self) -> None:
        now = self._clock()
        if is_within_window(now, _CLOSED_FROM, _CLOSED_TO):
            raise WorkingHoursError("Bank is closed from 00:00 to 05:00")

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

    def _record_error(self, tx: Transaction) -> None:
        self._error_stats[tx.fail_reason or "unknown"] += 1

    def _record_operation(self, tx: Transaction) -> None:
        self._audit_log.add(
            LogEntry(
                severity=AuditLogSeverity.NONE,
                tx_id=tx.id,
                message="Operation completed",
                tags=["transaction"],
                client_ids=self._affected_client_ids(tx),
                created_at=self._clock(),
            )
        )

    def _execute_sync(self, tx: Transaction) -> None:
        """Executes transaction immediately, propagates its failure"""
        self._processor.process_one(tx, self._accounts)
        if tx.status is TransactionStatus.FAILED:
            self._record_error(tx)
            if tx.failure is not None:
                raise tx.failure
            raise BankError(tx.fail_reason or "Transaction failed")

        self._record_operation(tx)

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
        currency: Currency = "RUB",
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

        extra_params = {}
        if kind == AccountKind.BANK:
            extra_params: dict[str, Currency] = {"currency": currency}

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

    @staticmethod
    def _affected_client_ids(tx: Transaction) -> list[UUID]:
        client_ids: list[UUID] = []
        for client_id in (tx.from_client_id, tx.to_client_id):
            if client_id is not None and client_id not in client_ids:
                client_ids.append(client_id)
        return client_ids

    def _set_risk_profile(self, client_id: UUID, severity: AuditLogSeverity) -> None:
        risk = _SEVERITY_TO_RISK[severity]
        if risk is None:
            return

        client = self._require_client(client_id)
        current = client.risk_profile
        if current is None or _RISK_ORDER[risk] > _RISK_ORDER[current]:
            object.__setattr__(client, "risk_profile", risk)

        if severity >= AuditLogSeverity.MEDIUM:
            self._mark_suspicious(client_id)

    def _audit(self, tx: Transaction) -> list[LogEntry]:
        entries = self._risk_analyzer.audit_operation(tx, self._audit_log) or []
        for entry in entries:
            self._audit_log.add(entry)

        severities: dict[UUID, AuditLogSeverity] = {}
        for entry in entries:
            for client_id in entry.client_ids:
                current = severities.get(client_id, AuditLogSeverity.NONE)
                severities[client_id] = max(current, entry.severity)

        for client_id, severity in severities.items():
            self._set_risk_profile(client_id, severity)

        return entries

    def _enforce_risk(self, tx: Transaction, entries: list[LogEntry]) -> None:
        severity = max(
            (entry.severity for entry in entries),
            default=AuditLogSeverity.NONE,
        )
        if severity is not AuditLogSeverity.HIGH:
            return

        initiator_id = tx.from_client_id or tx.to_client_id
        if initiator_id is not None:
            self._high_risk_counts[initiator_id] += 1
            if self._high_risk_counts[initiator_id] >= _HIGH_RISK_BLOCK_LIMIT:
                self._set_status(initiator_id, ClientStatus.BLOCKED)
                self._authenticated.discard(initiator_id)

        raise SuspiciousOperationError("Operation blocked by risk analyzer", entries)

    @validate_call
    def deposit(
        self,
        client_id: UUID,
        account_id: AccountId,
        amount: Annotated[float, Field(gt=0, strict=True)],
    ) -> Transaction:
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        account = self._require_own_account(client_id, account_id)
        now = self._clock()
        tx = Transaction(
            type=TransactionType.DEPOSIT,
            amount=amount,
            currency=account.currency,
            to_client_id=client_id,
            to_account_id=account.account_id,
            created_at=now,
            scheduled_at=now,
        )

        entries = self._audit(tx)
        self._validate_op_time()
        self._enforce_risk(tx, entries)
        self._execute_sync(tx)
        return tx

    @validate_call
    def withdraw(
        self,
        client_id: UUID,
        account_id: AccountId,
        amount: Annotated[float, Field(gt=0, strict=True)],
    ) -> Transaction:
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        account = self._require_own_account(client_id, account_id)
        now = self._clock()
        tx = Transaction(
            type=TransactionType.WITHDRAW,
            amount=amount,
            currency=account.currency,
            from_client_id=client_id,
            from_account_id=account.account_id,
            created_at=now,
            scheduled_at=now,
        )

        entries = self._audit(tx)
        self._validate_op_time()
        self._enforce_risk(tx, entries)
        self._execute_sync(tx)
        return tx

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
        self._validate_client_status(client_id)
        self._validate_auth(client_id)

        sender = self._require_own_account(client_id, from_account_id)
        recipient = None
        if to_account_id is not None:
            recipient = self._accounts.get(to_account_id)
            if recipient is None:
                raise AccountNotFoundError("Account not found")

        now = self._clock()
        tx = Transaction(
            type=TransactionType.TRANSFER,
            amount=amount,
            currency=sender.currency,
            from_client_id=client_id,
            from_account_id=sender.account_id,
            to_account_id=recipient.account_id if recipient else None,
            to_client_id=recipient.user.id if recipient else None,
            external_destination=external_destination,
            created_at=now,
            scheduled_at=now,
        )
        entries = self._audit(tx)
        self._validate_op_time()
        self._enforce_risk(tx, entries)
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
        self._validate_op_time()
        processed = self._processor.run_pending(self._queue, self._accounts)
        for tx in processed:
            if tx.status is TransactionStatus.COMPLETED:
                self._record_operation(tx)
            elif tx.status is TransactionStatus.FAILED:
                self._record_error(tx)
        return processed

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

    def get_client_risk_profile(self, client_id: UUID) -> ClientRiskReport:
        client = self._require_client(client_id)
        findings = [
            entry
            for entry in self._audit_log.search_logs(client_id=client_id)
            if entry.severity is not AuditLogSeverity.NONE
        ]
        counts = Counter(entry.severity for entry in findings)

        return {
            "risk_profile": client.risk_profile,
            "suspicious": client.suspicious,
            "findings": dict(counts),
        }

    def get_error_stats(self) -> dict[str, int]:
        return dict(self._error_stats)
