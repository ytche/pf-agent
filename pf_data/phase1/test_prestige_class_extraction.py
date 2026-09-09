#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进阶职业标题解析回归测试。"""

import unittest
from pathlib import Path

import vectorization_prep_profession as v


class PrestigeClassExtractionTest(unittest.TestCase):
    def _extract(self, title: str, rel_path: str):
        return v._extract_prestige_class_name(title, Path(rel_path))

    def test_source_prefix_with_attached_abbr(self):
        self.assertEqual(
            self._extract("传奇编年史CoL 密传骑士", "职业/进阶职业/传奇编年史CoL_进阶职业.md"),
            "密传骑士",
        )

    def test_source_prefix_with_abbr_and_parentheses(self):
        self.assertEqual(
            self._extract(
                "元素大师手册（Elemental Master's Handbook）EMH 进阶职业",
                "职业/进阶职业/元素大师手册EMH_进阶职业.md",
            ),
            None,
        )

    def test_source_prefix_space_abbr(self):
        self.assertEqual(
            self._extract("内海海盗 PIS 内海海盗", "职业/进阶职业/内海海盗PIS_内海海盗.md"),
            "内海海盗",
        )

    def test_no_source_prefix(self):
        self.assertEqual(
            self._extract("间谍大师（Master Spy）", "职业/进阶职业/APG进阶职业/page_145.md"),
            "间谍大师",
        )

    def test_source_prefix_with_long_abbr(self):
        self.assertEqual(
            self._extract(
                "第一世界TFWRotF 妖精誓缚者",
                "职业/进阶职业/第一世界TFWRotF_妖精誓缚者.md",
            ),
            "妖精誓缚者",
        )

    def test_known_non_class_title(self):
        self.assertEqual(
            self._extract(
                "地狱骑士之道PotH 地狱骑士戒律",
                "职业/进阶职业/地狱骑士之道PotH_戒律.md",
            ),
            None,
        )

    def test_generic_heading_requirements(self):
        self.assertEqual(
            self._extract("进阶条件（Requirements）", "职业/进阶职业/CRB进阶职业/page_999.md"),
            None,
        )

    def test_filename_fallback(self):
        self.assertEqual(
            self._extract("", "职业/进阶职业/传奇编年史CoL_密传骑士.md"),
            "密传骑士",
        )


if __name__ == "__main__":
    unittest.main()
