from dataclasses import dataclass
from pathlib import Path

import pytest
from seekbell.collectors.rss import parse_rss
from seekbell.config import Settings
from seekbell.db.models import Source
from seekbell.db.runtime import create_database_engine, migrate
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.domain.rules import Rule
from seekbell.services.configuration import Configuration
from seekbell.services.ingestion import Ingestion
from seekbell.sites.nodeseek import NodeSeekAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.rss_samples import rss


def batch(*ids, **fields):
    return NodeSeekAdapter().normalize(
        parse_rss(rss([{"id": key, "title": "VPS synthetic offer", **fields} for key in ids]))
    )


@dataclass
class Core:
    engine: object
    config: Configuration
    ingestion: Ingestion
    target: str
    task: str
    data_dir: Path

    def ingest(self, *ids, at=100, **fields):
        return self.ingestion.ingest("nodeseek-rss", batch(*ids, **fields), at=at)

    def count(self, model):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(model))

    def one(self, model, *conditions):
        with Session(self.engine) as session:
            return session.scalars(select(model).where(*conditions)).one()

    def queued(self):
        self.ingest(9001, at=10)
        return self.ingest(9001, 9002, at=20)


@pytest.fixture
def core(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    engine = create_database_engine(Settings(data_dir=directory))
    migrate(engine)
    configuration = Configuration(engine)
    target = configuration.create_target("Synthetic target")
    task = configuration.create_task("Synthetic rule", Rule(), [target], at=1)
    with write_session(engine) as session:
        session.get(Source, "nodeseek-rss").enabled = True
    yield Core(engine, configuration, Ingestion(engine), target, task, directory)
    engine.dispose()


class RecordingNotifier:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    async def send(self, target, payload):
        self.calls.append((target, payload))
        return self.results.pop(0) if self.results else SendResult(status="success")
