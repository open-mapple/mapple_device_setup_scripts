"""Memory map: DRAM, LK's fixed reservations, what is left, the holes XNU will keep out of, ramoops."""
import dts

PAGE = 0x4000
BOUNDARY = 0x2000000      # the kernel maps RAM in 32 MB blocks


def reservations(live):
    rm = live.node("reserved-memory")
    out = []
    for n in (rm.kids if rm else []):
        for base, size in dts.reg(n):
            out.append((base, base + size, n.name, n.has("no-map"), n))
    return sorted(out, key=lambda r: r[:3])


def holes(res, lo, hi, page=PAGE):
    """The shim's rule (every reservation, 16 KiB pages, clipped to RAM, merged), without the payload and tree it adds at boot."""
    out = []
    for a, e, *_ in res:
        a, e = max(a & ~(page - 1), lo), min((e + page - 1) & ~(page - 1), hi)
        if a >= e:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([a, e])
    return out


def free(holes_, lo, hi):
    out, cur = [], lo
    for a, e in holes_:
        if a > cur:
            out.append((cur, a))
        cur = max(cur, e)
    if cur < hi:
        out.append((cur, hi))
    return out


def run(c):
    # pools the kernel tree asks Android to place at run time (alloc-ranges, no reg): their place is only in /proc/iomem
    pools = []
    rm = c.tree.node("reserved-memory")
    for n in (rm.kids if rm else []):
        if not n.has("reg") and (n.has("size") or n.has("alloc-ranges")):
            pools.append({"name": n.name, "size": hex(dts.num(n.cells("size")[-1])) if n.cells("size") else None,
                          "no_map": n.has("no-map")})
    if pools:
        c.fact("memory", "runtime_pools", pools, "dts: /reserved-memory, nodes with alloc-ranges and no reg")
    mem = c.tree.node("memory")
    if mem and not c.live:
        c.fact("memory", "dram_in_tree", [[hex(a), hex(s)] for a, s in dts.reg(mem)],
               "dts: /memory (the base tree's: LK writes the real node)")
    if not c.live:
        c.gap("memory", "no --fdt: DRAM size, LK's reservations, the framebuffer and ramoops are only in the phone's own tree")
        c.probe("memory", "adb shell su -c 'cat /sys/firmware/fdt' > live.dtb", "LK's tree: memory, reserved-memory, chosen")
    c.probe("memory", "adb shell su -c 'cat /proc/iomem'", "where Android placed the runtime pools (wifi, consys, ssmr, scp)")
    if not c.live:
        return
    L = c.live
    m = L.node("memory") or next((n for n in L.root.kids if n.name.startswith("memory")), None)
    rng = dts.reg(m) if m else []
    if not rng:
        c.gap("memory", "the live tree has no memory node")
        return
    lo, hi = min(a for a, s in rng), max(a + s for a, s in rng)
    c.fact("memory", "dram", {"base": hex(lo), "end": hex(hi), "mib": (hi - lo) >> 20,
                              "ranges": [[hex(a), hex(s)] for a, s in rng]}, "live tree: /memory")
    res = reservations(L)
    c.fact("memory", "reservations", [{"base": hex(a), "end": hex(e), "kib": (e - a) >> 10, "name": n, "no_map": nm}
                                      for a, e, n, nm, _ in res], "live tree: /reserved-memory (fixed reg)")
    h = holes(res, lo, hi)
    fr = free(holes(res, lo, hi, 1), lo, hi)      # as the reservations are written, not rounded to our pages
    frp = free(h, lo, hi)
    c.fact("memory", "holes", [[hex(a), hex(e)] for a, e in h], "the shim's rule over the reservations")
    c.fact("memory", "free", [{"base": hex(a), "end": hex(e), "mib": round((e - a) / 2**20, 1)} for a, e in fr],
           "DRAM minus the reservations as written")
    big = max(frp, key=lambda r: r[1] - r[0])
    top = max(a for a, e, *_ in res)
    mem_end = (big[1]) & ~(BOUNDARY - 1)
    c.fact("memory", "xnu_phys_base", hex(big[0]), "start of the largest free range (16 KiB pages)")
    c.fact("memory", "xnu_mem_end", hex(mem_end), "its end rounded down to 32 MB (the kernel maps 32 MB blocks)")
    c.fact("memory", "xnu_mem_size", hex(mem_end - big[0]), "")
    c.fact("memory", "top_reservation", hex(top), "the highest fixed reservation")
    c.fact("memory", "reserved_mib", round(sum(e - a for a, e, *_ in res) / 2**20), "")
    for a, e, n, nm, node in res:
        if "pstore" in n or "ramoops" in " ".join(node.strs("compatible")):
            c.fact("memory", "ramoops", {"base": hex(a), "size": hex(e - a)}, "live tree: /reserved-memory/" + n, [hex(a)[2:]])
    ch = L.node("chosen")
    if ch:
        bs = ch.blob("atag,videolfb")
        if len(bs) >= 20:
            fb = int.from_bytes(bs[:8], "little")
            fps, vram = int.from_bytes(bs[12:16], "little"), int.from_bytes(bs[16:20], "little")
            name = bs[20:].split(b"\0")[0].decode(errors="replace")
            c.fact("memory", "lk_fb", {"base": hex(fb), "vram": hex(vram), "fps_x100": fps, "lcm": name},
                   "live tree: /chosen atag,videolfb (fb_base u64, found u32, fps u32, vram u32, lcm name)", [hex(fb)[2:]])
        bootargs = (ch.str("bootargs") or "")
        keep = {k: v for k, v in (a.partition("=")[::2] for a in bootargs.split()) if k == "lcm" or k.startswith("ramoops")
                or k == "bootopt"}
        if keep:
            c.fact("memory", "cmdline_kept", keep, "live tree: /chosen bootargs (only these keys; serials and ids dropped)")
