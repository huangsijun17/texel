"""Release-surface gates for the public Texel 0.999.4 repository."""

import json
import os
import re
import unittest
from pathlib import Path

from importer.serialize import serialize

ROOT = Path(__file__).resolve().parent.parent


class PublicReleaseTest(unittest.TestCase):
    def test_importer_emits_only_current_wire_version(self):
        text = serialize(1, 1, "char", [], [{"op": "fill", "slot": 0}])
        self.assertIn('"version": 1', text)
        self.assertNotIn('"version": ' + str(0), text)

    def test_only_current_specs_are_published(self):
        self.assertTrue((ROOT / "spec" / "PXL.md").is_file())
        self.assertTrue((ROOT / "spec" / "PXL.en.md").is_file())
        self.assertFalse((ROOT / "spec" / ("PXL-v" + str(0) + ".md")).exists())
        self.assertFalse((ROOT / "spec" / "PXL-v1.md").exists())

    def test_release_metadata_is_consistent(self):
        importer = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        compiler = (ROOT / "compiler" / "python" / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(importer, r'(?m)^version = "0\.999\.4"$')
        self.assertRegex(compiler, r'(?m)^version = "0\.999\.4"$')
        fixture = json.loads((ROOT / "spec" / "conformance" / "capabilities" /
                              "pxl-v1.json").read_text(encoding="utf-8"))
        self.assertEqual("0.999.4", fixture["compiler_version"])
        self.assertEqual("pxl-v1", fixture["conformance_profile"])
        self.assertEqual([1], fixture["language_versions"])
        self.assertEqual(set(["1"]), set(fixture["error_code_ranges"]))
        self.assertEqual("pxl-png", fixture["png_input_profile"])

    def test_community_health_files_exist(self):
        required = (
            "README.md", "README.zh-CN.md", "CONTRIBUTING.md",
            "CONTRIBUTING.zh-CN.md", "SECURITY.md", "SECURITY.zh-CN.md",
            "SUPPORT.md", "SUPPORT.zh-CN.md", "CODE_OF_CONDUCT.md",
            "CODE_OF_CONDUCT.zh-CN.md", "GOVERNANCE.md", "CHANGELOG.md",
            "NOTICE", ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/documentation.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/dependabot.yml", ".github/workflows/release.yml",
        )
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_internal_process_documents_are_not_published(self):
        self.assertFalse((ROOT / "docs" / "reviews").exists())
        self.assertFalse((ROOT / "docs" / "findings").exists())
        self.assertFalse((ROOT / "docs" / "superpowers").exists())

    #: 私有信息模式。
    #:
    #: **必须用单反斜杠**：正则里"一个反斜杠"写作 ``\\``，在 raw string 里就是 ``r"\\"``。
    #: 写成 ``r"\\\\"`` 会匹配"两个字面反斜杠"，于是真实路径一个都命中不了——这条门禁
    #: 曾经整年恒绿，连 ``spec/PXL.md`` 里的本机绝对路径都放过去了（2026-11-14 审查实测）。
    #: ``test_private_path_patterns_can_fail`` 是它的自检：规则必须能命中真实路径。
    PRIVATE_PATTERNS = (
        re.compile(r"[A-Za-z]:\\src\\"),                     # E:\src\...
        re.compile(r"C:\\Users\\", re.IGNORECASE),           # C:\Users\...
        re.compile(r"AppData\\(?:Roaming|Local)\\", re.IGNORECASE),
        re.compile(r"Program Files\\(?:BellSoft|Java|Eclipse Adoptium|Temurin|Zulu|Microsoft)\\", re.IGNORECASE),
        re.compile(r"\\\\(?:wsl\$|wsl\.localhost)\\"),        # \\wsl$\<distro>\
        re.compile(r"\\\\[A-Za-z0-9][\w.-]*\\[A-Za-z0-9$._-]+\\"),  # UNC \\host\share\
        re.compile(r"%USERPROFILE%", re.IGNORECASE),
        re.compile(r"/home/[A-Za-z0-9._-]+/"),               # 本机 POSIX 家目录
        re.compile(r"/Users/[A-Za-z0-9._-]+/"),              # macOS 家目录
        re.compile(r"(?:^|[\s(\"'`])~/"),                    # 波浪号家目录
    )

    #: 剪枝目录：全是构建/测试产物，内容不参与发布面检查。
    #: 代价是"把泄漏样本搬进沙箱避难"会看不见，所以 ``test_scratch_dirs_are_ignored``
    #: 另外要求这些目录必须被 .gitignore 覆盖（不会被发布）。
    PRUNED = {".git", ".gradle-home", "build", "_sandbox", "_tmp"}

    def test_private_path_patterns_can_fail(self):
        """规则集的自检：负例必须命中，正例必须不命中。

        没有这条，正则写错（多一层转义）会让下面的扫描变成恒真式，而 CI 依旧全绿。
        """
        offenders = (
            r"E:\src\gt6-modern-review\neoforge\x.png",
            r"C:\Users\someone\texel",
            r"C:\Users\someone\AppData\Roaming\npm\node_modules",
            r"C:\Program Files\BellSoft\LibericaJDK-21\bin\java.exe",
            r"\\wsl$\Ubuntu\home\me\texel",
            r"\\nas-01\share\texel\x.png",
            "%USERPROFILE%\\texel",
            "/home/someone/texel/spec/PXL.md",
            "/Users/someone/texel/spec/PXL.md",
            "见 ~/texel/spec/PXL.md",
        )
        for sample in offenders:
            hits = [p.pattern for p in self.PRIVATE_PATTERNS if p.search(sample)]
            self.assertTrue(hits, "规则集没有命中真实路径样本: %r" % sample)
        benign = ("E:/src/texel", "compiler/java/core", "spec/PXL.md",
                  "https://github.com/gt6-modern/texel", "docs/releasing.md")
        for sample in benign:
            hits = [p.pattern for p in self.PRIVATE_PATTERNS if p.search(sample)]
            self.assertEqual([], hits, "误报: %r 命中 %r" % (sample, hits))

    def test_scratch_dirs_are_ignored(self):
        """被剪枝的目录必须在 .gitignore 里：否则泄漏可以藏进沙箱躲过扫描。"""
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in ("tests/_sandbox/", "tests/_tmp/"):
            self.assertIn(entry, ignored,
                          "%s 被扫描剪枝，但没有被 .gitignore 覆盖" % entry)

    #: 扫描器自身的模式表必然包含这些字面量——它们是规则，不是泄漏。
    SELF = "tests/test_public_release.py"

    def test_public_text_has_no_private_machine_paths(self):
        checked = 0
        skipped = 0
        offenders = []
        for directory, names, files in os.walk(str(ROOT), topdown=True):
            names[:] = [name for name in names
                        if name not in self.PRUNED and not name.startswith(".review-")]
            base = Path(directory)
            for name in files:
                path = base / name
                rel = path.relative_to(ROOT).as_posix()
                if rel == self.SELF:
                    continue
                if path.suffix.lower() in (".png", ".jar", ".class", ".zip", ".gz"):
                    skipped += 1
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    # `.pxl` 按规范必须是 UTF-8 文本，读不出来就是缺陷而不是"跳过"。
                    self.assertNotEqual(".pxl", path.suffix.lower(),
                                        rel + " 不是可读的 UTF-8 文本")
                    skipped += 1
                    continue
                checked += 1
                for pattern in self.PRIVATE_PATTERNS:
                    match = pattern.search(text)
                    if match is not None:
                        offenders.append("%s: %r" % (rel, match.group(0)))
        self.assertEqual([], offenders, "私有本机路径进了发布面")
        # 空集合守卫：一个文件都没扫到（或全被跳过）等于门禁没跑。
        self.assertGreater(checked, 500, "只扫到 %d 个文本文件，扫描范围异常" % checked)
        self.assertGreater(skipped, 0, "二进制跳过数为 0，判据可能失效")


if __name__ == "__main__":
    unittest.main()
