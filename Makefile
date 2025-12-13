setup-antlr:
	@bash scripts/setup_antlr.sh > /dev/null


codegen: antlr codegen-proto codegen-extensions codegen-version


antlr: setup-antlr
	cd third_party/substrait/grammar \
		&& java -jar ../../../lib/antlr-complete.jar -o ../../../src/substrait/gen/antlr -Dlanguage=Python3 SubstraitType.g4 \
		&& rm ../../../src/substrait/gen/antlr/*.tokens \
		&& rm ../../../src/substrait/gen/antlr/*.interp

codegen-version:
	echo -n 'substrait_version = "' > src/substrait/gen/version.py \
		&& cd third_party/substrait && git describe --tags | tr -d 'v\n' >> ../../src/substrait/gen/version.py && cd ../.. \
		&& echo '"' >> src/substrait/gen/version.py

codegen-proto:
	./scripts/gen_proto.sh

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
