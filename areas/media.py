"""Audio codec and amplifier, camera sensors and flash, vibrator."""
import re

import dts


def run(c):
    afe = c.compat("-afe-pcm") or c.compat("afe")
    if afe:
        r = dts.reg(afe)[0]
        c.fact("audio", "afe", {"base": hex(r[0]), "compat": afe.str("compatible")}, c.src(afe), [hex(r[0])[2:].zfill(8)])
    snd = [n for n in c.tree.root.walk() if re.search(r"mt63\d\d_snd|mt63\d\d-sound", " ".join(n.strs("compatible")) + n.name)]
    if snd:
        c.fact("audio", "codec_node", sorted({n.name for n in snd}), c.src(snd[0]), [re.search(r"mt63\d\d", snd[0].name + " ".join(snd[0].strs("compatible")))[0]
                                                                                    if re.search(r"mt63\d\d", snd[0].name + " ".join(snd[0].strs("compatible"))) else ""])
    amps = sorted(k.replace("CONFIG_SND_SOC_", "") for k, v in c.sym.items()
                  if v == 1 and re.match(r"CONFIG_SND_SOC_(AW8|SIA8|TFA|RT5|WSA|CS35|TAS)", k))
    if amps:
        c.fact("audio", "amplifiers_on", amps, "defconfig CONFIG_SND_SOC_*", [a.lower() for a in amps])
    amps_n = []
    for n in c.tree.root.walk():
        comp = " ".join(n.strs("compatible"))
        if re.search(r"awinic,aw87|sia81|tfa98|aw8\d{4}", comp) and n.parent and ("i2c" in n.parent.name):
            a = n.ints("reg")
            amps_n.append({"compat": comp, "bus": n.parent.name, "addr": hex(a[0]) if a else None, "src": c.src(n)})
    if amps_n:
        c.fact("audio", "amp_nodes", amps_n, "dts (i2c children)", [x["compat"].split(",")[-1] for x in amps_n])
    c.probe("audio", "adb shell su -c 'cat /proc/asound/cards; cat /proc/asound/card0/codec#* 2>/dev/null | head -40; tinymix 2>/dev/null | head -80'",
            "card, codec and the mixer's default routes")
    # camera
    sens = (c.cfg("CUSTOM_KERNEL_IMGSENSOR") or "").split()
    if sens:
        if c.project:
            mine = [s for s in sens if s.endswith("_" + str(c.project))]
        else:
            mine = sens
        c.fact("camera", "sensors", mine or sens, "defconfig CUSTOM_KERNEL_IMGSENSOR (project %s)" % c.project,
               [s.split("_")[0] for s in (mine or sens)][:6])
    cam = c.compat("camisp") or c.compat("seninf_top") or c.compat("seninf")
    if cam:
        r = dts.reg(cam)[0]
        c.fact("camera", "isp", {"base": hex(r[0])}, c.src(cam), [hex(r[0])[2:].zfill(8)])
    fl = c.compat("flashlights") or c.compat("mt6370-pmu-fled") or c.compat("fled")
    flash = sorted({k.replace("CONFIG_", "") for k, v in c.sym.items() if v == 1 and "FLED" in k})
    if fl or flash:
        c.fact("torch", "flash", {"dts": fl.str("compatible") if fl else None, "defconfig": flash},
               "dts / defconfig; the exact part reads from its id on the phone", [x.split("_")[0].lower() for x in flash])
    vib = [n for n in c.tree.root.walk() if n.str("compatible") and "vibr" in n.str("compatible")]
    vib += [n for n in c.tree.root.walk() if "vibr" in n.name or "haptic" in n.name]
    if vib:
        c.fact("haptic", "node", vib[0].name, c.src(vib[0]))
    c.probe("camera", "adb shell su -c 'dmesg | grep -i -e imgsensor -e seninf | head -60; cat /proc/kd_camera/* 2>/dev/null'",
            "which sensors answered on this unit")
