"""
formats/spell.py — 法术格式归一化与结构提升

7 种格式变体支持：
  A — 管道表格（CRB, APG）
  B — Bold 标签（UM, UC）
  C — 冒号标签（ACG）
  D — AONPRD（冒险之路）
  E — 紧凑内联（玩家伴侣）
  F — 换行无冒号（MTT）
  G — 文章体（page_625 神话法术）

用法：
  format = SpellFormat()
  normalized = format.normalize(raw_text)
  promoted = format.promote(normalized)
  items = format.split_into_items(promoted)
"""

import logging
import re
from typing import Dict, List, Optional

from vectorizer.formats.base import BaseFormat

logger = logging.getLogger(__name__)
from vectorizer.registry import (
    LEGACY_13_LABELS,
    LEGACY_EXPANDED_LABELS,
    LEGACY_INLINE_COMPACT_LABELS,
    LEGACY_INLINE_COMPACT_STEP23_LABELS,
    LEGACY_LABELS_NO_LEVEL,
    ALL_FIELD_LABELS,
    LABEL_ALIAS_TO_CANONICAL,
    F2_INLINE_ALIAS_LABELS,
)


class SpellFormat(BaseFormat):
    """法术格式归一化与结构提升"""

    # KN019 D 类正文段守卫：以这些词开头的候选行大概率是正文句子而非法术名
    # （法术名是名词短语，正文句以主语/连词/时间词开头）。
    # 与逗号/括号开头、前 6 字数字、HTML 标签等信号配合使用。
    _BARE_TITLE_PROSE_HEADS = (
        '你', '当', '可以', '你的', '该法术', '召唤来', '施法者', '那些',
        '除了', '这个法术', '由于', '如果', '随着', '在', '若该', '每位',
        '第一轮', '第二轮', '第三轮',
    )

    @property
    def category(self) -> str:
        return "spell"

    def get_audit_rules(self) -> dict:
        return {
            "min_spells_per_book": {
                "CRB": 50, "APG": 30, "UM": 20, "UC": 10, "ACG": 10,
            },
            "required_schools": [
                "咒法系", "变化系", "死灵系", "塑能系",
                "幻术系", "附魔系", "预言系", "防护系",
            ],
            "unknown_school_max_pct": 0.05,
            "empty_description_max": 10,
        }

    def _fix_unclosed_bold_headers(self, text: str) -> str:
        """
        修复未闭合的 ** 章节标题。

        模式：行首 **标题\n（无闭合 **，直接换行接散文）
        → 闭合为 **标题**。

        排除含 (或（的行（跨行英文名标题会被 _fix_broken_english_names 处理，
        不应在此处闭合）。

        影响文件：page_1013/1148/1159/1171 的 **新法术，
        Spell FoP 的 **信仰的法术，MC-怪物志 的 **沼蜍人法术 等。
        """
        # 排除下一行已以 ** 结尾的情况（即 ** 已在同段落内闭合），
        # 避免误伤 ISG 跨行英文名：**巴风特之赐\\nBlessing**
        return re.sub(
            r'^(\*\*)([^*\n（(]{2,30})(\n)(?=[^\n*])(?!.*\*\*[ \t]*$)',
            r'\1\2\1\3',
            text,
            flags=re.MULTILINE,
        )

    def _fix_split_titles(self, text: str) -> str:
        """
        修复 ISG 格式的分行标题，合并为 **中文 (English)**。

        ISG 特有格式（英文名不在括号内，神祇名在独立行）：
          **阿巴达尔的诚实告解 Abadar\\'s Truthtelling
          (阿巴达尔)
          ****学派：**惑控系...
          → **阿巴达尔的诚实告解 (Abadar's Truthtelling)**
          **学派：**惑控系...

        变体 B：**中文行\\nEnglish (Deity)\\n****
          **辟谷术
          Abstemiousness (义洛里)
          ****学派：**变化系...

        变体 C：**中文 English 同行\\n(Deity)\\n****
          同上

        变体 D：**中文 English\\n(Deity)**\\n（神祇行以 )** 结尾）
          **幸运灯塔 Beacon of Luck
          (戴斯娜)**

        变体 E：跨行英文名
          **巡守的祝福 Blessing of the
          Watch (阿巴达尔)
          ****学派：**...

        必须在 _fix_quadruple_asterisk 之前运行，以保留 **** 边界标记。
        """
        field_labels = "|".join(LEGACY_13_LABELS)
        eng = r'[A-Z][A-Za-zÀ-ɏ\s,.\'\-0-9]+'

        # V1: **Chinese\\nEnglish\\n(Deity)\\n****field
        text = re.sub(
            rf'^\*\*([^*\n]+?)\s*\n({eng}?)\s*\n[（(]([^）)]+)[）)]\n\*\*\*\*(?=(?:{field_labels}))',
            r'**\1 (\2)**\n**',
            text,
            flags=re.MULTILINE,
        )

        # V2: **Chinese\\nEnglish (Deity)\\n****field（中文独占一行，English+神祇在下一行）
        # 用 (?![ \\t]*[A-Z]) 确保 Chinese 行尾没有 English 名（仅查同行，不跨换行），
        # 避免 \s 匹配换行后误把下一行 English 也当作"同行英文"
        text = re.sub(
            rf'^\*\*([^*\n]+?)(?![ \t]*[A-Z])\s*\n({eng}?)\s*[（(][^）)]+[）)]\n\*\*\*\*(?=(?:{field_labels}))',
            r'**\1 (\2)**\n**',
            text,
            flags=re.MULTILINE,
        )

        # V3: **Chinese English 同行\\n(Deity)\\n****field（中文+English 同行）
        text = re.sub(
            rf'^\*\*([^*\n]+?)\s+({eng}?)\s*\n[（(]([^）)]+)[）)]\n\*\*\*\*(?=(?:{field_labels}))',
            r'**\1 (\2)**\n**',
            text,
            flags=re.MULTILINE,
        )

        # V4: **Chinese\\nEnglish\\n(Deity)**\\n（神祇行以 )** 结尾，无 **** 分隔）
        text = re.sub(
            rf'^\*\*([^*\n]+?)\s+({eng}?)\s*\n[（(]([^）)]+)[）)]\*\*\s*$',
            r'**\1 (\2)**',
            text,
            flags=re.MULTILINE,
        )

        # V5: **Chinese\\nEnglish_part1\\nEnglish_part2...\\n(Deity)\\n****field（跨行英文名）
        # 匹配 ** 后 2-4 行不含 * 的内容，最后以 ****field 结尾
        for _ in range(3):  # 重复以处理嵌套/级联
            text = re.sub(
                rf'^\*\*([^*\n]+?)\s*\n({eng}?)\s*\n'
                rf'([A-Za-z][A-Za-z\s,.\'\-0-9]+)\s*\n[（(]([^）)]+)[）)]\n\*\*\*\*(?=(?:{field_labels}))',
                r'**\1 (\2 \3)**\n**',
                text,
                flags=re.MULTILINE,
            )

        # V6: 通用兜底：合并 ** 与 **** 之间的所有无 * 内容
        # **任意内容（不含 *，可跨行，最多 5 行）\\n****field → **合并内容**\\n**field
        # 行数上限避免大文件（APG/UM，>13000 行）中正则回溯爆炸
        text = re.sub(
            rf'^\*\*([^*][^*]*(?:\n[^*][^*]*){0,4})\n\*\*\*\*(?=(?:{field_labels}))',
            lambda m: '**' + ' '.join(m.group(1).split()) + '**\n**',
            text,
            flags=re.MULTILINE,
        )

        return text

    # ---- Phase 1 normalize（法术特有） ----

    def _normalize_custom(self, text: str) -> str:
        """法术类目特有的去噪规则（按顺序执行）"""
        # Phase 1a：全局去噪（不依赖格式上下文）
        text = self._strip_markdown_url_lines(text)
        text = self._strip_html_artifacts(text)
        text = self._strip_translator_notes(text)
        text = self._strip_image_markers(text)
        text = self._strip_metadata_lines(text)

        # Phase 1a¼：page_1365 等编译帖的索引表 + 书籍分组标题剥离
        # 必须在标题归一化之前，否则 `##### PZO9401` 被识别为标题
        text = self._strip_compilation_intro(text)

        # U+3000 中文空格 → 普通空格
        text = text.replace("\u3000", " ")

        # Phase 1a½：修复结构性缺陷
        # ISG 格式合并分行标题（必须在 _fix_unclosed_bold_headers 和 _fix_quadruple_asterisk 之前，
        # 因为依赖完整的 **Title\n...\n**** 边界）
        text = self._fix_split_titles(text)
        text = self._fix_unclosed_bold_headers(text)

        # Phase 1a²：格式修复（跨行、四星号、多余前置星号等）
        text = self._fix_broken_english_names(text)
        text = self._fix_quadruple_asterisk(text)
        text = self._fix_star_before_bracket(text)
        text = self._fix_bracket_crossline_english(text)
        text = self._fix_crossline_closing_bold(text)
        text = self._fix_bracket_crossline_english_name(text)
        text = self._fix_closing_bold_on_newline(text)

        # Phase 1b：标题清理
        text = self._strip_strikethrough(text)
        text = self._strip_title_suffixes(text)

        # Phase 1c：标题归一化为 **中文 (English)**
        # 必须先处理 【学派】和分组标题，再处理裸标题加粗和格式统一
        text = self._unify_school_bracket_titles(text)
        text = self._normalize_group_headers(text)
        text = self._wrap_bare_spell_titles(text)
        text = self._unify_spell_name_format(text)

        # Phase 1c½：/神祇名后缀（在 ** 包裹后剥离）
        # KN017：收窄为标题结构 `**X (Y)**/deity` — 仅作用于完整标题行，
        # 永不匹配字段行（**持续时间：** 1分钟/等级 / **环位：** 吟游诗人/歌者）。
        text = re.sub(
            r'^(\*\*[^*]+\([^)]+\)\*\*)/[一-鿿]{1,12}\s*$',
            r'\1',
            text,
            flags=re.MULTILINE
        )

        # Phase 1d：字段归一化（全角空格内联 → 展开内联 → 裸字段 → 合并跨行 → 统一标签）
        text = self._fix_ff_space_inline_fields(text)
        text = self._fix_inline_compact(text)
        text = self._fix_bare_inline_fields(text)
        text = self._merge_bold_field_lines(text)
        text = self._merge_pipe_table_lines(text)
        text = self._unify_field_labels(text)

        # KN016：标题形态归一化簇（Phase 1e）— 在字段块已归位后把
        # 8 簇异常形态归一为标准 **中文 (English)**。归一化在 split 之前，
        # 故 split_into_items 的单一形态匹配逻辑不动（红线）。
        text = self._normalize_spell_titles(text)
        return text

    def _strip_markdown_url_lines(self, text: str) -> str:
        """剥离整行 URL（Markdown 链接或裸 URL 占一行的模式）"""
        # [text](url)
        text = re.sub(
            r'^\s*\[[^\]]*\]\(https?://[^)]+\)\s*$',
            '',
            text,
            flags=re.MULTILINE,
        )
        # [http://...] 裸 URL 在方括号中
        text = re.sub(
            r'^\s*\[https?://[^\]]+\]\s*$',
            '',
            text,
            flags=re.MULTILINE,
        )
        return text

    def _strip_html_artifacts(self, text: str) -> str:
        """剥离 HTML 残留标签（size、table、td/tr 等）"""
        text = re.sub(r'\[/?size=\d+pt\]', '', text)
        text = re.sub(r'\[/?[a-z]+\]', '', text)
        return text

    def _strip_translator_notes(self, text: str) -> str:
        """剥离 ◎ ○ 译者标记。

        两步处理：
          1. 剥离 ◎[name]译文引自[translator] 前缀（行首与行内），保留后续内容
          2. 纯译者注释行（无 【）整行剥离
        """
        # ◎[name]译文引自[translator] → 保留后续内容（行首与行内均适用）
        text = re.sub(r'[◎○]\[[^\]]+\]译文引自[^\]]*\]', '', text)
        # 行尾残余的独立 ◎ ○ 行（无 【 跟随）：整行剥离
        text = re.sub(r'^[◎○]\s*.*$', '', text, flags=re.MULTILINE)
        return text

    def _strip_image_markers(self, text: str) -> str:
        """
        剥离 ![[图片]][(url)] Markdown 图片标记（行内匹配，不吞同行内容）。

        之前用 ^...$ 匹配整行，但 ISR-内海种族 等文件将
        ![[图片]](url) 与 **法术标题** 放在同一行，
        整行删除会丢失一半标题（英文名行也随之断裂）。
        """
        # 移除 ![[alt]](url) 或 ![[alt]]（无 URL 变体）
        return re.sub(r'!\[\[[^\]]*\]\](?:\([^)]*\))?', '', text)

    def _strip_metadata_lines(self, text: str) -> str:
        """剥离 整理者： 等元数据行"""
        return re.sub(r'^整理者[：:].*$', '', text, flags=re.MULTILINE)

    def _strip_compilation_intro(self, text: str) -> str:
        """剥离 page_1365 等编译帖的索引表与书籍分组标题。

        page_1365.md 是果园编译帖，结构为：
          1. 头部编译说明（叙述性文字，跳过即可）
          2. 玩家伴侣索引表（| PZO9401 书籍名 | 原译者 | 校正 |）
          3. 各书籍分组 `##### PZO94xx` + 副标题（如 `(开头+边栏待补完)`）
          4. 真实法术（以 `**Title (English)**` 开头，逐行字段布局）

        本函数剥离 (2) 索引表和 (3) 书籍分组标题及其副标题行，避免：
          - 索引表中的书籍名（如「二度黑暗玩家指南」）被误识别为法术
          - `##### PZO9401` 被识别为标题产生空 chunk
          - `(开头+边栏待补完)` 等副标题被吞入下一个真实法术 chunk

        不剥离 (1) 头部说明（叙述性，不产生 chunk）。
        不剥离 (4) 真实法术（由后续标题归一化处理）。

        实现策略：行级状态机扫描。
          - 索引表剥离：从含 `索引` 或 `Index` 的行（含跨行嵌套加粗）开始，
            剥离该行及后续所有 `|` 管道行 + 分隔行 + 紧邻空行 + 标题跨行延续。
          - PZO 分组剥离：从 `##### PZO94xx` 行开始，剥离该行及后续 0-5 行副标题
            （跨行 + 含括号注释），直到空行/新分组/法术起点。
        """
        lines = text.split('\n')
        out: list[str] = []
        i = 0
        n = len(lines)
        # 状态机模式
        mode = 'normal'

        while i < n:
            ln = lines[i]

            if mode == 'normal':
                # 检测索引表标题：含「索引」或「Index」的行
                # KN023：URL 行（含 ://，如 .../bbs/index.php?topic=...）不得触发——
                # "index" 子串误中 URL，6 文件 45 处链接后正文被吞
                if '://' not in ln and ('索引' in ln or 'Index' in ln or 'index' in ln):
                    mode = 'pipe_skip'
                    i += 1
                    continue
                # 检测 ##### PZO94xx 书籍分组标题
                if re.match(r'^#####\s+PZO\d{4,5}', ln):
                    mode = 'pzo_group_skip'
                    i += 1
                    continue
                out.append(ln)
                i += 1

            elif mode == 'pipe_skip':
                # 剥离管道行（| 开头）或分隔行
                stripped = ln.lstrip()
                if stripped.startswith('|'):
                    i += 1
                    continue
                # 容忍标题跨行延续（嵌套加粗跨行）：如 `**玩家伴侣索引（****Player
                # \nCompanion Index****）**` 的次行。特征收窄为嵌套加粗 `****`
                # 或以 `）**` 结尾——KN023：原条件"含 ** 且非 ** 开头"过宽，
                # 误吞行中加粗的字段行（如 `+ 每2个等级5尺）**目标**：…`）
                if ('****' in ln or ln.rstrip().endswith('）**')
                        or ln.rstrip().endswith(')**')):
                    i += 1
                    continue
                if ln.strip() == '' and i < n:
                    # 空行：检查下一行是否为管道行（容忍表内空行）
                    if i + 1 < n and lines[i + 1].lstrip().startswith('|'):
                        i += 1
                        continue
                # 退出管道模式
                mode = 'normal'
                # 当前行不消耗，重新判断

            elif mode == 'pzo_group_skip':
                # 副标题模式：吃 0-5 行直到空行/新分组/法术起点
                if ln.strip() == '':
                    mode = 'normal'
                    continue
                if ln.startswith('#####') or ln.startswith('**') or '【' in ln:
                    # 新分组/法术起点：退出
                    mode = 'normal'
                    continue
                # 否则吃掉这一行（最多 5 行）
                if i < n:
                    j = i
                    consumed = 0
                    while j < n and consumed < 5:
                        nxt = lines[j]
                        nxt_s = nxt.strip()
                        if nxt_s == '' or nxt.startswith('#####') or nxt.startswith('**') or '【' in nxt:
                            break
                        consumed += 1
                        j += 1
                    i = j
                mode = 'normal'

        return '\n'.join(out)

    def _wrap_bare_spell_titles(self, text: str) -> str:
        """
        检测无 ** 包裹的法术名行，为它们添加 **...**。

        UC 格式范例：
          超越之障 (Ablative Barrier)  →  **超越之障 (Ablative Barrier)**

        严格条件：
          - 行首无缩进（不是正文段落）
          - 英文名含大写字母开头
          - 整行不超过 80 字符（排除段落中的含括号内容）
          - 中文名不以"领域"结尾（排除领域典礼子条目，如 气领域（Air））
          - 不使用 \\s 匹配跨行（[ \t] 限制在同一行），避免误吞
            跨行字段值如 成分…法器 \\n(DF)

        **KN019 D 类修复（2026-08-04）**：
        stat block 表格后或正文中的正文首段（行首无缩进 + 行尾英文括号，
        如 坐骑术「你召唤出一匹轻型马 (light horse) 或矮种马 (pony)」、
        魔法恒定术「你可以以20000GP的代价来释放一个魔法恒定术 (Permanency)」）
        会被误判为裸标题包星，split 后正文与法术名失联。
        守卫 `_is_prose_first_line`：候选行「前一非空行是表格行 或 组1 含
        正文句特征（主语词/逗号/括号开头/数字）」且「紧邻后行是正文续行」→
        判正文首段，跳过包星。合法标题（后行空/后行标题形态）不受影响。
        """
        # 半角括号：**中文 (English)**
        # [ \t] 而非 \s 避免匹配跨行
        # (?!领域) 排除领域典礼子条目（任务与战役_法术 的 气领域/动物领域/...）
        # (?!-) 排除子弹列表条目（任务与战役_法术 的 - 葬礼 / - 节庆 / ...）
        # (?!出自) 排除来源引用行（ISR-内海种族 的 出自《内海种族》）
        # (?!#|\*\*|\[http) 排除标题行（'#' 开头或 '**' 开头）
        # **关键修复（2026-07-28）**：
        #   - 行首字符要求 `[^\s|\n]` 必须在 group(1) **内部** — 否则
        #     group(1) 从位置 1 开始丢首字符（修复前「典礼」→「礼」）。
        #   - 否定 lookahead 必须在 group(1) **外部之前**（紧随 `^`），
        #     否则会被 group(1) 吞掉进而在 group(1) 末尾运行（错位），
        #     导致 `(?!-)` 见不到前导 `-`，- 葬礼 会被错误加粗。
        #   - 末尾追加 `(?<!领域)` 确保 group(1) 末两字符不是「领域」，
        #     避免气领域 / 动物领域 等被误识别（仅 group(1) 内逐字符
        #     `(?<!领域)` 检查不够，因 `气` 单独通过后 `领域` 两字符
        #     会逐个通过判定）。
        bare_pattern = re.compile(
            r'^(?!#|\*\*|\[http|-)(?!出自)'
            r'([^\s|\n](?:(?<!领域)[^\n。：]){0,39})(?<!领域)'
            r'[ \t]*\(([A-Za-z][A-Za-zÀ-ɏ\s,.;\'\-0-9]+)\)[ \t]*$',
        )
        # 全角括号：**中文（English）**
        # 同上半角版本的结构修复
        bare_pattern_fw = re.compile(
            r'^(?!#|\*\*|\[http|-)(?!出自)'
            r'([^\s|\n](?:(?<!领域)[^\n。：]){0,39})(?<!领域)'
            r'[ \t]*（([A-Za-z][A-Za-zÀ-ɏ\s,.;\'\-0-9]+)）[ \t]*$',
        )
        lines = text.split('\n')
        out = []
        prev_nonblank_is_table = False
        for i, ln in enumerate(lines):
            m = bare_pattern.match(ln)
            if m and not self._is_prose_first_line(m.group(1), prev_nonblank_is_table, lines, i):
                ln = f'**{m.group(1)} ({m.group(2)})**'
            elif not m:
                m_fw = bare_pattern_fw.match(ln)
                if m_fw and not self._is_prose_first_line(m_fw.group(1), prev_nonblank_is_table, lines, i):
                    ln = f'**{m_fw.group(1)} ({m_fw.group(2)})**'
            out.append(ln)
            if ln.strip():
                prev_nonblank_is_table = (
                    ln.strip().startswith('|') or ln.strip().startswith('[tr]')
                )
        return '\n'.join(out)

    def _is_prose_first_line(
        self, group1: str, prev_nonblank_is_table: bool, lines: list, i: int
    ) -> bool:
        """KN019 D 类守卫：候选裸标题行是否为正文首段（不应包星）。

        - 强特征（第二类，2026-08-04）：HTML 跨行残留的强正文句特征——
          组1 含 `***`（<i> 跨行斜体残留）、含中文句号「。」（页引言）、
          以逗号开头（续段首行）。强特征直接判正文段，跳过后的行判据
          （这些行的后行往往为空/表格行，后行判据会误判为合法标题）
        - 前文信号：上一非空行是表格行（stat block 后续段）
          或组1 含正文句特征（主语词开头 / 逗号 / 括号开头 / HTML 标签 / 前 6 字数字）
        - 后行判据：紧邻后行是正文续行（非空、非标题/字段/表格/列表形态）——
          正文段落连续，而合法标题行后为空行/标题行
        """
        strong_prose_marker = (
            '***' in group1
            or '。' in group1
            or group1.startswith(('，', ','))
        )
        if strong_prose_marker:
            return True
        prose_marker = (
            group1.startswith(self._BARE_TITLE_PROSE_HEADS)
            or group1.startswith(('(', '（'))
            or '，' in group1 or ',' in group1
            or group1.startswith('[')
            or any(ch.isdigit() for ch in group1[:6])
        )
        if not (prev_nonblank_is_table or prose_marker):
            return False
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ''
        if not nxt:
            return False
        if nxt.startswith(('**', '|', '#', '-', '●', '【', '>', '=', '####')):
            return False
        return True

    def _strip_strikethrough(self, text: str) -> str:
        """
        剥离 ~~ 删除线标记（保留内部文本），支持 ~~**标题**~~ 嵌套。
        同时清理孤立的 ~~（无配对关闭标记的 CHM 转换残留），
        避免 OA 格式中 **~~Title (Eng)**** 转换后 ~~ 残留在标题中。
        """
        text = re.sub(r'~~(.*?)~~', r'\1', text)
        text = text.replace('~~', '')  # 清理孤立 ~~
        return text

    def _strip_title_suffixes(self, text: str) -> str:
        """
        剥离标题行末尾的附加标记。

        - [种族] 后缀：**隆地术 (Groundswell) [矮人]** → **隆地术 (Groundswell)**
        - （AP资源）后缀
        """
        # **中文 (English) [XXX]** → **中文 (English)**
        text = re.sub(
            r'(\*\*[^*]+\s*\([^)]+\))\s*\[[^]]*\](\*\*)',
            r'\1\2',
            text
        )
        # 【学派】标题后的附加描述符 [XXX]
        text = re.sub(
            r'(【[^】]+】[^】\(]*\([^)]+\))\s*\[[^]]*\]',
            r'\1',
            text
        )
        # （AP资源）/（皇冠战争AP资源）等后缀
        text = re.sub(
            r'（[^）]*AP资源[^）]*）',
            '',
            text
        )
        # **中文（English）【神名】** → **中文（English）**
        # 允许】和 ** 之间有空白（如拥王者 "【古拉姆】 **"）
        text = re.sub(
            r'【[^】]*】\s*(\*\*)',
            r'\1',
            text
        )
        # ─种族(English) 后缀（如 ─加隆德人(Garundi)）
        text = re.sub(
            r'─[^（(]*[（(][^）)]*[）)]$',
            '',
            text,
            flags=re.MULTILINE
        )
        # 出自：... 行尾后缀（如 **title)**出自：Pathfinder #42: ...）
        text = re.sub(
            r'(\*\*)\s*出自[#：:].*$',
            r'\1',
            text,
            flags=re.MULTILINE
        )
        # 出自Pathfinder#...（中间无冒号，符文领主的崛起等）
        text = re.sub(
            r'\s*出自Pathfinder.*$',
            '',
            text,
            flags=re.MULTILINE
        )
        # #XXX: 来源标注 后缀（暴君魔爪等冒险之路： **Title(English)**#140: 来源）
        text = re.sub(
            r'(\*\*)\s*#\d+:.*$',
            r'\1',
            text,
            flags=re.MULTILINE
        )
        # /神祇名 后缀（Spell FoP: **Title(English)/埃拉斯蒂尔**）
        return text

    def _merge_bold_field_lines(self, text: str) -> str:
        """
        合并跨行的 Bold 字段标签与值（仅限已知字段名）。

        UC 格式：
          **学派          \n**咒法系 (创造) [力场]
          → **学派：** 咒法系 (创造) [力场]

        仅当 ** 中的内容匹配已知字段标签时生效，避免误合并空行。
        """
        field_labels = "|".join(LEGACY_LABELS_NO_LEVEL)
        merged = re.sub(
            rf'\*\*({field_labels})\s*\n\*\*(.+)',
            r'**\1：** \2',
            text,
        )
        return merged

    def _fix_broken_english_names(self, text: str) -> str:
        """修复被换行切断的英文名。

        覆盖：
          - "Adhesive\\n       Blood" → "Adhesive Blood"（字母后直接换行）
          - "Celestial \\nCompanion" → "Celestial Companion"（空格后换行）
          - "Walk, \\nCommunal" → "Walk, Communal"（逗号后换行）
        """
        return re.sub(
            r'([a-zA-Z,])[ \t]*\n[ \t]*([a-zA-Z])',
            r'\1 \2',
            text
        )

    def _fix_quadruple_asterisk(self, text: str) -> str:
        """
        将 **** 归一化为 **（Spell CotR / 拥王者 等格式）。

        注意：不匹配 ）**** 或 )****，因为这是 OA/UI 紧凑格式中
        标题结束 ** 与字段开始 ** 的边界，由 _fix_inline_compact 处理。
        但匹配行尾的 ）****，因为那是标题自身的闭合标记（CotR 格式）。
        """
        # 行尾 ）**** → ）**（CotR 标题闭合）
        text = re.sub(r'([）)])\*\*\*\*\s*$', r'\1**', text, flags=re.MULTILINE)
        # 其他非紧凑格式边界的 **** → **
        return re.sub(r'(?<![\）)])\*\*\*\*', '**', text)

    def _fix_star_before_bracket(self, text: str) -> str:
        """剥离 【学派】 标题前的多余 * 号（如 *【防护】或 **【防护】）"""
        # 行首：无条件剥离
        text = re.sub(r'^\*+【', '【', text, flags=re.MULTILINE)
        # 行内：仅当 ** 前是句号/空格时剥离（安全边界，不破坏字段内的 **）
        text = re.sub(r'([。！？\s])\*+【', r'\1【', text)
        return text

    def _fix_closing_bold_on_newline(self, text: str) -> str:
        """
        合并跨行的 ** 闭合标记。

        处理场景：
          **黄衣之印 (Yellow Sign)\n**\n**学派** → **黄衣之印 (Yellow Sign)**\n**学派**
          **盗窃术\n(Swipe)** → **盗窃术 (Swipe)**

        只匹配 ）,**)\n** 模式（法术名行尾必有英文名反括号），
        避免误伤 **标记**+中文内容\n** 的独立段落交界。
        """
        # 合并 **中文）\n** → **中文）**
        text = re.sub(r'(\*\*[^*\n]+?[）)])[ \t]*\n[ \t]*\*\*', r'\1**', text)
        # 合并 **中文\n(English)** → **中文 (English)**
        text = re.sub(
            r'(\*\*[^*\n]+?)[ \t]*\n[ \t]*\(([A-Z][A-Za-zÀ-ɏ\s\'\-]+)\)[ \t]*(\*\*)',
            r'\1 (\2)\3',
            text
        )
        return text

    def _fix_bracket_crossline_english(self, text: str) -> str:
        """
        合并 【学校】中文\n（English）为 【学校】中文（English）。

        水下冒险AA 等文件用此格式：
          【预言】水下追迹
          （Aquatic Trail) [水]
        """
        return re.sub(
            r'(【[^】]+】[^\n]*?)[ \t]*\n[ \t]*([（(][A-Za-z][A-Za-zÀ-ɏ\s,.;\'\-]*[）)])',
            r'\1\2',
            text
        )

    def _fix_crossline_closing_bold(self, text: str) -> str:
        """
        合并 ** 包裹标题中跨行的英文名。

        暴君魔爪等冒险之路文件常见模式：
          **血石护心镜（Bloodstone
          Mirror）**#140: Eulogy for Roslar's Coffer
          → **血石护心镜（Bloodstone Mirror）**#140: ...

        规则：仅匹配 ** 开头+ ** 收尾，且括号包裹的英文名跨行，
        保留 ** 闭合标记后的内容（如来源标注 #140）。
        """
        # **中文（English1\nEnglish2）** → **中文（English1 English2）**
        # English1 至少 1 字母，English2 至少 1 字母
        # 闭合 ** 不要求在行尾（来源标注 #140: ... 可能在同一行）
        text = re.sub(
            r'(\*\*[^*\n]+?[（(])'
            r'([A-Za-zÀ-ɏ\'\-’][A-Za-zÀ-ɏ\s,;.\'\-’]*?)'
            r'[ \t]*\n[ \t]*'
            r'([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\s,;.\'\-’]*?)'
            r'([）)])'
            r'(\*\*)',
            r'\1\2 \3\4\5',
            text,
        )
        return text

    def _fix_bracket_crossline_english_name(self, text: str) -> str:
        """
        合并 【学派】标题中跨行的英文名。

        page_1008/1141/1142 等文件常见模式：
          【变化】(变形)返初溯源(First
          World Revisions)
          → 【变化】(变形)返初溯源(First World Revisions)

          【变化】太阳恐惧(FEAR
          THE SUN)
          → 【变化】太阳恐惧(FEAR THE SUN)

        与 _fix_bracket_crossline_english（整个英文名在下行）和
        _fix_crossline_closing_bold（** 包裹标题的跨行）互补，
        处理 【】 内括号英文名被物理换行断开的场景。
        """
        for _ in range(3):  # 最多 3 次迭代（处理 First\nWorld\nRevisions 多行断裂）
            new_text = re.sub(
                r'(【[^】]+】[^\n]*?[（(])'
                r'([A-Za-z][A-Za-zÀ-ɏ\s,;\'\-]*)'
                r'[ \t]*\n[ \t]*'
                r'([A-Za-z][A-Za-zÀ-ɏ\s,;\'\-]*?)'
                r'([）)])',
                r'\1\2 \3\4',
                text,
            )
            if new_text == text:
                break
            text = new_text
        return text

    def _unify_spell_name_format(self, text: str) -> str:
        """
        统一法术名格式为 **中文 (English)** 行。

        覆盖场景：
          - A/B/E: **中文 (English)**  — 无需修改
          - C:     **中文（English）** — 全角括号转半角
          - D:     **中文**（[English](url)）— 提取英文名
          - F:     ## 中文（English）— 从 ## 改为 **格式
          - E-semicolon: 中文（English）**field**： → **中文 (English)**\n**field**：
          - G-separate:  **中文** 后跟独立英文名行

        注意：C½（裸标题全角→半角）已移除，改为 Step 0b/0c 在 _fix_inline_compact 中
        用全角括号直接匹配行内标题，避免贪婪 [^*\n]* 匹配到行尾错误位置。
        """
        # C: 全角括号 → 半角（在 split_into_items regex 之前做）
        text = re.sub(
            r'(\*\*[^*]+)（([^）]+)）(\*\*)',
            r'\1 (\2)\3',
            text
        )

        # D: **中文**（[English](url)）→ **中文 (English)**
        text = re.sub(
            r'\*\*([^*]+)\*\*[（(]\[([^\]]+)\]\([^)]+\)[）)]',
            r'**\1 (\2)**',
            text
        )

        # E-semicolon: 中文 (English)**field**：→ **中文 (English)**\n**field**：
        # 处理分号合并字段格式中无 ** 包裹的标题
        field_labels = "|".join(LEGACY_13_LABELS)
        text = re.sub(
            r'^(?!\*\*)(.+?)\(([^)]+)\)\s*(\*\*(?:' + field_labels + r')[：:].*)$',
            r'\1 (\2)**\n\3',
            text,
            flags=re.MULTILINE
        )

        # F0: ## 中文〔【学派】｜元素〕→ **中文**（EMH 无英文名格式）
        text = re.sub(
            r'^##\s+(.+?)〔[^〕]+〕.*$',
            r'**\1**',
            text,
            flags=re.MULTILINE,
        )

        # F: ## 中文 (English) → **中文 (English)**
        text = re.sub(
            r'^##\s+(.+?)\s*[（(](.+)[）)]\s*$',
            r'**\1 (\2)**',
            text,
            flags=re.MULTILINE
        )

        # H: **中文 English** → **中文 (English)**（TG 格式，英文名无括号包裹）
        # 要求中文名含至少一个 CJK 字符，避免误伤纯英文行
        # 注意：Group 1 必须以 CJK 字符结束（无 [^*\n]*? 后缀），防止 MTT/AArch
        # 格式 **中文English**（无空格）将首单词吞入 Group 1 产生假阳性标题。
        text = re.sub(
            r'^\*\*([^*\n]*[一-鿿])\s+'
            r"([A-Z][A-Za-z0-9\s'\-’]+?)\s*\*\*\s*$",
            lambda m: f'**{m.group(1).strip()} ({m.group(2).strip()})**',
            text,
            flags=re.MULTILINE,
        )

        # G: **中文** + 独立英文名行 → **中文 (English)**
        text = re.sub(
            r'^(\*\*([^*]+)\*\*)\s*\n'  # **中文** 行
            r"([A-Z][A-Za-z0-9\s'’&;:/!?,-]+)$",  # English Name 行
            r'**\2 (\3)**',
            text,
            flags=re.MULTILINE
        )

        return text

    def _normalize_group_headers(self, text: str) -> str:
        """
        将分组标题转为 ## 章节标题，避免被 split_into_items 误识别为法术条目。

        匹配模式：**XX法术（ALLCAPS_ENGLISH）** 或 **XX法术 (ALLCAPS_ENGLISH)**
        """
        text = re.sub(
            r'^\*\*([^*]*法术)\s*[（(]([A-Z][A-Z\s\'\-]+)[）)]\*\*',
            r'## \1',
            text,
            flags=re.MULTILINE
        )
        return text

    def _unify_school_bracket_titles(self, text: str) -> str:
        """
        将 【学派】标题格式归一化为 **中文 (English)**。

        输入：【咒法系】(创造)强酸箭(Acid Arrow)[酸]
        输出：**强酸箭 (Acid Arrow)**

        格式模式：
          【学派】(可选子学派)中文名(English)[可选描述符]

        仅当标题行包含英文名（括号内）时转换，避免误转单行分组标题（如 【防护系】 单独一行）。
        """
        # 行首模式：^【学派】...(↑ 已有正则覆盖)
        pattern = re.compile(
            r'^【[^】]+】'                        # 【学派】
            r'(?:\([^)]*\))?'                     # 可选(子学派)
            r'([^（(]+)'                          # 中文名
            r'[（(]([^）)]+)[）)]'                # (English)
            r'(?:/[^\n（(]*)?'                    # 可选/神祇名（Spell FoP 格式）
            r'(?:[ \t]*\[[^]]*\])?'               # 可选[描述符]（前可有空格）
            r'\s*(?:\*\*.*)?$',                   # 可选紧跟字段标签
            re.MULTILINE,
        )
        text = pattern.sub(r'**\1 (\2)**', text)

        # 行内模式：【学派】中文（English） → **中文 (English)**
        # 仅当【前是句号/空格/行首时生效，避免破坏字段中的【】内容
        text = re.sub(
            r'(?:([。！？\s])|^)'
            r'【[^】]+】'                          # 【学派】
            r'(?:\([^)]*\))?'                     # 可选(子学派)
            r'([^（(【\n]+?)'                     # 中文名
            r'[（(]([^）)]+)[）)]'                # (English)
            r'(?:/[^\n（(]*)?'                    # 可选/神祇名（Spell FoP 格式）
            r'(?:[ \t]*\[[^]]*\])?',              # 可选[描述符]（前可有空格）
            lambda m: (m.group(1) or '') + '**' + m.group(2) + ' (' + m.group(3) + ')**',
            text
        )
        return text

    def _fix_ff_space_inline_fields(self, text: str) -> str:
        """
        展开全角空格分隔的无 ** 内联字段格式（跨书合并内容）。

        格式: **Title**学派　　　咒法（医疗）环位　　　牧师2
              → **Title**\\n**学派：** 咒法（医疗）\\n**环位：** 牧师2
        """
        field_pat = '|'.join(LEGACY_EXPANDED_LABELS)

        # Step 1: 在字段名前插入换行（前面不是换行）
        text = re.sub(
            rf'(?<!\n)({field_pat})(　+)',
            r'\n\1\2',
            text
        )

        # Step 2: 给字段名加 **：  （字段名 + 全角空格 → **字段名：** ）
        text = re.sub(
            rf'\n({field_pat})(　+)',
            r'\n**\1：** ',
            text
        )

        return text

    def _fix_bare_inline_fields(self, text: str) -> str:
        """
        在无 ** 也无全角空格的内联字段标签前加换行。

        格式: **学派：** 死灵系等级：牧师 3施法时间：标准动作
              → **学派：** 死灵系\n等级：牧师 3\n施法时间：标准动作
        """
        field_pat = '|'.join(LEGACY_EXPANDED_LABELS)

        # 在字段名 + ：前加换行，当前面是内容字符（非换行、非**、非开头）
        text = re.sub(
            rf'([^\n*])((?:{field_pat})[：:])',
            r'\1\n\2',
            text
        )

        return text

    def _fix_inline_compact(self, text: str) -> str:
        """
        展开 OA/UI 格式的内联紧凑字段，在 **字段名** 前加换行。

        输入：**中文（English）****学派**：值**等级**：值
        输出：**中文（English）**\\n**学派**：值\\n**等级**：值
        """
        field_pat = '|'.join(LEGACY_INLINE_COMPACT_LABELS)
        # KN012：Step 2/3 切换到扩展标签集（含别名 施放时间/持续/抗力/SR），
        # 以拆分行内粘连的别名标签（如 **豁免：** …无效**抗力**：可）。
        # Step 4 保持原集合（避免散文中 **抗力**/**持续** 强调被误拆行）。
        step23_pat = '|'.join(LEGACY_INLINE_COMPACT_STEP23_LABELS)

        # English name character class: letters, spaces, common punctuation, curly apostrophe
        _EN = r"[A-Z][A-Za-zÀ-ɏ\s,.;\'\-0-9’]+"

        # Step 0: 在非换行文本后的 **中文 (English)** 标题前加换行
        # 处理 Cluster 9 超紧凑格式：介绍段落末尾直接接法术标题
        # 只对紧跟 **field** 的标题生效，避免误伤描述中的法术名引用
        # 用 (?<!\n) 保证幂等性：标题前已有换行时不再重复添加
        text = re.sub(
            r'(?<!\n)(\*\*[^*]+\s*\([^)]+\)\*\*)(?=\*\*(?:' + field_pat + r'))',
            r'\n\1',
            text
        )

        # Step -1: 空格分隔 **中文 English****field → **中文 (English)**\n**field
        # MC-怪物志: **饕食灵气 Aura of Cannibalism****学派：**
        # 注意：G1 必须以 CJK 结束（[^*]*[一-鿿] 而非 [^*]+?），且 G2 需要至少
        # 一个小写字母（[a-z]），避免 MTT 的 **中文 ALL-CAPS****field 假阳性标题。
        text = re.sub(
            rf'(\*\*[^*]*[一-鿿])\s+([A-Z][A-Za-z\s\'’]*[a-z][A-Za-z\s\'’]*?)\*\*((?:{"|".join(LEGACY_13_LABELS)}))',
            r'\1 (\2)**\n**\3',
            text
        )

        # Step 0b: 内联标题+紧接字段 — 中文（English）**field**：→ **中文 (English)**\n**field**：
        # 无 (?<!\n) 前缀限制，以处理 ## 标题行后首个内联法术（纯洁勇士 等格式）
        text = re.sub(
            r'([^\n]{1,40}?)\s*（(' + _EN + r')）(\*\*(?:' + field_pat + r')[：:])',
            r'\n**\1 (\2)**\n\3',
            text
        )

        # Step 0c: 行尾全角括号标题 → 下一行 **field**：模式
        # 如：...散文。冷漠术（Apathy）\n**学派：** → ...散文。\n**冷漠术 (Apathy)**\n**学派：**
        # (?!出自) 排除来源引用行（ISR-内海种族 的 出自《内海种族》）
        text = re.sub(
            r'([。！？，；\s])(?!出自)([^\n。！？，；\s]{1,20})\s*（(' + _EN + r')）[ \t]*\n(\*\*(?:' + field_pat + r')[：:])',
            r'\1\n**\2 (\3)**\n\4',
            text
        )

        # Step 0d: 同行裸字段内联标题 — 中文（English）field：→ **中文 (English)**\n**field：**
        # 处理无 ** 包裹字段名的超紧凑格式（page_1104 等）
        text = re.sub(
            r'([。！？，；\s])([^\n。！？，；\s]{1,20})\s*（(' + _EN + r')）((?:' + field_pat + r')[：:])',
            r'\1\n**\2 (\3)**\n**\4**',
            text
        )

        # Step 0e: 已有 **title)** 但后接裸字段同行 — **title)**学派：→ **title)**\n学派：
        # 处理前一个法术描述尾部嵌入下一个标题的情况
        text = re.sub(
            r'(?<!\n)(\*\*[^*]+\s*\([^)]+\)\*\*)((?:' + field_pat + r')[：:])',
            r'\1\n\2',
            text
        )

        # Step 0f: 任何非行首的 **title (English)** → 提前换行
        # 处理散文尾部嵌入标题的情况（page_1013/1148/1159/1171/1333 等）
        # KN019 第二类（2026-08-04）：(?<!\*) 守卫——HTML <i> 跨行残留的
        # `***，除了…(shaitan)**`（3 星 + 行尾星壳）开星前是 `*`，会误当
        # 行尾标题拆行成 `*` + `**，除了…**` 伪标题（page_1365 0191）。
        # 合法散文尾部标题开星前是普通字符，不受影响。
        text = re.sub(
            r'(?<=\S)(?<!\*)(\*\*[^*]+\s*\([A-Za-z][A-Za-z\s\'\-’]+\)\*\*)\s*$',
            r'\n\1',
            text,
            flags=re.MULTILINE
        )

        # Step 1: 标题结尾 )** 与首字段 **field** 之间加换行
        # 处理 OA 紧凑格式：**Title****field**： → **Title**\n**field**：
        text = re.sub(
            r'([）)]\*\*)\*\*(?=(?:' + field_pat + r'))',
            r'\1\n**',
            text
        )

        # Step 1b: 为裸标题（无 ** 前缀的中文名行）添加 ** 包裹
        # OA 格式中 Step 1 把 )**** 拆分为 )**\n**，产生如下行：
        #   动物召来（Apport Animal）**  或  动物召来 (Apport Animal)**
        # 这些行有 ending ）** 但缺少 leading **。本步补上。
        # 匹配：行首非 *，有中文[（(]English[）)]**，行尾。
        text = re.sub(
            r'^([^*\n].{0,40}?)[（(]([A-Z][A-Za-zÀ-ɏ\s,.;\'\-0-9]+)[）)]\*\*\s*$',
            r'**\1 (\2)**',
            text,
            flags=re.MULTILINE,
        )

        # Step 2: 字段值末尾与下一字段 **field**：之间加换行
        # 匹配模式：非换行字符 + **field**： → 在两者间加换行
        # KN012：用扩展标签集（别名 抗力/持续/施放时间 也能触发拆行）
        text = re.sub(
            r'([^\n])(\*\*(?:' + step23_pat + r')\*\*[：:])',
            r'\1\n\2',
            text
        )

        # Step 3: 同 Step 2，但 field 格式为 **field：**（冒号在粗体内）
        # 匹配模式：非换行字符 + **field：** → 在两者间加换行
        text = re.sub(
            r'([^\n])(\*\*(?:' + step23_pat + r')[：:]\*\*)',
            r'\1\n\2',
            text
        )

        # Step 4: 无冒号粗体字段（**field** 值**field** 值 → 展开）
        # 匹配模式：非换行字符 + **field**（无冒号）→ 在 ** 前加换行
        # 这会在 _unify_field_labels 之前处理 **学派** 值；**等级** 值 类型
        # KN012：保持原 labelset（field_pat），不扩展别名 — 避免散文
        # 中 **抗力**/**持续** 强调被误拆行（方案文档 §3.1）
        text = re.sub(
            r'([^\n])(\*\*(?:' + field_pat + r')\*\*)',
            r'\1\n\2',
            text
        )

        return text

    def _merge_pipe_table_lines(self, text: str) -> str:
        """
        合并 CRB 多行管道表格行为单行 `| 字段 值 |` 格式。

        CRB 表格特殊结构：
          - 首行 `| 字段名`（带 `|`）
          - 后续字段 `       字段名`（缩进，无 `|`）
          - 值在字段名后的缩进行上
          - 以 `| --- |` 结束

        原始输入：                      →  处理后：
          | 学派                              | 学派 咒法系 (创造) [酸] |
                 咒法系                        | 环位 魔战士 2, 术士/法师 2 |
                 (创造) [酸]                   | 施法时间 标准动作 |
                 环位                          ...
                 魔战士 2, 术士/法师 2
                 ...
          | --- |
        """
        LABELS = "|".join(LEGACY_LABELS_NO_LEVEL)
        is_field_header = re.compile(r'^\s*(' + LABELS + r')\s*$').match
        is_table_end = re.compile(r'^\s*\|\s*-+\s*\|').match
        is_pipe_field = re.compile(r'^\|\s*(' + LABELS + r')\s*$').match

        lines = text.split('\n')
        result = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # 检测表格起始：| 字段名
            m = is_pipe_field(line)
            if not m:
                result.append(line)
                i += 1
                continue

            # ---- 进入表格块 ----
            current_label = m.group(1)
            current_vals = []
            fields = []             # [(label, "值字串"), ...]

            j = i + 1
            while j < len(lines):
                raw = lines[j]
                stripped = raw.strip()

                # 表格结束
                if is_table_end(raw):
                    j += 1
                    break

                if not stripped:
                    j += 1
                    continue

                # 检测字段头（缩进行且内容为已知字段名）
                fm = is_field_header(raw)
                if fm and not raw.lstrip().startswith('|'):
                    # 保存上一个字段
                    if current_vals:
                        fields.append((current_label, ' '.join(current_vals)))
                    current_label = fm.group(1)
                    current_vals = []
                    j += 1
                    continue

                # 普通值行
                val = stripped
                if val.endswith('|') and not val.endswith('\\|'):
                    val = val[:-1].strip()
                if val:
                    current_vals.append(val)
                j += 1

            # 最后一个字段
            if current_vals:
                fields.append((current_label, ' '.join(current_vals)))

            # 输出为单行管道行
            for label, val in fields:
                result.append(f'| {label} {val} |')

            i = j

        return '\n'.join(result)

    def _unify_field_labels(self, text: str) -> str:
        """
        统一 5 种字段变异为 **字段名：** 值 格式。

        A: | 学派 咒法系 | → **学派：** 咒法系
        B: **学派** 咒法系 → **学派：** 咒法系  （无冒号 → 加冒号）
        C: **学派：** 咒法系 → 不变
        F: 学派 咒法系 → **学派：** 咒法系   （无标签标记 → 加 **）
        F3: 施放时间：标准动作 → **施法时间：** 标准动作  （F2 裸标签，按规范标签归一化）

        所有字段别名（施放时间/持续/抗力 等）通过 registry 的 LABEL_ALIAS_TO_CANONICAL
        归一化为规范标签（施法时间/持续时间/法术抗力）。
        """
        # 定义字段标签映射（含所有别名，长标签优先）
        field_labels = ALL_FIELD_LABELS
        field_labels_pat = '|'.join(re.escape(label) for label in field_labels)

        def _normalize_label(label: str) -> str:
            """把别名标签归一化为规范标签。"""
            return LABEL_ALIAS_TO_CANONICAL.get(label, label)

        # A: 管道表格 → 标准格式
        table_pattern = rf'^\|\s*({"|".join(LEGACY_LABELS_NO_LEVEL)})\s+(.+?)\s*\|$'
        text = re.sub(
            table_pattern,
            lambda m: f"**{_normalize_label(m.group(1))}：** {m.group(2)}",
            text,
            flags=re.MULTILINE
        )

        # B: Bold 无冒号 → 加冒号（如 **学派** 咒法系 → **学派：** 咒法系）
        text = re.sub(
            rf'\*\*({field_labels_pat})\*\*\s+(?!：)(.+)',
            lambda m: f"**{_normalize_label(m.group(1))}：** {m.group(2)}",
            text
        )

        # B2: **标签**：值 → **标签：** 值（** 在冒号前关闭的变体）
        text = re.sub(
            rf'\*\*({field_labels_pat})\*\*[：:]\s*',
            lambda m: f"**{_normalize_label(m.group(1))}：** ",
            text
        )

        # F: 无标记行（行首为字段名 + 空格 + 值）
        text = re.sub(
            rf'^({field_labels_pat})\s+(.+)$',
            lambda m: f"**{_normalize_label(m.group(1))}：** {m.group(2)}",
            text,
            flags=re.MULTILINE
        )

        # F2: 无标记行带冒号（如 等级：魔战士 2 → **等级：** 魔战士 2；含 F2 变体 施放时间/持续/抗力）
        # 兼容 COMP 格式 抗力：** 否（值以 bold 开头），吃掉冒号后所有 * 和空白。
        # Python 3.14+ 兼容性：\* 和 \s 都被当作新 escape sequence 而非 regex 元字符，
        # 必须用字符类 [*\s] 才能正常匹配字面星号和空白。
        text = re.sub(
            rf'^({field_labels_pat})[：:][*\s]*(.+)$',
            lambda m: f"**{_normalize_label(m.group(1))}：** {m.group(2)}",
            text,
            flags=re.MULTILINE
        )

        # F2-inline: 紧跟前字段值的行内裸标签（仅 F2 别名）
        # 例：豁免：** 意志，通过则无效抗力：无
        #     → 豁免：** 意志，通过则无效\n**法术抗力：** 无
        # 严格约束：抗力标签 NOT 在 **...** 内（避免误转 **法术抗力**）
        # 即：`抗力` 前必须是行首、换行、或汉字+`：**` 关闭符（字段值结束标记）
        # 更宽松的启发式：仅识别 COMP 等已知格式的紧贴场景，加入换行符让 parse_fields 抽取。
        # 别名集合从 registry.F2_INLINE_ALIAS_LABELS 派生，不在 formats 层维护字面标签列表。
        _f2_alias_pat = '|'.join(F2_INLINE_ALIAS_LABELS)
        text = re.sub(
            r'(?<![一-鿿A-Za-z0-9])'        # 抗力/持续/施放时间 不在 词/字/数字 之后
            r'(' + _f2_alias_pat + r')'
            r'[：:][*\s]*'
            r'(有|无|是|否|可|不可'
            r'|见下文|见文本|见后文)',
            lambda m: f"\n**{_normalize_label(m.group(1))}：** {m.group(2)}",
            text
        )

        # F2-inline (tight)：豁免值尾词后的裸标签边界。
        # 处理 "无效抗力：无" / "见下抗力：无" 等已知模式，
        # 其中前导汉字属于已知豁免值尾词集合。
        # 安全约束：值限定为 {有,无,是,否,可,不可,见下文,见文本,见后文}，
        # 且只匹配已知豁免尾词（无效/有效/生效/见下/减半/通过），
        # 防止 "效果持续：一轮后失效" 等散文被误转。
        # 别名集合从 registry.F2_INLINE_ALIAS_LABELS 派生，不在 formats 层维护字面标签列表。
        # 尾词含「无」以处理 save 值为孤立「无」后紧跟裸标签的 P&P 等格式。
        # 长尾词（无效/有效）在短尾词（无）之前，防止前缀吞并。
        _KNOWN_SAVE_TAILS = r'(?:无效|有效|生效|见下|减半|通过|无)'
        text = re.sub(
            r'(' + _KNOWN_SAVE_TAILS + r')'
            r'(' + _f2_alias_pat + r')'
            r'[：:][*\s]*'
            r'(有|无|是|否|可|不可'
            r'|见下文|见文本|见后文)',
            lambda m: f"{m.group(1)}\n**{_normalize_label(m.group(2))}：** {m.group(3)}",
            text
        )

        return text

    # ---- Phase 2 promote ----

    def promote(self, text: str) -> str:
        """结构提升：统一字段标签（幂等）+ 输出 census 统计。

        Phase 2 仅做字段标签统一（_unify_field_labels 已在 normalize 中调用，
        此处为幂等安全网）。不做字段抽取（Phase 3 职责）。

        census 统计通过 compute_census() 类方法单独调用。
        """
        text = self._unify_field_labels(text)
        return text

    @staticmethod
    def compute_census(items: list) -> dict:
        """从 split_into_items 产出的条目列表计算字段覆盖率统计。

        Args:
            items: split_into_items() 的返回值（list[dict]）

        Returns:
            {
                "total_items": int,
                "fields": {
                    "学派": {"present": int, "total": int, "pct": float},
                    ...
                },
                "unified_labels": int,  # 使用统一标签 **字段名：** 的 chunk 数
            }
        """
        field_labels = LEGACY_13_LABELS
        field_counts = {label: 0 for label in field_labels}
        total = len(items)

        for item in items:
            text = item.get("text", "")
            for label in field_labels:
                if re.search(rf'\*\*{re.escape(label)}[：:]', text):
                    field_counts[label] += 1

        fields = {}
        for label in field_labels:
            fields[label] = {
                "present": field_counts[label],
                "total": total,
                "pct": round(field_counts[label] / total * 100, 1) if total > 0 else 0.0,
            }

        # 统计已有统一标签的 item 数（至少含一个 **字段名：** 模式）
        unified = sum(
            1 for item in items
            if re.search(rf'\*\*(?:{"|".join(LEGACY_13_LABELS)})[：:]', item.get("text", ""))
        )

        return {
            "total_items": total,
            "fields": fields,
            "unified_labels": unified,
        }

    # ---- KN016 标题形态归一化簇 ----

    # 字段块开头（用于 _normalize_spell_titles 安全约束）
    _TITLE_FIELD_HEAD: tuple[str, ...] = (
        "**学派：**", "**学派**", "**等级：**", "**等级**",
        "**环位：**", "**环位**",
    )

    def _has_field_head_after(self, lines: list[str], idx: int, window: int = 3) -> bool:
        """候选标题行 lines[idx] 之后 1~window 个非空行内是否出现字段块开头。

        安全约束：避免将散文中的 `如同 X (Y) 一般` 误升级为标题。
        """
        seen = 0
        for j in range(idx + 1, min(idx + window + 1, len(lines))):
            stripped = lines[j].strip()
            if not stripped:
                continue
            if any(stripped.startswith(h) for h in self._TITLE_FIELD_HEAD):
                return True
            seen += 1
            if seen >= window:
                return False
        return False

    def _normalize_spell_titles(self, text: str) -> str:
        """KN016：8 簇标题形态归一化为标准 **中文 (English)** 单行。

        簇：
          E  闭合断裂跨行 + 页码尾巴：`**X (Y) **\\n\\n**\\n<page>` → 标准形 + 页码行转正文
          H  缺闭合粗体：`**X (Y)` → `**X (Y)**`
          B  跨行粗体：`**X\\n(Y)**` → `**X (Y)**`
          C  标题粘句尾：`…**X (Y)**` → `…\\n**X (Y)**`
          D  标题带致谢/出自尾巴：`**X (Y)**｜致谢 …` → `**X (Y)**\\n致谢 …`
          I  嵌套粗体：`X (**Y**)**` / `X（**Y**）**` → `**X (Y)**`

        安全约束：所有簇共用 — 候选标题行之后 1~3 个非空行内必须出现字段块开头
        （**学派：** / **等级：** / 规范后等价别名），否则不触发归一化（方案 §3.2）。
        不动 split_into_items 的标题匹配逻辑（红线）。
        """
        # ---- I 簇：嵌套粗体去嵌套（最早处理，避免被其他簇吃掉）----
        # X (**Y**)**  /  X（**Y**）**  →  **X (Y)**  /  **X（Y）**
        # 必须消耗尾部 **，否则 split_into_items 会把残留 ** 留在行尾导致匹配失败
        # KN023（2026-08-01，page_277 实证）：OA 标题形态 `**X（**Y**）**`
        # （中文名自身也被 ** 包裹）必须由本簇先行消耗——否则前置 ** 成孤岛
        # （**刺**），反向兜底正则随后把 `**刺**X (Y)**` 整体当非法包裹吞掉"刺"
        # （刺青魔法 → 青魔法）。行首 ** 形态优先匹配，裸形态维持原逻辑。
        text = re.sub(
            r'^\s*\*\*([^\s\*\n（(]{1,40})\s*[（(]\*\*([^*\n]+)\*\*[）)]\*\*',
            r'**\1 (\2)**',
            text,
            flags=re.MULTILINE,
        )
        text = re.sub(
            r'(?<![\*（(])([^\s\*\n（(]{1,40})\s*[（(]\*\*([^*\n]+)\*\*[）)]\*\*',
            r'**\1 (\2)**',
            text,
        )
        # 反向故障兜底：**<任意非星号内容>**<title>** 整段非法包裹 →
        # 保留 title，丢弃前面的非法 bold 包裹（方案 §2.2）
        # 反例：spell_动物档案AArch_法术_0008 — title 被污染成整句描述
        # R1 fix：group2 的 ** 后面不能是空格（否则会把 **学派：** 咒法系 (召唤)
        # 的字段值误判为标题，丢弃学派：前缀）
        # KN023（2026-08-01）：group1 原为 [^*]*，可跨行——`**` 开头的长正文行
        # + 下一行标题被整体匹配，整段正文被删只留标题（Spell OA 169 处）。
        # 收窄为 [^\n*]* 仅同行匹配，跨行不触发。
        # 再收窄（2026-08-01，page_782/787 实证）：group1 排除括号字符——
        # 合法标题 **中文 (English)** 自身含括号，若被 group1 吞下且同行正文
        # 后续出现 (...)** 形态（如 **先决条件 (Requirements)**），整段误吞
        # 标题（灰花匠/卡利斯拉德先知 职业条目）。group1 不含括号时原始
        # 污染场景（动物档案AArch_法术_0008）仍触发。
        text = re.sub(
            r'^\*\*([^\n*（(]*)(\*\*(?!\s)[^*]+?\s*\([^)]+\)\*\*)',
            r'\2',
            text,
            flags=re.MULTILINE,
        )

        # ---- E / H / B / D / C 簇：基于行扫描的统一处理 ----
        lines = text.split("\n")
        out: list[str] = []
        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.rstrip()

            # ---- E 簇：`**X (Y) **\n\n**\n<page>` 合并闭合 + 页码行剥离 ----
            m_e = re.match(r'^\*\*([^*\n]+?)\s*\(([^)]+)\)\s*\*\*\s*$', line)
            if m_e and i + 2 < len(lines):
                next_blank = lines[i + 1].strip() == ""
                third_open = lines[i + 2].strip().startswith("**") and not lines[i + 2].strip().startswith("**学派")
                if next_blank and third_open:
                    # 找后续首个非空非 ** 开头的页码/致谢行（≤3 行内）
                    page_idx = None
                    for j in range(i + 2, min(i + 6, len(lines))):
                        s = lines[j].strip()
                        if not s:
                            continue
                        if s.startswith("**") and not s.startswith("**学派") and not s.startswith("**等级"):
                            # 该行可能是空的 **** 或 致谢粗体
                            if s in ("**", "****"):
                                continue
                            page_idx = j
                            break
                        page_idx = j
                        break
                    if page_idx is not None and self._has_field_head_after(lines, page_idx):
                        # 合并：**X (Y) ** + ** + 页码行 → **X (Y)** + 页码行（不删信息）
                        cn, en = m_e.group(1).strip(), m_e.group(2).strip()
                        out.append(f"**{cn} ({en})**")
                        # 把 *** 等空粗体行跳过
                        j = i + 2
                        while j < page_idx:
                            if lines[j].strip() not in ("**", "****", ""):
                                # 中间非空非粗体行也保留为正文
                                out.append(lines[j])
                            j += 1
                        # 页码行转正文
                        out.append(lines[page_idx])
                        # 跳过空粗体（**/****）和 page_idx 之前的空行
                        i = page_idx + 1
                        continue

            # ---- H 簇：`**X (Y)` 缺闭合 → 补 `**` ----
            m_h = re.match(r'^\*\*([^*\n]+?)\s*\(([^)]+)\)\s*$', line)
            if m_h and self._has_field_head_after(lines, i):
                cn, en = m_h.group(1).strip(), m_h.group(2).strip()
                out.append(f"**{cn} ({en})**")
                i += 1
                continue

            # ---- B 簇：`**X\n(Y)**` 跨行合并 ----
            m_b_top = re.match(r'^\*\*([^*\n]+?)\s*$', line)
            if m_b_top and i + 1 < len(lines):
                m_b_bot = re.match(r'^\s*\(([^)\n]+)\)\*\*\s*$', lines[i + 1])
                if m_b_bot and self._has_field_head_after(lines, i + 1):
                    cn, en = m_b_top.group(1).strip(), m_b_bot.group(1).strip()
                    out.append(f"**{cn} ({en})**")
                    i += 2
                    continue

            # ---- D 簇：`**X (Y)**｜致谢 …` 标题与尾巴拆开 ----
            # 标题已成形但同行有致谢/出自标注 → 标题独立成行，尾巴转下一行正文
            m_d = re.match(r'^(\*\*[^*]+\s*\([^)]+\)\*\*)([｜|].+)$', line)
            if m_d and self._has_field_head_after(lines, i):
                out.append(m_d.group(1))
                tail = m_d.group(2).lstrip("｜| ")
                if tail:
                    out.append(tail)
                i += 1
                continue

            out.append(raw)
            i += 1

        text = "\n".join(out)

        # ---- C 簇：标题粘句尾 — 行末 …**X (Y)** 紧跟字段块 → 在 ** 前插换行 ----
        # 必须在行扫描后做（行扫描已规范簇 D/I 等形态）
        # R1 fix：标题后紧跟的 ** 不能以空格开头（否则是把字段值误判为标题，
        # 如 **学派：** 咒法系 (召唤)**环位：** → ** 咒法系 (召唤)** 被 C 簇错误拆分）
        text = re.sub(
            r'([。！？，；：]|[^\n])\s*(\*\*(?!\s)(?!该法术|这法术|此法术)[^*]+\s*\([^)]+\)\*\*)(\s*\n\s*\*\*(?:学派|等级|环位)[：:])',
            r'\1\n\2\3',
            text,
        )

        # ---- J 簇（R1）：裸标题 + 字段同行 — OA 格式 — 中文（English）**field：** → **中文 (English)**\n**field：** ----
        # OA/ARG/APG 次级法术标题无 ** 包裹，紧接字段头同行。
        # 前向约束：后接规范字段开头（学派/等级/环位）；仅在行首或空白后触发。
        # KN019 第二类（2026-08-04）：组1 排除中文句号「。」——page_1177 页引言
        # 「施法者们在烦扰别人上创意无限。**【死灵】(Calamitous Flailing)」被误判
        # 裸标题包星（正文句含句号，合法标题名不含句号）。
        text = re.sub(
            r'(?:^|\n)([^\n*。]{1,40}?)[（）(]([A-Za-z\s\'\-，,]+)[（）)]\**\s*(\*\*(?:学派|等级|环位|施法|成分|范围|目标|持续|豁免|法术抗力))',
            r'\n**\1 (\2)**\n\3',
            text,
            flags=re.MULTILINE,
        )

        # ---- K 簇（R1/R2）：英文名前缀 + 裸双行标题 — UM 格式 —- English name\n\n中文\n(English)\n\n**field：** ----
        # Spell UM 次级法术：先合并 English name + 中文 + (English) → **中文 (English)**
        text = re.sub(
            r'(?:^|\n)([A-Z][A-Za-z\s\'\-]+)\s*\n+\s*'
            r'([^\n*]{1,40})\s*\n\s*'
            r'\(([A-Za-z\s\'\-]+)\)\s*\n+'
            r'(?=\*\*(?:学派|等级|环位))',
            r'\n**\2 (\3)**\n',
            text,
            flags=re.MULTILINE,
        )

        return text

    def split_into_items(self, text: str, *, source_name: Optional[str] = None) -> List[dict]:
        """将法术文本拆分为结构化条目列表。

        KN017：增加 source_name 仅用于丢失告警（可观测性，不改 split 行为）。
        当 current_name is None 且被跳过的段落非空且含字段信号
        （**学派：** / **环位：** / **等级：**），输出 warning 日志。
        """
        items = []
        # 以 **中文 (English)** 行为法术分隔符
        spell_pattern = re.compile(
            # R3 N2 防护：散文起始词（"该法术的功能如同..."）不得成为 chunk 标题
            r'^\*\*(?!该法术|这法术|此法术|如同)([^*]+)\s*\(([^)]+)\)\*\*\s*$',
            re.MULTILINE
        )

        # 字段信号正则（用于 KN017 丢弃告警判定）
        _FIELD_SIGNAL_RE = re.compile(r'\*\*(?:学派|环位|等级)(?:[：:]|\s|\n|$)')

        def _warn_dropped(start: int, end: int, kind: str) -> None:
            """当被丢弃段含字段信号时输出 warning。仅可观测性。"""
            dropped_text = "\n".join(lines[start:end]).strip()
            if not dropped_text or not _FIELD_SIGNAL_RE.search(dropped_text):
                return
            preview = dropped_text[:80].replace("\n", " ")
            logger.warning(
                "[split_drop] file=%s kind=%s preview=%r",
                source_name or "<unknown>",
                kind,
                preview,
            )

        # 简单分割：按法术名行切分
        lines = text.splitlines()
        current_start = None
        current_name = None
        current_name_en = None  # 在循环外初始化，避免 UnboundLocalError

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 章节标题边界
            if stripped.startswith('## ') or stripped.startswith('### '):
                if current_name is not None:
                    items.append({
                        "name": current_name,
                        "name_en": current_name_en,
                        "text": "\n".join(lines[current_start:i]).strip(),
                    })
                else:
                    # KN017：current_name is None 时，被跳过段（current_start~i）含字段信号 → 告警
                    _warn_dropped(current_start, i, "chapter_boundary")
                current_name = None
                current_name_en = None
                current_start = i + 1
                continue

            # Phase 1.5：page_625 A-Z 索引（**A**/**B**/...）排除
            # 不再误把字母标题识别为 chunk 标题边界，也不让管道表行
            # 通过 spell_pattern 误识别为法术条目。
            if re.match(r'^\*\*[A-Z]\*\*\s*$', stripped):
                # 当前 spell 收口，把累积的 chunk 先压入
                if current_name is not None:
                    items.append({
                        "name": current_name,
                        "name_en": current_name_en,
                        "text": "\n".join(lines[current_start:i]).strip(),
                    })
                    current_name = None
                    current_name_en = None
                # KN017：A-Z 索引后 current_name 为 None，被丢弃段含字段信号 → 告警
                _warn_dropped(current_start, i, "az_index")
                # 视 A-Z 行为章节边界：标记 current_start 到该字母之后
                # 的非表格行（让管道表被并入下一个真标题，或被自然吞掉）
                current_start = i + 1
                continue

            m = spell_pattern.match(stripped)
            if m:
                # 过滤分组标题
                new_name = m.group(1).strip()
                new_name_en = m.group(2).strip()
                # KN136：拒收 `[PZO` 开头的书目引用伪标题
                # （`**[PZO9202 神与魔法（Gods and Magic）](url)**` 形态——
                # a46e68f 收窄 _strip_url_lines 后，锚=中文正文的链接行保留，
                # page_1363 该行被误切为法术标题 +1 chunk 并顺移后 128 个 id）
                if new_name.startswith('[PZO'):
                    continue
                # 防御性检查：标题为空（如 **   (D)** 被误匹配为法术标题）→ 跳过
                if not new_name:
                    continue
                # 防御：括号内容与标题均不含英文字母 → 字段值误判为法术标题，跳过
                # （如 **语言，姿势，材料（一株蒲公英的茎秆）**、**意志无效（无害）** 等）
                # ISG 神祇法术（**夜莺之型 Aspect of the Nightingale（莎琳）**）
                # 英文在标题中而非括号中，通过 has_en_in_title 放行
                # 纯 ASCII 括号内容（如 N/A）即使 <3 连续字母也放行（EMH 占位符等）
                has_no_cjk = not bool(re.search(r'[一-鿿]', new_name_en))
                has_en3 = bool(re.search(r'[A-Za-z]{3}', new_name_en))
                has_en_in_parens = has_en3 or (has_no_cjk and bool(re.search(r'[A-Za-z]', new_name_en)))
                has_en_in_title = bool(re.search(r'[A-Za-z]', new_name))
                if not has_en_in_parens and not has_en_in_title:
                    continue
                if (new_name.endswith("法术") and new_name_en.isupper()):
                    if current_name is not None:
                        items.append({
                            "name": current_name,
                            "name_en": current_name_en,
                            "text": "\n".join(lines[current_start:i]).strip(),
                        })
                    else:
                        # KN017：分组标题视为丢弃，告警
                        _warn_dropped(current_start, i, "group_header")
                    current_name = None
                    current_name_en = None
                    current_start = i + 1
                    continue
                if current_name is not None:
                    items.append({
                        "name": current_name,
                        "name_en": current_name_en,
                        "text": "\n".join(lines[current_start:i]).strip(),
                    })
                else:
                    # KN017：新标题出现时 current_name 仍为 None，丢弃段告警
                    _warn_dropped(current_start, i, "new_title")
                current_name = m.group(1).strip()
                current_name_en = m.group(2).strip()
                current_start = i

        # 最后一条
        if current_name is not None:
            items.append({
                "name": current_name,
                "name_en": current_name_en,
                "text": "\n".join(lines[current_start:]).strip(),
            })

        return items

    # ---- 法术特有字段解析 ----

    @staticmethod
    def parse_school_abbreviation(school_cn: str) -> str:
        """学派简称 → 全称（如 咒法→咒法系）"""
        mapping = {
            "咒法": "咒法系",
            "变化": "变化系",
            "死灵": "死灵系",
            "塑能": "塑能系",
            "幻术": "幻术系",
            "附魔": "附魔系",
            "预言": "预言系",
            "防护": "防护系",
            "咒法系": "咒法系",
            "变化系": "变化系",
            "死灵系": "死灵系",
            "塑能系": "塑能系",
            "幻术系": "幻术系",
            "附魔系": "附魔系",
            "预言系": "预言系",
            "防护系": "防护系",
        }
        return mapping.get(school_cn.strip(), school_cn.strip())

    @staticmethod
    def parse_spell_level(level_str: str) -> List[dict]:
        """
        解析环位字符串。

        示例：
          "魔战士 2, 术士/法师 2" → [{"class": "魔战士", "level": 2}, {"class": "术士/法师", "level": 2}]
          "魔战士 2，术士/法师 2" → 同上（全角逗号兼容）
          "3" → [{"class": None, "level": 3}]
          "审判者 2 领域 机运领域 2" → [{"class": "审判者", "level": 2}, {"class": "机运领域", "level": 2}]
          "召唤师 1 领域 家园子域 1" → [{"class": "召唤师", "level": 1}, {"class": "家园子域", "level": 1}]
          "邪恶领域 2" → [{"class": "邪恶领域", "level": 2}]

        复合职业（如 术士/法师）的 / 拆分不在本函数处理，由 _extract_spell_level 调用方负责。
        """
        if not level_str:
            return []

        # 预处理：替换换行为空格，全角逗号/顿号为半角逗号，剥离 ** 包裹
        cleaned = (level_str
                   .replace('\n', ' ')
                   .replace('，', ',')
                   .replace('、', ',')
                   .replace('**', ' ')
                   .strip())

        items = []
        parts = [p.strip() for p in cleaned.split(",")]
        for part in parts:
            if not part:
                continue

            # F3: 复合 part "class N 领域|subdomain N"
            # 提取 class 部分；subdomain 部分（领域/子域名）不放入 classes，
            # 交给 _extract_domains_from_level / _extract_subdomains_from_level 处理。
            # 例 "审判者 2 领域 机运领域 2" → class=审判者(2)
            # 例 "召唤师 1 领域 家园子域 1" → class=召唤师(1)
            m = re.match(
                r'^(.+?)\s+(\d+)\s+(?:领域|子域)\s+(.+?)\s+(\d+)\s*$',
                part
            )
            if m:
                cls_name = m.group(1).strip()
                cls_lv = int(m.group(2))
                items.append({"class": cls_name, "level": cls_lv})
                continue

            # F3: 纯领域/子域条目（如 "邪恶领域 2"）→ 不放入 class，
            # 让 _extract_domains_from_level / _extract_subdomains_from_level 单独处理
            if re.match(r'^(.+(?:领域|子域))\s+(\d+)\s*$', part):
                continue

            # 标准 "class N"
            m = re.match(r'(.+?)\s+(\d+)\s*$', part)
            if m:
                items.append({"class": m.group(1).strip(), "level": int(m.group(2))})
                continue

            # KN017：无空格兜底 — 源数据 "法师2" / "术士/法师2" 形态
            # PF 中文职业名无数字结尾，且字符集 `[一-鿿/]` 不会误匹配非职业串（如 "1分钟/等级" 含数字开头）
            m = re.match(r'^([一-鿿][一-鿿/]*?)(\d+)$', part)
            if m:
                items.append({"class": m.group(1).strip(), "level": int(m.group(2))})
                continue

            # 纯数字
            try:
                items.append({"class": None, "level": int(part)})
            except ValueError:
                pass

        return items

    @staticmethod
    def parse_descriptors(text: str) -> List[str]:
        """从文本中提取描述符标签。

        示例：
          "**描述：** 该法术造成 [酸] 伤害" → ["acid"]
        """
        mapping = {
            "酸": "acid",
            "电": "electricity",
            "火": "fire",
            "寒": "cold",
            "力场": "force",
            "音波": "sonic",
            "光": "light",
            "暗": "darkness",
            "邪恶": "evil",
            "善良": "good",
            "秩序": "lawful",
            "混乱": "chaotic",
            "恐惧": "fear",
            "心灵": "mind-affecting",
            "依赖语言": "language-dependent",
            "死亡": "death",
        }
        descriptors = []
        for cn, en in mapping.items():
            if f"[{cn}]" in text:
                descriptors.append(en)
        return descriptors
