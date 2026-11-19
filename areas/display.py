"""Display panel and LK's framebuffer."""
import dts


def run(c):
    dsi = c.compat(c.soc_name() + "-dsi") or c.compat("-dsi")
    panels = []
    if dsi:
        for k in dsi.kids:
            if k.has("compatible") and k.has("reg"):
                panels.append(k.str("compatible"))
        r = dts.reg(dsi)[0]
        c.fact("display", "dsi", {"base": hex(r[0])}, c.src(dsi), [hex(r[0])[2:].zfill(8)])
    c.fact("display", "panels_in_tree", panels, "dts: dsi panel nodes (LK picks one at boot: lcm= in the live tree)")
    ovl = c.compat("-disp-ovl") or c.compat("disp_ovl0")
    if ovl:
        r = dts.reg(ovl)[0]
        c.fact("display", "ovl0", {"base": hex(r[0])}, c.src(ovl), [hex(r[0])[2:].zfill(8)])
    w, h = c.cfg("LCM_WIDTH"), c.cfg("LCM_HEIGHT")
    if w and h:
        c.fact("display", "size", [int(w), int(h)], "defconfig CONFIG_LCM_WIDTH/HEIGHT")
    for n in c.tree.root.walk():
        if n.has("touchpanel,panel-coords"):
            c.fact("display", "touch_coords", n.ints("touchpanel,panel-coords"), c.src(n))
            break
    lk = c.facts.get("memory", {}).get("lk_fb")
    if lk:
        c.fact("display", "lcm", lk["value"]["lcm"], lk["src"])
        c.fact("display", "lk_fb", {k: lk["value"][k] for k in ("base", "vram")}, lk["src"], lk["ident"])
    else:
        c.gap("display", "no --fdt: the panel LK picked, the framebuffer address, its pitch and the layer are not known")
    c.probe("display", "adb shell su -c 'cat /proc/devinfo/lcd /sys/kernel/debug/dispsys/* 2>/dev/null'", "panel name and the layer LK leaves on")
