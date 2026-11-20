# mapple_device_setup_scripts

Reads a MediaTek phone's open Android trees and does the deterministic part of a port, with no guessing: it writes a device
repository skeleton, a match report against our drivers and a porting brief. Facts only: every line says where it was read
(`file:line`), and nothing of the trees' files, no firmware and no vendor file is copied. No network, no AI; the same inputs give
the same bytes.

The method follows HakiOS's `docs/mtk-porting.md` ("Read these from your phone first"), which this automates for the parts the
sources can answer.

```sh
python3 bringup.py spaced \
    --android-device android_device_realme_spaced \
    --android-kernel android_kernel_realme_mt6781 \
    --fdt live.dtb --gpt gpt-sdc.bin \
    --ours kernel/mediatek/mt6781 --ours mapple/loader \
    --project 21690 --title "realme 8i" --maintainer you --out out
```

Needs Python 3 and `dtc` (only to read the phone's own tree). `--fdt` is `/sys/firmware/fdt` and `--gpt` the first blocks of the
disk, both with serials and GUIDs masked; without them the memory map, the framebuffer and the partition room are gaps, and the
brief says which command pulls them.

MediaTek only. If the trees are Qualcomm's or any other vendor's (a `TARGET_BOARD_PLATFORM` such as `sm6150`, `CONFIG_ARCH_QCOM`,
a `qcom,` root compatible in `--fdt`), the run stops and writes nothing; SM7150 phones belong to the Qualcomm line
(`xnu_kernel_qcom_common`, `xnu_device_xiaomi_sweet`, `xnu_device_google_sunfish`).

The script stops rather than guesses. It prints the SoC and where it read it at the start of a run, and writes both in `BRIEF.md`.
It looks, in this order, at `TARGET_BOARD_PLATFORM` (the device tree's makefiles and the `include` / `inherit-product` lines into
the common trees beside it, such as `android_device_<vendor>_<soc>-common`), the kernel config (`CONFIG_MACH_MT*`, else
`CONFIG_MTK_PLATFORM`), the root compatible of `--fdt`, and the SoC dts if the kernel tree has only one. Sources that disagree are
listed and the run stops; so does a run where none answers. `--soc mt6768` settles either.

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

## Proof

`proof/spaced.sh` regenerates the realme 8i from its trees and a masked copy of its own tree and GPT, and compares with the real
device repository, the ADT builder's constants and the notes of the bring-up (`proof/check.py` holds each expected value and where
it is stated). It prints what matches, what differs and why, and what the sources cannot give.

`proof/merlinx.sh` reads the Redmi Note 9 (MT6768) from LineageOS's public trees (`android_device_xiaomi_merlinx`, `..._mt6768-common`
beside it, `android_kernel_xiaomi_mt6768`) and checks the SoC is found in the common tree, nothing of mt6781 appears, and that missing
or disagreeing sources stop the run. `proof/qcom.sh` feeds it LineageOS's Redmi Note 10 Pro (sweet, sm6150) trees and checks that it
stops and writes nothing.

Licence: MIT.
