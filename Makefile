antlr:
	cd third_party/substrait/grammar \
		&& java -jar ${ANTLR_JAR} -o ../../../src/substrait/gen/antlr -Dlanguage=Python3 SubstraitType.g4 \
		&& rm ../../../src/substrait/gen/antlr/*.tokens \
		&& rm ../../../src/substrait/gen/antlr/*.interp

codegen-extensions:
	uv run --with datamodel-code-generator datamodel-codegen \
		--input-file-type jsonschema \
		--input third_party/substrait/text/simple_extensions_schema.yaml \
		--output src/substrait/gen/json/simple_extensions.py \
		--output-model-type dataclasses.dataclass

lint:
	uvx ruff@0.11.11 check

format:
	uvx ruff@0.11.11 format
