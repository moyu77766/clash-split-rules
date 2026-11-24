# 同出口分流规则：设计、历史与统计

## 历史

- **2026-11-16**：作者整理出 383 条（规则来源 `Claude-Check-Same-Egress.yaml`，最早用 Clash Verge 扩展脚本挂在订阅上）。
  三份导出（纯规则 yaml、完整 yaml、JS 扩展脚本）已逐条比对，完全相同。之后改为直接写进自己服务器生成的 Clash 订阅，
  不再靠扩展脚本。
- **2026-11-23 补 20 条（10 对）**：对照 X 上 @qwerty__cs 的「最全 Claude 分流清单」(2026-11-22)，发现其中 10 项在 383 条里
  没有明确规则、只靠 `MATCH,LINQI-PROXY` 兜底，补进 AI-ONLY-Claude。按原写法每项一条代理 + 一条同条件 REJECT，插在
  `DOMAIN,unpkg.com,REJECT` 之后（原 383 条的内容和相对顺序不变）：
  `DOMAIN-SUFFIX` intercomassets.com、intercom-messenger.com、r.stripe.com、fcmtoken.googleapis.com、hcaptcha.com、
  withpersona.com、yoti.com；`IP-CIDR …,no-resolve` 34.8.0.0/16、153.61.208.0/20、153.61.224.0/22。
  帖子另外 32 项原来就有明确规则（26 项 AI-ONLY-Claude、6 项 LINQI-PROXY，没有改动）；这些域名都不在 MetaCubeX
  `geosite:cn` 里（2026-11-23 核对），不会被直连规则截走。两个 153.61.x 段和 34.8.0.0/16 的归属帖子没给来源，没有核实；
  34.8.0.0/16 是一大段 Google Cloud 地址，因为带 `no-resolve`，只影响直接连这些 IP 的请求。
- **2026-11-24**：规则单独成为本技能并公开（内容没变，仍是 403 条）。

## 策略组

```yaml
proxy-groups:
- {name: <出口>, type: select, proxies: [<主节点>, <备用节点>, ...]}
- {name: LINQI-PROXY, type: select, proxies: [<出口>]}
- {name: AI-ONLY-Claude, type: select, disable-udp: true, proxies: [<出口>]}
rules: [见 rules/same_egress_rules.txt]
```

- `<出口>` 是手动选择组，第一个节点是默认；没有自动切换（原配置的设计）。
- LINQI-PROXY 和 AI-ONLY-Claude 共用 `<出口>` 这一个选择，所以所有代理流量走同一个出口——这就是“同出口”。
- 组名 `LINQI-PROXY`、`AI-ONLY-Claude` 被规则引用，不能改名；`<出口>` 只是显示名。
- 不带 `rule-providers`，也不带 `dns`：只管策略组和规则，DNS 由客户端自己的设置管。
- 嵌进订阅生成器时（例如 3x-ui 的 `subClashRules`），`rules` 里有 `MATCH` 才会整体替换默认规则，所以规则文件最后一条
  必须是 `MATCH`。注释行不进订阅，只改注释不影响已生成的订阅。

## 规则行为

- 从上到下匹配，第一条命中即停。
- 第 1 条 `NETWORK,UDP,REJECT` 拒绝进入规则链的**所有业务 UDP**（QUIC、视频通话、游戏、局域网 UDP 都会被拒，网页会退回
  TCP）。不影响代理协议本身用 UDP 做外层传输（例如 Hysteria2）。
- 每条代理规则后面紧跟一条同条件的 `REJECT`：前一条已经命中，这些 REJECT 实际不会生效，也**不是**代理失败后的兜底。
  原样保留，新增时也照这个写法。
- Claude / Anthropic 相关域名和 `160.79.104.0/21`，以及 2026-11-23 补的 Claude 依赖（Intercom 资源、Stripe 风控、FCM、
  hCaptcha、Persona / Yoti 身份验证和三个 IP 段）→ AI-ONLY-Claude（禁用 UDP）。
- OpenAI、各类遥测（sentry、datadog、statsig、intercom）、全球 NTP 授时域名 → LINQI-PROXY。
- `2026.ip138.com`、`my.ip.cn` → LINQI-PROXY（没有配对 REJECT，`rules.py check` 里列为已知例外）。它们把中国的 IP 查询网站
  送进代理；如果代理服务器屏蔽了中国站点，这两个会打不开。没有实测。
- 本机/局域网（localhost、.local、.lan、私有网段）、`.cn`、`GEOSITE,cn`、`GEOIP,CN` → 直连；其余 `MATCH,LINQI-PROXY`。
- GEOSITE / GEOIP 用客户端自己的分类数据库（Clash Verge 会自动下载），规则不固定数据库版本。

## 统计（`rules.py check` 的输出，改规则后照抄更新）

- 2026-11-24（403 条）：DOMAIN 221、DOMAIN-SUFFIX 157、IP-CIDR 15、DOMAIN-KEYWORD 6、NETWORK / GEOSITE / GEOIP / MATCH 各 1；
  去向 REJECT 195、LINQI-PROXY 145、AI-ONLY-Claude 52、DIRECT 11。规则 sha256（不含注释）
  `0e67b7fbfb551be9e7f152a0054595cd3398a5a4959baf488f0f058e4b559741`。另有 5 条被前面同去向的规则覆盖（多余但无害），
  没有被另一组抢先命中的规则。
- 2026-11-16 原 383 条：DOMAIN-SUFFIX 143、IP-CIDR 9、AI-ONLY-Claude 42、REJECT 185，其余同上。

## 分享时要提醒

带这套规则的订阅或扩展脚本发给别人，对方也会用这套规则，包括“拒绝全部 UDP”（视频通话、部分游戏会不通）。

## 以后分出口（还没做）

现在 LINQI-PROXY 和 AI-ONLY-Claude 是同一个出口，2026-11-23 补的 10 对**当时没有改变出口**；它们的用处是：以后若让
AI-ONLY-Claude 单独走另一个出口（例如固定的住宅 IP），Claude 的依赖也会跟着走同一个 IP。到那时：
- AI-ONLY-Claude 的 `proxies` 改成那个出口的节点（生成策略组的地方要跟着改，`rules.py export` 也要加相应参数）；
- 还要把仍在 LINQI-PROXY 的 intercom.io、intercomcdn.com、sentry、statsigapi.net、datadog、sift 挪到 AI-ONLY-Claude
  ——这是改原规则，按 SKILL.md 第 0 条先征得用户同意，删掉旧的那对、在 AI-ONLY-Claude 段末尾加新的一对。
