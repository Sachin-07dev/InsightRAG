#!/bin/sh
set -eu
umask 077
# Avoid placing the password in process arguments or tracked configuration.
printf 'bind 0.0.0.0\nprotected-mode yes\nappendonly yes\ndir /data\nrequirepass %s\n' \
  "$(cat /run/secrets/redis_password)" > /tmp/insightrag-redis.conf
chown redis:redis /tmp/insightrag-redis.conf
exec /usr/local/bin/docker-entrypoint.sh redis-server /tmp/insightrag-redis.conf
