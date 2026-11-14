"""What the areas read from, and where they put what they find."""
import glob
import os
import re
import struct
import tempfile

import dts


class Ctx:
    def __init__(self, name, android_dir, kernel_dir, project=None, fdt=None, gpt=None, ours=(), soc_layer=None,
                 title=None, maintainer="unmaintained"):
        self.name, self.android, self.kernel = name, android_dir, kernel_dir
        self.ours, self.soc_layer, self.maintainer = list(ours), soc_layer, maintainer
        self.facts, self.gaps, self.probes = {}, [], []
        self.board = read_mk(android_dir)
        self.dtsdir = os.path.join(kernel_dir, "arch/arm64/boot/dts/mediatek")
        self.defconfig_path = find_defconfig(kernel_dir, name, self.board)
        self.sym = dts.defconfig_symbols(self.defconfig_path)
        self.project = project or guess_project(self.dtsdir, self.sym)
        self.tree = self.load_tree()
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
        proj = sorted(f for f in order if f.startswith("oplus") and str(self.project) in f and soc[2:] in f)
        for f in plat + over + proj:
            t.add_file(os.path.join(self.dtsdir, f), incs, self.sym)
        self.dts_files = plat + over + proj
        return t

    def soc_name(self):
        m = re.search(r"mt\d{4}", self.board.get("TARGET_BOARD_PLATFORM", "") or "") or \
            re.search(r"mt\d{4}", " ".join(self.board.values()))
        return m[0] if m else "mt6781"

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


def find_defconfig(kernel, name, board):
    c = board.get("TARGET_KERNEL_CONFIG")
    d = os.path.join(kernel, "arch/arm64/configs")
    for f in ([c] if c else []) + [name + "_defconfig"]:
        if f and os.path.exists(os.path.join(d, f)):
            return os.path.join(d, f)
    g = glob.glob(os.path.join(d, "*" + name + "*"))
    return g[0] if g else None


def guess_project(dtsdir, sym):
    m = re.findall(r"_(\d{5})\b", sym.get("CONFIG_CUSTOM_KERNEL_IMGSENSOR", ""))
    return m[0] if m else None


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
