#!/usr/bin/env bash
set -euo pipefail

APT_CACHE_DATA="${APT_CACHE_DATA:-${RUNNER_TEMP:-/tmp}/apt-cacher-ng}"
APT_CACHE_IMAGE="${APT_CACHE_IMAGE:-sameersbn/apt-cacher-ng:3.7.4-20220421}"
mkdir -p "${APT_CACHE_DATA}"
chmod 0777 "${APT_CACHE_DATA}"

docker run -d --name apt-cache \
	--network swarm-lab \
	--hostname apt-cache \
	-v "${APT_CACHE_DATA}:/var/cache/apt-cacher-ng" \
	"${APT_CACHE_IMAGE}"

for i in $(seq 1 60); do
	if docker exec apt-cache bash -c "</dev/tcp/127.0.0.1/3142" 2>/dev/null; then
		echo "apt-cacher-ng ready after ${i}s"
		exit 0
	fi
	sleep 1
done
echo "FAILURE: apt-cacher-ng did not become responsive within 60s"
echo "--- docker logs apt-cache ---"
docker logs apt-cache 2>&1 | tail -50
echo "--- docker inspect apt-cache (State) ---"
docker inspect --format '{{json .State}}' apt-cache 2>&1 || true
exit 1
