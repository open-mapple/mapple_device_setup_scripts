"""Touch, keys."""
import re

import dts


def run(c):
    for n in c.tree.root.walk():
        if n.has("chip-name") and n.has("irq-gpio"):
            bus = n.parent
            r = dts.reg(bus)
            cs = n.ints("reg")
            irq = n.cells("irq-gpio")
            rst = n.cells("reset-gpio")
            chip = n.str("chip-name")
            c.fact("touch", "chip", chip, c.src(n), [chip.split("_")[-1]])
            c.fact("touch", "bus", {"name": bus.name, "base": hex(r[0][0]) if r else None, "cs": cs[0] if cs else None,
                                    "max_hz": (n.ints("spi-max-frequency") or [None])[0]}, c.src(bus),
                   [hex(r[0][0])[2:].zfill(8)] if r else [])
            c.fact("touch", "pins", {"irq_gpio": dts.num(irq[1]) if len(irq) > 1 else None,
                                     "reset_gpio": dts.num(rst[1]) if len(rst) > 1 else None}, c.src(n))
            if n.has("touchpanel,max-num-support"):
                c.fact("touch", "fingers", n.ints("touchpanel,max-num-support")[0], c.src(n))
            if n.has("touchpanel,panel-coords"):
                c.fact("touch", "coords", n.ints("touchpanel,panel-coords"), c.src(n))
            if n.has("noflash_support"):
                c.fact("touch", "firmware", "sent by the host at power-up (noflash): a file is needed, name from the vendor tree",
                       c.src(n))
            break
    else:
        # other vendors: a child of an i2c/spi node with a touch-ish compatible
        for n in c.tree.root.walk():
            comp = " ".join(n.strs("compatible"))
            if any(k in comp for k in ("goodix,gt", "focaltech", "novatek,nt", "synaptics", "himax", "ilitek", "td4")) and n.parent:
                c.fact("touch", "chip", comp, c.src(n))
                break
        else:
            c.gap("touch", "no touch controller node with a chip name in the merged tree")
    cfgs = sorted(k[7:] for k, v in c.sym.items() if k.startswith("CONFIG_TOUCHPANEL_") and v == 1 and k.count("_") > 2)
    if cfgs:
        c.fact("touch", "kernel_drivers_on", cfgs, "defconfig")
    kp = c.compat("mediatek,kp", exact=True)
    if kp:
        r = dts.reg(kp)[0]
        c.fact("keys", "keypad", {"base": hex(r[0])}, c.src(kp), [hex(r[0])[2:].zfill(8)])
    pk = sorted(k[7:] for k, v in c.sym.items() if v == 1 and re.search(r"PMIC.*KEY|PWRKEY|KPD", k))
    if pk:
        c.fact("keys", "pmic_keys_drivers_on", pk, "defconfig (power and volume keys that sit on the PMIC are read through it)")
    c.probe("touch", "adb shell su -c 'cat /proc/touchpanel/* 2>/dev/null | head -50; ls /sys/bus/spi/devices'",
            "which controller answers and its firmware version")
    c.probe("keys", "adb shell getevent -lp | grep -B1 -A8 -i key", "the keys' scancodes")
