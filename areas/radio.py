"""CONNSYS Wi-Fi/Bluetooth, sensor hub, cellular's blocks."""
import re

import dts


def run(c):
    cs = c.compat("-consys")
    if cs:
        r = dts.reg(cs)[0]
        c.fact("wifi_bt", "consys", {"base": hex(r[0]), "compat": cs.str("compatible")}, c.src(cs), [hex(r[0])[2:].zfill(8)])
    chip = c.cfg("MTK_FM_CHIP") or c.cfg("MTK_COMBO_CHIP")
    chips = sorted({m for m in re.findall(r"MT66\d\d", " ".join(str(v) for k, v in c.sym.items() if "COMBO" in k or "_FM_CHIP" in k or "CONNSYS" in k))})
    if chip or chips:
        c.fact("wifi_bt", "chip", chips or [chip], "defconfig (CONFIG_MTK_FM_CHIP / combo chip)", [x.lower() for x in chips])
    for key, sub in (("wifi", "mediatek,wifi"), ("btif", "mediatek,btif")):
        n = c.compat(sub)
        if n:
            r = dts.reg(n)[0]
            c.fact("wifi_bt", key, {"base": hex(r[0]), "size": hex(r[1])}, c.src(n), [hex(r[0])[2:].zfill(8)])
    bt = [n for n in c.tree.root.walk() if n.parent is c.tree.root and n.name.startswith("bt")]
    for n in c.tree.root.walk():
        if n.has("memory-region") and n.parent is c.tree.root and (n.name.startswith("wifi") or n.name.startswith("consys")):
            ref = n.cells("memory-region")
            c.fact("wifi_bt", n.name.split("@")[0] + "_region", ref[0] if ref else None, c.src(n))
    blobs = _blobs(c, r"connsys|conninfra|wlan|wmt|mt66|bluetooth|combo")
    if blobs:
        c.fact("wifi_bt", "vendor_blobs", blobs, "proprietary-files.txt (names only; firmware comes off the user's own phone)")
    c.probe("wifi_bt", "adb shell su -c 'ls -l /vendor/firmware /vendor/etc/firmware 2>/dev/null | head -60; cat /proc/iomem | grep -i -e consys -e wifi'",
            "the firmware files and where the EMI pools were placed")
    scp = c.compat("mediatek,scp", exact=True)
    if scp:
        r = dts.reg(scp)[0]
        c.fact("sensor_hub", "scp", {"base": hex(r[0]), "sram": hex((scp.ints("scp_sramSize") or [0])[0])}, c.src(scp),
               [hex(r[0])[2:].zfill(8)])
    sensors = sorted({k[7:].replace("CUSTOM_KERNEL_", "") for k, v in c.sym.items() if k.startswith("CONFIG_CUSTOM_KERNEL_") and k.endswith("_SENSOR") and v == 1})
    if sensors:
        c.fact("sensor_hub", "sensor_kinds_on", sensors, "defconfig")
    if c.cfg("CUSTOM_KERNEL_SENSORHUB"):
        c.fact("sensor_hub", "sensorhub", True, "defconfig CONFIG_CUSTOM_KERNEL_SENSORHUB")
    ss = c.compat("mediatek,sspm", exact=True)
    if ss:
        r = dts.reg(ss)[0]
        c.fact("sensor_hub", "sspm", {"base": hex(r[0])}, c.src(ss), [hex(r[0])[2:].zfill(8)])
    cc = c.compat("ccif")
    md = [n for n in c.tree.root.walk() if n.str("compatible") and re.search(r"ccif|dpmaif|mddriver", n.str("compatible"))]
    if md:
        c.fact("cellular", "blocks", sorted({n.str("compatible") for n in md}), "dts (nodes only: the modem's bring-up is its own work)")
    c.probe("sensor_hub", "adb shell su -c 'ls /sys/class/sensor* /vendor/firmware | head -40; dmesg | grep -i -e scp -e sensorhub | head -40'",
            "the SCP image Android loads and the sensor list it exposes")


def _blobs(c, pat):
    import os
    p = os.path.join(c.android, "proprietary-files.txt")
    out = []
    if os.path.exists(p):
        for line in open(p, errors="replace"):
            s = line.strip().lstrip("-")
            if s and not s.startswith("#") and re.search(pat, s, re.I):
                out.append(os.path.basename(s.split("|")[0].split(";")[0]))
    return sorted(set(out))[:40]
