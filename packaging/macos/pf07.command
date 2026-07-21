#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$script_dir/PF07 Launcher.app/Contents/MacOS/PF07-OrderOps"
