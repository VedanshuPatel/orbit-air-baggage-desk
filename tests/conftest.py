from datetime import datetime

import pytest

import db

T0 = datetime.fromisoformat("2026-11-02T08:00:00")


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()
