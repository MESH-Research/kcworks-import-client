#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# Copyright (C) 2024-2026 MESH Research
#
# kcworks-import-client is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see LICENSE
# file for more details.

# Quit on errors
set -o errexit

# Quit on unbound symbols
set -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

pytest_args=()
for arg in "$@"; do
  pytest_args+=("${arg}")
done

cov_args=(
  --cov=kcworks_import_client
  --cov-report=term-missing
)

# Isolated package venv so tests do not depend on the monorepo root env.
if command -v uv >/dev/null 2>&1; then
  if [ ! -d .venv ]; then
    uv venv
  fi
  uv pip install -e ".[tests]" --python .venv --quiet
  python_bin=".venv/bin/python"
else
  python -m pip install -e ".[tests]" --quiet
  python_bin="python"
fi

if [ ${#pytest_args[@]} -eq 0 ]; then
  echo "Running pytest"
  "${python_bin}" -m pytest -vv -s --disable-warnings tests/ \
    "${cov_args[@]}"
else
  echo "Running pytest with additional arguments"
  "${python_bin}" -m pytest "${pytest_args[@]}" -s --disable-warnings \
    "${cov_args[@]}"
fi

tests_exit_code=$?
exit "${tests_exit_code}"
