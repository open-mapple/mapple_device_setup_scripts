"""What the areas read from, and where they put what they find."""
import glob
import os
import re
import struct
import tempfile

import dts


class Ctx:
    def __init__(self, name, android_dir, kernel_dir, project=None, fdt=None, gpt=None, ours=(), soc_layer=None,
                 title=None, maintainer="unmaintained", soc=None, overlays=()):
        check_inputs(android_dir, kernel_dir)
        self.name, self.android, self.kernel = name, android_dir, kernel_dir
        self.ours, self.soc_layer, self.maintainer = list(ours), soc_layer, maintainer
        self.facts, self.gaps, self.probes = {}, [], []
        self.board = read_mk(android_dir)
        self.assigns = read_mk_tree(android_dir)
        self.dtsdir = os.path.join(kernel_dir, "arch/arm64/boot/dts/mediatek")
        self.kcfgs = find_kconfigs(kernel_dir, name, self.assigns)
        self.defconfig_path = self.kcfgs[0] if self.kcfgs else None
        self.sym = {}
        for f in self.kcfgs:
            self.sym.update(dts.defconfig_symbols(f))
        self.live = None
        if fdt:
            self.live = dts.Tree()
            tmp = tempfile.mkdtemp()
            p = os.path.join(tmp, "live.dts")
            if open(fdt, "rb").read(4) == b"\xd0\x0d\xfe\xed":
                open(p, "w").write(dts.load_live(fdt))
            else:
                p = fdt
            self.live.add_file(p)
        self.check_vendor()
        self.soc, self.soc_src, self.soc_also = self.find_soc(soc)
        print("SoC: %s" % self.soc_line())
        self.project, self.overlays = project, list(overlays)
        self.tree = self.load_tree()
        self.gpt = read_gpt(gpt) if gpt else None
        self.title = title or "%s %s" % (self.board.get("PRODUCT_BRAND", ""), self.board.get("PRODUCT_MODEL", name))

    def load_tree(self):
        t = dts.Tree()
        incs = [self.dtsdir, os.path.join(self.kernel, "include"), os.path.dirname(self.dtsdir)]
        soc = self.soc_name()
        order = []
        for f in os.listdir(self.dtsdir):
            if f.endswith(".dts"):
                order.append(f)
        plat = [f for f in order if re.fullmatch(soc + r"\.dts", f)]
        over = sorted(f for f in order if re.match(r"k\w*" + soc[2:] + r"\w*\.dts$", f))
        proj = self.pick_overlays(order, plat)
        for f in plat + over + proj:
            t.add_file(os.path.join(self.dtsdir, f), incs, self.sym)
        self.dts_files, self.overlay_files = plat + over + proj, proj
        return t

    def pick_overlays(self, files, plat):
        """The board's dts overlays: --overlay, else the files --project names, else the one overlay the kernel config builds.
        Several candidates and no choice stop the run."""
        cand = [os.path.basename(n) + ".dts" for n in self.sym.get("CONFIG_BUILD_ARM64_DTB_OVERLAY_IMAGE_NAMES", "").split()]
        cand = [f for f in dict.fromkeys(cand) if f in files and f not in plat]
        if self.overlays:
            out = []
            for o in self.overlays:
                f = next((x for x in (os.path.basename(o), os.path.basename(o) + ".dts") if x in files), None)
                if not f:
                    raise SystemExit("mapple-bringup: --overlay %s: no such file in %s%s" % (o, self.dtsdir, self.overlay_help(cand)))
                out.append(f)
            how = "--overlay"
        elif self.project:
            out = [f for f in cand if self.project in f] or sorted(f for f in files if self.project in f and f not in plat)
            if not out:
                raise SystemExit("mapple-bringup: --project %s names no dts file in %s%s" % (self.project, self.dtsdir, self.overlay_help(cand)))
            how = "--project " + self.project
        elif len(cand) > 1:
            raise SystemExit("mapple-bringup: the kernel config builds several dts overlays and nothing says which is this phone's%s"
                             % self.overlay_help(cand))
        else:
            out, how = cand, "the only overlay the kernel config builds"
        self.overlay_how = how
        print("Overlay: %s (%s)" % (", ".join(out) or "none, the SoC dts alone", how if out else "no overlay in the kernel config"))
        return out

    def overlay_help(self, cand):
        return ("\nCandidates (CONFIG_BUILD_ARM64_DTB_OVERLAY_IMAGE_NAMES):\n%s\n" % "\n".join("  " + f for f in cand) if cand else
                "\nThe kernel config names no overlay; look in the dts directory.\n") + "Pass --overlay FILE or --project NAME."

    def soc_name(self):
        return self.soc

    def check_vendor(self):
        """Stop on any sign that the trees are not MediaTek's; this tool reads nothing else."""
        qcom = re.compile(r"(?:sm|sdm|msm|apq|qcs)\w*|lito|kona|atoll|bengal|holi|trinket|lahaina|taro|kalama|waipio|parrot", re.I)
        ev = []
        for n, v, src in self.assigns:
            if n == "TARGET_BOARD_PLATFORM" and not re.search(r"mt\d{4}", v, re.I) and "$(" not in v:
                ev.append(("Qualcomm" if qcom.fullmatch(v) else "not MediaTek", "TARGET_BOARD_PLATFORM := %s (%s)" % (v, src)))
        for f in self.kcfgs:
            for i, l in enumerate(open(f, errors="replace"), 1):
                if l.strip() == "CONFIG_ARCH_QCOM=y":
                    ev.append(("Qualcomm", "kernel config CONFIG_ARCH_QCOM (%s:%d)" % (self.rel(f), i)))
        if self.live:
            comp = self.live.root.strs("compatible")
            if comp and not any(c.lower().startswith("mediatek,") for c in comp):
                q = any(c.lower().startswith("qcom,") for c in comp)
                ev.append(("Qualcomm" if q else "not MediaTek", "--fdt root compatible %s" % ", ".join(comp)))
        if not ev:
            return
        qc = any(v == "Qualcomm" for v, _ in ev)
        raise SystemExit("mapple-bringup: these trees are %s:\n%s\nThis tool only handles MediaTek phones, so nothing was written.%s" % (
            "Qualcomm's" if qc else "not MediaTek's", "\n".join("  " + e for _, e in ev),
            "\nFor SM7150 phones see the Qualcomm line: xnu_kernel_qcom_common and the device repos xnu_device_xiaomi_sweet and "
            "xnu_device_google_sunfish." if qc else ""))

    def find_soc(self, given):
        """(soc, where it was read, where else it was read). Never a default: sources that disagree, or none, stop the run."""
        if given:
            if not re.fullmatch(r"mt\d{4}", given.lower()):
                raise SystemExit("--soc %s: expected a MediaTek SoC name such as mt6768" % given)
            return given.lower(), "--soc", []
        found, looked = [], []
        for n, v, src in self.assigns:
            if n == "TARGET_BOARD_PLATFORM":
                m = re.search(r"mt\d{4}", v, re.I)
                if m:
                    found.append((m[0].lower(), "TARGET_BOARD_PLATFORM (%s)" % src))
        if not any(n == "TARGET_BOARD_PLATFORM" for n, _, _ in self.assigns):
            looked.append("TARGET_BOARD_PLATFORM is not set in the device tree or the common trees beside it")
        cfg = [(re.fullmatch(r"CONFIG_MACH_MT(\d{4})=y", l.strip()), f, i) for f in self.kcfgs
               for i, l in enumerate(open(f, errors="replace"), 1)]
        cfg = [("mt" + m[1], "kernel config CONFIG_MACH_MT%s (%s:%d)" % (m[1], self.rel(f), i)) for m, f, i in cfg if m]
        if not cfg:
            cfg = [(m[1].lower(), "kernel config CONFIG_MTK_PLATFORM (%s:%d)" % (self.rel(f), i)) for f in self.kcfgs
                   for i, l in enumerate(open(f, errors="replace"), 1)
                   for m in [re.fullmatch(r'CONFIG_MTK_PLATFORM="(mt\d{4})"', l.strip(), re.I)] if m]
        found += cfg
        if not cfg:
            looked.append("the kernel config names no CONFIG_MACH_MT* or CONFIG_MTK_PLATFORM")
        if self.live:
            for c in self.live.root.strs("compatible"):
                m = re.fullmatch(r"mediatek,(mt\d{4})", c, re.I)
                if m:
                    found.append((m[1].lower(), "--fdt root compatible %s" % c))
        else:
            looked.append("no --fdt given")
        socs = sorted(f for f in os.listdir(self.dtsdir) if re.fullmatch(r"mt\d{4}\.dts", f)) if os.path.isdir(self.dtsdir) else []
        if len(socs) == 1:
            found.append((socs[0][:6], "the only SoC dts, arch/arm64/boot/dts/mediatek/" + socs[0]))
        else:
            looked.append("%d SoC dts files in the kernel tree (%s)" % (len(socs), " ".join(s[:-4] for s in socs[:8])))
        names = sorted({s for s, _ in found})
        if not found:
            raise SystemExit("mapple-bringup: no source names the SoC (%s). Pass --soc mtNNNN." % "; ".join(looked))
        if len(names) > 1:
            raise SystemExit("mapple-bringup: the sources disagree about the SoC:\n%s\nPass --soc mtNNNN to choose."
                             % "\n".join("  %s: %s" % f for f in found))
        return names[0], found[0][1], [w for _, w in found[1:]]

    def soc_line(self):
        return "%s, from %s%s" % (self.soc, self.soc_src, "; also " + "; ".join(self.soc_also) if self.soc_also else "")

    def rel(self, path):
        return os.path.relpath(path, self.kernel)

    def fact(self, area, key, value, src, ident=()):
        self.facts.setdefault(area, {})[key] = {"value": value, "src": src, "ident": list(ident)}

    def gap(self, area, text):
        self.gaps.append((area, text))

    def probe(self, area, cmd, why):
        self.probes.append((area, cmd, why))

    def src(self, node):
        return node.src or node.path

    def cfg(self, name, default=None):
        return self.sym.get("CONFIG_" + name, default)

    def compat(self, sub, tree=None, exact=False):
        """First node (in the merged tree) whose compatible has the substring (is the word, with exact)."""
        for n in (tree or self.tree).root.walk():
            if any(sub == c if exact else sub in c for c in n.strs("compatible")):
                return n


def read_mk(root):
    out = {}
    for f in glob.glob(os.path.join(root, "*.mk")) + glob.glob(os.path.join(root, "*", "*.mk")):
        for line in open(f, errors="replace"):
            m = re.match(r"\s*([A-Z0-9_]+)\s*(?::=|\+=|\?=|=)\s*(.*?)\s*(?:#.*)?$", line)
            if m:
                out[m[1]] = (out[m[1]] + " " + m[2]).strip() if m[1] in out and "+=" in line else m[2]
    return out


def check_inputs(android, kernel):
    """Stop, naming the option, when a tree is not source: a firmware dump, a wrong folder."""
    bad = []
    if not glob.glob(os.path.join(android, "BoardConfig*.mk")) + glob.glob(os.path.join(android, "device.mk")):
        bad.append("--android-device %s: this doesn't look like an Android device tree source (no BoardConfig.mk or device.mk). "
                   "Did you pass a firmware dump? Pass the android_device_<brand>_<codename> repository." % android)
    if not os.path.isdir(os.path.join(kernel, "arch/arm64/boot/dts")):
        bad.append("--android-kernel %s: this doesn't look like an Android kernel source (no arch/arm64/boot/dts). "
                   "Did you pass a firmware dump? Pass the vendor's kernel source for the phone." % kernel)
    if bad:
        raise SystemExit("mapple-bringup: " + "\n".join(bad))


MK_ASSIGN = re.compile(r"\s*([A-Z0-9_]+)\s*(?::=|\+=|\?=|=)\s*(.*?)\s*(?:#.*)?$")
MK_INCLUDE = re.compile(r"\s*(?:-?include\s+|\$\(call\s+inherit-product(?:-if-exists)?\s*,\s*)(.*?)\)?\s*(?:#.*)?$")


def read_mk_tree(root):
    """Every assignment in the device tree's makefiles, and in the common trees they include or inherit, as (name, value, file:line)
    in reading order. A tree named in a path (device/<vendor>/<name>/...) is the directory beside the device tree called
    *_<vendor>_<name>, <name> or *_<name>; if that is not exactly one directory, it is not followed."""
    root = os.path.abspath(root)
    parent = os.path.dirname(root)
    sibs = [d for d in os.listdir(parent) if os.path.isdir(os.path.join(parent, d))]
    out, seen, var = [], set(), {}

    def find(ref):
        for _ in range(3):
            ref = re.sub(r"\$\((\w+)\)", lambda m: var.get(m[1], m[0]), ref)
        p = ref.split("/")
        if len(p) < 4 or p[0] != "device" or "$(" in ref:
            return None
        for hit in ([d for d in sibs if d.endswith("_%s_%s" % (p[1], p[2])) or d == p[1] + "_" + p[2]],
                    [d for d in sibs if d == p[2]], [d for d in sibs if d.endswith("_" + p[2])]):
            if hit:
                return os.path.join(parent, hit[0], *p[3:]) if len(hit) == 1 else None

    def walk(path):
        if path in seen or not os.path.isfile(path):
            return
        seen.add(path)
        name = os.path.relpath(path, root if path.startswith(root + os.sep) else parent)
        for n, line in enumerate(open(path, errors="replace"), 1):
            m = MK_INCLUDE.match(line)
            if m:
                if find(m[1]):
                    walk(find(m[1]))
                continue
            m = MK_ASSIGN.match(line)
            if m:
                var[m[1]] = m[2]
                out.append((m[1], m[2], "%s:%d" % (name, n)))

    files = sorted(glob.glob(os.path.join(root, "*.mk")), key=lambda f: (os.path.basename(f) != "BoardConfig.mk", f))
    for f in files + sorted(glob.glob(os.path.join(root, "*", "*.mk"))):
        walk(f)
    return out


def find_kconfigs(kernel, name, assigns):
    """The kernel configs the device names (TARGET_KERNEL_CONFIG, in every tree read), else <name>_defconfig or one with the name in it."""
    d = os.path.join(kernel, "arch/arm64/configs")
    names = [t for n, v, _ in assigns if n == "TARGET_KERNEL_CONFIG" for t in v.split()]
    out = [os.path.join(d, t) for t in dict.fromkeys(names) if os.path.isfile(os.path.join(d, t))]
    if out:
        return out
    if os.path.exists(os.path.join(d, name + "_defconfig")):
        return [os.path.join(d, name + "_defconfig")]
    return glob.glob(os.path.join(d, "*" + name + "*"))[:1]


def read_gpt(path):
    """[(name, first LBA, last LBA)] and the block size, from a GPT header and entries (CRCs are not checked: identifiers
    in a shared copy may be masked)."""
    b = open(path, "rb").read()
    for bs in (4096, 512):
        if b[bs:bs + 8] == b"EFI PART":
            break
    else:
        return None
    lba = struct.unpack_from("<Q", b, bs + 72)[0]
    n, size = struct.unpack_from("<II", b, bs + 80)
    parts = []
    for i in range(n):
        off = lba * bs + i * size
        if off + 128 > len(b):
            break
        e = b[off:off + size]
        if e[:16] == bytes(16):
            continue
        first, last = struct.unpack_from("<QQ", e, 32)
        parts.append((e[56:128].decode("utf-16le").split("\0")[0], first, last))
    return {"block": bs, "parts": parts}
