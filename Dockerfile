FROM python:3.4-alpine
WORKDIR /app
COPY ./images /app/images
COPY ./libgrabsite /app/libgrabsite
COPY ./grab-site ./gs-dump-urls ./gs-server ./setup.py /app/
RUN apk add --update build-base libffi-dev && \
    pip3 install ./ && \
    apk del --purge build-base libffi-dev && \
    rm -R /root/.cache
VOLUME ["/data"]
WORKDIR /data
EXPOSE 29000
CMD ["python", "/app/gs-server"]
