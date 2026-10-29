"""Load a gold set: the material facts a good report must contain and the planted errors.

A gold file (`data/gold/<slug>.json`) holds `material_facts` (statement, category, doc and
page hints, must_have) and `planted_errors` (a wrong statement and why it is wrong). Both are
read into small pydantic models. `gold_path_for` turns a company name or slug into the file
path so callers can say `load_gold(gold_path_for("Acme Textiles Limited"))`.
"""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from busybee.schema.io import read_json

DEFAULT_GOLD_DIR = Path("data/gold")
_SUFFIXES = ("limited", "ltd", "pvt", "private", "inc", "corp")


class GoldFact(BaseModel):
    """One statement a report is expected to contain."""

    statement: str
    category: str = "other"
    doc_hint: str = ""
    page_hint: int | None = None
    must_have: bool = True


class PlantedError(BaseModel):
    """A deliberately wrong statement that verification should refuse to accept."""

    statement: str
    why_wrong: str = ""


class GoldSet(BaseModel):
    """A company's gold material facts and planted errors."""

    company: str = ""
    slug: str = ""
    material_facts: list[GoldFact] = Field(default_factory=list)
    planted_errors: list[PlantedError] = Field(default_factory=list)


def load_gold(path: str | Path) -> GoldSet:
    """Read a gold JSON file into a GoldSet."""
    return GoldSet.model_validate(read_json(path))


def slugify_company(company: str) -> str:
    """Turn 'Acme Textiles Limited' into 'acme_textiles'."""
    words = re.findall(r"[a-z0-9]+", company.lower())
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return "_".join(words)


def gold_path_for(company_or_slug: str, gold_dir: str | Path = DEFAULT_GOLD_DIR) -> Path:
    """Return the gold file path for a company name or slug."""
    return Path(gold_dir) / f"{slugify_company(company_or_slug)}.json"
