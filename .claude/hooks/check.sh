#!/usr/bin/env bash
# Stop hook: lint, format, type-check and test when Python files or pyproject.toml
# have uncommitted changes.
#
# Exit 2 blocks the stop and feeds the errors back to Claude. To avoid an endless
# loop, a stop that is already the result of this hook (stop_hook_active) is never
# blocked again: the user gets a warning instead.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"

# Hook input arrives as JSON on stdin; a manual run from a terminal has none.
stop_hook_active=false
if [[ ! -t 0 ]]; then
    stop_hook_active=$(jq -r '.stop_hook_active // false' 2>/dev/null || echo false)
fi

# --untracked-files=all lists files inside new, untracked directories.
if ! git status --porcelain --untracked-files=all -- src tests pyproject.toml \
    | grep -qE '(\.py|pyproject\.toml)$'; then
    exit 0
fi

log=$(mktemp)
trap 'rm -f "$log"' EXIT

run_pytest() {
    local status=0
    uv run pytest -q || status=$?
    # 5 = no tests collected: not a failure while the project has no tests yet.
    [[ "$status" -eq 0 || "$status" -eq 5 ]]
}

# Every stage runs even after a failure, so the single blocking stop shows all
# the errors at once.
run_checks() {
    local status=0
    echo "== ruff check" && uv run ruff check --fix || status=1
    echo "== ruff format" && uv run ruff format || status=1
    echo "== mypy" && uv run mypy src tests || status=1
    echo "== pytest" && run_pytest || status=1
    return "$status"
}

if run_checks >"$log" 2>&1; then
    exit 0
fi

if [[ "$stop_hook_active" == "true" ]]; then
    jq -n '{systemMessage: "Checks still failing after one fix attempt (ruff/mypy/pytest): run .claude/hooks/check.sh to see the errors."}'
    exit 0
fi

tail -n 150 "$log" >&2
exit 2
