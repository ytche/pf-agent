"""postprocess — pipeline finalize 阶段的后处理步骤实现（v2.2 决策 A）

类目在 processors/<类目>.py 声明 POSTPROCESSORS 有序列表，pipeline 在
chunks.jsonl 落盘后、verify 前逐个执行（顺序即声明顺序，不可变）。

契约（见 docs/VECTORIZER_ARCHITECTURE_DESIGN.md §4.9 v2.2）：
  ① 幂等性硬契约（重跑 diff 为空，test_postprocess.py 幂等测试）
  ② 顺序显式（有序列表；顺序敏感步骤注释「不可变」）
  ③ 默认关闭兼容（不声明 POSTPROCESSORS → finalize 无操作）

用法：无需直接调用，pipeline --category <类目> 自动执行；测试可实例化
步骤类调 run(output_dir, report_dir)。
"""
