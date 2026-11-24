# CHANGELOG

本项目遵循语义化版本。公开仓（github.com/ytche/pf-agent）为快照式发布，历史不连通，版本变更以本文件为准。

## [0.4.0] - 2026-11-19

**v1.0.0 前的最终候选版（release candidate）。** 自 0.3.1 以来完成一期批 A/批 B 收尾、数据冻结与发布链加固；本版不引入新功能，作为 v1.0.0 的冻结基线。除发布阻断问题外，后续只做版本号与发布说明变更。

### 新增

- **目录清单查询（F-008）**：新增四模块目录清单查询服务与 `listByToc` 工具，清单补 `toc_path` 与导出统计
- **语义重排（F-016）**：向量召回后经 DeepSeek listwise 重排，50 候选取 15；关闭 thinking 后单次约 3.4 秒，超时/失败/非法输出回退既有排序；请求级来源数量与字节护栏
- **用量与费用（F-009）**：逐次 LLM 调用用量落库、费用预测接口与前端用量页（按权限过滤）
- **引用抽取（F-017）**：条目引用离线抽取器与人工核对明细，为后续引用链治理提供基线
- **发布数据校验器**：新增 `scripts/validate_release_data.py`，打包前校验 8 个向量库与 chunks 产物条数/chunk_id 集合、1024 维 embedding、法术 `tocPath`、背景特性 `trait_type`、阿斯托莫伊人目标条目中英文字段，并核对 7 份清单
- **发布脚本加固**：`scripts/release_public_snapshot.sh` 先校验再打包，失败即停止；校验与打包共用 `collect_release_files()` 的同一份文件清单，zip 先写临时文件再原子替换，失败不覆盖已有包；数据包固定为 8 个向量库 + 8 份 chunks + `output/<模块>/` 下 7 份清单（含 `rule_tables.json`→规则），输出 zip 文件数、大小与 SHA-256
- **公开内容门禁与发布审计**：新增 `scripts/release_public_guard.py`，公开仓提交前硬校验实际 `.env`、`.kimi-code/`、过程文档、`.DS_Store`、构建垃圾、密钥文件与私钥/令牌内容；新增 `scripts/release_audit.py`，自动生成 `release-audit-v<版本>.json`（私有/公开 commit、逐文件 SHA-256、8 模块条数、7 清单统计、验收报告路径、外发状态），并把 zip/说明/审计转存到 `RELEASE_ARCHIVE_DIR`（默认 `~/.pf_agent_release/v<版本>`，0644），同版本不同 SHA 拒绝覆盖

### 修复与数据

- **KN-250 法术目录元数据**：补齐 17 个 Spell 聚合 doc 的 URL 解码映射与专用目录回填，法术 chunks 的 `chm_toc_path` 空值 2125→**0**/4202；`spell_lists.json` toc 非空 285→**10007**/10068（余 61 条既有 `join_failed`）；`SpellChunkMapper` 改为真实目录优先
- **AKN-028 种族特性过滤**：`race_name/race_name_en` 扁平化入向量 metadata，`searchByMetadata` 支持 `raceName`/`raceNameEn` 过滤；默认书黑名单清空，未知来源继续保留；阿斯托莫伊人八项种族特性可按独立 chunk 枚举
- **AKN-023 章节展开与耗时优化**：标题型父 chunk 按 `doc_id + tocPath` 展开 2~10 条小章节，大章节/capped 保守回退并明示未返回范围；`getEntryById` 支持同模块批量取文；真实三轮八项清规完整 3/3，端到端均值 33.03→25.96 秒
- **KN-148 背景特性收尾**：扩展书补标 61 条 `trait_type`，剩余 154 条主条目空值按决策保留；空类型在普通查询不降权、类型提问降权 0.05；正式 trait 库由 `TraitDataLoader` 重灌 1222 条
- **批 A/B 其余收口**：KN-096 专长亚产能归零（feat chunks 6011）、KN-097 Prepare 勘探基线 188 文件重建、KN-120 阿斯托莫伊人结构修正、KN-140 trait source 白名单 45 条、KN-201 跨模块可达性复核；AKN-021 提示文案、AKN-022 字段命名、F-023 管理后台入口与双入口 E2E
- **预构建包完整安装**：8 份 `chunks.jsonl` 随包发布，修复干净环境条目名索引为空；Compose 挂载完整 `output/`，修复 6 个清单/表格直查服务因文件未挂载而降级
- **引用异常防线**：非法自由 ID 不再导致检索证据被清空；无合法逐句引用时显式降级并返回 `citationDegraded`，保留链接与代码段；武僧清规显式批量取文复用小章节展开
- **重复评测**：`qa/evaluate.py` 支持 `--repetitions N`，保留逐次结果并报告逐题通过率、最差分、波动与引用降级次数
- **发布回归韧性（AKN-032/033）**：`[citation:#N]` 与 `(#N)` 统一为合法数字引用；空回答最多一次无工具重试，模型网络错误最多一次重试；新工具轮增加 60 秒时间预算；`resolveEntry` 支持模块消歧并在同名索引摘要与正文并存时优先正文，恢复药水/卷轴制作题稳定溯源

### 发布说明

- **数据包**：23 个文件 = 8 个 `vector_store_*.json`（classes 14060 / equipment 5342 / feats 6011 / races 3663 / rules 7499 / skills 556 / spells 4202 / traits 1222） + `output/<模块>/` 下 8 份 chunks 与 7 份清单（装备/专长/种族/职业表/法术清单/法术 union/规则表 612 张）
- **前置条件**：DeepSeek Chat API key（`DEEPSEEK_PF_API`）；本机 Ollama `bge-m3`（1024 维，查询与建库必须同模型）；PostgreSQL 16（默认持久化，`PF_CHAT_MEMORY=memory` 可回退纯内存）
- **升级重灌**：种族（AKN-028）、背景特性（KN-148）、法术（KN-250）三个向量库的消费字段/目录已变化，旧库不会被自动补写，升级后必须按 `docs/DEPLOYMENT.md` 第六节由对应 DataLoader 全量重灌；本版同时将 classes/feats 正式库对齐到当前 chunks
- **版权与使用边界**：代码采用 Anti-996 License；Pathfinder 1e 规则文本按 Paizo 社区使用政策（CUP）非商业使用，含第三方社区中文翻译著作权层，仅供个人学习与社区非商业用途，本仓库不收取任何使用费用（详见 `NOTICE.md`）

### 已知边界

- `spell_lists.json` 仍有 **61 条**既有 `join_failed` 条目无目录（占比 61/10068），不影响法术正文检索与其余 10007 条目录命中
- 背景特性 **215 条**空 `trait_type`（主条目 154、intro 61）为已拍板保留口径，不补标、不剔除；按类型精确枚举这些条目仍缺少结构化证据
- 规则表清单以 **612 张**为冻结基线，低于基线会阻断发布打包
- 职业 chunks 存在 **102 个历史重复 chunk_id（151 行重复，31 组书名归属冲突）**：会占用检索候选位，来源书名可能受召回顺序影响；该问题在 0.3.1 已存在，不是本次重灌回退，`SourceCollector` 按 chunk_id 去重后来源列表不重复，列入既有数据债，不阻断候选版
- `easy-13` 黑莲汁提问可能引用同页语义等价的毒药行或通用规则而非评测指定 chunk；完整回归保留该题为溯源 0，不以内容判断替代来源锚点评分
- macOS 若开启系统级 SOCKS 代理，JDK 会自动继承 `socksProxyHost`，可能使 JDBC 连接 `127.0.0.1` 失败；本地验证可在 JVM 增加 `-DsocksNonProxyHosts=*` 绕过，Linux/Docker 部署不受影响

### 质量基线

- 数据：`build all --force` 15/15，`build check` 15/15，pytest **2127 passed**
- Java：`mvn -B test` **1081 项，0 失败 / 0 错误 / 0 skipped**
- 前端：Vitest **51 passed**；生产构建通过；Playwright E2E **17 passed**；全栈 E2E **5 passed**
- 发布门禁：真实数据校验 **23 文件**（8 store + 8 chunks + 7 清单）通过；classes/feats 真实 DeepSeek 检索 4 问全部命中正确来源、`gapReported=false`
- 最终干净环境：本地与 Compose 均直接加载 8 库、8 chunks 与全部清单，`EntryResolver` 42404 条目；真实 56 题溯源 **55/56**、诚实 **56/56**、结构 **3.00**、0 error / 0 404、引用降级 **0**；唯一失败为 `easy-13` 的来源锚点选择

## [0.3.1] - 2026-11-12

公开快照清理，无功能变更（运行代码与 0.3.0 相同）。

- 公开快照不再包含内部过程文档：`docs/design/`、`docs/handover/`、`docs/superpowers/`、`docs/test-reports/`、`docs/templates/`、`docs/WORKFLOW.md` 及各登记/索引文档；仅保留 `docs/DEPLOYMENT.md`
- 公开快照移除本地 agent 配置目录 `.kimi-code/`
- `scripts/release_public_snapshot.sh` 纳入数据文件打包（8 个向量库 + `lists/` 6 份清单），并固化上述公开口径
- README 同步数据包清单说明，移除对已剔除过程文档的引用

## [0.3.0] - 2026-11-12

自 0.2.0（2026-09-19）以来的变更。本版含前端 SPA 改版、管理后台、宽查询收窄门禁，以及一批数据与检索修复。

### 新增

- **前端 SPA 改版（F-020 / F-022）**：Vue 单页应用与前端构建链；统一 `ConversationStore` 会话后端、V7 引用快照与会话 API；登录三态；来源默认 3 张紧凑卡片、展开全部与上标定位
- **宽查询收窄门禁（F-026）**：`query_gate_event` V6 事件持久化（JDBC）；首次宽查询先返回收窄建议与示例，用户确认后按指纹放行；同 requestId 重试、regenerate、并发旧请求与模型自我试探不得放行（AKN-024 / AKN-027 闭环）
- **管理后台（F-023）**：注册开关与用户管理，后端鉴权 + 管理页；最后一名 admin 自保护
- **遥测入库（F-021）**：问答遥测写 PostgreSQL，含迁移与 jsonb 回归护栏
- **法术列表去重（F-025）**：union 1.1 同职业环级保守键折叠（女巫 1 环 205→165）；Java 侧消费折叠清单并保留畸形数据降级
- **引用治理**：sources 仅保留被正文 `[#N]` 实际引用的条目并重编号（cited-only）；全角与混用引用标记统一归一为半角（F-014）
- **装备清单（AKN-025）**：2681→4319 条，新增 `price_gp`，支持价格排序与区间过滤；力量法杖 235,000 gp 固定契约
- **职业规则版本**：职业根目录 7 页纳入并标注 `rule_version` 与 PFS 来源，职业库重灌 14,060 条（KN108）
- **耗时可观测（AKN-023）**：请求级总耗时、LLM 端到端耗时与次数、工具耗时落盘
- **评测与规范**：问题归因与数据版本闭环规范及验收模板（F-012）

### 修复

- 诚实性判分改为“负例优先”：无来源时交 LLM 复核，LLM 失败记待复核而非 0 分（AKN-026）
- 展示层标题兜底：空标题取正文首个有效行，去尾中英文冒号，超长截断（F-002 / KN-204 / KN-219）
- 修复 `searchByMetadata` 工具 schema 悬空 `$ref` 导致 DeepSeek 400
- 删除法术元数据重放第二写路径并加 fail-fast 闸口，防止误用（DVG-001）
- 构建忽略 `.DS_Store`；保留职业根页标题锚点块；标题兜底改用 KN207 清洗后的正文

### 质量基线

- Java 单测 842 通过 / 0 失败 / 16 跳过；数据侧 pytest 1914 通过；前端 43 通过；QA 47 通过
- 评测：53 题全量 溯源 52/53、诚实 53/53、结构 3.00；56 题扩展集 溯源 54/56、诚实 55/56、结构 2.96，0 error / 0 404

## [0.2.0] - 2026-09-19

自 0.1.0（一期公开基线，2026-09-14）以来的变更。

### 新增

- **账户与持久化（SP7）**：注册/登录（JWT）+ PostgreSQL 默认持久化，会话跨重启保留；匿名配额与限频保持可配
- **检索工具增强（SP8）**：
  - `getEntryById`：按条目 ID 取完整原文（解决长条目截断漏规则）
  - `searchByMetadata` 增强：参数对象化，支持 or 组合、范围比较、排序与分页
  - `listDataGaps`：数据缺口看板，避免重复报告
  - 条目引用链 Layer 0：`resolveEntry` / `getEntryLinks`，全模块条目名索引与结构化引用链
  - `keywordSearch` v1：title/alias 子串匹配，补语义检索的精确名词盲区
- **J4 book 过滤落地**：`BookFilter` 全局来源书过滤（黑/白名单双模式，配置驱动，默认黑名单剔 `?`）
- **数据产物可复现构建链**：`build_manifest.json` + `vectorizer/build.py`（status/build/check/--force）+ `build_state.json` 指纹入库，数据产物可审计可复现

### 修复

- **数据治理（D1+KN226+trait）**：专长/规则/背景特性三模块 book 字段中文脏值清零；规则模块「怪物」843 条来源书失真修复（逐文件归书 B1/CRB/MC）；KN229 英文书名订正；三向量库全量重灌对齐
- **健壮性**：embedding 客户端增加连接/读超时（`pf.embedding.connect-timeout`/`read-timeout`），Ollama 僵死时超时降级而非悬挂拖垮连接池（AKN-010）；Ollama embedding 上下文/批大小放开至 8192（AKN-012，修复稠密中文长 chunk 400 报错）

### 质量基线

- 评测集 53/53 满分（溯源/诚实/结构三指标）；Java 单测 400 全绿；数据侧 pytest 1400+ 全绿

## [0.1.0] - 2026-09-14

一期公开基线（SP1~SP6）：规则问答 Agent 主链路（8 模块向量库检索 + 溯源引用）、会话持久化基础设施、限频与匿名配额、职业法术列表预整理、论文式上标来源标注、embedding 双通道（本地 Ollama / 云 API）、开源化工程（LICENSE/NOTICE/模板）。
