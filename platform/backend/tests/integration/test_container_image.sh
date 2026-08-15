#!/bin/sh
set -eu

image="${BEARVOICE_API_IMAGE:-bearvoice-api:latest}"

docker run --rm --entrypoint python "$image" -c \
  'from bearvoice.main import app; assert app.title == "BearVoice"'
