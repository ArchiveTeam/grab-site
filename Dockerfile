ARG PYTHON_VERSION=3.7
ARG ALPINE_VERSION=3.13

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION}

WORKDIR /app
VOLUME [ "/data" ]

ENV GRAB_SITE_INTERFACE=0.0.0.0
ENV GRAB_SITE_PORT=29000
ENV GRAB_SITE_HOST=127.0.0.1
EXPOSE 29000

RUN apk add --no-cache \
		git \
		gcc \
		libxml2-dev \
		musl-dev \
		libxslt-dev \
		g++ \
		re2-dev \
		libffi-dev \
		openssl-dev \
		patch \
		cargo \
	&& ln -s /usr/include/libxml2/libxml /usr/include/libxml \
	&& addgroup -S grab-site \
	&& adduser -S -G grab-site grab-site \
	&& chown -R grab-site:grab-site $(pwd) \
	&& mkdir -p /data \
	&& chown -R grab-site:grab-site /data

USER grab-site:grab-site
ENV PATH="/app:$PATH"
ENTRYPOINT [ "entrypoint.sh" ]
CMD [ "gs-server" ]

# TODO: resolve dependencies before loading library code to take advantage of build caching
# 	setup.py requires libgrabsite/__init__.py (__version__ property) to work

COPY --chown=grab-site:grab-site . .

RUN pip install . \
	&& chmod +x entrypoint.sh

WORKDIR /data

# docker build -t grab-site:latest .
# docker run --rm -it --entrypoint sh grab-site:latest
# docker network create -d bridge grab-network
# docker run --net=grab-network --name=gs-server -d -p 29000:29000 --restart=unless-stopped grab-site:latest
# docker run --net=grab-network --rm -d -e GRAB_SITE_HOST=gs-server -v ./data:/data:rw grab-site:latest grab-site https://www.example.com/
# docker run --net=grab-network --rm -d -e GRAB_SITE_HOST=gs-server -v C:\projects\grab-site\data:/data:rw grab-site:latest grab-site https://www.example.com/