FROM python:3.7.9-alpine
RUN apk add --no-cache git gcc libxml2-dev musl-dev libxslt-dev g++ re2-dev libffi-dev patch openssl-dev \
 && ln -s /usr/include/libxml2/libxml /usr/include/libxml \
 && python -m pip install -U pip \
 && pip3 install git+https://github.com/ArchiveTeam/grab-site.git
WORKDIR /data
ENTRYPOINT ["grab-site"]
