# 一次 PF 1e 向量化 bug 的复盘：从“加个 if”到“多态注入”

> 背景：我在做一个 PathFinder 1e 跑团辅助 Agent，先把规则书向量化，再让 Agent 基于 chunk 回答问题并给出溯源。 pipeline 在 `pf_data/phase1/vectorization_prep_profession.py` 里。

## 1. 用户的一个问题，扯出一串错标

用户问：

> “元素庇护主/冬女巫/尖笑/斜眼的详细信息分别列举一下。”

我查 `chunks.jsonl` 返回：

- 尖笑（Cackle, Su）→ APG ✔️
- 冬女巫（Winter Witch）→ ISM ✔️
- 冬女巫下面的 `冰魔法`、`冻抚` 等能力 → **APG** ❌
- 元素庇护主 → APG（这里还没暴露问题）

更尴尬的是，我把“邪眼”看成了“斜眼”，回答里写了个不存在的条目。为了圆场，我开始排查女巫相关 chunk 的来源书，结果发现系统性错标：

| 类别 | 错标示例 | 应为 |
|---|---|---|
| 巫术 | 凶兽、嗅童、野嚎等 21 个 | APG → **UM** |
| 变体能力 | 冬女巫的冰魔法、冻抚等 | APG → **ISM** |
| 庇护主 | 盛夏、深秋、寒冬、林地 | APG → **UW** |

## 2. 第一反应：在 `build_chunk()` 里加个 `if class_name == "女巫"`

问题暴露点就在 `build_chunk()`，看起来改动最小。我很快就写了一段硬编码修复：

```python
# 硬编码尝试（后来被废弃）
WITCH_UM_HEX_NAMES = {...}
if class_name == "女巫":
    if cn in WITCH_UM_HEX_NAMES:
        book_abbreviation = "UM"
    if archetype_name == "冬女巫":
        book_abbreviation = "ISM"
```

同时还想改 `split_into_blocks` 去识别 `出自《极限荒野》（Ultimate Wilderness）` 这种纯文本来源标记。

用户及时打断：

> “这违反 K3 设计。策略模式 + 注册表 + 条目表驱动，不写硬编码 `if`。”

## 3. 为什么我会想硬编码？

回头想，三个原因：

1. **路径依赖**：问题恰好出在 `build_chunk()`，顺手就在原地修。
2. **没意识到扩展点已存在**：`FileProcessor` 已经有 `clean()` / `expand()` / `keep()` 等可覆盖钩子，但 `build_chunk()` 还是个模块级函数，职业 Processor 无法注入规则。
3. **时间压力下的“最小改动”错觉**：加一个 `if` 比抽象 Processor 钩子快得多。

## 4. 历史设计约束回顾

这个项目的向量化阶段有一个明确分工：

- **k3（设计 Agent）**：定架构、定约束。
- **k2.7（执行 Agent）**：按约束写代码。

核心约束就一句：

> **策略模式 + 注册表 + 条目表驱动，不写硬编码 `if`。**

原因很现实：PF 1e 有几十个职业、几百个变体、几千个能力。如果每个职业特化都在通用引擎里写 `if class_name == "X"`，代码会迅速腐化成无法维护的意大利面。正确的做法是把职业规则收敛到各自的 `Processor` 子类里。

## 5. 正确方案：把 `build_chunk()` 吸收进 `FileProcessor`

### 5.1 重构模板方法

把模块级 `build_chunk()` 的逻辑迁移到 `FileProcessor.build_chunk()`，并拆出一组可覆盖的子钩子：

```python
class FileProcessor:
    def build_chunk(self, block, deprecated_titles) -> Optional[Chunk]:
        component_type = self.classify_component(...)
        class_name = self.infer_class_name(...)
        archetype_name = self.infer_archetype_name(...)
        master_info = self.get_archetype_master(class_name, title)

        book = self.resolve_source(..., master_info)
        # ...
        feature_subtype = self.infer_feature_subtype(...)
        # ...
        return Chunk(...)
```

子钩子包括：

| 钩子 | 职责 | 谁覆盖 |
|---|---|---|
| `resolve_source` | 推断来源书 | `WitchProcessor` |
| `infer_feature_subtype` | 推断 subtype | 默认逻辑已够用，可扩展 |
| `classify_component` | 判断组件类型 | 默认 |
| `get_archetype_master` | 查变体主表 | 默认 |

### 5.2 用 `WitchProcessor` 注入女巫规则

`create_processor()` 把所有路径含 `女巫` 的文件路由到 `WitchProcessor`：

```python
def create_processor(file_path, rel_path, ctx):
    spec = WITCH_SUPPLEMENT_REGISTRY.get(rel_path.as_posix())
    if "女巫" in rel_path.parts:
        return WitchProcessor(file_path, rel_path, ctx, spec)
    return FileProcessor(file_path, rel_path, ctx)
```

`WitchProcessor` 覆盖 `resolve_source()`，注入三条规则：

```python
class WitchProcessor(FileProcessor):
    def resolve_source(self, ..., master_info):
        book = super().resolve_source(...)
        if class_name != "女巫":
            return book

        # ① UM 巫术覆盖
        if cn in self.ctx["witch_um_hex_names"] and book[2] == "APG":
            return _UM

        # ② 变体能力继承变体来源
        if component_type == "class_feature" and archetype_name and book[2] == "APG":
            arch_master = self.get_archetype_master(class_name, archetype_name)
            if arch_master:
                return arch_master["source_book"], ..., arch_master["book_abbreviation"]

        # ③ 四季/林地庇护主覆盖
        if feature_subtype == "patron" and "四季庇护主" in breadcrumbs_text:
            return _UW

        return book
```

### 5.3 把庇护主奖励法术拆分也迁回 WitchProcessor

原本 `FileProcessor.expand()` 里硬编码判断“庇护主”并调用 `_split_patron_reward_tables()`。现在改成策略注册表：

```python
def _split_patron_reward_tables_strategy(block, ctx):
    if "庇护主" in block_title_or_breadcrumbs:
        return _split_patron_reward_tables(block, ctx["book_lookup"])
    return [block]

class WitchProcessor(FileProcessor):
    EXPAND_STRATEGIES = [_split_patron_reward_tables_strategy]
```

基类 `expand()` 完全通用，只负责遍历 `EXPAND_STRATEGIES`。

### 5.4 识别纯文本来源标记

`detect_book()` 增加对 `出自《书名》（Abbreviation）` 的扫描，让季节女巫这类带纯文本来源标记的 chunk 能直接命中 `UW`：

```python
for m in re.finditer(r"出自《([^《》]+)》(?:[（(]([A-Za-z][A-Za-z0-9'\-\s]*)[）)])?", snippet):
    abbr = (m.group(2) or "").strip().upper()
    if abbr:
        hints.append(abbr)
```

## 6. 验证结果

运行后：

```
493 个规范文件 → 9575 个 chunk
职业数：42，变体数：796
```

- 21 个 UM 巫术不再错标为 APG。
- 冬女巫 8 个能力全部继承为 ISM。
- 盛夏/深秋/寒冬/林地庇护主不再标为 APG。
- 关键变体（振奋乐师、切利亚斯歌姬）识别无回归。

## 7. 反思

1. **“最小改动”不等于“正确改动”**。原地加 `if` 确实改动小，但会破坏架构约束，后续每一个职业都会照葫芦画瓢，最终通用引擎变成一坨特判。
2. **设计文档在跨会话协作中很重要**。K3 的约束如果不是被用户及时提醒，我这一把就污染了。
3. **bug 是架构问题的显影剂**。这个错标问题表面是数据问题，根因是 `build_chunk()` 没有给职业 Processor 留下扩展点。修好架构，修复规则才能优雅落地。

## 8. 关键文件

- `pf_data/phase1/vectorization_prep_profession.py`
- `pf_data/phase1/规则书向量化规则.md`
- `pf_data/phase1/问题与修复记录.md`
- `pf_data/phase1/BLOG_POST_女巫来源书错标复盘.md`

---

*写于 2026-07-20，供 PF 1e Agent 项目复盘与博客发布。*
