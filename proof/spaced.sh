#!/bin/sh
# Regenerate spaced from the realme trees and the phone's own (masked) tree and GPT, then compare with the real repos and FACTS.
# Usage: proof/spaced.sh ANDROID_DEVICE ANDROID_KERNEL FDT GPT OUT [OURS_DIR...]
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
dev=$1 ker=$2 fdt=$3 gpt=$4 out=$5
shift 5
ours=""
for d in "$@"; do ours="$ours --ours $d"; done
python3 -I "$here/bringup.py" spaced --android-device "$dev" --android-kernel "$ker" --title "realme 8i" --maintainer DrtSinX98 \
	--fdt "$fdt" --gpt "$gpt" $ours --out "$out"
python3 -I "$here/proof/check.py" "$out"
# the same inputs give the same bytes
python3 -I "$here/bringup.py" spaced --android-device "$dev" --android-kernel "$ker" --title "realme 8i" --maintainer DrtSinX98 \
	--fdt "$fdt" --gpt "$gpt" $ours --out "$out.again" >/dev/null
diff -r "$out" "$out.again" && echo "deterministic: two runs, no difference"
rm -rf "$out.again"
