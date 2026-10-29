"""What the extractor is told beyond the pages: the policy focus and the rating agency's flags.

`ReadingAids` is passed down the extract functions. `focus` supplies the checklist added to the
system prompt of every window and the importance rule applied to each finished document (see
policy_focus.py); `flagged` is the digest of the rating rationales (see rating_first.py), added
to the user prompt of the windows of every other document. Both default to empty, which gives
the plain prompt and leaves the model's importance ratings as they are.
"""

from dataclasses import dataclass, replace

from .policy_focus import PolicyFocus


@dataclass(frozen=True)
class ReadingAids:
    """Optional policy additions for the extract stage."""

    focus: PolicyFocus | None = None
    flagged: str = ""

    def with_flagged(self, flagged: str) -> "ReadingAids":
        """A copy carrying the rating digest."""
        return replace(self, flagged=flagged)

    @property
    def checklist(self) -> str:
        """The policy checklist text, empty without a focus."""
        return self.focus.checklist if self.focus is not None else ""
