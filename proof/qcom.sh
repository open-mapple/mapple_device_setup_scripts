#!/bin/sh
# A Qualcomm phone's trees must stop the run and write nothing.
# Usage: proof/qcom.sh ANDROID_DEVICE ANDROID_KERNEL (for example LineageOS's sweet, sm6150-common beside it, and the sm6150 kernel)
here=$(cd "$(dirname "$0")/.." && pwd)
out=$(mktemp -d)/out
if msg=$(python3 -I "$here/bringup.py" x --android-device "$1" --android-kernel "$2" --out "$out" 2>&1); then
	echo "FAILED: the run went on"; exit 1
fi
echo "$msg"
[ ! -e "$out" ] || { echo "FAILED: wrote $out"; exit 1; }
echo "$msg" | grep -q "only handles MediaTek" || { echo "FAILED: no explanation"; exit 1; }
echo "stopped, nothing written"
