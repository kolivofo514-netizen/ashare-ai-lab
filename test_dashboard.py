import unittest
from pathlib import Path
import build_dashboard
class TestDashboard(unittest.TestCase):
    def test_build_offline(self):
        build_dashboard.build()
        s=(Path(__file__).parent/"site/index.html").read_text(encoding="utf-8")
        self.assertIn("A股独立AI盈利验证系统",s)
        self.assertNotIn("__REPORT_JSON__",s)
        self.assertIn("未验证真实行情",s)
if __name__=="__main__":unittest.main()
