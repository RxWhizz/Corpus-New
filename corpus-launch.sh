#!/usr/bin/env bash
cd "$(dirname "$(readlink -f "$0")")"
exec env -u ELECTRON_RUN_AS_NODE PYTHON=python3 ./dist/linux-unpacked/corpus "$@"
