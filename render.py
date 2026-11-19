"""Facts -> the device repo skeleton, adt-input.conf, report.md, BRIEF.md, facts.json."""
import json
import os
import re
import subprocess

STATUS = [("display", ["display", "memory"]), ("touch", ["touch"]), ("buttons", ["keys"]), ("cpu", ["soc"]),
          ("gpu", ["gpu"]), ("storage", ["storage"]), ("sensors", ["sensor_hub"]), ("wifi", ["wifi_bt"]),
          ("bluetooth", ["wifi_bt"]), ("audio", ["audio"]), ("battery", ["battery", "pmic"]), ("haptic", ["haptic"]),
          ("camera", ["camera"]), ("torch", ["torch"]), ("cellular", ["cellular"]), ("thermal", ["thermal"])]
NOTE_KEYS = {"display": ["lcm", "size", "lk_fb"], "touch": ["chip", "bus", "pins"], "buttons": ["keypad", "pmic_keys"],
             "cpu": ["cores"], "gpu": ["mali", "mfgcfg"], "storage": ["type", "controller", "system_lun"],
             "sensors": ["scp", "sspm"], "wifi": ["chip", "consys"], "bluetooth": ["btif", "chip"],
             "audio": ["codec_node", "amplifiers_on", "afe"], "battery": ["chip", "gauge", "charger"], "haptic": ["node"],
             "camera": ["sensors"], "torch": ["flash"], "cellular": ["blocks"], "thermal": ["controller"]}


def short(v, n=60):
    if isinstance(v, dict):
        s = " ".join("%s=%s" % (k, short(x, 24)) for k, x in v.items() if x is not None)
    elif isinstance(v, list):
        if v and isinstance(v[0], dict) and "core" in v[0]:
            k = [x["core"] for x in v]
            s = " + ".join("%dx %s" % (k.count(c), c) for c in dict.fromkeys(k))
        else:
            s = ",".join(short(x, 20) for x in v[:4]) + ("..." if len(v) > 4 else "")
    else:
        s = str(v)
    return s if len(s) <= n else s[:n - 1] + "..."


def get(c, area, key):
    return c.facts.get(area, {}).get(key, {}).get("value")


def adt_input(c):
    L = []

    def put(k, v, src):
        if v is not None:
            L.append("%s\t%s\t# %s" % (k, v, src))
    F = lambda a, k: c.facts.get(a, {}).get(k)
    for k, a, key in (("PHYS_BASE", "memory", "xnu_phys_base"),):
        f = F(a, key)
        put(k, f and f["value"], f and f["src"])
    f = F("memory", "xnu_mem_size")
    put("MEM_SIZE", f and f["value"], f and f["src"])
    for k, key in (("GICD", "gicd"), ("GICR", "gicr")):
        f = F("soc", key)
        if f:
            put(k, "%s %s" % (f["value"]["base"], f["value"]["size"]), f["src"])
    for k, key in (("TIMEBASE", "timebase_hz"), ("VTIMER_INTID", "vtimer_intid")):
        f = F("soc", key)
        put(k, f and f["value"], f and f["src"])
    f = F("soc", "uart")
    if f:
        put("UART", "%s %s" % (f["value"]["base"], f["value"]["size"]), f["src"])
    cores = get(c, "soc", "cores")
    if cores:
        put("CORES", " ".join("%s:%s" % (x["mpidr"], x["core"]) for x in cores), "dts: /cpus (MPIDR:part, boot core first)")
    f = F("memory", "lk_fb")
    sz = get(c, "display", "size")
    if f and sz:
        w, h = sz
        stride = w * 4
        put("FB", f["value"]["base"], f["src"])
        put("FB_W", w, "defconfig CONFIG_LCM_WIDTH")
        put("FB_H", h, "defconfig CONFIG_LCM_HEIGHT")
        put("FB_STRIDE", stride, "width x 4: assumes 32 bpp and no row padding; the LK probe confirms the pitch")
        put("FB_SIZE", hex((stride * h + 0x3fff) & ~0x3fff), "stride x height rounded to 16 KiB")
    f = F("storage", "controller")
    if f:
        base = int(f["value"]["base"], 16)
        put("UFS" if get(c, "storage", "type") == "ufs" else "MMC", "%s %s" % (f["value"]["base"], hex((int(f["value"]["size"], 16) + 0x3fff) & ~0x3fff)),
            f["src"] + " (size rounded to 16 KiB)")
    for k, a, key in (("OVL0", "display", "ovl0"), ("MFGCFG", "gpu", "mfgcfg"), ("SPI_TOUCH", "touch", "bus"),
                      ("KEYPAD", "keys", "keypad"), ("PWRAP", "pmic", "pwrap"), ("BTIF", "wifi_bt", "btif"),
                      ("CONSYS", "wifi_bt", "consys"), ("SCP", "sensor_hub", "scp"), ("TOPRGU", "soc", "toprgu")):
        f = F(a, key)
        if f and f["value"].get("base"):
            put(k, f["value"]["base"], f["src"])
    f = F("memory", "ramoops")
    if f:
        put("RAMOOPS", "%s %s" % (f["value"]["base"], f["value"]["size"]), f["src"])
    return "# facts the ADT builder needs, one per line: key, value, where it was read\n" + "\n".join(L) + "\n"


def device_conf(c):
    name = c.name
    vendor = (c.board.get("PRODUCT_MANUFACTURER") or "unknown")
    cores = get(c, "soc", "cores") or []
    args = []
    if cores:
        args.append("cpus=%d" % len(cores))
    lun = get(c, "storage", "system_lun")
    if lun is not None:
        args.append("mp_ufslun=%d" % lun)
    args.append("mp_ufsroot=xnusys")
    adt = ["--" + name]
    if get(c, "storage", "type") == "ufs":
        adt.append("--ufs")
    if "audio" in c.facts:
        adt.append("--audio")
    if "torch" in c.facts:
        adt.append("--torch")
    out = ["# %s. Written by mapple-bringup from the vendor's trees: facts only, nothing here has run on the phone." % c.title,
           "device %s" % name, "\ttitle\t%s (%s)" % (c.title, name), "\tvendor\t%s" % vendor,
           "\tsoc\t%s" % c.soc_name(), "\tdefconfig\t%s_defconfig" % name, "\tfirmware\tpull-firmware.sh",
           "\tmaintainer\t%s" % c.maintainer, "\tcmdline\t%s" % " ".join(args), "\tadt\t%s" % " ".join(adt)]
    for st, areas in STATUS:
        notes = []
        for a in areas:
            for k in NOTE_KEYS.get(st, []):
                v = get(c, a, k)
                if v is not None:
                    notes.append("%s %s" % (k, short(v)))
        out.append("\tstatus %s missing %s" % (st, "; ".join(notes)[:200] if notes else "nothing found in the trees"))
    return "\n".join(out) + "\n"


def configs(c):
    n, soc = c.name, c.soc_name()
    d = ("# defconfig for the %s (%s, MediaTek %s): the common kernel's configuration, the SoC's layer and this phone's own.\n"
         "#include common_defconfig\n#include %s.config\n#include %s.config\n" % (c.title, n, soc.upper(), soc, n))
    f = ("# Fragment: what is true of the %s and of no other phone with this SoC.\n"
         "# Nothing of the phone is on yet. Turn drivers on one at a time, only after a run on the phone shows them working.\n"
         'CONFIG_DEVICE="%s"\n' % (c.title, n))
    return d, f


def boot_args(c):
    L = ["# Boot arguments for the first boots, read-only steps first. Nothing runs without its argument; a value ending in ? is not",
         "# derivable from the trees (see BRIEF.md for the probe that settles it)."]
    cores = get(c, "soc", "cores")
    if cores:
        L.append("cpus=%d\t# cores in /cpus" % len(cores))
    L.append("mp_ufsroot=xnusys\t# our partition's name (the convention); it must exist in the GPT first")
    lun = get(c, "storage", "system_lun")
    L.append("mp_ufslun=%s\t# BoardConfig names the system partitions sd<letter>N" % (lun if lun is not None else "?"))
    if get(c, "storage", "type") == "ufs":
        L.append("mp_ufs=probe?\t# read the controller as LK leaves it before any write path is on")
    return "\n".join(L) + "\n"


def match(c):
    """[(area, key, status, files)]: facts with an identifier (a base address, a chip name) and where ours mentions it."""
    rows = []
    for area, d in c.facts.items():
        for key, f in d.items():
            ids = [i for i in f["ident"] if i]
            if not ids:
                continue
            files = set()
            for i in ids:
                for root in c.ours:
                    r = subprocess.run(["grep", "-rIl", "-i", "-F", "--exclude-dir=.git", "--exclude-dir=out", "-e", i, root],
                                       capture_output=True, text=True)
                    files |= {os.path.relpath(x, root) for x in r.stdout.split("\n") if x}
            rows.append((area, key, "named" if files else "not named", sorted(files)[:4]))
    return rows


def report(c, rows):
    L = ["# Match report: %s" % c.title, "",
         "Which of our code already mentions each thing the trees say this phone has (a base address or a part name found in the",
         "files of `--ours`). `named` means a driver or table of ours mentions it, not that it works here: read it before turning it on.",
         "`not named` means nothing of ours mentions it: a new driver, or an address or name spelled another way.", ""]
    if not rows:
        L.append("No `--ours` given: nothing compared.")
    else:
        L += ["| area | fact | status | where |", "| --- | --- | --- | --- |"]
        for a, k, s, files in rows:
            L.append("| %s | %s | %s | %s |" % (a, k, s, ", ".join("`%s`" % f for f in files) or "-"))
    L += ["", "## Not covered by sources (a phone probe settles each)", ""]
    L += ["- %s: %s" % (a, g) for a, g in c.gaps]
    return "\n".join(L) + "\n"


def brief(c, rows):
    L = ["# Porting brief: %s" % c.title, "",
         "Facts the vendor's open trees give for this phone, the gaps they leave, and the next steps. Generated by mapple-bringup;",
         "nothing here has run on the phone. Each fact names where it was read (`file:line` of the tree, or the defconfig).", "",
         "Inputs: Android device tree, kernel tree (%s, defconfig `%s`)%s%s." % (
             "project `%s`" % c.project if c.project else "overlay `%s`" % ", ".join(c.overlay_files) if c.overlay_files else "no overlay", os.path.basename(c.defconfig_path or "?"), ", the phone's own tree" if c.live else ", no phone tree",
             ", its GPT" if c.gpt else ", no GPT"), "", "SoC: %s." % c.soc_line(), "", "## Facts", ""]
    for area, d in c.facts.items():
        L.append("### " + area)
        for k, f in d.items():
            v = f["value"]
            if isinstance(v, list) and len(v) > 2 and all(isinstance(x, dict) for x in v) and not (k == "cores"):
                cols = list(dict.fromkeys(c_ for x in v for c_ in x))
                L += ["- **%s** (%s):" % (k, f["src"]), "", "  | " + " | ".join(cols) + " |", "  | " + " | ".join("---" for _ in cols) + " |"]
                L += ["  | " + " | ".join(str(x.get(c_, "")) for c_ in cols) + " |" for x in v[:120]]
                L.append("")
            else:
                L.append("- **%s**: `%s` (%s)" % (k, short(v, 400), f["src"]))
        L.append("")
    L += ["## Gaps", ""] + ["- %s: %s" % (a, g) for a, g in c.gaps] + [""]
    miss = [(a, k) for a, k, s, _ in rows if s == "not named"]
    if miss:
        L += ["## Not named in our trees (likely a driver of its own)", ""] + ["- %s %s" % m for m in miss] + [""]
    L += ["## Next steps", "",
          "1. Run the probes below on the phone (Android, root), read only; share them with identifiers masked.",
          "2. Make the GPT carve for `xnusys` (room: see storage facts) in files first; write it to the phone only on your word.",
          "3. Boot with nothing of the phone's: loader banner and the kernel's first lines in pstore.",
          "4. Memory: use the holes above; then storage read-only, display, touch, keys; then the rest, one boot-arg each, "
          "a risky step (voltage, clock, modem or SCP power, storage write) alone in its boot.", "",
          "## Read-only probes (Android, root)", ""]
    for a, cmd, why in c.probes:
        L += ["- %s: %s" % (a, why), "  ```", "  " + cmd, "  ```"]
    return "\n".join(L) + "\n"


def write(c, out):
    os.makedirs(os.path.join(out, c.name, "configs"), exist_ok=True)
    d, f = configs(c)
    rows = match(c) if c.ours else []
    files = {os.path.join(c.name, "device.conf"): device_conf(c), os.path.join(c.name, "configs", c.name + "_defconfig"): d,
             os.path.join(c.name, "configs", c.name + ".config"): f, os.path.join(c.name, "boot-args.txt"): boot_args(c),
             "adt-input.conf": adt_input(c), "report.md": report(c, rows), "BRIEF.md": brief(c, rows),
             "facts.json": json.dumps({"facts": c.facts, "gaps": c.gaps, "match": rows}, indent=1, sort_keys=True) + "\n"}
    for p, text in files.items():
        open(os.path.join(out, p), "w").write(text)
