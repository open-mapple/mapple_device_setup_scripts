"""PMIC and regulators, battery and charger, thermal."""
import re

import dts


def run(c):
    pw = c.compat("-pwrap")
    if pw:
        r = dts.reg(pw)[0]
        c.fact("pmic", "pwrap", {"base": hex(r[0])}, c.src(pw), [hex(r[0])[2:].zfill(8)])
    parts = sorted({k.replace("CONFIG_MTK_PMIC_CHIP_", "") for k, v in c.sym.items() if k.startswith("CONFIG_MTK_PMIC_CHIP_") and v == 1})
    pm = c.compat("-pmic")
    if pm or parts:
        c.fact("pmic", "chip", {"defconfig": parts, "dts": pm.str("compatible") if pm else None},
               "defconfig CONFIG_MTK_PMIC_CHIP_*; dts " + (c.src(pm) if pm else "-"),
               [p.lower() for p in parts])
    other = sorted({n.str("compatible").split(",")[-1] for n in c.tree.root.walk() if n.str("compatible") and
                    re.search(r"mt63(66|58|59|57)|mt6370|mt6371|mt6360|rt5133|mt6315", n.str("compatible"))})
    if other:
        c.fact("pmic", "parts_named", other, "dts compatibles; the exact PMIC is read from its hardware id on the phone")
    rails = []
    for n in c.tree.root.walk():
        if n.has("regulator-name") and n.has("regulator-min-microvolt"):
            rails.append({"name": n.str("regulator-name"), "min_uv": n.ints("regulator-min-microvolt")[0],
                          "max_uv": (n.ints("regulator-max-microvolt") or [0])[0]})
    if rails:
        c.fact("pmic", "rails", sorted(rails, key=lambda r: r["name"]), "dts regulator nodes (names and ranges only)")
    c.probe("pmic", "adb shell su -c 'cat /sys/kernel/debug/regulator/regulator_summary'", "rails and values Android runs with")
    for key, sub in (("gauge", "gauge"), ("battery", "battery"), ("charger", "charger"), ("chargerpump", "pump")):
        n = c.compat(sub)
        if n:
            c.fact("battery", key, n.str("compatible"), c.src(n))
    for n in c.tree.root.walk():
        if n.has("bat_type") or n.has("battery-capacity") or n.has("design_capacity"):
            c.fact("battery", "capacity_prop", {k: n.ints(k) for k in ("battery-capacity", "design_capacity") if n.has(k)}, c.src(n))
            break
    chg = [k[7:] for k, v in c.sym.items() if v == 1 and re.match(r"CONFIG_(MT6370_PMU_CHARGER|CHARGER_\w+|MTK_.*CHARGER\w*)$", k)]
    if chg:
        c.fact("battery", "charger_drivers_on", sorted(chg), "defconfig")
    c.probe("battery", "adb shell su -c 'cat /sys/class/power_supply/battery/uevent'", "capacity, technology, voltage, charge counter")
    th = c.compat("therm_ctrl") or c.compat("lvts")
    if th:
        r = dts.reg(th)[0]
        c.fact("thermal", "controller", {"compat": th.str("compatible"), "base": hex(r[0])}, c.src(th), [hex(r[0])[2:].zfill(8)])
    lv = [n for n in c.tree.root.walk() if "lvts" in n.name or any("lvts" in x for x in n.strs("compatible"))]
    if lv:
        c.fact("thermal", "lvts_nodes", [n.name for n in lv][:8], "dts")
    zones = [n.name for n in c.tree.root.walk() if n.parent and n.parent.name == "thermal-zones"]
    if zones:
        c.fact("thermal", "zones", zones, "dts: /thermal-zones")
    c.probe("thermal", "adb shell su -c 'for z in /sys/class/thermal/thermal_zone*; do echo $z $(cat $z/type) $(cat $z/temp); done'",
            "sensors and temperatures to compare against")
