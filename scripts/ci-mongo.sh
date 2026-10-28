#!/usr/bin/env bash
# Starts a single-node MongoDB replica set on 127.0.0.1:27017 for CI.
# Every wait is bounded, and the container log is printed when mongod dies,
# so a crash fails the job in seconds instead of hanging until the job timeout.
# Tries each image in turn: some runner images have crashed mongo:8.0 at boot.
set -euo pipefail

IMAGES=${MONGO_IMAGES:-"mongo:8.0 mongo:7.0"}

running() { [ "$(docker inspect -f '{{.State.Running}}' mongo 2>/dev/null)" = "true" ]; }

start() {
  docker rm -f mongo >/dev/null 2>&1 || true
  docker run -d --name mongo -p 27017:27017 \
    -e GLIBC_TUNABLES=glibc.pthread.rseq=0 "$1" --replSet rs0 --bind_ip_all >/dev/null
  for _ in $(seq 1 60); do
    running || { echo "mongod exited:"; docker logs --tail 50 mongo 2>&1; return 1; }
    if docker exec mongo mongosh --quiet --eval \
      "try { rs.status().ok } catch (e) { rs.initiate({_id:'rs0',members:[{_id:0,host:'127.0.0.1:27017'}]}).ok }" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  for _ in $(seq 1 60); do
    running || { echo "mongod exited:"; docker logs --tail 50 mongo 2>&1; return 1; }
    [ "$(docker exec mongo mongosh --quiet --eval 'rs.status().myState' 2>/dev/null)" = "1" ] && return 0
    sleep 1
  done
  echo "replica set did not become primary within 60s:"; docker logs --tail 50 mongo 2>&1
  return 1
}

for image in $IMAGES; do
  echo "Starting $image"
  if start "$image"; then
    echo "MongoDB $image is primary on 127.0.0.1:27017"
    exit 0
  fi
done
echo "No MongoDB image started" >&2
exit 1
