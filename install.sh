#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --from-source ]]; then
    shift
    exec python3 "$script_dir/scripts/build_source.py" "$@"
fi
exec python3 "$script_dir/scripts/install_prebuilt.py" "$@"
