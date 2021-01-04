FROM python:3-alpine
RUN apk add --no-cache git gcc libxml2-dev musl-dev libxslt-dev g++ re2-dev libffi-dev libressl-dev \
 && ln -s /usr/include/libxml2/libxml /usr/include/libxml \
 && pip3 install git+https://github.com/ludios/grab-site.git
WORKDIR /data
ENTRYPOINT ["grab-site"]
