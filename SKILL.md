---
name: clash-split-rules
description: Clash / Mihomo「同出口」分流规则（当前 403 条；策略组 LINQI-PROXY / AI-ONLY-Claude；第一条拒绝全部业务 UDP；Claude/Anthropic 及其依赖走 AI-ONLY-Claude）和维护流程：查看、解释某个网站走哪条规则、按成对写法增删规则、校验和统计、导出成 Mihomo 配置片段 / Clash Verge 扩展脚本 / 纯规则列表、比对订阅里的规则是否最新。只要用户提到分流规则、Clash 规则、加规则 / 删规则、某个域名或 IP 走哪个出口、Claude / Anthropic / OpenAI 分流、LINQI-PROXY、AI-ONLY-Claude、同出口规则、扩展脚本、规则条数、订阅规则是不是最新，即使没有点名本技能也要使用。
---

# 同出口分流规则（Clash / Mihomo）

> 免责声明：按现状提供，规则不能保证任何账号不被风控或封禁；一切后果由使用者自负，作者不负责。完整条款见 `DISCLAIMER.md`。

规则来自作者自己的配置（2026-11-16 的 383 条 + 2026-11-23 补的 10 对 Claude 依赖）。**`rules/same_egress_rules.txt`
是唯一的权威版本**，别处用到的都是从这里复制或导出的。本技能只管规则本身，不涉及服务器部署。

**和用户沟通一律用简体中文**（选项、总结、提问都用中文）。

## 0. 边界

- **规则原文和顺序不能改**（作者明确要求）。新增只能插入新行；删除、改写、挪动已有的行，必须先用中文说清楚改哪几行、
  会有什么影响，得到用户明确同意。
- 不启动、不打开、不读取、不修改 **Clash Verge**（含它的配置文件和扩展脚本）；导出的扩展脚本交给用户自己粘贴。
  不访问 IP 查询网站，也不为了验证规则去查本机或网络的 IP（所以 `2026.ip138.com`、`my.ip.cn` 两条的效果没有实测）。
- 订阅内容（`clash.yaml`）含节点 UUID / 密钥：只放会话 scratchpad，不贴进聊天，用完删掉。
- 加规则用的域名 / IP 段如果来自网上的帖子或清单，照实告诉用户哪些没核实过归属（2026-11-23 的 34.8.0.0/16 等就是这样）。
- 本技能的仓库是**公开**的：不能往技能文件夹里写真实服务器 IP、端口、订阅地址、节点密钥、代理账号。

## 1. 文件

| 文件 | 作用 |
|---|---|
| `rules/same_egress_rules.txt` | 规则原文，每行一条，`#` 开头为注释（注释不进订阅） |
| `scripts/rules.py` | 校验 / 统计 / 导出 / 比对，只用 Python 标准库 |
| `references/rules-design.md` | 规则怎么设计的、每段的去向、历史、统计 |

下文 `<RULES>` = 本技能目录，`<SCRATCH>` = 会话 scratchpad。命令写的是 macOS / Linux（`python3`）；Windows 用 `python`，
先 `$env:PYTHONIOENCODING = "utf-8"`，路径换成 `\`。

## 2. 规则一句话概览（细节见 references/rules-design.md）

从上到下匹配：第 1 条 `NETWORK,UDP,REJECT` 拒绝所有业务 UDP → Claude / Anthropic 域名、`160.79.104.0/21` 和 Claude 依赖
（Intercom、Stripe 风控、FCM、hCaptcha、Persona / Yoti 等）→ `AI-ONLY-Claude`（禁用 UDP）→ OpenAI、遥测（sentry、datadog、
statsig、intercom）、NTP 授时 → `LINQI-PROXY` → `2026.ip138.com`、`my.ip.cn` → `LINQI-PROXY` → 本机/局域网、`.cn`、
`GEOSITE,cn`、`GEOIP,CN` → 直连 → `MATCH,LINQI-PROXY`。每条代理规则后紧跟一条同条件 `REJECT`（前一条已命中，实际不生效，
原样保留）。三个策略组：`<出口>`（select，节点列表，第一个是默认）、`LINQI-PROXY` 和 `AI-ONLY-Claude` 都只指向 `<出口>`，
所以全部代理流量走同一个出口。组名 `LINQI-PROXY`、`AI-ONLY-Claude` 被规则引用，**不能改名**。

用户问“某个网站走哪”时：在规则文件里按顺序找第一条能匹配的（`DOMAIN` 全等、`DOMAIN-SUFFIX` 本身或子域、`DOMAIN-KEYWORD`
包含、`IP-CIDR` 落在段内），没有就落到直连段或 `MATCH,LINQI-PROXY`；GEOSITE / GEOIP 靠客户端的数据库，说清楚是推断。

## 3. 改规则

1. **问清楚**（不清楚就用 AskUserQuestion）：哪些域名 / IP、走 `AI-ONLY-Claude`（Claude/Anthropic 及其依赖）还是
   `LINQI-PROXY`（其它要代理的）、整个域名（`DOMAIN-SUFFIX`）还是单个主机（`DOMAIN`）。IP 段用 `IP-CIDR,<段>,<组>,no-resolve`。
2. **先查重**：`grep -n -i '<域名或关键字>' <RULES>/rules/same_egress_rules.txt`。已经被同去向的规则覆盖就告诉用户不用加；
   被另一组的规则覆盖（例如想把 LINQI-PROXY 里的某项挪到 AI-ONLY-Claude），属于改原规则，走第 0 条的确认。
3. **按原写法插入**，每项两行：`<类型>,<值>,<组>[,no-resolve]` 紧跟 `<类型>,<值>,REJECT[,no-resolve]`。位置：
   - `AI-ONLY-Claude`：放在 AI-ONLY-Claude 段末尾，即 `DOMAIN-SUFFIX,sentry.io,LINQI-PROXY` 这一行之前；
   - `LINQI-PROXY`：放在 LINQI-PROXY 段末尾，即 `DOMAIN,2026.ip138.com,LINQI-PROXY` 这一行之前；
   - 一律在直连段（`DOMAIN,localhost,DIRECT` 起）之前，否则 `.cn` / GEOSITE / GEOIP 会先命中。
   - 新的一批前面加一行注释：`# <日期> 补充：<来源/原因>`。
   改文件前先 `cp` 一份到 `<SCRATCH>` 备份。
4. **校验**：`python3 -B <RULES>/scripts/rules.py check`，最后一行必须是 `RULES_OK <条数>`。它检查：第一条是
   `NETWORK,UDP,REJECT`、最后一条是唯一的 `MATCH,LINQI-PROXY`、去向只能是两组 / DIRECT / REJECT、每条代理规则都有配对
   REJECT（ip138 / my.ip.cn 是已知例外）、没有重复、IP 段合法、代理规则不在直连段之后、没有被前面另一组的规则抢先命中。
   有 `ERROR` 就改到没有为止；`NOTE` 里“被前面去向相同的规则覆盖”是无害的。
5. **更新文档**：`references/rules-design.md` 的“历史”和“统计”（直接抄 `check` 输出的 by type / by target），
   本文件 description 和第 2 节里的条数、概览（如果新增了一类去向）、`README.md` 里的条数。
6. **告诉用户**：规则文件改了，不代表客户端已经生效——用到这套规则的订阅、扩展脚本都要重新生成或更新（见第 5 节）。

## 4. 导出（不碰 Clash Verge，文件交给用户）

```bash
python3 -B <RULES>/scripts/rules.py export verge-js --exit-name 代理出口 --out <SCRATCH>/同出口分流-扩展脚本.js
python3 -B <RULES>/scripts/rules.py export yaml --exit-name 代理出口 --nodes '节点A,节点B' [--extra '节点C'] --out <SCRATCH>/rules.yaml
python3 -B <RULES>/scripts/rules.py export list --out <SCRATCH>/rules.txt
```

- **verge-js**：给任意订阅套用这套规则。脚本把订阅里全部节点放进出口组（含 proxy-providers），重建三个组，
  整体替换规则；订阅没有节点时原样返回（不会悄悄改成直连）；重复运行不会叠加。用户在 Clash Verge → 订阅 → 右键 → 扩展脚本
  里自己粘贴。订阅本身已经内置这套规则的，不要再挂。拿到这个脚本的订阅同样会拒绝全部 UDP，交付时说一句。
- **yaml**：`proxy-groups` + `rules`，可以并进任意 Mihomo 配置，也可以填进能自定义 Clash 订阅规则的面板（3x-ui 的
  `subClashRules` 就是这个格式；`rules` 里有 `MATCH` 时会整体替换默认规则）。节点名必须和订阅里的完全一样，第一个是默认。
- **list**：纯规则，一行一条。
- 导出的文件不含任何密钥，可以用 SendUserFile 发给用户（display: attach）。

## 5. 用到别处、比对是否最新

- 规则被复制到别的地方（例如用户自己的服务器订阅、其它技能里的副本）时，那边按那边的流程更新；本技能只负责提供最新规则
  和导出文件。如果本机同时装了用户自己的部署技能，同步到服务器的步骤在那个技能里。
- 比对一份订阅是不是最新：把 Clash 订阅下载到 `<SCRATCH>/clash.yaml`（macOS / Linux：`curl -fsS -o <SCRATCH>/clash.yaml '<订阅地址>'`），
  然后 `python3 -B <RULES>/scripts/rules.py compare <SCRATCH>/clash.yaml` → `SAME_AS_RULES_FILE` 就是最新；
  `DIFFERENT` 会列出缺 / 多的规则和第一处不同。用完删掉 `clash.yaml`。
- 提醒用户在 Clash Verge 里**更新订阅**（用户自己操作）。
- 本技能有 GitHub 仓库时，改动要同步过去（提交、推送由用户决定）。推送前搜一遍，不能带真实服务器 IP、端口、订阅地址、
  节点密钥、代理账号。

## 6. 排错

| 现象 | 原因 / 处理 |
|---|---|
| 视频通话 / 游戏 / QUIC 不通 | 第 1 条 `NETWORK,UDP,REJECT` 有意拒绝全部业务 UDP（规则的设计），不是故障；网页会退回 TCP。用 UDP 做外层传输的代理协议本身不受影响 |
| ip138 / my.ip.cn 打不开 | 这两条把中国 IP 查询站送进代理，如果代理服务器屏蔽了中国站点就会打不开（没有实测） |
| 国内网站全打不开 | 订阅没带这套规则（只有默认 `MATCH`），国内流量也走了代理。拉订阅跑 `compare` 看规则在不在 |
| 新加的规则不生效 | 先跑 `check`（顺序 / 被抢先命中）；再拉订阅跑 `compare` 看订阅是否已更新；最后让用户在 Clash Verge 更新订阅 |
| `compare` 报 rules 是单行格式 | 不是常规的块格式输出，用 `yq '.rules | length' clash.yaml` 之类的 YAML 工具看 |
| 组和规则都对，但 Claude 仍和其它流量同一个出口 | 本来就是这样设计的（同出口）；要让 AI-ONLY-Claude 单独走别的出口，见 references/rules-design.md「以后分出口」 |
