# PF 数据清洗项目

## 目标

- **一期**：精确规则查询（基于资料库内容，不推测）
- **二期**：车卡辅助 + DM 可行性建议

## 核心资产

所有资产位于 `pf_data/` 目录下。

### 文档

| 文档 | 说明 |
|------|------|
| `CHM_FULL_TOC.md` | 完整目录索引（2376 项） |
| `CHM_FULL_TOC_WITH_LEVELS.md` | 带 L1-L5 层级标注 |
| `CHM_STRUCTURE_ANALYSIS.md` | 目录结构分析规律 |
| `README_CHM_CONVERT.md` | CHM 转换说明（子代理任务文档） |

### 脚本

| 脚本 | 说明 |
|------|------|
| `chm_to_md_converter_v2.py` | 最终转换脚本 |
| `extract_full_toc_v6.py` | 最终 TOC 提取 |

### 数据

| 位置 | 内容 |
|------|------|
| `~/.openclaw/workspace/pf_rules_md/` | 2156 个 Markdown 文件 |
| `~/.openclaw/workspace/pf_rules/` | 原始 CHM 解压后的 HTML |

**数据现状：**
- 已分类：15 个文件夹（对应 L1 目录）
- 未分类：约 2141 个在根目录

## 关键结论

- L1 = 17 个（非 4 个）
- 层级计算：`ul_depth == 1` 为 L1
- 冒险之路属于「未整理」L1 下的 L2

## 详细迭代过程

如需查看完整版本迭代、错误纠正记录，查阅 `pf_data/pf_data_cleanup_detail.md`

---

*记录时间：2026-06-15*
