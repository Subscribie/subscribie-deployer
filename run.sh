#!/bin/bash

set -euxo pipefail

podman-compose up --build --force-recreate
#docker-compose -f compose.yaml up --build --force-recreate
