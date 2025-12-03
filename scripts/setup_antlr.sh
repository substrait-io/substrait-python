#!/bin/bash
# Setup ANTLR for Substrait Python

set -e

ANTLR_VERSION="4.13.2"
ANTLR_JAR_DIR="lib"
ANTLR_JAR="${ANTLR_JAR_DIR}/antlr-complete.jar"
ANTLR_URL="http://www.antlr.org/download/antlr-${ANTLR_VERSION}-complete.jar"
VERSION_FILE="${ANTLR_JAR_DIR}/.antlr_version"

echo "Setting up ANTLR ${ANTLR_VERSION}..." >&2

# Create directory if it doesn't exist
mkdir -p "${ANTLR_JAR_DIR}"

# Check if installed version matches required version
INSTALLED_VERSION=""
if [ -f "${VERSION_FILE}" ]; then
    INSTALLED_VERSION=$(cat "${VERSION_FILE}")
fi

if [ "${INSTALLED_VERSION}" = "${ANTLR_VERSION}" ] && [ -f "${ANTLR_JAR}" ]; then
    echo "ANTLR ${ANTLR_VERSION} is already installed" >&2
else
    echo "Downloading ANTLR ${ANTLR_VERSION}..." >&2
    rm -f "${ANTLR_JAR}"
    curl -s -L -o "${ANTLR_JAR}" "${ANTLR_URL}"
    echo "${ANTLR_VERSION}" > "${VERSION_FILE}"
    echo "ANTLR ${ANTLR_VERSION} downloaded successfully" >&2
fi

# Output the path so it can be captured
echo "${ANTLR_JAR}"
