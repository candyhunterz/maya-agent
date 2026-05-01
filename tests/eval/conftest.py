import pytest
from pathlib import Path

CASES_DIR = Path(__file__).parent / "cases"
RECORDINGS_DIR = Path(__file__).parent / "recordings"


def pytest_collect_file(parent, file_path):
    """Collect all .json case files automatically."""
    if file_path.suffix == ".json" and file_path.parent.name == "cases":
        return None  # We use pytest.mark.parametrize instead


@pytest.fixture
def cases_dir():
    return CASES_DIR


@pytest.fixture
def recordings_dir():
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return RECORDINGS_DIR
