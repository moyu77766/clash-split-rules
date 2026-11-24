#!/usr/bin/env python3
"""同出口分流规则工具。只用 Python 标准库，Mac（python3）和 Windows（python）都能直接跑。

  rules.py check                                  校验 + 统计。改完规则必须跑，最后一行是 RULES_OK 才算对
  rules.py export yaml --exit-name 代理出口 --nodes 节点A,节点B [--extra 节点C]
                                                  proxy-groups + rules 的 YAML：可并进任意 Mihomo 配置或订阅生成器
  rules.py export verge-js [--exit-name 代理出口]  Clash Verge 扩展脚本（用户自己粘贴，Claude 不碰 Clash Verge）
  rules.py export list                            纯规则，一行一条
  rules.py compare <clash.yaml>                   订阅里的 rules 是否与规则文件逐条相同，三个策略组是否都在

默认读 ../rules/same_egress_rules.txt；--file 可指定别的文件（例如别处的副本）。
Windows 中文输出乱码时先设 PYTHONIOENCODING=utf-8。
"""
import argparse
import collections
import hashlib
import ipaddress
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.normpath(os.path.join(HERE, "..", "rules", "same_egress_rules.txt"))

PROXY_GROUPS = ("LINQI-PROXY", "AI-ONLY-Claude")  # 规则引用的组名，不能改
TARGETS = set(PROXY_GROUPS) | {"DIRECT", "REJECT"}
KNOWN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-REGEX", "IP-CIDR", "IP-CIDR6",
               "IP-SUFFIX", "IP-ASN", "GEOSITE", "GEOIP", "NETWORK", "DST-PORT", "PROCESS-NAME", "MATCH"}
# 用户原规则里本来就没有配对 REJECT 的两条（中国 IP 查询站，送进代理）
UNPAIRED_OK = {"DOMAIN,2026.ip138.com,LINQI-PROXY", "DOMAIN,my.ip.cn,LINQI-PROXY"}


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def split(rule):
    """-> (type, value, target, options)。MATCH 的 value 为空。"""
    p = [x.strip() for x in rule.split(",")]
    if p[0] == "MATCH":
        return "MATCH", "", (p[1] if len(p) > 1 else ""), tuple(p[2:])
    return p[0], (p[1] if len(p) > 1 else ""), (p[2] if len(p) > 2 else ""), tuple(p[3:])


def cond(rule):
    t, v, _, opts = split(rule)
    return (t, v.lower(), opts)


def rules_digest(rules):
    return hashlib.sha256("\n".join(rules).encode("utf-8")).hexdigest()


def first_match(rules, i):
    """规则 i（域名或 IP 类）前面会先命中同一流量的规则下标，没有返回 None。只判断能静态确定的情况。"""
    t, v, _, _ = split(rules[i])
    v = v.lower()
    for j in range(i):
        tj, vj, tgt_j, _ = split(rules[j])
        if tgt_j == "REJECT":
            continue  # 配对的 REJECT 永远在它的代理规则之后，不会先命中别人
        vj = vj.lower()
        if t in ("DOMAIN", "DOMAIN-SUFFIX"):
            if (tj == "DOMAIN" and t == "DOMAIN" and vj == v) or \
               (tj == "DOMAIN-SUFFIX" and (v == vj or v.endswith("." + vj))) or \
               (tj == "DOMAIN-KEYWORD" and vj in v):
                return j
        elif t in ("IP-CIDR", "IP-CIDR6") and tj in ("IP-CIDR", "IP-CIDR6"):
            try:
                a, b = ipaddress.ip_network(v, strict=False), ipaddress.ip_network(vj, strict=False)
            except ValueError:
                continue
            if a.version == b.version and a.subnet_of(b):
                return j
    return None


def cmd_check(args):
    rules = load(args.file)
    errors, warns, notes = [], [], []
    print(f"file: {args.file}")
    if not rules:
        print("RULES_PROBLEM: 文件里没有规则")
        return 1

    seen = collections.Counter(rules)
    for r, n in seen.items():
        if n > 1:
            errors.append(f"整行重复 {n} 次: {r}")

    first_direct = None
    for i, r in enumerate(rules):
        t, v, tgt, opts = split(r)
        where = f"第 {i + 1} 条 {r}"
        if t not in KNOWN_TYPES:
            errors.append(f"{where}: 不认识的规则类型 {t}")
        if t != "MATCH" and not v:
            errors.append(f"{where}: 缺少匹配值")
        if tgt not in TARGETS:
            errors.append(f"{where}: 去向必须是 {sorted(TARGETS)} 之一")
        if any(o != "no-resolve" for o in opts):
            errors.append(f"{where}: 只允许附加 no-resolve")
        if t in ("IP-CIDR", "IP-CIDR6"):
            try:
                ipaddress.ip_network(v, strict=True)
            except ValueError as e:
                errors.append(f"{where}: IP 段写错了（{e}）")
            if "no-resolve" not in opts:
                warns.append(f"{where}: IP 规则没带 no-resolve，会让客户端先做 DNS 解析")
        if t in ("DOMAIN", "DOMAIN-SUFFIX") and (v != v.strip(".") or " " in v or "/" in v or ":" in v):
            errors.append(f"{where}: 域名格式不对（不要带协议、路径、端口、首尾点）")
        if tgt == "DIRECT" and first_direct is None and t != "MATCH":
            first_direct = i
        if tgt in PROXY_GROUPS and t != "MATCH" and first_direct is not None:
            errors.append(f"{where}: 代理规则放在了直连段（第 {first_direct + 1} 条起）后面，"
                          ".cn / GEOSITE,cn / GEOIP,CN 可能先命中；挪到直连段之前")

    if rules[0] != "NETWORK,UDP,REJECT":
        errors.append(f"第 1 条必须是 NETWORK,UDP,REJECT（用户的设计），现在是 {rules[0]}")
    matches = [i for i, r in enumerate(rules) if r.startswith("MATCH,")]
    if matches != [len(rules) - 1]:
        errors.append("MATCH 必须有且只有一条，并且在最后（3x-ui 只有看到 MATCH 才会整体替换默认规则）")
    elif rules[-1] != "MATCH,LINQI-PROXY":
        errors.append(f"最后一条应为 MATCH,LINQI-PROXY，现在是 {rules[-1]}")

    # 成对写法：每条代理规则后面紧跟同条件 REJECT；每条 REJECT（第 1 条除外）前面是它的代理规则
    for i, r in enumerate(rules):
        t, _, tgt, _ = split(r)
        if t == "MATCH":
            continue
        if tgt in PROXY_GROUPS:
            nxt = rules[i + 1] if i + 1 < len(rules) else ""
            paired = nxt and split(nxt)[2] == "REJECT" and cond(nxt) == cond(r)
            if not paired:
                (notes if r in UNPAIRED_OK else errors).append(
                    f"第 {i + 1} 条 {r}: 后面没有同条件 REJECT" + ("（用户原规则如此，已知例外）" if r in UNPAIRED_OK else ""))
        elif tgt == "REJECT" and i > 0:
            prev = rules[i - 1]
            if not (split(prev)[2] in PROXY_GROUPS and cond(prev) == cond(r)):
                errors.append(f"第 {i + 1} 条 {r}: 单独的 REJECT，前面不是同条件的代理规则")

    # 同一个条件写了两次（去向不同时第二条永远不生效）
    by_cond = collections.defaultdict(list)
    for i, r in enumerate(rules):
        if split(r)[2] != "REJECT":
            by_cond[cond(r)].append(i)
    for c, idx in by_cond.items():
        if len(idx) > 1:
            errors.append("同一条件写了多次: " + "、".join(f"第 {i + 1} 条 {rules[i]}" for i in idx))

    # 被前面的规则抢先命中
    redundant = 0
    for i, r in enumerate(rules):
        t, _, tgt, _ = split(r)
        if tgt == "REJECT" or t not in ("DOMAIN", "DOMAIN-SUFFIX", "IP-CIDR", "IP-CIDR6"):
            continue
        j = first_match(rules, i)
        if j is None or cond(rules[j]) == cond(r):
            continue
        if split(rules[j])[2] == tgt:
            redundant += 1
        else:
            errors.append(f"第 {i + 1} 条 {r} 永远不会生效：第 {j + 1} 条 {rules[j]} 会先命中，走 {split(rules[j])[2]}")
    if redundant:
        notes.append(f"{redundant} 条被前面去向相同的规则覆盖（多余但无害）")

    types = collections.Counter(split(r)[0] for r in rules)
    targets = collections.Counter(split(r)[2] for r in rules)
    print(f"rules: {len(rules)}    first: {rules[0]}    last: {rules[-1]}")
    print("by type:   " + "  ".join(f"{k} {v}" for k, v in types.most_common()))
    print("by target: " + "  ".join(f"{k} {v}" for k, v in targets.most_common()))
    print(f"rules sha256 (不含注释): {rules_digest(rules)}")
    for n in notes:
        print("NOTE  " + n)
    for w in warns:
        print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)
    print(f"RULES_OK {len(rules)}" if not errors else f"RULES_PROBLEM ({len(errors)} 个错误)")
    return 0 if not errors else 1


def yaml_str(s):
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.,/:_\-]*", s) and s.lower() not in ("true", "false", "null", "yes", "no", "on", "off", "y", "n"):
        return s
    return json.dumps(s, ensure_ascii=False)  # JSON 字符串就是合法的 YAML 双引号字符串


def groups(exit_name, members):
    return [
        {"name": exit_name, "type": "select", "proxies": members},
        {"name": PROXY_GROUPS[0], "type": "select", "proxies": [exit_name]},
        {"name": PROXY_GROUPS[1], "type": "select", "disable-udp": True, "proxies": [exit_name]},
    ]


def cmd_export(args):
    rules = load(args.file)
    if args.format == "list":
        out = "\n".join(rules) + "\n"
    elif args.format == "yaml":
        members = [x.strip() for x in (args.nodes or "").split(",") if x.strip()] + \
                  [x.strip() for x in (args.extra or "").split(",") if x.strip()]
        if not members:
            sys.exit("export yaml 需要 --nodes（出口组里的节点名，逗号分隔；第一个是默认选择）")
        if len(set(members)) != len(members):
            sys.exit("节点名有重复")
        lines = ["proxy-groups:"]
        for g in groups(args.exit_name, members):
            lines.append(f"- name: {yaml_str(g['name'])}")
            lines.append(f"  type: {g['type']}")
            if g.get("disable-udp"):
                lines.append("  disable-udp: true")
            lines.append("  proxies:")
            lines += [f"  - {yaml_str(p)}" for p in g["proxies"]]
        lines.append("rules:")
        lines += [f"- {yaml_str(r)}" for r in rules]
        out = "\n".join(lines) + "\n"
    else:  # verge-js
        body = ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rules)
        out = f"""// 同出口分流规则（{len(rules)} 条），由 clash-split-rules 技能生成：rules.py export verge-js
// 规则 sha256（不含注释）：{rules_digest(rules)}
// 用法：Clash Verge → 订阅 → 右键这个订阅 → 扩展脚本，整段替换后保存，再更新订阅。
// 作用：新建「{args.exit_name}」（订阅里的全部节点，手动选，默认第一个）、LINQI-PROXY、AI-ONLY-Claude（禁用 UDP）
// 三个策略组，并用这套规则整体替换订阅自带的规则。第 1 条拒绝全部业务 UDP（视频通话、部分游戏会不通）。
// 订阅本身已经内置这套规则的，不要再挂本脚本。
const EXIT = {json.dumps(args.exit_name, ensure_ascii=False)};
const RULES = [
{body}
];

function main(config, profileName) {{
  const names = (config.proxies || []).map((p) => p.name);
  const providers = Object.keys(config["proxy-providers"] || {{}});
  if (names.length === 0 && providers.length === 0) return config; // 没有节点就原样返回，不改成直连
  const exit = {{ name: EXIT, type: "select" }};
  if (names.length) exit.proxies = names;
  if (providers.length) exit.use = providers;
  const mine = new Set([EXIT, "LINQI-PROXY", "AI-ONLY-Claude"]);
  const others = (config["proxy-groups"] || []).filter((g) => !mine.has(g.name));
  config["proxy-groups"] = [
    exit,
    {{ name: "LINQI-PROXY", type: "select", proxies: [EXIT] }},
    {{ name: "AI-ONLY-Claude", type: "select", "disable-udp": true, proxies: [EXIT] }},
    ...others,
  ];
  config.rules = RULES.slice();
  return config;
}}
"""
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        print(f"wrote {args.out} ({len(rules)} rules)")
    else:
        sys.stdout.write(out)
    return 0


def unquote(s):
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return json.loads(s)
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1].replace("''", "'")
    return s


def yaml_rules(text):
    """从订阅 YAML 里取出顶层 rules 列表（3x-ui / Mihomo 生成的块格式：每行 `- 规则`）。"""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"^rules:\s*(.*)$", l)
        if not m:
            continue
        if m.group(1).strip():
            sys.exit("rules 写成了单行格式，本工具只认块格式（每行 `- 规则`）；请用 yq 等 YAML 工具查看")
        out = []
        for l2 in lines[i + 1:]:
            if not l2.strip() or l2.lstrip().startswith("#"):
                continue
            m2 = re.match(r"^\s*-\s+(.*?)\s*$", l2)
            if m2:
                out.append(unquote(m2.group(1)))
            elif not l2[0].isspace():
                break
        return out
    return None


def cmd_compare(args):
    with open(args.clash_yaml, encoding="utf-8-sig") as f:
        text = f.read()
    want = load(args.file)
    got = yaml_rules(text)
    if got is None:
        print("COMPARE_PROBLEM: 订阅里找不到顶层 rules:")
        return 1
    got = [g.strip() for g in got]
    ok = got == want
    print(f"subscription rules: {len(got)}    rules file: {len(want)}")
    if not ok:
        n = next((i for i in range(min(len(got), len(want))) if got[i] != want[i]), min(len(got), len(want)))
        print(f"第一处不同在第 {n + 1} 条：订阅 = {got[n] if n < len(got) else '(没有)'}    文件 = {want[n] if n < len(want) else '(没有)'}")
        missing = [r for r in want if r not in set(got)]
        extra = [r for r in got if r not in set(want)]
        print(f"订阅里缺 {len(missing)} 条" + (": " + "; ".join(missing[:10]) if missing else ""))
        print(f"订阅里多 {len(extra)} 条" + (": " + "; ".join(extra[:10]) if extra else ""))
    for g in PROXY_GROUPS:
        has = re.search(r"name:\s*[\"']?" + re.escape(g) + r"[\"']?\s*[,}\n]", text) is not None
        print(f"group {g}: {'present' if has else 'MISSING'}")
        ok = ok and has
    print("SAME_AS_RULES_FILE" if ok else "DIFFERENT")
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description="同出口分流规则工具")
    p.add_argument("--file", default=RULES_FILE, help="规则文件（默认本技能 rules/same_egress_rules.txt）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    e = sub.add_parser("export")
    e.add_argument("format", choices=["yaml", "verge-js", "list"])
    e.add_argument("--exit-name", default="代理出口", help="出口策略组的显示名，例如 代理出口")
    e.add_argument("--nodes", help="yaml：出口组里的主节点，逗号分隔，第一个是默认")
    e.add_argument("--extra", help="yaml：追加在出口组末尾的出口节点（住宅 IP 等），逗号分隔")
    e.add_argument("--out", help="写到文件（UTF-8、LF）；不给就打印")
    c = sub.add_parser("compare")
    c.add_argument("clash_yaml")
    args = p.parse_args()
    return {"check": cmd_check, "export": cmd_export, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
