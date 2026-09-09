# PF 数据清洗 - 详细迭代过程

> 所有脚本位于 `pf_data/` 目录下。

## 完整脚本清单

### 目录提取脚本（版本迭代）

| 脚本 | 版本 | 状态 | 说明 |
|------|------|------|------|
| `extract_chm_toc.py` | v1 | 初始 | 初始提取尝试 |
| `extract_full_toc.py` | v2 | 迭代 | 改进提取逻辑 |
| `extract_full_toc_v2.py` | v3 | 迭代 | 修正深度计算 |
| `extract_full_toc_v3.py` | v4 | 迭代 | 修正范围计算 |
| `extract_full_toc_v4.py` | v5 | 迭代 | 修正分组逻辑 |
| `extract_full_toc_v5.py` | v6 | 迭代 | 接近正确 |
| `extract_full_toc_v6.py` | v7 | **最终** | 正确版本 |

### 层级分析脚本

| 脚本 | 说明 |
|------|------|
| `extract_first_level.py` | 提取 L1（初始错误版本） |
| `extract_l1_correct.py` | 提取 L1（修正版本） |
| `extract_all_levels.py` | 提取所有层级 |
| `extract_occupation_l2.py` | 提取 L2（初始） |
| `extract_occupation_l2_correct.py` | 提取 L2（修正） |
| `extract_occupation_l2_fixed.py` | 提取 L2（最终） |
| `extract_occupation_l3.py` | 提取 L3 |
| `extract_occupation_l3_fixed.py` | 提取 L3（修正） |
| `extract_occupation_l4.py` | 提取 L4 |
| `extract_occupation_l4_by_parent.py` | 提取 L4（按父项） |
| `extract_occupation_l5.py` | 提取 L5 |
| `extract_occupation_by_parent.py` | 按父项提取（初始） |
| `extract_occupation_by_parent_fixed.py` | 按父项提取（修正） |

### 内容分析脚本

| 脚本 | 说明 |
|------|------|
| `analyze_crb.py` | 分析核心规则（初始） |
| `analyze_crb_fixed.py` | 分析核心规则（修正） |
| `analyze_spell.py` | 分析法术结构 |
| `analyze_all_l1.py` | 分析所有 L1 |
| `find_paths.py` | 查找路径 |
| `check_local.py` | 检查本地文件 |

### 转换脚本

| 脚本 | 说明 |
|------|------|
| `chm_to_md_converter.py` | 初版转换 |
| `chm_to_md_converter_v2.py` | **最终转换脚本** |

## 错误与纠正记录

### 错误 1：L1 数量错误
- **错误**：认为只有 4 个 L1
- **原因**：只分析了文件开头部分，没有遍历完整文件
- **纠正**：实际有 17 个 L1，通过完整遍历确认

### 错误 2：法术位置错误
- **错误**：认为法术的子项在核心规则下
- **原因**：混淆了嵌套层级
- **纠正**：法术是独立的 L1

### 错误 3：深度计算错误
- **错误**：从局部位置开始计算深度
- **原因**：没有从根 `<UL>` 开始
- **纠正**：必须从根 `<UL>`（line 15）开始，初始深度为 0

### 错误 4：范围计算错误
- **错误**：用 `</UL>` 匹配来结束范围
- **原因**：多个 `</UL>` 可能连续出现
- **纠正**：用下一个同级项的开始位置作为当前项的结束位置

### 错误 5：长文档搜索卡顿
- **错误**：在同一区域反复读取 < 20 行
- **原因**：没有扩大搜索范围
- **纠正**：单次读取 ≥ 100 行，卡顿超过 3 次换策略

## 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-15 03:17 | README_CHM_CONVERT.md 创建（子代理任务指导） |
| 2026-06-15 03:19 | 转换开始 |
| 2026-06-15 03:21 | 转换完成，1993 个文件成功转换 |
| 2026-06-15 04:31 | 任务报告提交 |
| 2026-06-15 05:39 | 资产清单整理完成 |

## 关键决策

1. **保留迭代痕迹**：所有中间版本脚本保留，不删除
2. **分层记录**：核心资产放 `pf_data_cleanup.md`，详细过程放本文档
3. **上下文隔离**：本文档不进入 MEMORY.md，按需加载

---

*记录时间：2026-06-15*
