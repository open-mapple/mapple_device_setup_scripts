"""SoC and boot chain: cores, interrupt controller, timer, UART, watchdog, the Android boot image's header."""
import dts

A_CORES = {"arm,cortex-a55": "a55", "arm,cortex-a75": "a75", "arm,cortex-a76": "a76", "arm,cortex-a53": "a53",
           "arm,cortex-a73": "a73", "arm,cortex-a78": "a78", "arm,cortex-a77": "a77"}


def run(c):
    t = c.tree
    c.fact("soc", "soc", c.soc_name(), c.soc_src)
    model = t.root.str("model")
    if model:
        c.fact("soc", "model", model, "dts: /model")
    cores = []
    for n in t.root.walk():
        if n.name.startswith("cpu@") and n.str("device_type") == "cpu":
            cores.append((n.cells("reg") and dts.num(n.cells("reg")[0]), A_CORES.get(n.str("compatible"), n.str("compatible")),
                          (n.ints("clock-frequency") or [0])[0]))
    cores.sort()
    c.fact("soc", "cores", [{"mpidr": hex(m), "core": k, "mhz": f // 1000000} for m, k, f in cores], "dts: /cpus", ["cpus"])
    variant = c.board.get("TARGET_CPU_VARIANT")
    if variant and cores and variant.replace("cortex-", "") != cores[-1][1]:
        c.fact("soc", "cpu_variant_android", variant,
               "BoardConfig TARGET_CPU_VARIANT; the dts names the big cores %s: trust neither, read MIDR on the phone" % cores[-1][1])
        c.probe("soc", "adb shell su -c 'for i in 0 1 2 3 4 5 6 7; do cat /sys/devices/system/cpu/cpu$i/regs/identification/midr_el1; done'",
                "the cores' real part numbers (dts and BoardConfig disagree)")
    gic = c.compat("arm,gic-v3")
    if gic:
        r = dts.reg(gic)
        c.fact("soc", "gicd", {"base": hex(r[0][0]), "size": hex(r[0][1])}, c.src(gic), [hex(r[0][0])[2:].zfill(8)])
        c.fact("soc", "gicr", {"base": hex(r[1][0]), "size": hex(r[1][1])}, c.src(gic))
    tm = c.compat("arm,armv8-timer")
    if tm:
        cells = tm.cells("interrupts")
        virt = dts.num(cells[7]) if len(cells) >= 12 else None   # sec-phys, phys, virt, hyp
        c.fact("soc", "timebase_hz", (tm.ints("clock-frequency") or [None])[0], c.src(tm))
        if virt is not None:
            c.fact("soc", "vtimer_intid", virt + 16, c.src(tm) + " (the third PPI, 16 added)")
    u = next((n for n in t.root.walk() if n.name.startswith("serial") and any("uart" in x for x in n.strs("compatible"))), None)
    if u:
        r = dts.reg(u)[0]
        c.fact("soc", "uart", {"base": hex(r[0]), "size": hex(r[1])}, c.src(u), [hex(r[0])[2:].zfill(8)])
    w = c.compat("toprgu")
    if w:
        r = dts.reg(w)[0]
        c.fact("soc", "toprgu", {"base": hex(r[0])}, c.src(w), [hex(r[0])[2:].zfill(8)])
    psci = c.compat("arm,psci")
    if psci:
        c.fact("soc", "psci_method", psci.str("method", "smc"), c.src(psci))
    b = c.board
    keys = ("BOARD_KERNEL_BASE", "BOARD_KERNEL_OFFSET", "BOARD_RAMDISK_OFFSET", "BOARD_DTB_OFFSET", "BOARD_KERNEL_PAGESIZE",
            "BOARD_BOOTIMG_HEADER_VERSION", "BOARD_BOOTIMAGE_PARTITION_SIZE")
    c.fact("soc", "boot_header", {k.replace("BOARD_", "").lower(): b.get(k) for k in keys if k in b}, "BoardConfig.mk")
    ab = "AB_OTA_UPDATER" in b and b["AB_OTA_UPDATER"] == "true"
    c.fact("soc", "ab_slots", ab, "BoardConfig/device.mk AB_OTA_UPDATER")
    plat = b.get("TARGET_BOOTLOADER_BOARD_NAME")
    c.fact("soc", "bootloader", "LK (MediaTek)" if c.soc_name().startswith("mt") else "unknown",
           "SoC vendor" + (", board name " + plat if plat else ""))
    if c.gpt:
        names = {p[0] for p in c.gpt["parts"]}
        c.fact("soc", "boot_partitions", sorted(n for n in names if n in ("lk", "lk2", "preloader", "boot", "boot_a", "boot_b",
                                                                          "recovery", "dtbo", "vbmeta", "tee1", "tee2", "scp1", "sspm_1")),
               "GPT")
    else:
        c.gap("soc", "no --gpt: partition names and the boot chain's partitions come from fstab only")
    c.probe("soc", "adb shell cat /proc/cmdline | tr ' ' '\\n' | grep -v -e serial -e imei",
            "what LK passes (lcm=, ramoops, bootopt); keep out serials before sharing")
