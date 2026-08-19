#!/usr/bin/env bash
set -euo pipefail

if (($# == 0)); then
	echo "Usage: $0 <package> [package ...]" >&2
	exit 1
fi

APT_TIMEOUT=10m
APT_OPTS=(-o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30)

sudo timeout -k 30 "${APT_TIMEOUT}" apt-get "${APT_OPTS[@]}" update
sudo timeout -k 30 "${APT_TIMEOUT}" apt-get "${APT_OPTS[@]}" install -y "$@"
