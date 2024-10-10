FROM mcr.microsoft.com/vscode/devcontainers/python:3.10-buster
USER vscode
RUN curl -s "https://get.sdkman.io" | bash
SHELL ["/bin/bash", "-c"]
RUN source "/home/vscode/.sdkman/bin/sdkman-init.sh" && sdk install java 20.0.2-graalce
RUN mkdir -p ~/lib && cd ~/lib && curl -L -O http://www.antlr.org/download/antlr-4.13.1-complete.jar
ENV ANTLR_JAR="~/lib/antlr-4.13.1-complete.jar"
USER root