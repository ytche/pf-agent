"""formats/normalize_common.py — 类目无关的 Markdown 形态归一公共层

从 formats/feat.py 抽取（2026-08-04 种族模块开工，第二使用方出现，按
「禁止 copy 模板扩展」原则抽公共层）。标签集感知函数以参数传入——标签集
是类目特有知识（专长：先决条件/专长效果；种族：体貌描述/属性调整）。

搬移后行为零变化（feat.py 557 测试回归验证）；feat.py 与 race.py 共同引用。
"""

import re


def _is_title_case_en(en: str) -> bool:
    """英文名是否专有名词形态（Title Case）：首字母大写且含小写字母。

    'Deep breath'/'Favor of the empress of torrents' → True（真专长名）；
    'APG'/'CR'（全大写缩写）、'tangible object'/'acid'（小写描述）→ False。
    """
    en = en.strip()
    return bool(en) and en[0].isupper() and any(ch.islower() for ch in en)

def _is_multiword_en(en: str) -> bool:
    """英文名是否多词（≥2 词，含空格）。跨行拆英文的条目必为多词（水下冒险AA
    『深呼吸Deep \\nbreath』→『Deep breath』）；单字专名（『卡塔佩什Katapesh』）
    是地区散文引言而非条目名。"""
    return " " in en.strip()

def _is_fragment_title(name: str) -> bool:
    """中文名是否为正文句段碎片（非专长/章节标题）。R5 probe 同口径：

      1. 尾虚词结尾（『该生物的』『皆属』『在你的』是断行悬挂）
      2. 句号收尾（星内散文句：『标注星号专长为战斗专长。』）
      3. 句首引导黑名单（『你向/你在/你获得/选择一种/均衡生物居住…』）

    注意：不用 ≥10 字阈值——『格拉里昂的盔甲与护盾战斗流派』是合法章节名
    （护甲大师手册，星包裹标题），长度是名词短语而非散文句。
    """
    if _RE_FRAGMENT_TAIL.search(name) or name.endswith("。"):
        return True
    return bool(_RE_PROSE_LEAD_RX.match(name))

def _merge_cross_line_en(text: str) -> str:
    """跨行英文名合并：`Ambush \nAwareness` → `Ambush Awareness`。

    源数据排版断行常把英文名拆成两行，合并后标题/字段才能按单行解析。
    仅合并字母紧邻换行（中文断行不受影响）；中文行首跨行（`指引 \n
    Celestial`）走 _RE_CROSS_EN_CN（首字母大写词，避开 M10 全大写形态）。
    """
    text = _RE_CROSS_EN.sub(r"\1 \2", text)
    text = _RE_CROSS_EN_CN.sub(r"\1 \2", text)
    return text

def _merge_table_continuation(text: str) -> str:
    """表格单元格内跨行合并（中文续行）：`| Brewmaster\n酿造大师 |` → 同行。

    须在跨行英文合并之后（英文断行已由 _RE_CROSS_EN 先行合并）。
    """
    return _RE_TABLE_CONT.sub(r"\1 \2", text)

def _mark_pfs(text: str) -> str:
    """PFS 图标/否定标签 → 行内标记（split 消费为 pfs_eligible）。"""
    text = _RE_PFS_IMG.sub("[[PFS]]", text)
    text = _RE_PFS_NEG.sub("[[PFSN]]", text)
    return text

_RE_HR_LINE = re.compile(r"^[ \t]*---[ \t]*$", re.MULTILINE)


def _strip_hr_lines(text: str) -> str:
    """裸 `---` 水平线行剥除（KN123）：CHM 转换 HTML `<hr>` 的 Markdown
    形态，无语义（stat block 章节分隔/段落分隔）。剥成空行保留段落边界；
    带管道符的表格分隔行 `| --- | --- |` 不命中（race `_RE_TABLE_SEP_ROW`
    单独处理，feat/spell 既有行为不变——调用方按类目启用）。"""
    return _RE_HR_LINE.sub("", text)


def _strip_http_links(text: str) -> str:
    """KN075：正文参考链接剥离（源数据 427 处 → 产出残留 25 处清洗）。

    HTML 追溯确认 `<A href="论坛帖">锚文本</A>` 形态——URL 是参考指向
    噪声，锚文本即有效内容。三种形态：
    - `[锚文本](httpURL)` → 留锚文本（星内锚 `[*唤起神力PA*]` 整体消费
      再交星号归一）；
    - `[URL](URL)` / `**[URL](URL) **`（页头论坛链接行）→ 整链剥空（含
      紧邻加粗壳，防 `****` 空壳残留）；
    - `](httpURL)` 残缺（锚文本缺失，如 archivesofnethys）→ 剥空。
    """
    text = _RE_HTTP_URL_LINK.sub("", text)
    text = _RE_HTTP_LINK.sub(
        lambda m: m.group(1) if not m.group(1).startswith("http") else "", text
    )
    text = _RE_HTTP_LINK_TAIL.sub("", text)
    return text

def _fix_quadruple_star(text: str) -> str:
    """四星/六星归一 + 嵌套剥皮（elided 包裹形态收敛为标准双星）。

    seed 06：`**酿造大师（****Brewmaster****）******` → `**酿造大师（Brewmaster）**`
    seed 04：`****酩酊侠****` → `**酩酊侠**`（后续由 _fix_elided_quadruple_title 合并）
    R5：星内散文句（`****标注星号专长为战斗专长。******`，page_553）→ 去星留
    正文，避免散文冒充标题并吞掉后续真实专长。
    """
    def _repl(m):
        inner = m.group(1)
        if _is_fragment_title(inner):
            return inner
        return f"**{inner}**"

    # 整行星号散文剥离（先于四星归一，防残留星重组）：碎片内容去整行星号留正文
    lines = []
    for ln in text.split("\n"):
        m_line = _RE_FULL_STAR_LINE.match(ln)
        if m_line and _is_fragment_title(m_line.group(1).strip()):
            lines.append(m_line.group(1).strip())
        else:
            lines.append(ln)
    text = "\n".join(lines)

    text = _RE_QUAD_STAR.sub(_repl, text)
    text = _RE_HEX_STAR.sub("**", text)
    text = _RE_NESTED_STAR.sub(r"**\1（\2）**", text)
    # KN070：行首无星嵌套星剥皮 + 括号外粘连 EN 剥星 + 4 星粘连拆行
    # （顺序：先剥嵌套星让 `）****正文` 定位到真实括号，再拆 4 星粘连）
    text = _RE_PAREN_NESTED_STAR.sub(r"（\1\2）", text)
    text = _RE_CN_EN_ADJACENT_STAR.sub(r"\1\2", text)
    text = _RE_BOLD_GLUE_SPLIT.sub(r"\1**\n**\2", text)
    # 括号闭合前尾星残留：`（Catfolk Rogue Talents****）`（_RE_QUAD_STAR
    # 剥前导星后括号内英文尾部 4 星无配对可剥，残留污染 name_en/aliases）
    text = _RE_PAREN_TAIL_STAR.sub(r"（\1）", text)
    # 字段标签与值粘连 4 星：`**强韧豁免****DC**“10+1/2…”` → `**强韧豁免 DC**…`
    #（豁免/类型等字段行源数据 `**标签****EN**` 形态，2026-08-04 race 修复）
    text = _RE_LABEL_EN_QUAD_GLUE.sub(r"**\1 \2**", text)
    return text

def _fix_elided_quadruple_title(text: str) -> str:
    """elided 四星标题：`**中文**` 行 + `English****（类型）*****正文` 行 → 标准标题。

    源数据（page_538 等）把中文名与英文名/类型标签拆成两行且星号残缺，
    直接合并为 `**中文（English）〔类型〕**` 走标准标题解析。
    """
    return _RE_ELIDED_QUAD.sub(r"[[fc:elided]]**\1（\2）〔\3〕**\n\4", text)

def _fix_quad_star_halfparen(text: str, *, guard: bool = False) -> str:
    """四星+半角括号截断（seed 11）：`）****(Combat,` → 闭合标题 + 残留落新行。

    括号未闭合的英文名是源数据截断残留，截断在 `(` 之前保留信息量，
    同时避免残留括号把标题拖入 text。
    guard=True（race 侧）：4 星前必须是 `）`/`)`（截断形态）才拆行；
    `**中文****（EN）**`（4 星前是中文名——闭合标题+正文同行）不拆
    （2026-08-04 race 修复：page_160 `**援护防御****（****Defensive Aid,
    Ex****）**` 跨行 EN 合并后被误拆 elided，标题残片污染正文）。
    guard=False（feat 侧，默认）：无条件拆 `****(`/`****（`——武器技法
    子条目（`**Choke Up****（特技动作…）**`，4 星前是英文名）依赖拆行
    成 elided，否则半残星壳行吞正文致类别标题整段丢失（e80ec0e 回归，
    P1：武器大师手册 6 技法）。
    """
    lines = []
    for ln in text.split("\n"):
        if "****(" in ln or "****（" in ln:
            if guard:
                new = _RE_QUAD_HALFPAREN_PUNCT.sub(r"**\n", ln)
                if new != ln:
                    ln = new
                    if not ln.startswith("[[fc:"):
                        ln = "[[fc:elided]]" + ln
            else:
                ln = ln.replace("****(", "**\n(").replace("****（", "**\n（")
                if not ln.startswith("[[fc:"):
                    ln = "[[fc:elided]]" + ln
        lines.append(ln)
    return "\n".join(lines)

def _fix_colon_title_glue(text: str, labels: set[str]) -> str:
    """KN083：`**中文[：:]**英文**` 冒号标题粘连 → 标准 FC-1n 标题。

    page_529/530 索引表格后正文区：`<B>中文</B>：<B>English</B>` 相邻加粗段
    转换残留 4 星粘连（`**奥法陷阱压制者：****ARCANE TRAP SUPPRESSOR******`），
    `_RE_QUAD_STAR` 剥 `****X****` 后残留 `**中文：**X****`（或半角冒号+
    英文闭合星+字段开星残留 `**淡化身形:**X**：****`）——`_wrap_bare_titles`
    各分支与 split 标题正则全失配 → 正文条目并入前条目/静默丢失（判别器
    FC-3b 带冒号变体不匹配 → est=got 假一致，page_529 6 条正文丢失）。

    守卫：
    - 组1 ∈ 调用方标签集（feat 传 `_ALL_FIELD_LABELS`）→ 字段标签
      （`先决条件：**Prereq**` 值同行）不转换；
    - 英文名无大写字母（`yhx_178` 翻译署名等）→ 不转换（真英文名含大写，
      与判别器 FC-3b Title Case 口径同源）。
    """
    def _repl(m):
        if m.group(1) in labels or not re.search(r"[A-Z]", m.group(2)):
            return m.group(0)
        return f"**{m.group(1)}（{m.group(2)}）**"

    return _RE_COLON_TITLE_GLUE.sub(_repl, text)

def _merge_type_seg_line(text: str) -> str:
    """合并标题行后独立〔〕类型段残留（page_197 多段加粗标题）"""
    return _RE_TYPE_SEG_LINE.sub(
        lambda m: m.group(1)[:-2] + "〔" + m.group(2) + "**", text
    )

def _fix_label_trailing_star(text: str) -> str:
    """KN083：字段标签闭合星后残留星剥除：`**特殊情况：**** **值` → 字段行。

    标签+值同行粘连（`**特殊情况：**** **你可以…`）`_RE_QUAD_STAR` 不匹配
    （` **` 不足 2 非星字符），`_wrap_bare_titles` D 分支把「：」当英文名捕获
    → `[[fc:elided]]**特殊情况（：）**` 伪条目并吞前条目收益尾巴。剥星后
    `**特殊情况：** **值` 走字段行/正文并入路径（值同行 L1140 冒号正则需行尾
    闭合星失配，落 L1207 并入 cur，内容不丢）。须后于 `_fix_colon_title_glue`
    （英文形态先整体消费，此处只剥无英文的字段残留星）。
    """
    return _RE_LABEL_TRAILING_STAR.sub(r"\1", text)

def _wrap_index_line(text: str) -> str:
    """【来源缩写】索引行（seed 07）→ 标准标题 + fc/src 标记。

    造物专长一览等页的列表形态：`【PotW】抵异作成（造物）（Aligned Crafting）`，
    来源缩写经 [[src:]] 标记传给 processor 层写入 source 字段。
    """
    return _RE_INDEX_LINE.sub(r"[[fc:lb_marker]][[src:\1]]**\2（\4）〔\3〕**", text)

def _wrap_bare_titles(text: str, labels: set[str]) -> str:
    """无星标题包裹（elided：星号缺失形态）。

    `labels` 字段标签集（feat 传 `_ALL_FIELD_LABELS`），转发给
    `_wrap_bare_paren_lines` 排除字段值行。

    B 先于 A：B 的中文+粘连英文+类型括号形态更特定，A 只吃 `中文(English)`。
    C 处理 `中文 English*****正文`（5 星分隔标题与正文）。
    D 处理行首已有星的 `**中文 English*****正文`（判别器 FC-8c，ISI 风格化法术）。
    A 改为逐行：排除字段值行（前一行是字段标签）与术语定义行（括号后 `**：`）。
    R5 守卫：B 中文名是正文句段碎片**且**类型括号为长散文（>15 字）时不包裹——
    `该生物的CR（该CR要基于…种族，而不包括…）`（page_856）括号内是散文而非
    类型标签；仅碎片判定会误伤合法专长（seed_08『困于城中City-Locked(故事)』
    以粒子『中』结尾是真实专长名，类型括号『故事』为短标签）。
    C/D 守卫：星形散文（`通过规则调整来降低魔法…`）碎片名直接不包裹。
    """
    # E 分支（KN053）：`**中文（EN）****　　*描述*` 同行 elided——闭合标题
    # + 4 星 + 同行单星描述（任务与战役_专长 17 处，跨行 EN 已由
    # _merge_cross_line_en 合并）。先于 D 分支：D 的组2 `[^*\n]{1,}?`
    # 会吞掉 `（EN）` 括号再包层 → `（（EN））` 双括号 split 不识别。
    # 组1 以 `）` 结尾锚定「EN 带括号的闭合标题」，D 输入（EN 无括号）
    # 天然不匹配。
    text = _RE_ELIDED_INLINE_DESC.sub(r"[[fc:elided]]**\1**\n\2", text)

    def _repl_cnparen(m):
        # 组合条件：碎片名 + 长类型括号（正文悬挂；合法类型标签 ≤11 字实测）
        if _is_fragment_title(m.group(1)) and len(m.group(3)) > 15:
            return m.group(0)
        return f"[[fc:elided]]**{m.group(1)}（{m.group(2)}）〔{m.group(3)}〕**\n{m.group(4)}"

    def _repl_star(m):
        if _is_fragment_title(m.group(1)):
            return m.group(0)
        return f"[[fc:elided]]**{m.group(1)}（{m.group(2)}）**\n{m.group(3)}"

    text = _RE_BARE_CN_EN_CNPAREN.sub(_repl_cnparen, text)
    text = _RE_BARE_CN_EN_STAR.sub(_repl_star, text)
    # 无空格紧邻 elided（KN090 收口，page_311 详细条目块）：`**中文****EN`
    # 中文与英文间无空格（HTML 相邻加粗段），D 分支 `\s+` 不匹配 → 此处
    # 归一；EN 须行尾（同行正文/中文尾缀不吞，`[A-Za-z0-9 .'-]` 限英文名
    # 常见字符防 `**中文****EN，中文续句` 整段误吞）。
    text = _RE_ELIDED_CN_EN_GLUE.sub(r"[[fc:elided]]**\1（\2）**", text)
    text = _RE_BARE_CN_EN_STAR_BOLD.sub(_repl_star, text)
    return _wrap_bare_paren_lines(text, labels)

# 字段标签行形态（通用，与标签集无关）：`**先决条件：**` / `**先决条件**`
# （feat.py split 另有同名常量，模块各自定义互不影响）
_RE_FIELD_LABEL_COLON = re.compile(r"^\*\*([一-鿿]{2,8})[：:]\*\*$")
_RE_FIELD_LABEL_BARE = re.compile(r"^\*\*([一-鿿]{2,8})\*\*$")
# A 分支守卫 8 判据（2026-08-04 M10）：裸中文冒号空值行
# （`替代墨汁云：`，BotS 替代特性形态）——其后「中文（EN）」行不包裹。
_RE_BARE_CN_COLON_EMPTY = re.compile(r"^[一-鿿/]{2,8}[：:][ \t]*$")

def _wrap_bare_paren_lines(text: str, labels: set[str]) -> str:
    """A 分支逐行：`中文(English) 正文` 包裹，排除三类非标题行。

    `labels` 字段标签集（feat 传 `_ALL_FIELD_LABELS`），用于守卫 1 的
    字段值行排除。

    1. 字段值行（R5）：前一行是字段标签（**先决条件：** 等）时，本行是
       字段值而非标题——永罪之书 L147 `魔族仪典（Fiendish Obedience ）`
       （**先决条件：** 的值）误产 2 个 elided 伪条目根因。
    2. 术语定义行：括号后紧跟 `**：` 或 `：`（`表现描述符（Apparent
       Descriptor）**：风格化法术…` 型）是条目正文的加粗术语，非标题。
    3. 正文句段（R5 扩展）：`_is_fragment_title`——尾虚词（『该生物的（CR）』）、
       句号、句首引导（『你向法术注入了来自骨园（Boneyard）…』等全库 28 条
       `中文（English）正文` 散文句，probe 同口径）。

    R7 扩展（2026-08-02 空 text chunk 调查）：三类合法非标题行穿透
    上述守卫被误包为 elided 伪条目（原条目空 text）：
      4. 召唤列表行：组2 英文以「,阵营缩写」结尾（`天界海豚(Celestial
         dolphin,NG)`）——纯洁勇士召唤善良怪物列表 27 行。
      5. 长散文正文行：组3 >30 字且句号结尾（`拉兹米尔（Razmir）谙熟将…`
         章节引言、武术手册MAH 化形扭/化形势、武器大师 在塔尔多）。
      6. 量词开头正文行：组1 以「一只」开头（`一只豺化人（Jackalwere）
         蹲在你的家谱上。`——豺产正文，9 字短句句号结尾，阈值 5 不覆盖）。
    回归护栏：短尾缀真标题（`海滨后裔（Shoreborn）半精灵可获得以下专长。`
    11 字句号结尾）维持包裹——测试 test_short_trailer_title_still_wrapped。
    R8 扩展（2026-08-02 KN070 补）：组3 以逗号开头 = 列表续行——纯洁勇士
    `爱与和平（Euphoric Tranquility），和谐术（Serenity）**` 是和平缔造者
    效果文本跨行法术列表续行（L13 效果列举法术以 `，` 结尾），任务与战役
    `静思者（Scholar of the Great Beyond）, 漫游者（Wanderlust）` 同族
    （专长名列表续行）。真实条目标题正文不从逗号开始，误伤面趋零。
    R9 扩展（2026-08-04 M10）：裸中文冒号空值行（BotS 替代特性
    `替代墨汁云：`）后的「中文（EN）」行是替代特性的英文名/正文行——
    不包裹。保持裸由 `_wrap_bare_colon_titles_race` 跨行吞并产出
    `**替代墨汁云**：灵巧触须（Dexterous Tentacles）` 单条目（洛卡鱼人
    [0057] 同构），防 elided 伪条目与空 text（feat 源无裸中文冒号空值行
    形态，0 行实测）。
    """
    lines = text.split("\n")
    out: list[str] = []
    prev_label = False
    prev_bare_cn_colon = False
    for ln in lines:
        m = _RE_BARE_CN_EN_PAREN.match(ln)
        rest = m.group(3).lstrip("　 ") if m else ""
        if (
            m
            and not prev_label
            and not prev_bare_cn_colon
            and not rest.startswith(("**：", "**:", "：", ":"))
            and not _is_fragment_title(m.group(1))
            and not _RE_ALIGN_SUFFIX.search(m.group(2))
            and not (rest.strip().endswith(("。", "？", "！")) and len(rest.strip()) > 30)
            and not m.group(1).startswith("一只")
            and not rest.startswith(("，", ","))
            # R10 扩展（2026-08-04 M13 取代条款）：`此特性取代腐化抗性（ward
            # against corruption）.` / `该特性取代防御（Armor）。` / `此能力
            # 取代偏好地形（favored terrain）`——守卫 5 只拦「中文句号 +
            # >30 字长散文」，英文句点/无标点短行穿透被误包成 elided 伪条目
            # + 孤立标点 chunk（PA 暮行者 2 + 狗头人 1 + 怪物种族 1）。
            # 保持裸行 → 后续并入前条目（纯中文形态既有行为同向）。
            and not _RE_REPLACE_CLAUSE.match(m.group(1))
            # 双括号+冒号（`喷射（Jet）（1 RP）： `，BotS 海地精）：tail 拆行
            # 会被 `_normalize_whitespace_title` 跨行合并成 `**…**` + 独立
            # `：` 行 → text 以 `：` 开头。留整行给 `_wrap_bare_paren_colon_titles`
            # 转星 `**…（1 RP）： **`，split `_RE_TITLE` 组4 剥冒号（feat 源
            # 无此形态，0 行实测，公共守卫无影响）
            and not re.search(r"[)）][：:]", rest)
        ):
            out.append(f"[[fc:elided]]**{m.group(1)}（{m.group(2)}）**\n{rest}")
        else:
            out.append(ln)
        stripped = ln.strip()
        m_fl = _RE_FIELD_LABEL_COLON.match(stripped) or _RE_FIELD_LABEL_BARE.match(stripped)
        prev_label = bool(m_fl and m_fl.group(1) in labels)
        prev_bare_cn_colon = bool(_RE_BARE_CN_COLON_EMPTY.match(stripped))
    return "\n".join(out)

def _wrap_bare_cn_type_paren(text: str, re_type_paren: re.Pattern) -> str:
    """裸/星外中文类型括号标题包裹为 **中文（类型）**。

    `re_type_paren` 由调用方按各自类型守卫集编译（feat 传
    `_RE_BARE_CN_TYPE_PAREN`，守卫 = FEAT_TYPE_NORMALIZE ∪ 动物伙伴专长）。
    """
    return re_type_paren.sub(r"**\2（\4）**", text)

def _normalize_whitespace_title(text: str) -> str:
    """whitespace：`**中文** (English，类型 )` 括号前空格形态 → 标准标题。

    要求 `**` 后至少一个空格：标准 `**X（Y）**` 无空格，天然免疫。
    \2 保留尾随空格无碍——标题解析时会 strip。
    """
    return _RE_WS_TITLE.sub(r"[[fc:whitespace]]**\1（\2）**\n\3", text)

def _fix_star_shell_remnants(text: str) -> str:
    """星壳残留收口：两端剥壳 + 删独立纯星行 / PFS 残留壳行。

    顺序：先 BOL/EOL/开星规则剥出行首行尾壳（`*  **正文** *` →
    `*正文*`），再删剥壳后无内容的纯星行（`*`/`**`/`*** ***` 等）——
    若先删星行，`**` 行与下邻 `**标签：**` 的跨行误匹配在 EOL 无影响，
    但剥壳优先保证 `*  **正文** *` 单行两段壳被完整消费。
    """
    text = _RE_SHELL_BOL.sub("*", text)
    text = _RE_SHELL_EOL.sub("*", text)
    text = _RE_SHELL_TRIPLE_OPEN.sub(r"*\1*", text)
    text = _RE_SHELL_DASH.sub(r"*\1——\2*", text)
    text = _RE_SHELL_QUAD_OPEN.sub(r"*\1*", text)
    text = _RE_SHELL_ITALIC_TRAIL.sub(r"*\1*", text)
    text = _RE_SHELL_FIELD_QUAD.sub(r"\1**\2", text)
    text = _RE_SHELL_BLANK_STAR_LINE.sub("", text)
    text = _RE_SHELL_PFS_STAR.sub("", text)
    return text

def _fix_field_star_right(text: str) -> str:
    """右星残缺：`**值**标签：**` → 拆行 + `**标签：**`（seed 04 效果字段）。"""
    return _RE_FL_STAR_RIGHT.sub(r"\1\n**\2：**", text)

def _fix_field_star_left(text: str) -> str:
    """左星残缺：`标签**：` → `**标签**：`（seed 12 先决条件）。

    非行首拆行、行首归一不拆——行首已是独立字段行，仅补齐星号。
    """
    text = _RE_FL_STAR_LEFT_SPLIT.sub(r"\n**\1**：", text)
    text = _RE_FL_STAR_LEFT_BOL.sub(r"**\1**：", text)
    return text

def _split_inline_fields(text: str, re_split_bare: re.Pattern) -> str:
    """字段同行紧贴拆分（三形态统一为独立行）。

    - 星形（`**标签：**` / `**标签**：`）非行首出现 → 前插换行
    - 裸标签（`先决条件：` 等）仅限句末标点后（seed 08 任务链正文），
      散文句中段的"先决条件"等字样不受影响

    `re_split_bare` 由调用方按各自标签集编译（feat 传 `_RE_FIELD_SPLIT_BARE`，
    标签 = FEAT_ALL_FIELD_LABELS 的 `_LABELS_ALT`）。
    """
    text = _RE_FIELD_SPLIT_A.sub(r"\n\1", text)
    text = _RE_FIELD_SPLIT_B.sub(r"\n\1", text)
    text = re_split_bare.sub(r"\1\n", text)
    return text

def _wrap_bare_field_labels(
    text: str, re_bare_label: re.Pattern, re_bare_label_period: re.Pattern
) -> str:
    """行首裸字段标签包裹为 **标签：**（parse_fields 可解析形态）。

    不保留前导缩进：parse_fields 字段边界要求换行后紧跟 `**`，
    行首空格会让值跨字段吞并（缩进对 split 无意义，strip 会清掉）。

    两个正则均由调用方按各自标签集编译（feat 传 `_RE_BARE_FIELD_LABEL` /
    `_RE_BARE_FIELD_LABEL_PERIOD`，标签 = FEAT_ALL_FIELD_LABELS 的
    `_FIELD_LABEL_ALT`）。
    """
    text = re_bare_label.sub(r"**\2**", text)
    return re_bare_label_period.sub(r"**\1：**", text)

def _fix_bare_label_colon_nextline(text: str) -> str:
    """裸标签值行归位（R2，AG 涤净引导型）。

    源数据整理时把来源引用块插在字段标签与值之间、值行以冒号开头：
    `**先决条件**\n> 来源：…\n：魅力 15` → `**先决条件**：魅力 15`。
    归一后 parse_fields 的 field_re_v2 可直接解析；引用块行（整理时元信息）
    在此被消费——来源书解析走 resolve_source 的原始文件内容，不受影响。
    """
    return _RE_BARE_LABEL_VAL.sub(r"\1\2", text)

def _fix_star_outside_en(text: str) -> str:
    """M2 星外英文名并入：`**中文**English` → `**中文 English**`。

    源数据整理把英文名从星内挤出到闭合星后、紧贴英文再跟来源（seed 35）。
    并入成 FC-3 形态（`**中文 English**`）让 split 直接识别。
    """
    return _RE_STAR_OUTSIDE_EN.sub(r"**\1 \2**", text)

def _split_closed_title_source(text: str) -> str:
    r"""M1a 闭合星+同行来源拆行：`**…** 出自…` / `**…** Source …pg` → 拆行。

    来源同行会把标题拖出 `^\*\*…\*\*$` 锚定（seed 34/35），拆行后标题独立、
    来源并入 text（来源解析走 resolve_source 原始文件，不受影响）。
    """
    return _RE_CLOSED_TRAILER_SRC.sub(r"\1\n\2", text)

def _fix_spaced_parens_cn_en(text: str) -> str:
    """M1b 星内'中文(类型) English(English)'空格分隔 → FC-1n 单括号。

    源数据用半角括号且类型与英文名空格分隔（seed 34 `不屈坐骑(战斗)
    Indomitable Mount (Combat)`）。现有正则无法精确吸收：FC-1n 的非贪婪
    `\1` 会回溯把 `(战斗)` 吞进 name。归一到单括号 `（类型, English）`
    后 `_split_paren_content` 按逗号拆出 name_en 与类型。
    """
    return _RE_SPACED_PARENS_CN_EN.sub(r"**\1（\2, \3）**", text)

def _split_closed_title_colon(text: str) -> str:
    """M7 闭合星+同行冒号拆行：`**中文（English, 类型）**：正文` → 拆行。

    要求星内含括号（标题特征）防误拆 `**先决条件**：` 字段行（seed 40）。
    """
    return _RE_CLOSED_TRAILER_COLON.sub(r"\1\n\2", text)

def _fix_fc1v_paren_en(text: str) -> str:
    """M3 FC-1v：`**中文**（English）` 闭合星后括号英文 → `**中文（English）**`。

    星内中文闭合、英文名在星外括号（seed 36）。归一为 FC-1n 形态后 split
    的 `_split_paren_content` 拆出 name_en。
    """
    return _RE_FC1V_CLOSED_STAR_PAREN.sub(r"**\1（\2）**", text)

def _fix_fc1n_no_closing_star(text: str) -> str:
    """M4 FC-1n 无闭合星补星：`**中文（English）` → `**中文（English）**`。

    源数据英文名跨行合并后行尾缺闭合星（seed 37，判别器'闭合星可缺'型）。
    补星成标准 FC-1n 形态。
    """
    return _RE_FC1N_NO_CLOSING_STAR.sub(r"**\1（\2）**", text)

def _wrap_hash_titles(text: str) -> str:
    """M5 井号条目标题转星：`# 中文（English）` → `**中文（English）**`。

    判别器 FC-H 井号形态（seed 38）。文件标题型（`（…）EMH 专长` 结尾）
    行尾非括号天然不匹配。
    """
    return _RE_HASH_TITLE.sub(r"**\1（\2）**", text)

def _wrap_hash_titles_type_en(text: str) -> str:
    """M11a 井号带类型+英文：`## 中文（类型） English` → `**中文（English，类型）**`。

    判别器 FC-Hb（seed 44，天界/炼狱血脉聚合文件）。归一到单括号形态后
    `_split_paren_content` 按逗号拆出 name_en 与类型。
    """
    return _RE_HASH_TITLE_TYPE_EN.sub(r"**\1（\3，\2）**", text)

def _wrap_hash_titles_cn_en(text: str) -> str:
    """M11b 井号中文+英文：`## 中文 English` → `**中文（English）**`。

    判别器 FC-Hb 无类型形态（seed 45）。行尾须英文名（`## 树蛙人专长` 无
    英文天然不匹配，落正文）。
    """
    return _RE_HASH_TITLE_CN_EN.sub(r"**\1（\2）**", text)

def _split_title_glue_paren(text: str) -> str:
    """M13a 行首闭合星+粘连正文拆行：`**中文（English）**正文` → 拆行。

    源数据把正文紧贴标题星（判别器 FC-G/FC-1x，seed 46 page_950 `**领导力
    （Leadership）***正文*`）。先于 M8 运行：`**中文（类型）**English正文`
    的粘连形态若让 M8 处理会把整行吞进英文名（构装体专精 0 条目缺陷），
    先拆行后 M8 只吃 `**中文（类型）** English` 空格形态。
    """
    return _RE_TITLE_GLUE_PAREN.sub(r"\1\n", text)

def _split_title_glue_cn_en(text: str) -> str:
    """M13b 行首星内中文+大写英文+粘连正文拆行：`**中文 EN**正文` → 拆行。

    判别器 FC-3 大写英文形态（seed 47 page_673 冥想专长）。`_RE_TITLE_CN_EN`
    需行尾闭合星，粘连正文使其不匹配；拆行后恢复标题识别。
    """
    return _RE_TITLE_GLUE_CN_EN.sub(r"\1\n", text)

def _wrap_bare_cn_en_lines(text: str) -> str:
    """M6/M9 裸中英行包裹：`中文English` → elided 标题。

    判别器 FC-8e 段流英文裸奔（seed 39/42）。无星无括号形态，`_wrap_bare_titles`
    系列不覆盖；整行=中文+英文短语（+可选中文尾缀如 seed 42 的『伟业』），
    含中文标点的散文/字段行天然不匹配。中文尾缀不并入 name_en——英文名停在上
    一个非字母前（判别器 FC8E_RX `(?=$|[^A-Za-z0-9])` 同口径），尾缀落新行并
    入 text。

    R5 扩展守卫：正文断行碎片不包裹（中文名≥10 字 / 尾虚词 / 长尾缀且英文非
    Title Case——详见 `_RE_FRAGMENT_TAIL` 注释）。种子 49 反例：page_1564
    『当你使用元素拳APG攻击造成寒冷伤害时…』整行是正文描述（英文 APG 全大写
    缩写），包裹成"当你使用元素拳/APG"伪标题；水下冒险AA『深呼吸Deep breath
    你屏住…』是真条目（英文 Deep breath 为 Title Case），长尾缀是同行描述，
    必须保留（R5 返工回归点）。
    """
    def _repl(m):
        tail = m.group(3) or ""
        name = m.group(1)
        en = m.group(2)
        # 正文句碎片：
        #   长中文名是句段（『均衡生物居住在…』，M6 无合法长名可安全用阈值）
        #   尾虚词/句号/句首引导（_is_fragment_title：『该生物的』『标注星号…。』）
        #   长尾缀+英文非 Title Case 或单字专名（『…APG攻击造成…』『卡塔佩什
        #   Katapesh 卡塔佩什的峡谷…』）是正文续接/散文引言；多词 Title Case
        #   长尾缀是真条目同行描述（水下冒险AA『深呼吸Deep breath 你屏住…』）
        if (
            len(name) >= 10
            or _is_fragment_title(name)
            or (
                len(tail) > 8
                and (not _is_title_case_en(en) or not _is_multiword_en(en))
            )
        ):
            return m.group(0)
        base = f"[[fc:elided]]**{name}（{en}）**"
        return f"{base}\n{tail}" if tail else base

    return _RE_BARE_CN_EN_LINE.sub(_repl, text)

def _fix_star_outside_en_type(text: str) -> str:
    """M8 星内类型闭合+星外英文名并入：`**中文（类型）** English` → 单括号。

    判别器 FC-4 变体（seed 41）：类型括号在星内、英文名在星外同行。归一到
    `**中文（类型, English）**` 后 `_split_paren_content` 按逗号拆出类型与
    英文名。
    """
    return _RE_STAR_OUTSIDE_EN_TYPE.sub(r"**\1（\2, \3）**", text)

def _wrap_bare_cn_en_allcaps(text: str) -> str:
    """M10 中文行+全大写英文行包裹：`中文\\nALLCAPS` → elided 标题。

    判别器 FC-7c（seed 43）：中文专长名独占一行、英文名下一行全大写。跨行
    英文已由 merge 合并（`DIVERSE \\nOBEDIENCE` → `DIVERSE OBEDIENCE`）。
    """
    return _RE_BARE_CN_EN_ALLCAPS.sub(r"[[fc:elided]]**\1（\2）**", text)

def _split_paren_content(
    content: str, type_normalize_fn: callable
) -> tuple[str, list[str]]:
    """标题括号内容 → (name_en, type 列表)。

    逗号/顿号拆段：含字母的段合并为英文名（空格连接），纯中文段为类型标签
    （经调用方归一化函数处理：feat 传 `split_feat_types` 白名单归一）。
    `Barrage of Styles，战斗，团队` → (`Barrage of Styles`, [战斗, 团队])。
    `，又译别译` 段是翻译注记而非类型（狂暴撞飞/诈欺师/抗拒死亡等全库
    78 形态），`^又译` 前缀剥离——真类型标签不以「又译」开头，无误伤。
    """
    parts = [p.strip() for p in re.split(r"[,，、]", content) if p.strip()]
    en_parts: list[str] = []
    cn_parts: list[str] = []
    for p in parts:
        if re.search(r"[A-Za-z]", p):
            en_parts.append(p)
        elif re.search(r"[一-鿿]", p) and not p.startswith("又译"):
            cn_parts.append(p)
    return (" ".join(en_parts), type_normalize_fn("，".join(cn_parts)))


# ---- 常量（自 feat.py 搬移，2026-08-04，提取脚本补搬）----
_RE_PROSE_LEAD = (
    r"当你|通过|如果|若|每当|只要|因为|由于|尽管|虽然|一旦|要是|即便"
    r"|哪怕|假如|若是|直到|除非|但是|并且|然而"
    r"|你向|你无法|你在|你获得|你对|你曾|你在对抗"
    r"|演武专长用于|阴影攻击能够|标注星号专长为"
    r"|在阿维斯坦|一个角色能|下列|在尝试|均衡生物居住在|擅长此类"
    r"|选择一种|此手能|此为一个|一名|达成你|拥有凶猛能力|当敌人|成功制造"
    r"|你也可以选择|也可以选择"
)

_RE_PROSE_LEAD_RX = re.compile(_RE_PROSE_LEAD)

_RE_FRAGMENT_TAIL = re.compile(r"[的在了与照需至到上中后属]$")

# 换行前容忍星壳残留（`Catfolk**** \nRacial`——4 星闭合后断行形态，
# 2026-08-04 race 修复：源数据英文名常为 `（****EN****\nEN2****）` 三行）
_RE_CROSS_EN = re.compile(r"([a-zA-Z,])[ \t]*\*{0,4}[ \t]*\r?\n[ \t]*([a-zA-Z])")

_RE_CROSS_EN_CN = re.compile(r"([一-鿿])[ \t]*\r?\n[ \t]*([A-Z][a-z])")

_RE_TABLE_CONT = re.compile(r"(?m:^)(\|[^\n|]*)\n([^\n]*\|)")

_RE_PFS_IMG = re.compile(r"!\[\[图片\]\]\([^)]*\)")

_RE_PFS_NEG = re.compile(r"[〔［【]PFS(?:不可?用?)?[〕］】]")

_RE_QUAD_STAR = re.compile(r"\*\*\*\*([^*\n]{2,})\*\*\*\*")

# 括号闭合前尾星残留：`（EN****）`（四星剥前导星后尾部无配对星壳）
_RE_PAREN_TAIL_STAR = re.compile(r"（([^（\n]*?)\*{2,}）")

# 字段标签与英文值粘连 4 星：`**强韧豁免****DC**`（标签闭合星+值开星成 4 星）
_RE_LABEL_EN_QUAD_GLUE = re.compile(r"\*\*([一-鿿]{2,8})\*\*\*\*([A-Za-z]{1,6})\*\*")

_RE_HEX_STAR = re.compile(r"\*{6}")

_RE_NESTED_STAR = re.compile(r"\*\*([^*\n]+?)（\*\*([^*\n]+)\*\*）\*\*")

_RE_PAREN_NESTED_STAR = re.compile(r"（\*\*([^*\n]+?)\*\*([^）]*?)）")

_RE_CN_EN_ADJACENT_STAR = re.compile(r"([一-鿿/])\*\*([A-Za-z][^*\n：:]{1,}?)\*\*(?=[（(])")

_RE_BOLD_GLUE_SPLIT = re.compile(r"(\*{0,2}[^*\n]*?[）)])\*{4}(?!\*)(?![：:；;])(\S)")
# _fix_quad_star_halfparen 守卫：`）****(` / `）****（` 截断形态才拆行
# （4 星前是 `）`/`)`；`**中文****（EN）` 前是中文名不拆）
# 拆行后置守卫：`****` 后跟冒号/分号（`）****：`）是标题内粘连不拆——
# `）****：` 留给 _RE_TITLE 括号后星容限（race 尖耳朵形态，2026-08-04）；
# `）****(` / `）****（` 仍拆行（KN070：标题闭合 + 截断残留落正文行，
# feat seed 11 既定行为，回归测试 test_regression_halfparen_no_break）
_RE_QUAD_HALFPAREN_PUNCT = re.compile(r"[）)]\*{4}(?!\*)(?=[（(：:])")

_RE_ELIDED_QUAD = re.compile(
    r"^\*{2,4}([^*\n]+)\*{2,4}\s*\n?\s*([A-Za-z][^*\n]*?)\*{4}（([^）]+)）\*{4,5}(.*)$",
    re.M,
)

_RE_INDEX_LINE = re.compile(
    r"^【([^】]+)】\s*([一-鿿/]{2,})（([^）]+)）\s*（([A-Za-z][^）\n]*)）"
    r"\s*(?:【[^】]+】)?\s*$", re.M
)

_RE_BARE_CN_EN_CNPAREN = re.compile(
    r"^([一-鿿]{2,})\s*([A-Za-z][A-Za-z\- ]{1,})[（(]([一-鿿][^）)]*)[)）]\s*(.*)$", re.M
)

_RE_BARE_CN_EN_STAR = re.compile(
    r"^([一-鿿/]{2,})\s*([A-Za-z][A-Za-z \n]{1,})\*{4,}(.*)$", re.M
)

_RE_BARE_CN_EN_STAR_BOLD = re.compile(
    r"^\*\*([一-鿿/]{2,})\s+([^*\n(（]{1,}?)\*{4,}(.*)$", re.M
)

_RE_ELIDED_CN_EN_GLUE = re.compile(
    r"^\*\*([一-鿿/]{2,})\*\*\*\*\s*([A-Za-z][A-Za-z0-9 .'\-]*)$", re.M
)

_RE_ELIDED_INLINE_DESC = re.compile(
    r"^\*\*([^*\n]+?[）)])\*{4}　\s*(\*[^*\n]+\*)\s*$", re.M
)

_RE_BARE_CN_EN_PAREN = re.compile(
    rf"^(?!(?:{_RE_PROSE_LEAD}))([一-鿿]{{2,}})[（(]([A-Za-z][^）)]*)[)）]\s*(.*)$",
    re.M,
)

_RE_ALIGN_SUFFIX = re.compile(r",\s*(?:NG|CG|LG|NE|CE|CN|LE|LN|TN)\s*$")

# R10/M13 取代条款行组1（`此特性取代腐化抗性`、`该特性取代防御`、
# `此能力取代偏好地形`、`这些特性取代…`——替换特性条目后的独立行
# replaces 说明）。race 暮行者/狗头人/怪物种族 16 处 + 非 race 类目
# （魔宠变体/游荡剑客）同形态。「替换/变更」词汇不在此模式
# （`种族特性替换（Alternate Racial Traits）` 是真章节标题，首字「种」
# 不匹配）。
_RE_REPLACE_CLAUSE = re.compile(
    r"^(?:此|该|这(?:一|些)?)(?:种族|职业)?(?:特性|能力|动作)取代"
)

_RE_WS_TITLE = re.compile(r"^\*\*([^*\n]+)\*\*\s+[（(]([^）)〕]{1,60})[)）]\s*(.*)$", re.M)

_RE_FL_STAR_RIGHT = re.compile(r"(\*\*[^*\n]+?\*\*)([一-鿿]{2,8})[：:]\*\*")

# 左星残缺拆分：`标签**：` 前插换行补左星（seed 12）。负向断言含数字——
# `-2感知**：` / `-2 敏捷**：`（属性调整值中文粘连/空格分隔）不应拆
# （race 形态；feat 无数字+中文 `**：` 场景，无回归）。
_RE_FL_STAR_LEFT_SPLIT = re.compile(r"(?<![一-鿿\*\n　0-9])(?<![+−-]\d[ \t])([一-鿿]{2,8})\*\*[：:]")

_RE_FL_STAR_LEFT_BOL = re.compile(r"(?<!\S)(?<![+−-]\d[ \t])([一-鿿]{2,8})\*\*[：:]")

_RE_FIELD_SPLIT_A = re.compile(r"(?<!^)(\*\*[一-鿿]{2,8}[：:]\*\*)", re.M)

_RE_FIELD_SPLIT_B = re.compile(r"(?<!^)(\*\*[一-鿿]{2,8}\*\*[：:])", re.M)

_RE_TABLE_EN = re.compile(r"([A-Za-z][A-Za-z .'’-]{1,})")

_RE_TABLE_CN = re.compile(r"([一-鿿]{2,})")

_RE_HTTP_URL_LINK = re.compile(r"(\*{1,4})?\[(http[^\]]*)\]\(http[^)\s]*\)(\*{1,4})?")

_RE_HTTP_LINK = re.compile(r"\[([^\[\]]*)\]\(http[^)\s]*\)")

_RE_HTTP_LINK_TAIL = re.compile(r"\]\(http[^)\s]*\)")

_RE_FULL_STAR_LINE = re.compile(r"^\*{3,}([^*\n].*?)\*{3,}\s*$")

_RE_COLON_TITLE_GLUE = re.compile(
    r"\*\*([一-鿿][^*\n：:]{0,14})[：:]\*{0,4}([A-Za-z][^*\n]*?)\*{2,}"
    r"(?:[：:]\*{0,2})?"
)

_RE_LABEL_TRAILING_STAR = re.compile(r"(\*\*[一-鿿]{2,8}[：:]\*\*)\*{2,}")

_RE_TYPE_SEG_LINE = re.compile(
    r"(\*\*[^*\n]{1,40}?\*\*)\n\*\*〔\*{0,4}([^〕\n]{1,10}〕)(?:\*{2,6})"
)

_RE_SHELL_BOL = re.compile(r"^[ \t　]*\*{1,4}[ \t　]+\*{1,4}", re.MULTILINE)

_RE_SHELL_EOL = re.compile(
    r"(?:\*{1,4}[ \t　]+\*{1,4}|\*{4,})[ \t　]*$", re.MULTILINE
)

_RE_SHELL_TRIPLE_OPEN = re.compile(r"^[ \t　]*\*{3}([^*\n]+?)\*{1}[ \t　]*$", re.MULTILINE)

_RE_SHELL_QUAD_OPEN = re.compile(r"^[ \t　]*\*{4,6}([^*\n]+?)\*{0,9}[ \t　]*$", re.MULTILINE)

_RE_SHELL_DASH = re.compile(
    r"^[ \t　]*\*{2,6}([^*\n]+?)\*{2,6}——\*\*([^*\n]+?)[ \t　]*$", re.MULTILINE
)

_RE_SHELL_ITALIC_TRAIL = re.compile(r"^[ \t　]*\*([^*\n]+?)\*{2,}[ \t　]*$", re.MULTILINE)

_RE_SHELL_FIELD_QUAD = re.compile(r"(\*\*[^*\n]{1,20}?[：:])\*\*\*\*([^*\n])")

_RE_SHELL_BLANK_STAR_LINE = re.compile(
    r"^[ \t　]*\*{1,6}(?:[ \t　]\*{1,6})*[ \t　]*$", re.MULTILINE
)

_RE_SHELL_PFS_STAR = re.compile(r"^[ \t　]*\[\[PFS\]\]\*{1,6}[ \t　]*$", re.MULTILINE)

_RE_STRIKE_SHELL = re.compile(r"~{2,}")

_RE_BARE_LABEL_VAL = re.compile(r"(\*\*[一-鿿]{2,8}\*\*)(?:\n(?:>[^\n]*\n)?)([：:])")

_RE_STAR_OUTSIDE_EN = re.compile(
    r"\*\*([一-鿿/]{2,})(?<![一-鿿·/\-]专长)\*\*\s*([A-Za-z][^*\n（(]*?)"
    r"(?=\s+(?:Source|出自|第\d+页)|\s*$)",
    re.MULTILINE,
)

_RE_CLOSED_TRAILER_SRC = re.compile(
    r"(\*\*[^*\n]+?\*\*)\s+((?:出自|Source)[^\n]*|[A-Za-z][A-Za-z .'’\-]*pg\.\s*\d*[^\n]*)"
)

_RE_FC1V_CLOSED_STAR_PAREN = re.compile(
    r"\*\*([一-鿿/]{2,})\*\*\s*[（(]([A-Za-z][^）)]*)[)）]\s*$",
    re.MULTILINE,
)

_RE_FC1N_NO_CLOSING_STAR = re.compile(
    r"^\*\*([一-鿿/]{2,})[（(]([A-Za-z][^）)]*)[)）]\s*$",
    re.MULTILINE,
)

_RE_HASH_TITLE = re.compile(
    r"^#{1,3}\s*([一-鿿]{2,})[（(]([A-Za-z][^）)]*)[)）]\s*$",
    re.MULTILINE,
)

_RE_BARE_CN_EN_LINE = re.compile(
    r"^([一-鿿]{2,})([A-Za-z][A-Za-z'’\.\- ]*?)(?:([一-鿿][^\n]*))?\s*$",
    re.MULTILINE,
)

_RE_STAR_OUTSIDE_EN_TYPE = re.compile(
    r"\*\*([一-鿿/]{2,})[（(]([一-鿿][^）)]*)[)）]\*\*\s*([A-Za-z][^\n（(]*?)(?=\n|$)",
    re.MULTILINE,
)

_RE_BARE_CN_EN_ALLCAPS = re.compile(
    r"^([一-鿿]{2,})\n([A-Za-z][A-Za-z'’\.\- ]{2,})\s*$",
    re.MULTILINE,
)

_RE_SPACED_PARENS_CN_EN = re.compile(
    r"\*\*([一-鿿/]{2,})\s*[（(]([一-鿿][^）)]*)[)）]\s+([A-Za-z][^*\n]*?)\s*\*\*"
)

_RE_CLOSED_TRAILER_COLON = re.compile(
    r"(\*\*[^*\n]*?[（(][^）)]*[)）][^*\n]*?\*\*)[：:]([^\n]*)$",
    re.MULTILINE,
)

_RE_HASH_TITLE_TYPE_EN = re.compile(
    r"^#{2,3}\s*([一-鿿]{2,})[（(]([一-鿿][^）)]*)[)）]\s+([A-Za-z][^*\n]*?)\s*$",
    re.MULTILINE,
)

_RE_HASH_TITLE_CN_EN = re.compile(
    r"^#{2,3}\s*([一-鿿]{2,})\s+([A-Za-z][^*\n]*?)\s*$",
    re.MULTILINE,
)

_RE_TITLE_GLUE_PAREN = re.compile(
    r"^[ \t]*(\*\*[一-鿿][^*\n]*?[（(][^）)〕］】]{1,30}[)）][^*\n]*?\*\*)(?![\n：:])(?!\*{1,4}[：:])(?![ \t]+[A-Za-z])",
    re.MULTILINE,
)

_RE_TITLE_GLUE_CN_EN = re.compile(
    r"^[ \t]*(\*\*[一-鿿/]{2,}\s+[A-Z][A-Za-z'’\- ]{2,}\*\*)(?![\n：:])",
    re.MULTILINE,
)
