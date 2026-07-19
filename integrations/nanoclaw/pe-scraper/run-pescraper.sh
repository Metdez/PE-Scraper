#!/bin/sh
set -eu

export NO_PROXY="host.docker.internal,127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

exec node /workspace/agent/run-pescraper.mjs "$@"
