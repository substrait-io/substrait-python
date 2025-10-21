FROM mcr.microsoft.com/vscode/devcontainers/python:3.13
USER vscode
RUN curl -s "https://get.sdkman.io" | bash
SHELL ["/bin/bash", "-c"]
RUN source "/home/vscode/.sdkman/bin/sdkman-init.sh" && sdk install java 25-graalce
RUN mkdir -p ~/lib && cd ~/lib && curl -L -O http://www.antlr.org/download/antlr-4.13.2-complete.jar
ENV ANTLR_JAR="~/lib/antlr-4.13.1-complete.jar"
RUN cd ~ && curl -LO https://github.com/protocolbuffers/protobuf/releases/download/v30.2/protoc-30.2-linux-x86_64.zip && \
    unzip protoc-30.2-linux-x86_64.zip -d ~/.local && \
    rm protoc-30.2-linux-x86_64.zip
RUN curl -sSL "https://github.com/bufbuild/buf/releases/download/v1.58.0/buf-$(uname -s)-$(uname -m)" -o ~/.local/bin/buf && chmod +x ~/.local/bin/buf
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
USER root