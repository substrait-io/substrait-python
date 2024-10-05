antlr:
	java -jar ${ANTLR_JAR} -o src/substrait/gen/antlr -Dlanguage=Python3 SubstraitType.g4
