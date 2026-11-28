#!/usr/bin/env bash
# Param:
#   $1  swarm node container that runs the WordPress task
#   $2  WordPress container id on that node
#   $3  unique stamp the saved post carries
# Returns: 0 once a published post titled with $3 was saved and read back through wp-cli
set -euo pipefail

title="failover-save-$3"
id=$(timeout 60 docker exec "$1" docker exec -u www-data "$2" \
	wp post create --path=/var/www/html --post_status=publish --post_title="${title}" --porcelain)
read_back=$(timeout 60 docker exec "$1" docker exec -u www-data "$2" \
	wp post get "${id}" --path=/var/www/html --field=post_title)
if [ "${read_back}" != "${title}" ]; then
	echo "post ${id} reads back '${read_back}', expected '${title}'" >&2
	exit 1
fi
echo "post ${id} saved and read back"
