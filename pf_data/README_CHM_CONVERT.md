# CHM HTML -> Markdown 转换

## 状态

当前环境为沙盒容器，无法直接访问源文件目录 ~/.openclaw/workspace/pf_rules_chm/，且容器内无 Python 3。转换脚本已准备就绪，需要在主机（Mac）上执行。

## 转换脚本

脚本位置：/workspace/chm_to_md_converter.py（即 ~/.openclaw/workspace/touniang/chm_to_md_converter.py）

### 功能
- 自动解析 CHM_FULL_TOC.md 目录结构
- 按 TOC 层级组织输出目录
- 自动检测 GBK/UTF-8 编码
- 保留标题层级（H1-H6）
- 保留表格、列表等基本格式
- 图片链接保留为 ![图片](src)
- 内部链接转换为 Markdown 链接格式
- 处理行内格式：加粗、斜体、代码等

### 执行方式（在主机终端）

cd ~/.openclaw/workspace/touniang
python3 chm_to_md_converter.py

输出目录：~/.openclaw/workspace/pf_rules_md/

## 已知限制

- 正则解析无法处理嵌套表格或极其复杂的 HTML 结构
- 部分格式可能因原始 HTML 的复杂性而转换不完美
- 建议先运行示例文件（page_300.html）验证输出格式

---

*脚本生成时间：2026-06-15*
