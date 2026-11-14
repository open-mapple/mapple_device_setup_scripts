"""A reader for Linux device tree sources, enough to ask a phone's tree questions.

It does not compile anything: `#include` and `#if` are handled (the `#if`s against the kernel's defconfig), the macros
of dt-bindings headers stay as words (a sparse kernel checkout has none of them), `&label { }` blocks merge into the
node they name, so a base tree plus its overlays reads as one tree. A live tree (`/sys/firmware/fdt`) goes through
`dtc -I dtb -O dts` first.
"""
import os
import re
import subprocess

GIC = {"GIC_SPI": 0, "GIC_PPI": 1, "IRQ_TYPE_EDGE_RISING": 1, "IRQ_TYPE_EDGE_FALLING": 2,
       "IRQ_TYPE_LEVEL_HIGH": 4, "IRQ_TYPE_LEVEL_LOW": 8}

TOKEN = re.compile(r'"(?:\\[\s\S]|[^"\\])*"|[<>{};=,\[\]]|\((?:[^()]|\([^()]*\))*\)|(?:[^\s<>{};=,\[\]"]|,(?=[^\s<>{};=,\[\]"]))+')


class Node:
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent
        self.props = {}      # name -> list of values: str, or list of cell words
        self.kids = []
        self.labels = []
        self.src = ""        # file:line where the node was first written

    @property
    def path(self):
        return "/" if self.parent is None else (self.parent.path.rstrip("/") + "/" + self.name)

    def kid(self, name):
        for k in self.kids:
            if k.name == name or k.name.split("@")[0] == name:
                return k

    def walk(self):
        yield self
        for k in self.kids:
            yield from k.walk()

    def find(self, **want):
        """Nodes under this one whose properties match: find(compatible="mediatek,mt6781-ufs") (substring in any string)."""
        for n in self.walk():
            if all(any(isinstance(v, str) and w in v for v in n.props.get(k, [])) for k, w in want.items()):
                yield n

    def strs(self, name):
        return [v for v in self.props.get(name, []) if isinstance(v, str)]

    def str(self, name, default=None):
        s = self.strs(name)
        return s[0] if s else default

    def cells(self, name):
        out = []
        for v in self.props.get(name, []):
            if isinstance(v, list):
                out += v
        return out

    def ints(self, name):
        return [num(c) for c in self.cells(name) if num(c) is not None]

    def blob(self, name):
        """A property's bytes: `<cells>` as big-endian words, `[bytes]` as written."""
        out = bytearray()
        for v in self.props.get(name, []):
            if isinstance(v, list):
                for w in v:
                    if w.startswith("0x"):
                        out += int(w, 16).to_bytes(4, "big")
                    else:
                        out += bytes.fromhex(w)
        return bytes(out)

    def has(self, name):
        return name in self.props

    def status_ok(self):
        return self.str("status", "okay") in ("okay", "ok")


def num(word):
    if isinstance(word, int):
        return word
    w = word.strip("()")
    try:
        return int(w, 0)
    except ValueError:
        pass
    if w in GIC:
        return GIC[w]
    if re.fullmatch(r"[\w\s|<>+()-]+", w) and re.search(r"\d", w) and not re.search(r"[A-Za-z_]", w.replace("0x", "")):
        try:
            return int(eval(w, {"__builtins__": {}}))
        except Exception:
            return None
    return None


def defconfig_symbols(path):
    sym = {}
    if path and os.path.exists(path):
        for line in open(path, errors="replace"):
            m = re.match(r"(CONFIG_\w+)=(.*)", line.strip())
            if m:
                sym[m[1]] = 1 if m[2] in ("y", "m") else m[2].strip('"')
    return sym


def preprocess(path, incdirs, sym, seen=None, out=None):
    """Lines of the file with includes inlined and `#if` resolved; each line is (text, 'file:line')."""
    out = [] if out is None else out
    seen = seen or []
    if path in seen:
        return out
    stack = [True]      # is this branch live
    taken = [True]      # has a branch of this #if been taken
    src = os.path.basename(path)
    for n, line in enumerate(open(path, errors="replace"), 1):
        s = line.strip()
        if s.startswith("#"):
            d = s[1:].split(None, 1)
            word, rest = (d + [""])[:2] if d else ("", "")
            if word in ("ifdef", "ifndef"):
                v = rest.strip() in sym
                v = v if word == "ifdef" else not v
                stack.append(stack[-1] and v)
                taken.append(v)
                continue
            if word == "if":
                v = bool(cond(rest, sym))
                stack.append(stack[-1] and v)
                taken.append(v)
                continue
            if word == "elif":
                v = (not taken[-1]) and bool(cond(rest, sym))
                stack[-1] = stack[-2] and v
                taken[-1] = taken[-1] or v
                continue
            if word == "else":
                stack[-1] = stack[-2] and not taken[-1]
                taken[-1] = True
                continue
            if word == "endif":
                stack.pop()
                taken.pop()
                continue
            if not stack[-1]:
                continue
            if word == "include":
                m = re.match(r'["<]([^">]+)[">]', rest.strip())
                if m:
                    for d in [os.path.dirname(path)] + incdirs:
                        f = os.path.join(d, m[1])
                        if os.path.isfile(f):
                            preprocess(f, incdirs, sym, seen + [path], out)
                            break
                continue
            if word == "define":
                p = rest.split(None, 1)
                if p:
                    sym[p[0]] = p[1] if len(p) > 1 else 1
                continue
            continue
        if stack[-1]:
            out.append((line, "%s:%d" % (src, n)))
    return out


def cond(expr, sym):
    e = re.sub(r"/\*.*?\*/", "", expr)
    e = re.sub(r"defined\s*\(?\s*(\w+)\s*\)?", lambda m: "1" if m[1] in sym else "0", e)
    e = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: str(sym.get(m[0], 0)) if str(sym.get(m[0], 0)).lstrip("-").isdigit() else "0", e)
    e = re.sub(r"!(?!=)", " not ", e.replace("&&", " and ").replace("||", " or "))
    try:
        return eval(e, {"__builtins__": {}})
    except Exception:
        return 0


def tokens(lines):
    text = "".join(l for l, _ in lines)
    starts, pos = [], 0
    for l, s in lines:
        starts.append((pos, s))
        pos += len(l)
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m[0]), text, flags=re.S)
    text = re.sub(r'("(?:\\[\s\S]|[^"\\])*")|//[^\n]*', lambda m: m[1] or "", text)
    for m in TOKEN.finditer(text):
        # position -> source line
        i = 0
        lo, hi = 0, len(starts) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if starts[mid][0] <= m.start():
                i, lo = mid, mid + 1
            else:
                hi = mid - 1
        yield m[0], starts[i][1]


def parse_value(toks):
    """Property value tokens (between `=` and `;`) -> list of str / list of words."""
    vals, cur, mode = [], None, None
    for t in toks:
        if t == "<":
            cur, mode = [], "cells"
        elif t == ">" and mode == "cells":
            vals.append(cur)
            cur, mode = None, None
        elif t == "[":
            cur, mode = [], "bytes"
        elif t == "]":
            vals.append(cur)
            cur, mode = None, None
        elif t == ",":
            continue
        elif cur is not None:
            cur.append(t)
        elif t.startswith('"'):
            vals.append(bytes(t[1:-1], "utf-8").decode("unicode_escape"))
        else:
            vals.append(t)
    return vals


class Tree:
    def __init__(self):
        self.root = Node("")
        self.labels = {}

    def add_file(self, path, incdirs=(), sym=None):
        sym = dict(sym or {})
        toks = list(tokens(preprocess(path, list(incdirs), sym)))
        i = 0
        stack = []
        n = len(toks)
        while i < n:
            t, src = toks[i]
            if t in ("/dts-v1/", "/plugin/"):
                i += 2 if toks[i + 1][0] == ";" else 1
                continue
            if t == "/memreserve/":
                while toks[i][0] != ";":
                    i += 1
                i += 1
                continue
            if t == "}":
                stack.pop()
                i += 2 if i + 1 < n and toks[i + 1][0] == ";" else 1
                continue
            if t in ("/delete-node/", "/delete-property/"):
                name = toks[i + 1][0]
                cur = stack[-1] if stack else self.root
                if t == "/delete-node/":
                    ref = self.labels.get(name[1:]) if name.startswith("&") else cur.kid(name)
                    if ref and ref.parent:
                        ref.parent.kids.remove(ref)
                else:
                    cur.props.pop(name, None)
                i += 3
                continue
            # a node opens with `[labels:] name {`, a property is `name = ...;` or `name;`
            j = i
            while j < n and toks[j][0] not in ("{", "=", ";"):
                j += 1
            head = []
            for x in toks[i:j]:
                a, c, b = x[0].partition(":")
                head += [a + ":", b] if c and b and not x[0].startswith("&") else [x[0]]
            if j < n and toks[j][0] == "{":
                labels = [h[:-1] for h in head if h.endswith(":")]
                name = [h for h in head if not h.endswith(":")][-1]
                if name == "/" and not stack:
                    node = self.root
                elif name.startswith("&"):
                    node = self.labels.get(name[1:].strip("{}")) or self._orphan(name)
                else:
                    cur = stack[-1] if stack else self.root
                    node = cur.kid(name) if name in [k.name for k in cur.kids] else None
                    if node is None:
                        node = Node(name, cur)
                        node.src = src
                        cur.kids.append(node)
                for lb in labels:
                    node.labels.append(lb)
                    self.labels[lb] = node
                stack.append(node)
                i = j + 1
                continue
            cur = stack[-1] if stack else self.root
            name = head[-1] if head else ""
            if j < n and toks[j][0] == "=":
                k = j + 1
                while toks[k][0] != ";":
                    k += 1
                cur.props[name] = parse_value([x[0] for x in toks[j + 1:k]])
                i = k + 1
            else:
                if name:
                    cur.props[name] = []
                i = j + 1

    def _orphan(self, name):
        return Node(name)

    def node(self, path):
        n = self.root
        for p in path.strip("/").split("/"):
            if p:
                n = n.kid(p)
                if n is None:
                    return None
        return n


def load_live(dtb):
    r = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", "-q", dtb], capture_output=True, text=True)
    if r.returncode and not r.stdout:
        raise SystemExit("dtc could not read %s: %s" % (dtb, r.stderr.strip()))
    return r.stdout


def load_live_tree(dtb, tmp):
    p = os.path.join(tmp, "live.dts")
    open(p, "w").write(load_live(dtb))
    t = Tree()
    t.add_file(p)
    return t


def reg(node, ac=2, sc=2):
    """[(base, size)] of a node's reg, with the parent's cell counts when the parent says them."""
    p = node.parent
    if p is not None:
        ac = (p.ints("#address-cells") or [ac])[0]
        sc = (p.ints("#size-cells") or [sc])[0]
    c = node.ints("reg")
    out, step = [], ac + sc
    for i in range(0, len(c) - step + 1, step):
        a = 0
        for x in c[i:i + ac]:
            a = (a << 32) | x
        s = 0
        for x in c[i + ac:i + step]:
            s = (s << 32) | x
        out.append((a, s))
    return out


def irq(node):
    """[(spi number, flags)] of GIC_SPI interrupts."""
    c = node.cells("interrupts")
    return [(num(c[i + 1]), num(c[i + 2])) for i in range(0, len(c) - 2, 3) if num(c[i]) == 0]
