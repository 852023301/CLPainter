"""Real-data checks opt into required roots; pure unit tests need no dataset."""

from pathlib import Path

import pytest

from CLPainter.web.backend.app._config.settings import settings


def required_directory(path: str, kind: str) -> Path:
    root = Path(path)
    if not root.is_dir():
        pytest.fail(f"Required {kind} test data directory is missing: {root}", pytrace=False)
    return root


@pytest.fixture(scope="session")
def require_curated_data() -> Path:
    return required_directory(settings.CACHE_DUMP_DIR, "curated")


@pytest.fixture(scope="session")
def require_raw_data() -> Path:
    return required_directory(settings.DATA_DIR, "raw")
