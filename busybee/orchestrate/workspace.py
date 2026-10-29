"""The on-disk layout of one run: `workspace/<run_id>/` and every file the stages exchange.

Each property is a path only; nothing here touches the disk except `ensure`, which creates the
run directory. Stages and the orchestrator use these paths so the file names named in
ARCHITECTURE section 2 live in exactly one place.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """Path properties for one run directory."""

    root: Path
    run_id: str

    @property
    def run_dir(self) -> Path:
        """The directory holding every file of this run."""
        return self.root / self.run_id

    @property
    def corpus_dir(self) -> Path:
        return self.run_dir / "corpus"

    @property
    def documents(self) -> Path:
        return self.corpus_dir / "documents.json"

    @property
    def index_dir(self) -> Path:
        return self.run_dir / "index"

    @property
    def vectors(self) -> Path:
        return self.index_dir / "vectors.npy"

    @property
    def notebook(self) -> Path:
        return self.run_dir / "notebook.json"

    @property
    def verified_facts(self) -> Path:
        return self.run_dir / "verified_facts.json"

    @property
    def dropped(self) -> Path:
        return self.run_dir / "dropped.json"

    @property
    def scores(self) -> Path:
        return self.run_dir / "scores.json"

    @property
    def policy_eval(self) -> Path:
        return self.run_dir / "policy_eval.json"

    @property
    def inferences(self) -> Path:
        return self.run_dir / "inferences.json"

    @property
    def concerns(self) -> Path:
        return self.run_dir / "concerns.json"

    @property
    def report(self) -> Path:
        return self.run_dir / "report.json"

    @property
    def llm_log(self) -> Path:
        return self.run_dir / "llm_log.jsonl"

    @property
    def stages(self) -> Path:
        return self.run_dir / "stages.json"

    @property
    def out_dir(self) -> Path:
        return self.run_dir / "out"

    @property
    def lean_dir(self) -> Path:
        return self.run_dir / "lean"

    def ensure(self) -> Path:
        """Create the run directory and return it."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        return self.run_dir
