"""Bind a slot to the bank's own figure in code, without asking the model.

A slot that names a `run_parameter` (proposed exposure, projected turnover) is supplied by the
bank at run time and `bank_inputs.py` writes it as a synthetic fact (`added_by == "bank_input"`,
`source_entry_id == "bank_input:<parameter>"`). When such a fact exists, `bank_input_binding`
binds the slot to it directly, scaled exactly like any other binding, with the method
recorded in the binding note; `bind_inputs.py` does this before any LLM binding so a smaller
model can never reject or misplace a figure the bank stated itself.
"""

from busybee.policy.bank_inputs import BANK_INPUT, is_bank_input
from busybee.policy.scaling import ScalingError, to_scaled_int
from busybee.schema.facts import VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot

BANK_INPUT_METHOD = "bank_input"


def bank_input_binding(slot: InputSlot, facts: list[VerifiedFact]) -> BoundInput | None:
    """Return the slot bound to its bank-supplied fact, or None when there is none."""
    if not slot.run_parameter:
        return None
    entry_id = f"{BANK_INPUT}:{slot.run_parameter}"
    fact = next(
        (f for f in facts if is_bank_input(f) and f.source_entry_id == entry_id and f.numbers),
        None,
    )
    if fact is None:
        return None
    number = fact.numbers[0]
    try:
        scaled = to_scaled_int(number.value, number.unit, slot)
    except ScalingError:
        return None
    return BoundInput(
        slot=slot.slot,
        fact_id=fact.fact_id,
        value=number.value,
        unit=number.unit,
        value_scaled=scaled,
        note=f"method: {BANK_INPUT_METHOD}",
    )
