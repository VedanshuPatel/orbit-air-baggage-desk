# STRETCH GOAL 1
# Blocks agent edits under tests/. The tests are the spec.
input=$(cat)
path=$(printf '%s' "$input" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    data = {}
tool_input = data.get("tool_input") or {}
print(tool_input.get("file_path") or tool_input.get("path") or "")
')

case "$path" in
  */tests/* | tests/* | */tests | tests)
    echo "Blocked: edits to the tests folder are not allowed. The tests are the spec." >&2
    exit 2
    ;;
esac

exit 0
