#!/usr/bin/env bash
# Canonical pytest runner. Usage:
#   bash scripts/test.sh                              # all tests, quiet
#   bash scripts/test.sh tests/test_config.py         # one file, verbose
#   bash scripts/test.sh tests/test_config.py::test_name -x  # one node
#   bash scripts/test.sh -q -k smoke                 # full suite with explicit pytest flags
# Selector, when provided, must come before pytest options.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

validation_error() {
	echo "$1" >&2
	exit 2
}

has_explicit_verbosity_flag() {
	local arg=""
	for arg in "$@"; do
		case "$arg" in
			-q|-qq|-v|-vv|-vvv|--quiet|--verbose)
				return 0
				;;
		esac
	done
	return 1
}

looks_like_selector() {
	local value="$1"
	[[ "$value" == "tests" || "$value" == "tests/" || "$value" == tests/* || "$value" == *.py || "$value" == *::* ]]
}

require_venv() {
	if [[ ! -f .venv/bin/activate ]]; then
		validation_error "WSL venv activate script not found: .venv/bin/activate"
	fi
}

validate_selector() {
	local selector="$1"
	local file_selector=""
	local node_suffix=""

	if [[ -z "$selector" ]]; then
		validation_error "Missing test selector. Expected tests/, tests/test_file.py, or tests/test_file.py::test_name"
	fi
	if [[ "$selector" == [A-Za-z]:* ]] || [[ "$selector" == /* ]] || [[ "$selector" == \\* ]]; then
		validation_error "Test selector must be repo-relative under tests/: $selector"
	fi
	if [[ "$selector" == *\\* ]]; then
		validation_error "Test selector must use forward slashes: $selector"
	fi
	if [[ "$selector" == "tests" || "$selector" == "tests/" ]]; then
		TEST_SELECTOR_KIND="suite"
		TEST_SELECTOR="tests"
		return
	fi
	if [[ "$selector" != tests/* ]]; then
		validation_error "Test selector must be under tests/: $selector"
	fi

	if [[ "$selector" == *::* ]]; then
		file_selector="${selector%%::*}"
		node_suffix="${selector#*::}"
		if [[ -z "$node_suffix" ]]; then
			validation_error "Pytest node suffix must not be empty: $selector"
		fi
		if [[ ! -f "$file_selector" ]]; then
			validation_error "Test file not found under repository root: $file_selector"
		fi
		if [[ "$file_selector" != *.py ]]; then
			validation_error "Pytest node selector must point to a Python test file: $selector"
		fi
		TEST_SELECTOR_KIND="node"
		TEST_SELECTOR="$file_selector::$node_suffix"
		return
	fi

	if [[ -d "$selector" ]]; then
		TEST_SELECTOR_KIND="suite"
		TEST_SELECTOR="${selector%/}"
		return
	fi
	if [[ -f "$selector" ]]; then
		if [[ "$selector" != *.py ]]; then
			validation_error "Test selector must point to a Python test file: $selector"
		fi
		TEST_SELECTOR_KIND="file"
		TEST_SELECTOR="$selector"
		return
	fi

	validation_error "Test selector not found under repository root: $selector"
}

TEST_SELECTOR="tests"
TEST_SELECTOR_KIND="suite"
PYTEST_ARGS=()

if [[ $# -gt 0 && "${1:-}" != -* ]]; then
	validate_selector "$1"
	shift
fi

PYTEST_ARGS=("$@")

for arg in "${PYTEST_ARGS[@]}"; do
	if looks_like_selector "$arg"; then
		validation_error "Test selector must appear before pytest options: $arg"
	fi
done

require_venv
. .venv/bin/activate

if has_explicit_verbosity_flag "${PYTEST_ARGS[@]}"; then
	exec pytest "$TEST_SELECTOR" "${PYTEST_ARGS[@]}"
fi

if [[ "$TEST_SELECTOR_KIND" == "suite" ]]; then
	exec pytest "$TEST_SELECTOR" -q "${PYTEST_ARGS[@]}"
fi

exec pytest "$TEST_SELECTOR" -vv "${PYTEST_ARGS[@]}"
