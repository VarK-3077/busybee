.PHONY: install test lint run-synthetic

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

run-synthetic:
	PYTHONPATH=tests/e2e BUSYBEE_LLM_PROVIDER=mock BUSYBEE_LLM_MOCK_CALLABLE=fake_llm:fake_llm \
	BUSYBEE_EMBED_PROVIDER=hashing uv run busybee run --docs data/synthetic/acme_textiles \
		--bank demo_bank --run-id synthetic --out workspace/synthetic/out \
		--proposed-exposure 432
