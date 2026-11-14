#!/usr/bin/env python3
"""Compare a regenerated spaced (facts.json, device.conf, adt-input.conf) with what the real repos and FACTS say.

Expected values are written here by hand from FACTS.md, mkadt.py's SPACED_* constants and the real device.conf, with the place each
is stated; nothing is read back from the script's own output. Exit 1 on an unexplained difference.
Usage: check.py OUT_DIR
"""
import json
import os
import re
import sys

out = sys.argv[1]
J = json.load(open(os.path.join(out, "facts.json")))
F = J["facts"]
conf = open(os.path.join(out, "spaced", "device.conf")).read()
adt = open(os.path.join(out, "adt-input.conf")).read()
MiB = 2 ** 20


def v(a, k):
    return F.get(a, {}).get(k, {}).get("value")


def adt_val(k):
    m = re.search(r"^%s\t([^\t#]+)" % k, adt, re.M)
    return m[1].strip() if m else None


def conf_val(k):
    m = re.search(r"^\t%s\t(.*)$" % k, conf, re.M)
    return m[1] if m else None


def hx(x):
    return int(x, 16)


def free_incl():
    return [(hx(f["base"]), hx(f["end"]) - 1) for f in v("memory", "free") or []]


FREE = [(0x40000000, 0x4cdfffff), (0x4d100000, 0x55ffffff), (0x56720000, 0x5fefffff), (0x5ff80000, 0x7577ffff),
        (0x75790000, 0x771affff), (0x7e500000, 0x7e5fffff), (0x7ea41000, 0x7eabffff), (0x80000000, 0x8bffffff),
        (0x8d6a0000, 0x8dffffff), (0x8e700000, 0x9fafffff), (0x9ff00000, 0xadffffff), (0xbe000000, 0xbff2ffff),
        (0xc0000000, 0x13fffefff)]


def part(name):
    for p in v("storage", "partitions") or []:
        if p["name"] == name:
            return p


def cmdline_has(k):
    return k in (conf_val("cmdline") or "").split()


FB_STRIDE = 1080 * 4
# (what, where it is stated, got, expected, mode)  mode: eq, prefix; or ("known", reason) when the trees and the phone differ
C = [
    ("DRAM base", "FACTS RAM", v("memory", "dram") and v("memory", "dram")["base"], "0x40000000", "eq"),
    ("DRAM end", "FACTS RAM (0x13fffffff)", v("memory", "dram") and hx(v("memory", "dram")["end"]), 0x140000000, "eq"),
    ("reserved MB", "FACTS RAM (442 MB)", v("memory", "reserved_mib"), 442, "eq"),
    ("free ranges", "FACTS RAM table (13 rows)", free_incl(), FREE, "eq"),
    ("largest free range", "FACTS RAM (2048 MB at 0xc0000000)", adt_val("PHYS_BASE"), "0xc0000000", "eq"),
    ("XNU RAM size", "mkadt SPACED_MEM_SIZE", adt_val("MEM_SIZE"), hex(0x13e000000 - 0xc0000000), "eq"),
    ("ramoops", "FACTS pstore", v("memory", "ramoops"), {"base": "0x4d010000", "size": "0xe0000"}, "eq"),
    ("LK framebuffer", "FACTS Framebuffer, mkadt SPACED_FB", adt_val("FB"), "0x771b0000", "eq"),
    ("LK vram", "FACTS Framebuffer (0x1e50000)", v("memory", "lk_fb") and v("memory", "lk_fb")["vram"], "0x1e50000", "eq"),
    ("panel name", "FACTS Framebuffer (ili7807s_fhdp_dsi_vdo_boe_boe)", v("display", "lcm"), "ili7807s_fhdp_dsi_vdo_boe_boe", "prefix"),
    ("panel size", "FACTS Framebuffer (1080x2412)", v("display", "size"), [1080, 2412], "eq"),
    ("FB stride", "mkadt SPACED_FB_STRIDE", adt_val("FB_STRIDE"), str(FB_STRIDE), "eq"),
    ("FB size", "mkadt SPACED_FB_SIZE", adt_val("FB_SIZE"), hex((FB_STRIDE * 2412 + 0x3fff) & ~0x3fff), "eq"),
    ("storage type", "FACTS Storage", v("storage", "type"), "ufs", "eq"),
    ("UFS LUN", "FACTS Storage (sdc), device.conf mp_ufslun=2", v("storage", "system_lun"), 2, "eq"),
    ("block size", "FACTS Storage", v("storage", "block_size"), 4096, "eq"),
    ("no A/B", "FACTS Storage", v("storage", "ab"), False, "eq"),
    ("boot size", "FACTS Storage (32 MB)", part("boot") and part("boot")["mib"], 32.0, "eq"),
    ("dtbo size", "FACTS Storage (8 MB)", part("dtbo") and part("dtbo")["mib"], 8.0, "eq"),
    ("lk size", "FACTS Storage (5 MB)", part("lk") and part("lk")["mib"], 5.0, "eq"),
    ("userdata first LBA", "FACTS Storage (2881536)", part("userdata") and part("userdata")["first"], 2881536, "eq"),
    ("userdata GiB", "FACTS Storage (26.58)", v("storage", "userdata") and v("storage", "userdata")["gib"], 26.58, "eq"),
    ("xnusys range", "FACTS smoke staging (9848576..15615991)", part("xnusys") and (part("xnusys")["first"], part("xnusys")["last"]),
     (9848576, 15615991), "eq"),
    ("super bytes", "FACTS Storage (9.5 GB)", v("storage", "super_bytes"), 10200547328, "eq"),
    ("UFS base", "mkadt MAPPLE_UFS", adt_val("UFS"), "0x11270000 0x4000", "eq"),
    ("UFS DT size", "FACTS UFS (0x2300)", v("storage", "controller") and v("storage", "controller")["size"], "0x2300", "eq"),
    ("cores", "FACTS Cores (6x A55 + 2 big; the DT says A75)", [x["core"] for x in v("soc", "cores") or []],
     ["a55"] * 6 + ["a75"] * 2, "eq"),
    ("big cores' real part", "FACTS Cores (A76)", v("soc", "cpu_variant_android"), "cortex-a76", "eq"),
    ("GICD", "mkadt MAPPLE_GICD", adt_val("GICD"), "0xc000000 0x40000", "eq"),
    ("GICR", "mkadt MAPPLE_GICR", adt_val("GICR"), "0xc040000 0x200000", "eq"),
    ("timebase", "mkadt MAPPLE_TIMEBASE", adt_val("TIMEBASE"), "13000000", "eq"),
    ("virtual timer INTID", "mkadt MAPPLE_VTIMER_INTID", adt_val("VTIMER_INTID"), "27", "eq"),
    ("TOPRGU", "FACTS (mtkloader SOC_PROBE)", v("soc", "toprgu") and v("soc", "toprgu")["base"], "0x10007000", "eq"),
    ("OVL0", "FACTS Framebuffer (0x14005000)", adt_val("OVL0"), "0x14005000", "eq"),
    ("touch chip", "FACTS Touch (ILI7807S)", v("touch", "chip"), "ILI7807S", "contains"),
    ("touch bus", "FACTS Touch (spi4, 0x11014000)", v("touch", "bus") and v("touch", "bus")["base"], "0x11014000", "eq"),
    ("touch irq", "FACTS Touch (EINT 12)", v("touch", "pins") and v("touch", "pins")["irq_gpio"], 12, "eq"),
    ("touch reset", "FACTS Touch (GPIO121)", v("touch", "pins") and v("touch", "pins")["reset_gpio"], 121, "eq"),
    ("keypad", "FACTS Touch (mtk-kpd 10010000)", adt_val("KEYPAD"), "0x10010000", "eq"),
    ("PMIC wrapper", "device.conf buttons / mtkpwrap.h", adt_val("PWRAP"), "0x1000d000", "eq"),
    ("PMIC register layout", "FACTS smoke 5 (MT6358 layout)", v("pmic", "chip") and v("pmic", "chip")["defconfig"], ["MT6358"], "eq"),
    ("PMIC part named", "FACTS smoke 2 (MT6366)", "mt6366-sound" in (v("pmic", "parts_named") or []), True, "eq"),
    ("GPU", "device.conf (Mali-G57, Valhall)", v("gpu", "mali") and v("gpu", "mali")["compat"], ["arm,mali-valhall"], "eq"),
    ("mfgcfg", "README (0x13fbf000)", adt_val("MFGCFG"), "0x13fbf000", "eq"),
    ("Wi-Fi/BT chip", "device.conf (MT6631)", v("wifi_bt", "chip"), ["MT6631"], "eq"),
    ("BTIF", "device.conf (BTIF)", v("wifi_bt", "btif") and v("wifi_bt", "btif")["base"], "0x1100c000", "eq"),
    ("amplifiers", "FACTS audio (AW87319 on 3-0058, sia81xx on 3-0028)",
     sorted((a["compat"].split(",")[-1], a["bus"].split("@")[0], a["addr"]) for a in v("audio", "amp_nodes") or []),
     [("aw87319_pa", "i2c3", "0x58"), ("sia81xx-i2c", "i2c3", "0x28")], "eq"),
    ("audio codec", "device.conf (MT6366)", "mt6366_snd" in (v("audio", "codec_node") or []), True, "eq"),
    ("sensor hub", "SENSORS.md (scp 0x10500000)", v("sensor_hub", "scp") and v("sensor_hub", "scp")["base"], "0x10500000", "eq"),
    ("torch part", "device.conf (MT6371 FLED1 on I2C5)", v("torch", "flash") and v("torch", "flash")["defconfig"],
     ("known", "the tree names an MT6370 flash; the phone's torch is on an MT6371 that no tree names: read its id on the phone"),
     "known"),
    ("device.conf title", "real device.conf", conf_val("title"), "realme 8i (spaced)", "eq"),
    ("device.conf vendor", "real device.conf", conf_val("vendor"), "realme", "eq"),
    ("device.conf soc", "real device.conf", conf_val("soc"), "mt6781", "eq"),
    ("device.conf defconfig", "real device.conf", conf_val("defconfig"), "spaced_defconfig", "eq"),
    ("device.conf firmware", "real device.conf", conf_val("firmware"), "pull-firmware.sh", "eq"),
    ("device.conf adt flags", "real device.conf (--spaced --ufs --audio --torch)", conf_val("adt"), "--spaced --ufs --audio --torch", "eq"),
    ("cmdline cpus", "real device.conf cmdline", cmdline_has("cpus=8"), True, "eq"),
    ("cmdline UFS LUN", "real device.conf cmdline", cmdline_has("mp_ufslun=2"), True, "eq"),
    ("cmdline UFS root", "real device.conf cmdline", cmdline_has("mp_ufsroot=xnusys"), True, "eq"),
]
STATUS_AREAS = ["display", "touch", "buttons", "cpu", "gpu", "storage", "sensors", "wifi", "bluetooth", "audio", "battery", "haptic",
                "camera", "torch", "cellular", "thermal"]
NOT_DERIVABLE = [
    ("LK's OVL layer state (layer 1, alpha on, pitch 0x10e0)", "FACTS Framebuffer: a register state, read by mtkloader"),
    ("framebuffer pitch (padding)", "FACTS: 4320 = 1080 x 4 here; the script assumes it and says so"),
    ("UFS controller state as LK leaves it (HCE, CAP, lists)", "FACTS UFS: registers"),
    ("SSPM/DVFS tables, LVTS calibration, PMIC rails at LK's state", "FACTS DVFS/LVTS/smoke 5: probes"),
    ("EMI MPU regions and violations", "FACTS smoke 11: Android's dmesg"),
    ("Wi-Fi/consys EMI pool (mp_wifi_emi=0xbf000000) and the shim's alloc-range hole 0xbe000000-0xbff30000",
     "Android placed them at run time: /proc/iomem (probe listed)"),
    ("every cmdline knob but cpus/LUN/root (mp_gpu, mp_therm, ...)", "run-proven choices in device.conf, not facts of the trees"),
    ("device.conf status states (works/partial)", "only a run says that; the script writes missing"),
    ("maintainer", "an input (--maintainer)"),
]


def main():
    bad = 0
    for what, src, got, exp, mode in C:
        if mode == "known":
            print("differs (explained)  %-24s %s" % (what, exp[1]))
            continue
        ok = got == exp or (mode == "prefix" and isinstance(got, str) and got.startswith(exp)) or \
            (mode == "contains" and isinstance(got, str) and exp in got)
        if ok:
            print("match                %-24s %s" % (what, src))
        else:
            bad += 1
            print("DIFFERS              %-24s %s\n    got      %r\n    expected %r" % (what, src, got, exp))
    have = re.findall(r"^\tstatus (\w+) missing", conf, re.M)
    if have != STATUS_AREAS:
        bad += 1
        print("DIFFERS              status lines %s != %s" % (have, STATUS_AREAS))
    else:
        print("match                status areas, all missing (the real device.conf lists the same %d)" % len(have))
    print()
    for what, why in NOT_DERIVABLE:
        print("not derivable        %s: %s" % (what, why))
    print("\n%d checks, %d differ unexplained" % (len(C) + 1, bad))
    return 1 if bad else 0


sys.exit(main())
