#!/bin/sh
# A MediaTek phone that is not realme's: the Redmi Note 9 (MT6768) from LineageOS's public trees must be read as mt6768, with
# TARGET_BOARD_PLATFORM found in the common tree beside the device tree, and nothing of mt6781 in the output. The same trees
# stripped of what names the SoC, or told something else, must stop.
# Usage: proof/merlinx.sh ANDROID_DEVICE ANDROID_KERNEL
#   android_device_xiaomi_merlinx, with android_device_xiaomi_mt6768-common beside it, and android_kernel_xiaomi_mt6768
here=$(cd "$(dirname "$0")/.." && pwd)
dev=$1 ker=$2
tmp=$(mktemp -d)
fail() { echo "FAILED: $1"; exit 1; }
run() { python3 -I "$here/bringup.py" merlinx --android-device "$dev" --android-kernel "$ker" --title "Redmi Note 9" "$@"; }

run --out "$tmp/out" > "$tmp/log" || fail "the run stopped"
cat "$tmp/log"
grep -q "^SoC: mt6768, from TARGET_BOARD_PLATFORM (.*mt6768.mk:[0-9]*)" "$tmp/log" || fail "SoC or its source"
grep -q "^Overlay: merlin.dts" "$tmp/log" || fail "overlay"
grep -q "^SoC: mt6768, from TARGET_BOARD_PLATFORM" "$tmp/out/BRIEF.md" || fail "SoC missing from BRIEF.md"
grep -q "$(printf '\tsoc\tmt6768$')" "$tmp/out/merlinx/device.conf" || fail "device.conf soc"
grep -q "6x a55 + 2x a75" "$tmp/out/merlinx/device.conf" || fail "cores"
for kv in soc_vendor:mediatek machine:MT6768 boot:lk-chain bootimg_version:2 bootimg_pagesize:2048 bootimg_os_version: gpu:mali root_size: payload_max:; do
	grep -q "$(printf '\t%s\t%s$' "${kv%%:*}" "${kv#*:}")" "$tmp/out/merlinx/device.conf" || fail "device.conf ${kv%%:*}"
done
grep -q "^# bootimg_os_version:" "$tmp/out/merlinx/device.conf" || fail "no comment on the empty bootimg_os_version"
# no --fdt here: RAM and the framebuffer are not in the trees, so they stay empty under a comment
grep -q "^RAM = None" "$tmp/out/merlinx/adt.py" && grep -q "^FB = None" "$tmp/out/merlinx/adt.py" && grep -q "^ECID = None" "$tmp/out/merlinx/adt.py" ||
	fail "adt.py: empty values"
grep -q "^PRODUCT_NAME = 'Redmi Note 9'" "$tmp/out/merlinx/adt.py" || fail "adt.py PRODUCT_NAME"
! grep -rqi "mt6781" "$tmp/out" || fail "mt6781 in the output"
echo "match                mt6768 from the common tree's TARGET_BOARD_PLATFORM, overlay merlin, 6x A55 + 2x A75, no mt6781"
echo "match                device.conf soc_vendor, machine, boot and the boot image header; adt.py with what it could not read left empty"

# the device tree alone: nothing names the SoC any more
mkdir "$tmp/alone"
ln -s "$(cd "$dev" && pwd)" "$tmp/alone/device_merlinx"
python3 -I "$here/bringup.py" merlinx --android-device "$tmp/alone/device_merlinx" --android-kernel "$ker" --out "$tmp/o2" >"$tmp/err" 2>&1 \
	&& fail "went on without a SoC"
grep -q "Pass --soc" "$tmp/err" && [ ! -e "$tmp/o2" ] || fail "no stop, or output written"
echo "match                no source names the SoC: stops, asks for --soc, writes nothing"

# a live tree that says another SoC
printf '/dts-v1/;\n/ { compatible = "mediatek,mt6785"; };\n' > "$tmp/live.dts"
run --fdt "$tmp/live.dts" --out "$tmp/o3" >"$tmp/err" 2>&1 && fail "went on with disagreeing sources"
grep -q "sources disagree" "$tmp/err" && [ ! -e "$tmp/o3" ] || fail "no stop, or output written"
echo "match                sources disagree: stops, lists them, writes nothing"
run --fdt "$tmp/live.dts" --soc mt6768 --out "$tmp/o4" >/dev/null 2>&1 || fail "--soc did not settle it"
echo "match                --soc settles a disagreement"
rm -rf "$tmp"
