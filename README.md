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
    --title "realme 8i" --maintainer you --out out
```

Needs Python 3 and `dtc` (only to read the phone's own tree). `--fdt` is `/sys/firmware/fdt` and `--gpt` the first blocks of the
disk, both with serials and GUIDs masked; without them the memory map, the framebuffer and the partition room are gaps, and the
brief says which command pulls them.

| out | what |
| --- | --- |
| `<name>/device.conf`, `configs/`, `boot-args.txt` | the device repository's skeleton: every status `missing` with what was found |
| `adt-input.conf` | the numbers the device-tree builder needs: RAM, interrupt controller, timer, framebuffer, block bases |
| `report.md` | for each fact, which of our files name it; what nothing of ours names |
| `BRIEF.md` | facts, gaps, next steps and the read-only phone commands that settle the rest |
| `facts.json` | the same, for diffing |

The trees do not say everything. LK's reservations, framebuffer and panel come from the phone's own tree; where Android placed
its run-time pools only `/proc/iomem` says; registers as LK leaves them, SSPM and DVFS tables, calibration and rail values need
a probe. These are listed, not guessed.

## Proof

`proof/spaced.sh` regenerates the realme 8i from its trees and a masked copy of its own tree and GPT, and compares with the real
device repository, the ADT builder's constants and the notes of the bring-up (`proof/check.py` holds each expected value and where
it is stated). It prints what matches, what differs and why, and what the sources cannot give.

Licence: MIT.
