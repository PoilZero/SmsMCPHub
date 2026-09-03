from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from smsmcphub.api.app import create_app
from smsmcphub.config import AppSettings, ProviderConfig
from smsmcphub.domain.service import MessageService
from smsmcphub.storage.sqlite import SQLiteRepository


@pytest.fixture
def repository() -> SQLiteRepository:
    repo = SQLiteRepository(":memory:")
    yield repo
    repo.close()


@pytest.fixture
def service(repository: SQLiteRepository) -> MessageService:
    return MessageService(repository)


@pytest.fixture
def app(repository: SQLiteRepository):
    settings = AppSettings(
        database_path=":memory:",
        providers=(ProviderConfig(id="phone-main", type="smsforwarder"),),
    )
    return create_app(settings, repository=repository)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
