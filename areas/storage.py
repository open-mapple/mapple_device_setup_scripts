"""Storage: UFS or eMMC, the system's LUN, the GPT, free space for our partition; GPU."""
import re

import dts


def run(c):
    ufs = c.compat("ufshci")
    if ufs:
        r = dts.reg(ufs)[0]
        c.fact("storage", "type", "ufs", c.src(ufs))
        c.fact("storage", "controller", {"base": hex(r[0]), "size": hex(r[1])}, c.src(ufs), [hex(r[0])[2:].zfill(8)])
    else:
        mm = [n for n in c.tree.root.walk() if n.str("compatible") and "mmc" in n.str("compatible") and n.has("reg")]
        if mm:
            r = dts.reg(mm[0])[0]
            c.fact("storage", "type", "emmc", c.src(mm[0]))
            c.fact("storage", "controller", {"base": hex(r[0]), "size": hex(r[1])}, c.src(mm[0]), [hex(r[0])[2:].zfill(8)])
    # BoardConfig's comments name the device node of each partition: (sdc42) is LUN 2 (sda=0)
    luns = {m[0] for m in re.findall(r"\(sd([a-z])\d+\)", " ".join(c.board.values()) + _raw_board(c))}
    if len(luns) == 1:
        c.fact("storage", "system_lun", ord(next(iter(luns))) - ord("a"), "BoardConfig.mk partition comments (sd<letter>N)")
    else:
        c.gap("storage", "the LUN of the system partitions is not stated in BoardConfig.mk")
        c.probe("storage", "adb shell ls -l /dev/block/by-name | head", "sd<letter> of the partitions: LUN = letter - 'a'")
    fs = _fstab(c)
    if fs:
        c.fact("storage", "android_partitions", fs, "rootdir/etc/fstab*")
    if "BOARD_SUPER_PARTITION_SIZE" in c.board:
        c.fact("storage", "super_bytes", int(c.board["BOARD_SUPER_PARTITION_SIZE"]), "BoardConfig.mk")
    if c.gpt:
        bs = c.gpt["block"]
        parts = sorted(c.gpt["parts"], key=lambda p: p[1])
        c.fact("storage", "block_size", bs, "GPT")
        c.fact("storage", "partitions", [{"name": n, "first": a, "last": z, "mib": round((z - a + 1) * bs / 2**20, 1)}
                                         for n, a, z in parts], "GPT")
        ud = [p for p in parts if p[0] == "userdata"]
        if ud:
            c.fact("storage", "userdata", {"first": ud[0][1], "last": ud[0][2], "gib": round((ud[0][2] - ud[0][1] + 1) * bs / 2**30, 2)},
                   "GPT: the partition our own is carved from")
        c.fact("storage", "ab", any(n.endswith("_a") for n, _, _ in parts), "GPT partition names")
    else:
        c.gap("storage", "no --gpt: sizes, LBAs and the room to carve our partition are unknown")
    c.probe("storage", "adb shell su -c 'dd if=/dev/block/sdc bs=4096 count=34 2>/dev/null' > gpt-head.bin",
            "the GPT (mask the disk and partition GUIDs before sharing)")
    # GPU
    g = c.compat("arm,mali") or c.compat("mediatek,mali")
    if g:
        r = dts.reg(g)[0]
        comp = [x for x in g.strs("compatible") if "arm," in x]
        c.fact("gpu", "mali", {"base": hex(r[0]), "compat": comp, "irqs": [i for i, _ in dts.irq(g)]}, c.src(g),
               [hex(r[0])[2:].zfill(8)])
    mf = c.compat("mfgsys") or c.compat("mfgcfg")
    if mf:
        r = dts.reg(mf)[0]
        c.fact("gpu", "mfgcfg", {"base": hex(r[0])}, c.src(mf), [hex(r[0])[2:].zfill(8)])
    c.probe("gpu", "adb shell su -c 'cat /sys/kernel/debug/ged/hal/gpu_utilization /proc/gpufreq/gpufreq_opp_dump 2>/dev/null'",
            "OPP table and rails Android runs the GPU with (before any clock or voltage is set from our side)")


def _raw_board(c):
    import glob, os
    out = ""
    for f in glob.glob(os.path.join(c.android, "*.mk")):
        out += open(f, errors="replace").read()
    return out


def _fstab(c):
    import glob, os
    out = []
    for f in sorted(glob.glob(os.path.join(c.android, "rootdir/etc/fstab*"))):
        for line in open(f, errors="replace"):
            m = re.match(r"/dev/block/by-name/(\w+)\s+(\S+)\s+(\w+)", line)
            if m:
                out.append({"name": m[1], "mount": m[2], "fs": m[3]})
    return out
