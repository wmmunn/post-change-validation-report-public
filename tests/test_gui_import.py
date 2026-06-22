import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _gui_tests_supported() -> bool:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False
    return not (sys.platform.startswith("linux") and not os.environ.get("DISPLAY"))


@unittest.skipUnless(_gui_tests_supported(), "GUI tests require tkinter and a display")
class GuiImportTests(unittest.TestCase):
    def test_gui_module_imports_app(self):
        from post_change_validation_gui import App

        self.assertTrue(callable(App))

    def test_app_instantiates(self):
        from post_change_validation_gui import App

        app = App()
        try:
            self.assertTrue(hasattr(app, "path_inputs"))
            self.assertEqual({"pre_log", "post_log", "port_map"}, set(app.path_inputs))
        finally:
            app.destroy()

    def test_reviewer_reexports_app(self):
        import post_change_validation_reviewer as reviewer

        self.assertIs(reviewer.App, __import__("post_change_validation_gui", fromlist=["App"]).App)

    def test_path_inputs_values_are_stringvars(self):
        import tkinter as tk
        from post_change_validation_gui import App

        app = App()
        try:
            for key in ("pre_log", "post_log", "port_map"):
                self.assertIsInstance(app.path_inputs[key], tk.StringVar)
        finally:
            app.destroy()

    def test_run_validation_passes_stripped_port_map_path(self):
        from post_change_validation_gui import App

        app = App()
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                pre = root / "pre.txt"
                post = root / "post.txt"
                port_map = root / "port_map.csv"
                pre.write_text(
                    "ACCESS-SW01#show version\nCisco IOS XE Software, Version 17.09.04\n",
                    encoding="utf-8",
                )
                post.write_text(
                    "ACCESS-SW02#show version\nCisco IOS XE Software, Version 17.09.04\n",
                    encoding="utf-8",
                )
                port_map.write_text("old_port,new_port,role,note\n", encoding="utf-8")

                app.path_inputs["pre_log"].set(str(pre))
                app.path_inputs["post_log"].set(str(post))
                app.path_inputs["port_map"].set(f"  {port_map}  ")

                captured: dict[str, str] = {}

                def fake_run_analysis(pre_text, post_text, port_map_path=""):
                    captured["pre_text"] = pre_text
                    captured["post_text"] = post_text
                    captured["port_map_path"] = port_map_path
                    return []

                with patch("post_change_validation_gui.run_analysis", side_effect=fake_run_analysis):
                    app.run_validation()

                self.assertEqual(
                    "ACCESS-SW01#show version\nCisco IOS XE Software, Version 17.09.04\n",
                    captured["pre_text"],
                )
                self.assertEqual(
                    "ACCESS-SW02#show version\nCisco IOS XE Software, Version 17.09.04\n",
                    captured["post_text"],
                )
                self.assertEqual(str(port_map), captured["port_map_path"])
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
