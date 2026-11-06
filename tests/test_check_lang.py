"""Unit and functional tests for scripts/check_lang.py.

Verifies language separation between English-only files (no Arabic U+0600-U+06FF)
and Arabic files (no English prose outside code blocks, inline code, URLs,
link targets, placeholders, and technical allowlist).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
CHECK_LANG_PY = os.path.join(SCRIPTS_DIR, "check_lang.py")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
import check_lang


class TestCheckLang(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="check_lang_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def run_check_lang(self, *args):
        cmd = [sys.executable, CHECK_LANG_PY] + list(args)
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        return res.returncode, res.stdout, res.stderr

    def test_clean_set_passes(self):
        # English files
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Maestro\n\nA tool for pair-programming agents.\n")
        doc_en = os.path.join(self.test_dir, "docs", "en")
        os.makedirs(doc_en, exist_ok=True)
        with open(os.path.join(doc_en, "quickstart.md"), "w", encoding="utf-8") as f:
            f.write("# Quickstart\n\nRun the installer to begin.\n")

        # Arabic files
        with open(os.path.join(self.test_dir, "README.ar.md"), "w", encoding="utf-8") as f:
            f.write("# Maestro\n\nأداة لتنسيق مهام الوكلاء الأذكياء عبر منصات التطوير.\n")
        doc_ar = os.path.join(self.test_dir, "docs", "ar")
        os.makedirs(doc_ar, exist_ok=True)
        with open(os.path.join(doc_ar, "quickstart.md"), "w", encoding="utf-8") as f:
            f.write("# دليل البدء السريع\n\nقم بتشغيل ملف التثبيت للبدء.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 0, f"Expected 0, got {code}. Output:\n{out}\n{err}")
        self.assertEqual(out.strip(), "")

    def test_arabic_in_english_file_detected(self):
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Maestro\n\nWelcome مرحبا to the project.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.md:3:", out)
        self.assertIn("Arabic character", out)

    def test_english_prose_in_arabic_file_detected(self):
        with open(os.path.join(self.test_dir, "README.ar.md"), "w", encoding="utf-8") as f:
            f.write("# العنوان\n\nهذا نص عربي لكنه يحتوي على unauthorized prose بالإنجليزية.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.ar.md:3:", out)
        self.assertIn("unauthorized", out)

    def test_code_blocks_and_inline_code_ignored(self):
        content = (
            "# توثيق الأداة\n\n"
            "استخدم الدالة المضمنة `process_data(debug=True, token='secret')` في العمل.\n\n"
            "```python\n"
            "# A multi-line python code block with English prose\n"
            "def calculate_metrics(items):\n"
            "    # This English text should be ignored completely\n"
            "    return len(items)\n"
            "```\n\n"
            "~~~bash\n"
            "echo 'another fenced code block with bash syntax'\n"
            "~~~\n\n"
            "خاتمة باللغة العربية.\n"
        )
        with open(os.path.join(self.test_dir, "README.ar.md"), "w", encoding="utf-8") as f:
            f.write(content)

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 0, f"Expected 0, got {code}. Output:\n{out}\n{err}")
        self.assertEqual(out.strip(), "")

    def test_links_urls_and_placeholders_ignored(self):
        line = "شغّل الأمر على <project> داخل المسار المحدد."
        content = (
            "# الروابط والعناوين\n\n"
            "انظر [دليل التثبيت](https://github.com/SalehOsman/Maestro/blob/main/docs/en/install.md) هنا.\n"
            "يمكنك أيضاً زيارة الموقع https://anthropic.com/research مباشرة.\n"
            f"{line}\n"
        )
        doc_ar = os.path.join(self.test_dir, "docs", "ar")
        os.makedirs(doc_ar, exist_ok=True)
        with open(os.path.join(doc_ar, "guide.md"), "w", encoding="utf-8") as f:
            f.write(content)

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 0, f"Expected 0, got {code}. Output:\n{out}\n{err}")
        self.assertEqual(out.strip(), "")

        # Control assertions: prove that <project> actually yields a violation once
        # placeholder stripping is disabled, and that the raw line contains the Latin word.
        raw_words = check_lang.LATIN_WORD_RE.findall(line)
        self.assertIn("project", raw_words)
        self.assertNotIn("project", check_lang.ALLOWLIST)
        unstripped_line = check_lang.clean_arabic_line(line, strip_placeholders=False)
        unstripped_words = check_lang.LATIN_WORD_RE.findall(unstripped_line)
        self.assertIn("project", unstripped_words)
        stripped_line = check_lang.clean_arabic_line(line, strip_placeholders=True)
        stripped_words = check_lang.LATIN_WORD_RE.findall(stripped_line)
        self.assertNotIn("project", stripped_words)

    def test_allowlisted_technical_names_accepted(self):
        allowlisted = [
            "Maestro", "Antigravity", "Claude", "Code", "IDE", "Gemini", "Flash", "High",
            "Python", "Windows", "macOS", "Linux", "Wayland", "X11", "MCP", "TDD", "Google",
            "Anthropic", "MIT", "GitHub", "CLI", "JSON", "PowerShell", "Bash", "Enter",
            "Return", "Accessibility", "Superpowers", "EGM", "AgentShield", "ECC",
            "Harness", "Engineering", "README", "md", "CSV"
        ]
        text_ar = "دعم كامل للأدوات: " + " و ".join(allowlisted) + " في البيئة العربية.\n"
        with open(os.path.join(self.test_dir, "README.ar.md"), "w", encoding="utf-8") as f:
            f.write(text_ar)

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 0, f"Expected 0, got {code}. Output:\n{out}\n{err}")
        self.assertEqual(out.strip(), "")

    def test_missing_files_skipped(self):
        # Empty temp dir: no files at all
        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_tests_and_scripts_not_checked(self):
        # tests/ with Arabic and English
        tests_dir = os.path.join(self.test_dir, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        with open(os.path.join(tests_dir, "test_sample.py"), "w", encoding="utf-8") as f:
            f.write("# Arabic test data: مرحبا بالعالم\ndef test_arabic(): assert True\n")

        # scripts/ with Arabic comments
        scripts_dir = os.path.join(self.test_dir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, "sample.py"), "w", encoding="utf-8") as f:
            f.write("# Arabic comment: تجربة\ndef main(): pass\n")

        # docs/DESIGN.ar.md (old file not in docs/ar/**)
        docs_dir = os.path.join(self.test_dir, "docs")
        os.makedirs(docs_dir, exist_ok=True)
        with open(os.path.join(docs_dir, "DESIGN.ar.md"), "w", encoding="utf-8") as f:
            f.write("Some unauthorized English prose in legacy file\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 0, f"Expected 0, got {code}. Output:\n{out}\n{err}")
        self.assertEqual(out.strip(), "")

    def test_cli_custom_root_argument(self):
        sub_root = os.path.join(self.test_dir, "subproject")
        os.makedirs(sub_root, exist_ok=True)
        with open(os.path.join(sub_root, "README.md"), "w", encoding="utf-8") as f:
            f.write("# English only clean readme\n")

        code, out, err = self.run_check_lang("--root", sub_root)
        self.assertEqual(code, 0)

    # Finding 1: Each Arabic block detected in English files
    def test_arabic_block_basic_detected(self):
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# English Header\n\nCharacter \u0627 from Arabic block.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.md:3: Arabic character U+0627 found in English file", out)

    def test_arabic_block_supplement_detected(self):
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# English Header\n\nCharacter \u0750 from Arabic Supplement.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.md:3: Arabic character U+0750 found in English file", out)

    def test_arabic_block_extended_b_detected(self):
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# English Header\n\nCharacter \u0870 from Arabic Extended-B.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.md:3: Arabic character U+0870 found in English file", out)

    def test_arabic_block_extended_a_detected(self):
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# English Header\n\nCharacter \u08A0 from Arabic Extended-A.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.md:3: Arabic character U+08A0 found in English file", out)

    def test_arabic_block_presentation_forms_a_detected(self):
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# English Header\n\nCharacter \uFB50 from Arabic Presentation Forms-A.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.md:3: Arabic character U+FB50 found in English file", out)

    def test_arabic_block_presentation_forms_b_detected(self):
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# English Header\n\nCharacter \uFE70 from Arabic Presentation Forms-B.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.md:3: Arabic character U+FE70 found in English file", out)

    def test_english_file_with_bom_accepted(self):
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("\uFEFF# Clean English Header\n\nValid documentation with zero Arabic.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 0, f"Expected 0, got {code}. Output:\n{out}\n{err}")
        self.assertEqual(out.strip(), "")

    # Finding 2: English prose in docs/ar/** detected
    def test_english_prose_in_docs_ar_detected(self):
        doc_ar = os.path.join(self.test_dir, "docs", "ar")
        os.makedirs(doc_ar, exist_ok=True)
        with open(os.path.join(doc_ar, "x.md"), "w", encoding="utf-8") as f:
            f.write("# توثيق إضافي\n\nهذا الملف يحتوي على unauthorized prose بالإنجليزية.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("docs/ar/x.md:3: English prose word 'unauthorized' found in Arabic file", out)

    # Finding 4: Glued Latin and Arabic words
    def test_latin_glued_to_arabic_reported(self):
        with open(os.path.join(self.test_dir, "README.ar.md"), "w", encoding="utf-8") as f:
            f.write("# توثيق\n\nتحية Helloبيئة إلى الجميع.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.ar.md:3: English prose word 'Hello' found in Arabic file", out)

    def test_allowlisted_glued_to_arabic_accepted(self):
        with open(os.path.join(self.test_dir, "README.ar.md"), "w", encoding="utf-8") as f:
            f.write("# توثيق\n\nتطوير Pythonبيئة باللغة العربية.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 0, f"Expected 0, got {code}. Output:\n{out}\n{err}")
        self.assertEqual(out.strip(), "")

    def test_link_label_english_words_reported(self):
        """Link labels in Arabic files must be checked for unauthorized English prose."""
        with open(os.path.join(self.test_dir, "README.ar.md"), "w", encoding="utf-8") as f:
            f.write("# توثيق\n\nانظر [the guide](x.md) للمزيد.\n")

        code, out, err = self.run_check_lang("--root", self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("README.ar.md:3: English prose word 'the' found in Arabic file", out)
        self.assertIn("README.ar.md:3: English prose word 'guide' found in Arabic file", out)


if __name__ == "__main__":
    unittest.main()
