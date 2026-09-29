FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY codegraph ./codegraph
RUN pip install '.[mcp]' && \
    groupadd --gid 10001 codegraph && \
    useradd --uid 10001 --gid codegraph --create-home codegraph
USER 10001:10001
WORKDIR /repo
ENTRYPOINT ["codegraph"]
CMD ["--help"]
