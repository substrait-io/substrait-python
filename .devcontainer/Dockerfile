FROM mcr.microsoft.com/vscode/devcontainers/python:3.9-buster
USER vscode
RUN curl -s "https://get.sdkman.io" | bash
SHELL ["/bin/bash", "-c"]
RUN source "/home/vscode/.sdkman/bin/sdkman-init.sh" && sdk install java 20.0.2-graalce
RUN mkdir -p ~/lib && cd ~/lib && curl -L -O http://www.antlr.org/download/antlr-4.13.1-complete.jar
ENV ANTLR_JAR="~/lib/antlr-4.13.1-complete.jar"
RUN cd ~ && curl -LO https://github.com/protocolbuffers/protobuf/releases/download/v25.1/protoc-25.1-linux-x86_64.zip && \
    unzip protoc-25.1-linux-x86_64.zip -d ~/.local && \
    rm protoc-25.1-linux-x86_64.zip
RUN curl -sSL "https://github.com/bufbuild/buf/releases/download/v1.50.0/buf-$(uname -s)-$(uname -m)" -o ~/.local/bin/buf && chmod +x ~/.local/bin/buf
RUN curl -LsSf https://astral.sh/uv/0.7.11/install.sh | sh
USER root