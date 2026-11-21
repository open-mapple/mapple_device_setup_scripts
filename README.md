# mapple_device_setup_scripts

Reads a MediaTek phone's open Android trees and does the deterministic part of a port, with no guessing: it writes a device
repository skeleton, a match report against Open Mapple's drivers and a porting brief. Facts only: every line says where it was read
(`file:line`), and nothing of the trees' files, no firmware and no vendor file is copied. No network, no AI; the same inputs give
the same bytes.

The method follows HakiOS's `docs/mtk-porting.md` ("Read these from your phone first"), which this automates for the parts the
sources can answer.

It reads source trees, not a firmware dump: nothing is unpacked from the phone's images, and no firmware or vendor binary is needed.

| option | what to pass |
| --- | --- |
| `--android-device` | the phone's Android device tree source: the repository `android_device_<brand>_<codename>` (it has `BoardConfig.mk` and `device.mk`), with the trees it inherits, `android_device_<brand>_<soc>-common`, as folders beside it |
| `--android-kernel` | the vendor's kernel source for the phone (it has `arch/arm64/boot/dts` and `arch/arm64/configs`) |
| `--ours` (optional, repeatable) | Open Mapple's driver sources, for the match report: folders of a repo sync of our manifest (`repo init -u https://github.com/open-mapple/manifest -b main && repo sync`), such as `kernel/mediatek/mt6781` and `mapple/loader` |
| `--fdt`, `--gpt` (optional) | the phone's own device tree and partition table, pulled with adb, identifiers masked |

```sh
python3 bringup.py spaced \
    --android-device android_device_realme_spaced \
    --android-kernel android_kernel_realme_mt6781 \
    --fdt live.dtb --gpt gpt-sdc.bin \
    --ours kernel/mediatek/mt6781 --ours mapple/loader \
    --project 21690 --title "realme 8i" --maintainer you --out out
```

Python 3 and `dtc` are needed (see Install). Without `--fdt` and `--gpt` the memory map, the framebuffer and the partition room are gaps,
and the brief says which command pulls them.

MediaTek only. If the trees are Qualcomm's or any other vendor's (a `TARGET_BOARD_PLATFORM` such as `sm6150`, `CONFIG_ARCH_QCOM`,
a `qcom,` root compatible in `--fdt`), the run stops and writes nothing; SM7150 phones belong to the Qualcomm line
(`xnu_kernel_qcom_common`, `xnu_device_xiaomi_sweet`, `xnu_device_google_sunfish`).

The script stops rather than guesses. It prints the SoC and where it read it at the start of a run, and writes both in `BRIEF.md`.
It looks, in this order, at `TARGET_BOARD_PLATFORM` (the device tree's makefiles and the `include` / `inherit-product` lines into
the common trees beside it, such as `android_device_<vendor>_<soc>-common`), the kernel config (`CONFIG_MACH_MT*`, else
`CONFIG_MTK_PLATFORM`), the root compatible of `--fdt`, and the SoC dts if the kernel tree has only one. Sources that disagree are
listed and the run stops; so does a run where none answers. `--soc mt6768` settles either, and the run warns if the trees
say another SoC and stops if the kernel has no dts for it.

Every input is checked before anything is read, and each stop names the option: a device or kernel folder that is not source
(a firmware dump), a missing `--fdt`, `--gpt` or `--ours`, a file that is not a device tree or a GPT, `dtc` not installed, a kernel
without the config the device names. At the end of a run, the values left empty for you to fill are listed.

The board's dts overlay is the file `--overlay` names, or the ones whose names contain `--project`; with neither, the one overlay the
kernel config builds (`CONFIG_BUILD_ARM64_DTB_OVERLAY_IMAGE_NAMES`). If it builds several, they are listed and the run stops:
pick with `--overlay FILE` (repeatable) or `--project NAME`.

| out | what |
| --- | --- |
| `<name>/device.conf`, `configs/`, `boot-args.txt` | the device repository's skeleton: every status `missing` with what was found; `soc_vendor`, `machine`, `boot`, `gpu` and the `bootimg_*` header as the trees give them |
| `<name>/adt.py` | the phone's values for the ADT builder (RAM, framebuffer, name, `ABOUT`, an empty `devices()`) |
| `report.md` | for each fact, which of our files name it; what nothing of ours names |
| `BRIEF.md` | facts, gaps, next steps and the read-only phone commands that settle the rest |
| `facts.json` | the same, for diffing |

A value the trees do not give (the ADT's `ECID` and `DISPLAY_GAMUT`, `root_size`, `payload_max`, the boot image's Android version and patch level, the RAM and
framebuffer without `--fdt`) is left empty, with a one-line comment above it saying what goes there. The build stops on an empty
required value and names it.

The trees do not say everything. LK's reservations, framebuffer and panel come from the phone's own tree; where Android placed
its run-time pools only `/proc/iomem` says; registers as LK leaves them, SSPM and DVFS tables, calibration and rail values need
a probe. These are listed, not guessed.

## Install

Python 3, `dtc` (it only reads the phone's own tree), `git`, and `adb` for the phone's files:

```sh
brew install dtc android-platform-tools                   # macOS
sudo apt install python3 device-tree-compiler adb git     # Debian, Ubuntu
sudo dnf install python3 dtc android-tools git            # Fedora
sudo pacman -S python dtc android-tools git               # Arch
```

On Linux, if `adb devices` lists the phone as "no permissions", install the udev rules (Debian, Ubuntu:
`sudo apt install android-sdk-platform-tools-common`), replug the phone and accept the debugging prompt on its screen. The phone
needs root (`adb shell su -c id` must work) only for the two files in the next section. Nothing else here runs on the phone.

## Getting the inputs

The source trees: clone them side by side in one folder, for example LineageOS's
`android_device_<brand>_<codename>` and `android_device_<brand>_<soc>-common`, and the vendor's kernel source (LineageOS's
`android_kernel_<brand>_<soc>`, or the OEM's open-source release). Only the dts and the configs are read, so a kernel can be cloned thin:

```sh
git clone --depth 1 --filter=blob:none --sparse URL kernel
git -C kernel sparse-checkout set arch/arm64/boot/dts arch/arm64/configs include
```

The phone's own files, over adb with the phone rooted and booted into Android. They hold your phone's serial and disk
identifiers: mask them before you share anything.

```sh
# --fdt: the device tree LK hands to Android's kernel
adb exec-out su -c 'cat /sys/firmware/fdt' > live.dtb
adb shell getprop ro.serialno        # then replace every copy of the serial with X's of the same length:
python3 -c 'import sys; b = open("live.dtb", "rb").read(); s = sys.argv[1].encode(); open("live.dtb", "wb").write(b.replace(s, b"X" * len(s)))' SERIAL
dtc -I dtb -O dts -q live.dtb | grep -i -e serial -e imei        # should show nothing of yours

# --gpt, eMMC: the first 32 KiB of the disk
adb exec-out su -c 'dd if=/dev/block/mmcblk0 bs=4096 count=8 2>/dev/null' > gpt.bin

# --gpt, UFS: the disk (LUN) that holds the Android partitions, then its first 32 KiB
adb shell su -c 'readlink -f /dev/block/by-name/super'           # /dev/block/sdc47 means the disk is sdc
adb exec-out su -c 'dd if=/dev/block/sdc bs=4096 count=8 2>/dev/null' > gpt.bin
```

Then zero the disk GUID and each partition's own GUID in `gpt.bin` (the names and ranges stay):

```sh
python3 - <<'EOF'
b = bytearray(open("gpt.bin", "rb").read())
bs = 4096 if b[4096:4104] == b"EFI PART" else 512
b[bs + 56:bs + 72] = bytes(16)
lba, n, size = (int.from_bytes(b[bs + o:bs + o + w], "little") for o, w in ((72, 8), (80, 4), (84, 4)))
for i in range(n):
    o = lba * bs + i * size + 16
    b[o:o + 16] = bytes(16)
open("gpt.bin", "wb").write(b)
EOF
```

## Proof

`proof/spaced.sh` regenerates the realme 8i from its trees and a masked copy of its own tree and GPT, and compares with the real
device repository, the ADT builder's constants and the notes of the bring-up (`proof/check.py` holds each expected value and where
it is stated). It prints what matches, what differs and why, and what the sources cannot give.

`proof/merlinx.sh` reads the Redmi Note 9 (MT6768) from LineageOS's public trees (`android_device_xiaomi_merlinx`, `..._mt6768-common`
beside it, `android_kernel_xiaomi_mt6768`) and checks the SoC is found in the common tree, nothing of mt6781 appears, and that missing
or disagreeing sources stop the run. `proof/qcom.sh` feeds it LineageOS's Redmi Note 10 Pro (sweet, sm6150) trees and checks that it
stops and writes nothing.

Licence: MIT.
