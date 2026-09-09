"""
run_tests.py — 轻量测试运行器（无需 pytest）

直接导入测试类并执行所有 test_* 方法。
在 pytest 不可用时作为替代。
"""

import importlib
import pkgutil
import sys
import traceback
from pathlib import Path


def discover_tests():
    """发现 vectorizer/tests/ 下的所有 test_*.py"""
    test_dir = Path(__file__).parent / "tests"
    sys.path.insert(0, str(test_dir.parent))

    test_files = sorted(test_dir.glob("test_*.py"))
    modules = []
    for f in test_files:
        mod_name = f"vectorizer.tests.{f.stem}"
        try:
            mod = importlib.import_module(mod_name)
            modules.append(mod)
        except Exception as e:
            print(f"  ⚠️  导入 {mod_name} 失败: {e}")
    return modules


def run_test_methods(mod):
    """找出模块中所有 test_ 开头的类和方法并执行"""
    results = {"pass": 0, "fail": 0, "error": 0}
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if not isinstance(obj, type) or not attr_name.startswith("Test"):
            continue
        # 实例化测试类
        try:
            instance = obj()
        except Exception as e:
            print(f"  ⚠️  实例化 {attr_name} 失败: {e}")
            continue

        for method_name in sorted(dir(obj)):
            if not method_name.startswith("test_"):
                continue
            method = getattr(instance, method_name)
            func_name = f"{attr_name}.{method_name}"
            try:
                # 尝试获取 pytest.fixture 参数
                import inspect
                sig = inspect.signature(method)
                args_needed = [p for p in sig.parameters.values()
                               if p.default is inspect.Parameter.empty
                               and p.name != 'self']
                if args_needed:
                    # 需要 fixture 参数 — run_tests.py 不支持 fixture，计入 fail 提示改用 pytest
                    print(f"  ❌ {func_name}: 需要 fixture 参数 {args_needed}（run_tests.py 不支持，请改用 pytest）")
                    results["fail"] += 1
                    continue

                method()
                print(f"  ✅ {func_name}")
                results["pass"] += 1
            except AssertionError as e:
                print(f"  ❌ {func_name}: {e}")
                results["fail"] += 1
            except Exception as e:
                print(f"  ❌ {func_name}: {e}")
                traceback.print_exc()
                results["error"] += 1

    return results


def main():
    print("=" * 50)
    print("vectorizer 轻量测试运行器")
    print("=" * 50)
    print()

    modules = discover_tests()
    if not modules:
        print("未找到测试模块")
        sys.exit(1)

    total = {"pass": 0, "fail": 0, "error": 0}
    for mod in modules:
        print(f"\n📦 {mod.__name__}")
        results = run_test_methods(mod)
        for k, v in results.items():
            total[k] += v

    print()
    print("=" * 50)
    print(f"结果: ✅ {total['pass']}  ❌ {total['fail']}  ⚠️ {total['error']}")
    if total["fail"] or total["error"]:
        sys.exit(1)
    print("全部通过!")


if __name__ == "__main__":
    main()
