"""Smoke tests — every tool module imports and exposes a main()."""
import importlib
import pkgutil
import unittest

import zens_ink

TOOLS = [
    "ai_crawler_audit", "brave_volume", "competitor_gap", "content_matrix",
    "content_qc", "domain_rating", "geo_fanout", "kd", "keyword_cluster",
    "keyword_research", "keyword_volume", "kgr_auto", "llms_gen", "mcp",
    "onpage_audit", "rank_tracker", "reddit_blueocean", "search_intent",
    "search_performance", "serp_intent", "setup_gsc", "site_audit",
]


class TestImports(unittest.TestCase):
    def test_package_imports(self):
        self.assertTrue(hasattr(zens_ink, "__version__"))

    def test_all_tool_modules_import(self):
        missing = []
        for tool in TOOLS:
            try:
                importlib.import_module(f"zens_ink.{tool}")
            except Exception as e:  # noqa: BLE001
                missing.append(f"{tool}: {e}")
        self.assertEqual(missing, [], f"import failures: {missing}")

    def test_tools_expose_main(self):
        no_main = []
        for tool in TOOLS:
            if tool == "mcp":  # server loop, not a CLI main
                continue
            mod = importlib.import_module(f"zens_ink.{tool}")
            if not hasattr(mod, "main"):
                no_main.append(tool)
        self.assertEqual(no_main, [], f"no main(): {no_main}")

    def test_stdlib_only(self):
        """No third-party top-level imports in any tool module."""
        import ast
        stdlib = set(sys_stdlib_names())
        offenders = []
        for tool in TOOLS:
            path = importlib.import_module(f"zens_ink.{tool}").__file__
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                for n in names:
                    if n not in stdlib and n not in ("zens_ink", "zens_ink_pro"):
                        offenders.append(f"{tool}: {n}")
        self.assertEqual(offenders, [], f"third-party imports: {offenders}")


def sys_stdlib_names():
    import sys
    return getattr(sys, "stdlib_module_names", ())


if __name__ == "__main__":
    unittest.main()
