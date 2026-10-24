#!/bin/bash
# Double-click to install Mabillon (macOS may ask you to right-click and choose Open the first time).
cd "$(dirname "$0")/../.." || exit 1
bash packaging/mac/install.sh "$@"
status=$?
echo
read -r -p "Press Return to close this window. "
exit $status
