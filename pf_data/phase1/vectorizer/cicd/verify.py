"""verify.py — cicd verify 子命令：完整验证链统一编排（v2.2 决策 B）

单一事实源：pytest 全量 → pipeline（含 finalize）→ verify 公共框架 →
数据不变量闸口，本地与 CI 同一命令同一结果（消除 regen 244 vs CI 530
验收面漂移，B1/决策 B 双教训）。

执行方式：subprocess 链（每步独立进程，退出码明确，输出与 CI 完全一致）。
步骤依赖 phase1 相对路径（input pf_rules_md_organized / md_mapping.json 等），
调用方须以 phase1 为 cwd（regen 脚本 cd、CI working-directory 均已是）。

用法：python3 -m vectorizer.cicd verify --category feat
"""
import argparse
import subprocess
import sys
from pathlib import Path

# phase1 根 = vectorizer/cicd/verify.py → parent×3
PHASE1 = Path(__file__).resolve().parent.parent.parent

# 类目装配表：新增类目 = 加一行（决策 D 矩阵同源）
# tests = 该类目验收面测试收集（决策 B 原案：--category 只收集该类目相关测试，
# 不跑其他类目专属——法术 test_spell_metadata_v0_3.py 属法术类目验收面）
# invariants = 命令 + 参数列表（首个元素为脚本名）；feat 用默认参数，
# race 显式传参（book '?' 1450 等设计保留口径，见 verify_data_invariants.py 头注释）
CATEGORIES = {
    "feat": {
        "output_dir": "vectorizer/output/专长",
        "verify_module": "vectorizer.verify.verify_feats",
        "invariants": ["verify_data_invariants.py"],
        "tests": [
            "test_category_*",                    # A~G 通用（所有类目验收面共用）
            "test_verify_base.py",                # verify 公共框架
            "test_cicd.py",                       # 编排自身
            "test_feat_*",                        # feat 专属格式/处理器
            "test_fc_match.py",                   # feat 判别器
            "test_per_file_chunk_counts.py",      # feat prepare 普查
            "test_postprocess.py",                # feat finalize 链
        ],
    },
    "race": {
        "output_dir": "vectorizer/output/种族",
        "verify_module": "vectorizer.verify.verify_races",
        "invariants": [
            "verify_data_invariants.py",
            "--chunks", "vectorizer/output/种族/chunks.jsonl",
            "--max-empty", "0",
            "--oversize-limit", "5000",
            "--max-oversize", "3",
            "--min-total", "1800",
            "--main-component", "alt_trait",
            "--min-main-count", "300",
            "--max-book-unknown", "2483",  # KN111（KN106 同口径）：9 页 859 全 '?' → 1518+859=2377；KN130（2026-08-04）page_11 三族表行恢复 +6（page_11 汇总页 70→76 全 '?' 设计保留）；KN131（2026-08-04）page_398 补星找回 15 条（源文件无 '> 来源：' 块、内容跨 ARG/ISR/BoS 多来源无法单一归书，'?' 设计保留同口径）；KN133（2026-08-04）page_815 组标题「替换+2天生护甲」+1（page_815 全文件无来源行 33 条 '?' 设计保留同口径）→ page_398 全量修复 35→42 条 +7（同 KN131 口径：源文件无 '> 来源：' 块、多来源无法单一归书，'?' 设计保留）→ page_806 8 亚种标题拆行 1→10 条 +9（怪物种族页无来源行，KN111 设计保留同口径）；**2026-08-05 首次双顶格审议**：注释链合计 2415 ↔ 实测 2483 缺口 68（含本注释 859/2377 与 KN111 文档 845/2352 的 25 基线毛刺）——定性为 KN133~135 各修复批次附带 '?' 增长被当时余量吸收未逐条登记（13d5846 半身人共享特性恢复、51d9e02 page_10 组标题归 race_intro 等）；文件级全量对账证实 55 个 '?' 文件全在 KN106/KN110/KN111 已裁定家族内、toc 兜底 100% 非空、越界 0，存量合法不调参；维持顶格不预放（棘轮设计，用户拍板），下一带 '?' 增量任务开工前须再审）
            "--max-toc-empty", "0",
        ],
        "tests": [
            "test_category_*",                    # A~G 通用（所有类目验收面共用）
            "test_verify_base.py",                # verify 公共框架
            "test_cicd.py",                       # 编排自身
            "test_race_*",                        # race 专属格式/处理器/finalize 链
        ],
    },
    "trait": {
        "output_dir": "vectorizer/output/背景特性",
        "verify_module": "vectorizer.verify.verify_traits",
        "invariants": [
            "verify_data_invariants.py",
            "--chunks", "vectorizer/output/背景特性/chunks.jsonl",
            "--max-empty", "18",       # trait_intro 章节介绍段空 text（KN085 同口径）
            "--oversize-limit", "5000",
            "--max-oversize", "0",
            "--min-total", "1100",
            "--main-component", "trait",
            "--min-main-count", "990",  # 6eeb48b 守卫剔除 13 个「出自…」伪条目后真值 996
                                        #（伪条目原计入 1009），门随真值收敛
            "--max-book-unknown", "205",  # 基础页 page_150~158 无来源条目 181 + page_1579
                                          # 编注形态 15 + 典范背景 6（「出自」行内形态，书
                                          # Chronicle of Legends 不在 50 书权威表）+ 坐骑
                                          # 背景 1（动物坐骑无来源行）——'?' 设计保留同
                                          # KN106 口径（2026-08-06 参数审议：203 实测 + 2
                                          # 余量，KN137 家族增量；见 已知问题记录.md KN137）
            "--max-toc-empty", "0",
        ],
        "tests": [
            "test_category_*",                    # A~G 通用（所有类目验收面共用）
            "test_verify_base.py",                # verify 公共框架
            "test_cicd.py",                       # 编排自身
            "test_trait_*",                       # trait 专属格式/处理器
        ],
    },
    "equipment": {
        "output_dir": "vectorizer/output/装备",
        "verify_module": "vectorizer.verify.verify_equipment",
        "invariants": [
            "verify_data_invariants.py",
            "--chunks", "vectorizer/output/装备/chunks.jsonl",
            "--max-empty", "115",      # 实测 113：C 形态价格表行 + A 形态无描述条目
                                       #（title/价格可检索），+2 余量
            "--oversize-limit", "5000",
            "--max-oversize", "25",    # 实测 21：巨型聚合条目/规则导言块（page_234 无位置
                                       # 奇物 17538、page_210 工具包 17039、page_214 intro
                                       # 11022 等全定性，KN186 登记）
            "--min-total", "4500",
            "--main-component", "gear",
            "--min-main-count", "2200",  # 实测 gear 2538
            "--max-book-unknown", "5",  # 超游神器 5 条 d20pfsrd 通用来源（专属表登记 '?'，
                                        # toc 兜底 100% 非空）——顶格不预放（棘轮设计）
            "--max-toc-empty", "0",
        ],
        "tests": [
            "test_category_*",                    # A~G 通用（所有类目验收面共用）
            "test_verify_base.py",                # verify 公共框架
            "test_cicd.py",                       # 编排自身
            "test_equipment_*",                   # equipment 专属格式/处理器
        ],
    },
    "rule": {
        "output_dir": "vectorizer/output/规则",
        "verify_module": "vectorizer.verify.verify_rule",
        "invariants": [
            "verify_data_invariants.py",
            "--chunks", "vectorizer/output/规则/chunks.jsonl",
            "--max-empty", "1",       # page_508 空文件唯一（CHM 法术效果图
                                      # 图片丢失，KN197 豁免登记）
            "--oversize-limit", "5000",
            "--max-oversize", "7",    # KN203 全定性登记：4 单行无界（page_955/
                                      # page_961 续2/运作游戏/魔宠手记FF 续23）+
                                      # page_517 预拆后超长表行 + page_400 整表
                                      # 不拆 + page_960 标题行混合正文
            "--min-total", "7000",    # 现量 7847（est 7385 冻结口径 + Δ462 全定性；
                                      # 9378→9377 KN206 伪段净清除 → 9366 批次 A →
                                      # 9256 批次 B → 7847 批次 C 字段行并入合法减少，
                                      # KN210~220），门随真值收敛（trait KN139 先例），
                                      # -10% 余量防正常波动，防大规模丢失护栏
            "--main-component", "rule_section",
            "--min-main-count", "6000",  # rule_section 现量 6759（同上收敛口径）
            "--max-book-unknown", "238",  # KN195 page_320 神祇扩展表混排 101 +
                                          # KN196 作祟汇总 90 = 191，+5 余量；
                                          # KN203 page_320 预拆扩散 +94 已含；
                                          # KN211（2026-08-09）表格行独立条目后
                                          # page_320 '?' 101→143（每行多来源
                                          # 混排无法单一归书，设计保留同口径），
                                          # 233 = 143+90，+5 余量——
                                          # '?' 家族逐次 KN 登记（棘轮不预放）
            "--max-toc-empty", "0",
        ],
        "tests": [
            "test_category_*",                    # A~G 通用（所有类目验收面共用）
            "test_verify_base.py",                # verify 公共框架
            "test_cicd.py",                       # 编排自身
            "test_rule_*",                        # rule 专属格式/处理器
        ],
    },
    "spell": {
        # ⚠️ input_dir 覆盖：spell 源文件集中在 法术/ 子目录。根目录全树遍历时
        # _spell_file_condition 会对索引/列表文件重复 dispatch（Spell CRB 等双份，
        # 实测 6145≠4172 索引双份），必须传子目录（2026-09-01 阶段二实测教训）。
        "input_dir": "pf_rules_md_organized/法术",
        "output_dir": "vectorizer/output/法术",
        "verify_module": "vectorizer.verify.verify_spells",
        "invariants": [
            "verify_data_invariants.py",
            "--chunks", "vectorizer/output/法术/chunks.jsonl",
            "--max-empty", "0",          # 实测空 text 0
            "--oversize-limit", "5000",
            "--max-oversize", "2",       # 实测 2 全定性：spell_index 主索引表 43085
                                         # + 任务与战役_法术 典礼 5244（长条目录条目）
            "--min-total", "3750",       # 现量 4172（KN136 修复后新基线），-10% 余量
            "--main-component", "spell",
            "--min-main-count", "3750",  # spell 主检索条目现量 4171，-10% 余量
            "--max-book-unknown", "3",   # Pathfinder_Comics:10 3 条（召唤犬魔 I/II、
                                         # 恶魔梦境）非 50 书权威表来源，KN106 口径设计保留
            "--max-toc-empty", "2124",   # SpellIndexProvider 生成列表索引 chunk
                                         # （Spell CRB/APG/UM…37 doc）无源页面 toc，
                                         # spell 模块早于 toc 回填框架构建的历史设计态，
                                         # 非回归——闸口只拦新增（棘轮口径）
        ],
        "tests": [
            "test_category_*",            # A~G 通用（所有类目验收面共用）
            "test_verify_base.py",        # verify 公共框架
            "test_cicd.py",               # 编排自身
            "test_spell_metadata_v0_3.py",  # spell 专属格式/处理器/基线（KN019/KN136）
        ],
    },
    "profession": {
        "output_dir": "vectorizer/output/职业",
        "verify_module": "vectorizer.verify.verify_profession",
        "invariants": [
            "verify_data_invariants.py",
            "--chunks", "vectorizer/output/职业/chunks.jsonl",
            "--max-empty", "0",          # 实测空 text 0（CP3 真重跑）
            "--oversize-limit", "5000",
            "--max-oversize", "15",      # 实测 15：全定性合法大块（女巫/审判者/术士
                                         # 法术列表、骑将长能力、异能选集PA_变体概述、
                                         # 技能解放、妖精之击ACG 25163 最大等），
                                         # KN 口径同 rule KN203 全定性登记
            "--min-total", "12500",      # 现量 13922（CP2 after 新基线；before 13895，
                                         # KN222 找回 +27），-10% 余量防正常波动，
                                         # 防大规模丢失护栏（rule/trait 收敛口径）
            "--main-component", "class_feature",
            "--min-main-count", "9500",  # class_feature 现量 10572（分布 overview 706 /
                                         # archetype 2409 / feature 10572 / rec 235），
                                         # -10% 余量
            "--max-book-unknown", "0",   # 实测 book '?' 0（9 Provider 链来源解析全覆盖，
                                         # 无 '?' 设计保留）——顶格不预放（棘轮设计）
            "--max-toc-empty", "0",      # 实测 chm_toc_path 空 0
        ],
        "tests": [
            "test_category_*",            # A~G 通用（所有类目验收面共用）
            "test_verify_base.py",        # verify 公共框架
            "test_cicd.py",               # 编排自身
            "test_profession_*",          # profession 专属格式/处理器/校验
        ],
    },
}


def collect_test_files(category: str) -> list:
    """类目验收面测试收集：装配表 tests glob 展开为文件列表（相对 vectorizer/tests/）。

    每个模式必须至少命中 1 个文件——glob 拼写错误在收集期 raise（ValueError）
    显形，防止静默漏测。
    """
    spec = CATEGORIES.get(category)
    if spec is None:
        raise KeyError(f"未知类目 {category!r}，已注册: {list(CATEGORIES)}")
    tests_dir = PHASE1 / "vectorizer" / "tests"
    files = []
    for pattern in spec["tests"]:
        matches = sorted(tests_dir.glob(pattern))
        if not matches:
            raise ValueError(f"测试模式 {pattern!r} 未匹配任何文件（类目 {category}）")
        files.extend(matches)
    return files


def _step(cmd: list, category: str, step_name: str) -> None:
    """顺序执行验证链一步；失败即整链失败（退出码透传）"""
    print(f"\n===== [{step_name}] {category} =====")
    r = subprocess.run(cmd, cwd=PHASE1)
    if r.returncode != 0:
        sys.exit(f"❌ {step_name} 失败（退出码 {r.returncode}），验证链终止")


def run_chain(category: str) -> None:
    """执行完整验证链（subprocess 四步，失败即终止）。解析与执行分离：
    __main__ 子命令与 python -m 直跑共用本函数。"""
    spec = CATEGORIES.get(category)
    if spec is None:
        sys.exit(f"❌ 未知类目 {category!r}，已注册: {list(CATEGORIES)}")

    py = sys.executable
    # 1. pytest 类目收集（决策 B 原案：--category 只收集该类目验收面测试）
    test_files = [str(f) for f in collect_test_files(category)]
    _step([py, "-m", "pytest", *test_files, "-q"], category, "单元测试（类目收集）")
    # 2. pipeline（含 finalize 后处理链，决策 A）
    # 默认 input 为根目录（feat 66 个根级 rel 等散布根级源文件需全树遍历）；
    # spell 等源文件集中在子目录的类目用 input_dir 覆盖（防索引双份，见装配表注释）
    _step([py, "-m", "vectorizer.pipeline", "--category", category,
           "--input", spec.get("input_dir", "pf_rules_md_organized"),
           "--output", spec["output_dir"]],
          category, "pipeline 重生成（finalize 内建）")
    # 3. verify 公共框架（类目装配的检查链）
    _step([py, "-m", spec["verify_module"]], category, "集成验收")
    # 4. 数据不变量闸口（数量护栏 + 来源书终态；invariants 为命令+参数列表）
    _step([py, *spec["invariants"]], category, "数据不变量闸口")

    print(f"\n✅ {category} 完整验证链通过")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="完整验证链（pytest → pipeline → verify → 不变量）")
    parser.add_argument("--category", required=True,
                        help=f"类目（已注册: {list(CATEGORIES)}）")
    args = parser.parse_args(argv)
    run_chain(args.category)


if __name__ == "__main__":
    main()
