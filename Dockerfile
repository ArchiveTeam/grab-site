# syntax=docker/dockerfile:1.6-labs

ARG VARIANT="3.12-slim"
ARG WORKDIR="/usr/src/grab-site"

# ------------------------------------------------------------------------------

FROM python:${VARIANT} as host-deps

ARG VARIANT
ARG WORKDIR

WORKDIR ${WORKDIR}

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked <<EOF
	apt-get -y update
	apt-get -y install --no-install-recommends \
		build-essential \
		libre2-dev \
		libxml2-dev \
		libxslt-dev \
		pkg-config \
		zlib1g-dev
EOF

# ------------------------------------------------------------------------------

FROM host-deps as build-deps

ARG VARIANT
ARG WORKDIR

WORKDIR ${WORKDIR}

COPY ./pyproject.toml ${WORKDIR}

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked <<EOF
	pip install --no-binary lxml --user ${WORKDIR}
EOF

# ------------------------------------------------------------------------------

FROM build-deps as builder

ARG VARIANT
ARG WORKDIR

WORKDIR ${WORKDIR}

COPY --from=build-deps ${WORKDIR}/pyproject.toml ${WORKDIR}

COPY ./src ${WORKDIR}/src

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked <<EOF
	pip install --user ${WORKDIR}
EOF

# ------------------------------------------------------------------------------

FROM python:${VARIANT} as runner

ARG VARIANT
ARG WORKDIR

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR ${WORKDIR}

# TODO: https://docs.docker.com/build/guide/multi-platform
COPY --from=host-deps /usr/lib/x86_64-linux-gnu/libexslt.so   /usr/lib/x86_64-linux-gnu/libexslt.so.0
COPY --from=host-deps /usr/lib/x86_64-linux-gnu/libicudata.so /usr/lib/x86_64-linux-gnu/libicudata.so.72
COPY --from=host-deps /usr/lib/x86_64-linux-gnu/libicuuc.so   /usr/lib/x86_64-linux-gnu/libicuuc.so.72
COPY --from=host-deps /usr/lib/x86_64-linux-gnu/libxml2.so    /usr/lib/x86_64-linux-gnu/libxml2.so.2
COPY --from=host-deps /usr/lib/x86_64-linux-gnu/libxslt.so    /usr/lib/x86_64-linux-gnu/libxslt.so.1

COPY --from=builder /root/.local /root/.local

COPY ./Dockerfile ${WORKDIR}

EXPOSE 29000

VOLUME  /tmp/gs
WORKDIR /tmp/gs

CMD ["gs-server"]
