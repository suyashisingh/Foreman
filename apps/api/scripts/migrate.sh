#!/bin/bash
set -euo pipefail
uv run alembic upgrade head
