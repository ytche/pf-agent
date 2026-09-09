"""cicd 包入口：python3 -m vectorizer.cicd <子命令> [--category <类目>]

子命令注册（未来可扩展 lint/release 等）：
  verify — 完整验证链（pytest → pipeline → verify → 不变量）
"""
import argparse
import sys

from vectorizer.cicd import verify as verify_cmd


def main() -> None:
    parser = argparse.ArgumentParser(prog="python3 -m vectorizer.cicd",
                                     description="验证链统一编排")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="完整验证链（pytest → pipeline → verify → 不变量）")
    p_verify.add_argument("--category", required=True, help="类目（feat / spell / ...）")
    p_verify.set_defaults(func=verify_cmd.run_chain)

    args = parser.parse_args()
    args.func(args.category)


if __name__ == "__main__":
    main()
