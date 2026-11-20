#!/usr/bin/env python3
"""mapple-bringup: a MediaTek phone's open Android trees -> a device repo skeleton, a match report and a porting brief.

Facts only: nothing of the trees' files is copied, every fact says where it was read. See README.md.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render  # noqa: E402
from areas import AREAS  # noqa: E402
from ctx import Ctx  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("name", help="the device's codename (spaced)")
    p.add_argument("--android-device", required=True, help="the phone's Android device tree SOURCE, the repository android_device_<brand>_<codename> (it has BoardConfig.mk and "
                   "device.mk), with the inherited android_device_<brand>_<soc>-common trees beside it. Source trees, not a firmware dump")
    p.add_argument("--android-kernel", required=True, help="the vendor's Android kernel SOURCE for the phone (it has arch/arm64/boot/dts and arch/arm64/configs). "
                   "A source tree, not a firmware dump")
    p.add_argument("--soc", help="the MediaTek SoC (mt6768); without it the trees must name it, and the run stops if they do not")
    p.add_argument("--project", help="the vendor's project name or number in the dts overlay's file name")
    p.add_argument("--overlay", action="append", default=[], help="the board's dts overlay file in the kernel's mediatek dts directory (repeatable)")
    p.add_argument("--fdt", help="the phone's own device tree (/sys/firmware/fdt), identifiers masked")
    p.add_argument("--gpt", help="the phone's GPT (first 34 blocks of the disk), identifiers masked")
    p.add_argument("--ours", action="append", default=[], help="Open Mapple's driver sources, for the match report (optional, repeatable): folders of a repo sync of our manifest, "
                   "such as kernel/mediatek/mt6781 and mapple/loader")
    p.add_argument("--title")
    p.add_argument("--maintainer", default="unmaintained")
    p.add_argument("--out", default="out")
    a = p.parse_args(argv)
    c = Ctx(a.name, a.android_device, a.android_kernel, a.project, a.fdt, a.gpt, a.ours, None, a.title, a.maintainer, soc=a.soc, overlays=a.overlay)
    for area in AREAS:
        area.run(c)
    render.write(c, a.out)
    n = sum(len(v) for v in c.facts.values())
    print("%s: %d facts, %d gaps, %d probes -> %s" % (a.name, n, len(c.gaps), len(c.probes), a.out))


if __name__ == "__main__":
    main()
