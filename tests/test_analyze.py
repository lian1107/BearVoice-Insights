import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "analyze", os.path.join(REPO, "scripts", "analyze.py")
)
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)


class ReportSafetyTests(unittest.TestCase):
    def render_fixture(self, raw_quote):
        records = [{
            "signal": "认知",
            "原声": raw_quote,
            "原声id": "fixture-id",
            "情感": "中性",
            "日期": "2026-08-03",
        }]
        clusters = [{
            "name": "测试反馈类型",
            "signal": "认知",
            "object": "说明书",
            "members": [0],
            "count": 1,
            "pct": 100.0,
            "情感分布": {"中性": 1},
        }]
        with tempfile.TemporaryDirectory() as tmp:
            original_reports = analyze.REPORTS
            analyze.REPORTS = tmp
            try:
                path = analyze.write_report(
                    "测试品类", [{}], records, clusters, []
                )
                with open(path, encoding="utf-8") as f:
                    return f.read()
            finally:
                analyze.REPORTS = original_reports

    def test_report_distinguishes_duplicate_ids_from_extra_rows(self):
        report = self.render_fixture("正常产品文本")

        self.assertIn("391 条多余重复行", report)
        self.assertIn("涉及 282 个重复 ID", report)
        self.assertNotIn("有 282 条完全重复", report)

    def test_report_masks_address_like_dialogue_segment(self):
        report = self.render_fixture(
            "按键无响应 / 省榆县街市场门口 / 正常产品文本"
        )

        self.assertIn("按键无响应", report)
        self.assertIn("正常产品文本", report)
        self.assertIn("[地址已脱敏]", report)
        self.assertNotIn("省榆县街市场门口", report)

    def test_load_rows_reports_duplicate_grain_without_inflating_percentages(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            rows = analyze.load_rows()

        self.assertEqual(1109, len(rows))
        self.assertIn("391 条多余重复行", stdout.getvalue())
        self.assertIn("涉及 282 个重复 ID", stdout.getvalue())
        self.assertIn("总量虚增 35.3%", stdout.getvalue())
        self.assertNotIn("占比会虚高", stdout.getvalue())

    def test_report_contains_no_trailing_whitespace(self):
        report = self.render_fixture("按键无响应 / ")

        for line in report.splitlines():
            self.assertEqual(line.rstrip(), line)


if __name__ == "__main__":
    unittest.main()
