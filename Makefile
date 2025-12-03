setup-antlr:
	@bash scripts/setup_antlr.sh > /dev/null

antlr:
	@export ANTLR_JAR=$$(bash scripts/setup_antlr.sh); \
	cd third_party/substrait/grammar \
		&& java -jar ../../../$${ANTLR_JAR} -o ../../../src/substrait/gen/antlr -Dlanguage=Python3 SubstraitType.g4 \
		&& rm ../../../src/substrait/gen/antlr/*.tokens \
		&& rm ../../../src/substrait/gen/antlr/*.interp

codegen-extensions:
	uv run --with datamodel-code-generator datamodel-codegen \
		--input-file-type jsonschema \
		--input third_party/substrait/text/simple_extensions_schema.yaml \
		--output src/substrait/gen/json/simple_extensions.py \
		--output-model-type dataclasses.dataclass \
		--target-python-version 3.10  \
		--disable-timestamp

lint:
	uvx ruff@0.11.11 check

lint_fix:
	uvx ruff@0.11.11 check --fix

format:
	uvx ruff@0.11.11 format

pre_push: format lint_fix antlr codegen-extensions
	uv sync --extra test
	uv run pytest
