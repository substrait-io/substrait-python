FROM mcr.microsoft.com/vscode/devcontainers/python:3.13
USER vscode
RUN curl -s "https://get.sdkman.io" | bash
RUN bash -c "source $HOME/.sdkman/bin/sdkman-init.sh && \
    sdk install java 25-graalce"
COPY scripts/setup_antlr.sh /tmp/setup_antlr.sh
RUN bash /tmp/setup_antlr.sh ~/lib 
ENV ANTLR_JAR="~/lib/antlr-complete.jar"
# protoc 29.5 is the last version with protobuf python v5 which is compatible with protoletariat v3
RUN cd ~ && curl -LO https://github.com/protocolbuffers/protobuf/releases/download/v29.5/protoc-29.5-linux-x86_64.zip && \
    unzip protoc-29.5-linux-x86_64.zip -d ~/.local && \
    rm protoc-29.5-linux-x86_64.zip
RUN curl -sSL "https://github.com/bufbuild/buf/releases/download/v1.58.0/buf-$(uname -s)-$(uname -m)" -o ~/.local/bin/buf && chmod +x ~/.local/bin/buf
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
USER root