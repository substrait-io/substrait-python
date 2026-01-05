FROM mcr.microsoft.com/vscode/devcontainers/python:3.13
USER vscode
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN curl -fsSL https://pixi.sh/install.sh | sh
ENV PATH=~/.pixi/bin:$PATH