"""Optional JS startup checks. The app itself does not require Node."""
from pathlib import Path
import shutil
import subprocess
import unittest


class FrontendRegressionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node is optional; frontend regression check skipped')
    def test_browser_globals_routes_and_startup_errors(self):
        root=Path(__file__).resolve().parent
        result=subprocess.run(['node',str(root/'test_frontend_smoke.cjs')],cwd=root,
                              capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':
    unittest.main()
