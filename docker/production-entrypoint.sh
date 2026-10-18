#!/bin/sh
set -eu

# The production image must not inherit a development mode from a runtime env file.
export DJANGO_ENV=production
exec "$@"
