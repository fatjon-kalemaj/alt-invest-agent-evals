.PHONY: install test check eval calibrate

install:
	uv sync --extra dev

test:
	uv run pytest -q

check:  ## offline harness sanity check: oracle should pass, null should fail
	uv run cimeval run --agent oracle --no-judge
	uv run cimeval run --agent null --no-judge

eval:
	uv run cimeval run --agent claude --prompt v2 --reps 2

calibrate:
	uv run cimeval calibrate-judge
