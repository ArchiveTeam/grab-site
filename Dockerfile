# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.14

# ---- build stage: compile lxml/html5-parser against the system libxml2 ----
FROM python:${PYTHON_VERSION}-slim-trixie AS build

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential pkg-config libxml2-dev libxslt1-dev libre2-dev \
      libssl-dev libffi-dev zlib1g-dev ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/grab-site
ENV PATH="/opt/grab-site/bin:$PATH"

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# --no-binary lxml: html5-parser is built against the system libxml2, and a
# prebuilt lxml wheel bundles its own libxml2; the two refuse to load together.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --no-binary lxml lxml \
 && pip install --no-cache-dir .

# ---- runtime stage ----
FROM python:${PYTHON_VERSION}-slim-trixie

LABEL org.opencontainers.image.title="grab-site" \
      org.opencontainers.image.description="The archivist's web crawler: WARC output, dashboard for all crawls, dynamic ignore patterns" \
      org.opencontainers.image.source="https://github.com/ArchiveTeam/grab-site" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update \
 && apt-get install -y --no-install-recommends libxml2 libxslt1.1 ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 grabsite \
 && mkdir /data && chown grabsite:grabsite /data

COPY --from=build /opt/grab-site /opt/grab-site
ENV PATH="/opt/grab-site/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GRAB_SITE_INTERFACE=0.0.0.0

USER grabsite
# Crawl directories (WARCs, wpull.db, control files) are created here.
WORKDIR /data
VOLUME /data

# gs-server dashboard / WebSocket port
EXPOSE 29000

# Run the dashboard with: docker run --entrypoint gs-server ...
ENTRYPOINT ["grab-site"]
CMD ["--help"]
