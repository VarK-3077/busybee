"""A non-numeric record value (a rating grade) skips the row instead of failing the window."""

from busybee.extract.prompts import WindowOutput


def test_rating_grade_value_skips_row():
    reply = WindowOutput.model_validate(
        {
            "entries": [],
            "records": [{"m": "Term loan rating", "v": "A+ (Negative)", "c": ["D1:p1:c0"]}],
        }
    )
    assert reply.records[0].value is None
    assert reply.records[0].to_record() is None


def test_bracketed_number_is_negative():
    reply = WindowOutput.model_validate({"entries": [], "records": [{"m": "PAT", "v": "(12.5)"}]})
    assert str(reply.records[0].value) == "-12.5"
