antlr:
	cd third_party/substrait/grammar \
		&& java -jar ${ANTLR_JAR} -o ../../../src/substrait/gen/antlr -Dlanguage=Python3 SubstraitType.g4 \
		&& rm ../../../src/substrait/gen/antlr/*.tokens \
		&& rm ../../../src/substrait/gen/antlr/*.interp
