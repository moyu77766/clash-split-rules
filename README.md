# clash-split-rules

Clash / Mihomo「同出口」分流规则（403 条），附校验、导出、比对工具。也是一个 Claude 技能（Skill），装上后可以直接用中文让 Claude
查规则、加规则、导出配置。

> ⚠️ **使用前请先阅读 [免责声明](DISCLAIMER.md)。** 按现状提供；规则不能保证任何账号不被风控或封禁，一切后果由使用者自负，作者不负责。

## 规则是什么样的

规则原文：[`rules/same_egress_rules.txt`](rules/same_egress_rules.txt)，从上到下匹配：

1. `NETWORK,UDP,REJECT`：拒绝全部业务 UDP（QUIC、视频通话、部分游戏会不通，网页会自动退回 TCP）。
2. Claude / Anthropic 域名、`160.79.104.0/21` 和 Claude 依赖（Intercom、Stripe 风控、FCM、hCaptcha、Persona / Yoti 等）→ `AI-ONLY-Claude`（禁用 UDP）。
3. OpenAI、遥测（sentry、datadog、statsig、intercom）、NTP 授时 → `LINQI-PROXY`。
4. 本机 / 局域网、`.cn`、`GEOSITE,cn`、`GEOIP,CN` → 直连。
5. 其余 → `MATCH,LINQI-PROXY`。

需要三个策略组：一个出口组（手动选节点）；`LINQI-PROXY` 和 `AI-ONLY-Claude` 都只指向这个出口组，所以全部代理流量走**同一个出口**。
组名 `LINQI-PROXY`、`AI-ONLY-Claude` 被规则引用，不能改名。每条代理规则后面跟着一条同条件的 `REJECT`，它不会生效，原样保留。
详细设计和统计见 [`references/rules-design.md`](references/rules-design.md)。

## 怎么用

工具只依赖 Python 3 标准库（Windows 用 `python` 代替 `python3`）。

校验规则文件（改完规则必须跑，最后一行是 `RULES_OK` 才对）：

```bash
python3 scripts/rules.py check
```

导出成 Clash Verge 扩展脚本：把订阅里的全部节点放进出口组，再用这套规则整体替换订阅自带的规则。在 Clash Verge →
订阅 → 右键 → 扩展脚本里粘贴：

```bash
python3 scripts/rules.py export verge-js --out 同出口分流.js
```

导出成 Mihomo 配置片段（`proxy-groups` + `rules`），节点名要和你的订阅里完全一致，第一个是默认：

```bash
python3 scripts/rules.py export yaml --exit-name 代理出口 --nodes 节点A,节点B --out rules.yaml
```

检查一份 Clash 订阅里的规则是不是和规则文件一模一样：

```bash
python3 scripts/rules.py compare clash.yaml
```

## 作为 Claude 技能安装

- **Claude Code**：把整个仓库文件夹复制到 `~/.claude/skills/clash-split-rules/`。
- **Claude 应用**：把仓库文件夹打包成 zip，按应用里上传自定义技能的方式添加。

## 说明

- 部分规则参考了公开资料，出处见规则文件里的注释；IP 段的归属没有逐一核实。
- 不要把你自己的服务器地址、订阅地址、节点密钥提交到这个仓库或它的分支。

## 许可

[MIT](LICENSE)。使用即表示同意 [免责声明](DISCLAIMER.md)。
