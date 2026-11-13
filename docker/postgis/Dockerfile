FROM postgres:18-alpine

RUN apk add --no-cache postgis \
    && find /usr/share/postgresql18/extension -maxdepth 1 -name 'postgis*' \
        -exec ln -s {} /usr/local/share/postgresql/extension/ \; \
    && find /usr/lib/postgresql18 -maxdepth 1 -name 'postgis*.so' \
        -exec ln -s {} /usr/local/lib/postgresql/ \;

COPY 10-enable-postgis.sql /docker-entrypoint-initdb.d/
