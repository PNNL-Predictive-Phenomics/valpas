"""Fast stdlib harness tests: no downloads or installed VaLPAS required."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load("validate_distribution")
smoke = load("distribution_smoke")


class HarnessCase(unittest.TestCase):
    def test_probe_hostile_literals_do_not_close_script_early(self):
        for probe in (validator.BROWSER_PROBE, validator.B1_BROWSER_PROBE):
            self.assertEqual(probe.lower().count("</script"), 1)
            self.assertTrue(probe.rstrip().endswith("</script>"))

    def test_environment_clears_source_and_install_redirection(self):
        inherited = {"PYTHONPATH": "/checkout/src", "PYTHONHOME": "/other", "PYTHONOPTIMIZE": "1",
                     "VIRTUAL_ENV": "/old", "PIP_TARGET": "/shared", "PIP_NO_DEPS": "1",
                     "PIP_INDEX_URL": "https://unrelated.invalid", "GIT_DIR": "/checkout/.git",
                     "SETUPTOOLS_SCM_PRETEND_VERSION": "fake", "HATCH_VERSION": "fake",
                     "HTTPS_PROXY": "https://proxy", "PATH": os.environ["PATH"]}
        with patch.dict(os.environ, inherited, clear=True):
            env = validator.clean_environment()
        for key in inherited.keys() - {"HTTPS_PROXY", "PATH"}:
            self.assertNotIn(key, env)
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)
        self.assertEqual(env["HTTPS_PROXY"], "https://proxy")

    def archive(self, path, extra=(), omit=None):
        names = set(validator.SDIST_FILES)
        names.update("src/valpas/comparison/assets/" + n for n in validator.ASSETS)
        names.update("tests/comparison/fixtures/demo-01/" + n for n in validator.FIXTURE_FILES)
        names.update("tests/comparison/fixtures/b2-reference/" + n for n in validator.B2_FIXTURE_FILES)
        names.update("src/valpas/comparison/" + n for n in validator.MODULES)
        names.discard(omit)
        with tarfile.open(path, "w:gz") as archive:
            for name in sorted(names):
                data = b"Name: valpas\nVersion: 1.2.3\n" if name == "PKG-INFO" else b"fixture"
                member = tarfile.TarInfo("valpas-1.2.3/" + name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            for member in extra:
                archive.addfile(member, io.BytesIO(b""))

    def test_sdist_safe_extract_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "source.tar.gz"
            self.archive(path)
            source, record = validator.extract_sdist(path, root / "extracted")
            self.assertEqual(record["version"], "1.2.3")
            self.assertTrue((source / "pyproject.toml").is_file())
            self.assertFalse((source / ".git").exists())
            self.assertEqual(record["sha256"], validator.digest(path))

    def test_sdist_rejects_unsafe_members_before_writing(self):
        cases = []
        for name in ("../escape", "/absolute", "valpas-1.2.3/../../escape", "valpas-1.2.3\\escape",
                     "valpas-1.2.3/README.md", "other-root/file", "valpas-1.2.3/.git/config"):
            cases.append(tarfile.TarInfo(name))
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE):
            member = tarfile.TarInfo("valpas-1.2.3/link")
            member.type = kind
            member.linkname = "../../escape"
            cases.append(member)
        for member in cases:
            with self.subTest(member=member.name, kind=member.type), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                archive = root / "source.tar.gz"
                self.archive(archive, [member])
                with self.assertRaises(ValueError):
                    validator.extract_sdist(archive, root / "extracted")
                self.assertFalse((root / "extracted").exists())

    def test_sdist_requires_profile_and_b1_fixtures(self):
        for name in ("profiles.json", "manifest-with-b1.json", "sample-metadata.json", "b1-profiles.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.archive(root / "source.tar.gz", omit="tests/comparison/fixtures/demo-01/" + name)
                with self.assertRaisesRegex(ValueError, name):
                    validator.extract_sdist(root / "source.tar.gz", root / "extracted")

    def marker(self, profiles=False, metadata=False, requests=()):
        return {"schema_version": 3, "complete": True, "report": {"profiles": profiles},
                "b1": {"sample_metadata": metadata, "diagnostic_requests": list(requests)}}

    def test_v3_exact_independently_optional_table_inventory(self):
        scientific = {"outputs", "configuration_differences", "coverage", "exclusions", "candidate_ranks",
                      "agreement", "run_recurrence", "agreement_summary", "query_summary", "dataset_summary"}
        profiles = {"profile_values", "feature_coverage"}
        for has_profiles in (False, True):
            for has_metadata in (False, True):
                cases = [([], set())]
                if has_profiles:
                    cases.append(([{"group_field": None}], {"diagnostics"}))
                    if has_metadata:
                        cases += [([{"group_field": "condition"}], {"diagnostics", "group_summaries"}),
                                  ([{"group_field": None}, {"group_field": "condition"}], {"diagnostics", "group_summaries"})]
                for requests, extra in cases:
                    with self.subTest(profiles=has_profiles, metadata=has_metadata, requests=requests):
                        marker = self.marker(has_profiles, has_metadata, requests)
                        expected = scientific | (profiles if has_profiles else set()) | extra
                        if has_metadata:
                            expected.add("sample_metadata")
                        self.assertEqual(smoke.expected_tables(marker), expected)
                        marker.update(tables=dict.fromkeys(expected), table_schema=dict.fromkeys(expected))
                        self.assertEqual(smoke.check_table_inventory(marker), expected)
                        # Same count is not enough: substitution must fail for either inventory.
                        for key in ("tables", "table_schema"):
                            original = marker[key]
                            marker[key] = {**original, "unexpected": None}
                            marker[key].pop("outputs")
                            with self.assertRaisesRegex(AssertionError, "inventory"):
                                smoke.check_table_inventory(marker)
                            marker[key] = original

    def test_v3_schema_and_presence_flags_are_strict(self):
        for version in (1, 2, 4, True, "3", 3.0):
            marker = self.marker()
            marker["schema_version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(AssertionError, "v3"):
                smoke.expected_tables(marker)
        for marker in (self.marker(profiles=1), self.marker(metadata="yes"),
                       self.marker(requests=[{"group_field": None}]),
                       self.marker(profiles=True, requests=[{"group_field": "condition"}])):
            with self.assertRaises(AssertionError):
                smoke.expected_tables(marker)
        marker = self.marker()
        marker["complete"] = 1
        with self.assertRaisesRegex(AssertionError, "incomplete"):
            smoke.expected_tables(marker)

    def test_b1_fixture_exact_fifteen_tables(self):
        expected = smoke.expected_tables(self.marker(True, True, [smoke.B1_REQUEST]))
        self.assertEqual(len(expected), 15)
        self.assertEqual(expected - smoke.SCIENTIFIC_TABLES - smoke.PROFILE_TABLES,
                         {"sample_metadata", "diagnostics", "group_summaries"})
        self.assertEqual(len(smoke.expected_tables(self.marker(True))), 12)
        self.assertEqual(len(smoke.expected_tables(self.marker())), 10)

    def test_b2_exact_optional_inventory_with_and_without_groups_sessions(self):
        references = {"reference_endpoints", "reference_evidence", "reference_recovery", "reference_summary"}
        for profiles, metadata, requests in ((False, False, []), (True, False, []), (True, True, [smoke.B1_REQUEST])):
            for groups in (False, True):
                for session in (False, True):
                    with self.subTest(profiles=profiles, metadata=metadata, groups=groups, session=session):
                        marker = self.marker(profiles, metadata, requests)
                        base = smoke.expected_tables(marker)
                        marker["b2_references"] = {"schema_version": 1, "query_groups": groups, "provenance_hash": "a" * 64}
                        if session:
                            marker["b2_session"] = {"schema_version": 1}
                        expected = base | references | ({"query_groups"} if groups else set())
                        self.assertEqual(smoke.expected_tables(marker), expected)
                        marker.update(tables=dict.fromkeys(expected), table_schema=dict.fromkeys(expected))
                        self.assertEqual(smoke.check_table_inventory(marker), expected)
                        for key in ("tables", "table_schema"):
                            original = marker[key]
                            marker[key] = {**original, "fake_reference": None}
                            marker[key].pop("reference_recovery")
                            with self.assertRaisesRegex(AssertionError, "inventory"):
                                smoke.check_table_inventory(marker)
                            marker[key] = original
        marker = self.marker(True, True, [smoke.B1_REQUEST])
        marker["b2_references"] = {"schema_version": 1, "query_groups": True, "provenance_hash": "a" * 64}
        self.assertEqual(len(smoke.expected_tables(marker)), 20)
        marker["b2_session"] = {"schema_version": 1}
        self.assertEqual(len(smoke.expected_tables(marker)), 20)  # session is a document, not a scientific table

    def test_b2_extension_shape_flags_and_digests_strict(self):
        valid = {"schema_version": 1, "query_groups": True, "provenance_hash": "a" * 64}
        for extension in (None, {}, valid | {"schema_version": True}, valid | {"query_groups": 1},
                          valid | {"unknown": 1}, valid | {"provenance_hash": "wrong"}, valid | {"provenance_hash": "z" * 64}):
            marker = self.marker()
            marker["b2_references"] = extension
            with self.subTest(extension=extension), self.assertRaises(AssertionError):
                smoke.expected_tables(marker)
        for extension in (None, {}, {"schema_version": True}, {"schema_version": 2}, {"schema_version": 1, "unknown": 0}):
            marker = self.marker()
            marker["b2_session"] = extension
            with self.subTest(extension=extension), self.assertRaises(AssertionError):
                smoke.expected_tables(marker)

    def test_sdist_requires_all_b2_modules_assets_fixtures_helpers_guide(self):
        required = ["src/valpas/comparison/assets/sessions.js", "tools/distribution_browser.py",
                    "tests/comparison/chrome_cdp.py", "docs/COMPARISON_FIGURES.md",
                    "tests/comparison/fixtures/demo-01/manifest-with-b2.json"]
        required += ["src/valpas/comparison/" + n for n in validator.MODULES]
        required += ["tests/comparison/fixtures/b2-reference/" + n for n in validator.B2_FIXTURE_FILES]
        for name in required:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.archive(root / "source.tar.gz", omit=name)
                with self.assertRaisesRegex(ValueError, "missing documented"):
                    validator.extract_sdist(root / "source.tar.gz", root / "extracted")
                self.assertFalse((root / "extracted").exists())

    def test_figure_validation_rejects_non_vector_or_external_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "bad.pdf"
            pdf.write_bytes(b"not a pdf")
            with self.assertRaisesRegex(AssertionError, "PDF"):
                smoke.check_figure(pdf)
            svg = root / "bad.svg"
            for content in ('<html/>', '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                            '<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.org/x"/></svg>'):
                svg.write_text(content)
                with self.assertRaises(AssertionError):
                    smoke.check_figure(svg)

    def test_reuse_requires_explicit_isolated_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = root / "build-env"
            env.mkdir()
            for content in (None, "include-system-site-packages = true\n", "include-system-site-packages = false\n"):
                if content:
                    (env / "pyvenv.cfg").write_text(content)
                with self.assertRaises(ValueError):
                    validator.retained_python(root, "build-env")
            python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python.parent.mkdir()
            python.touch()
            self.assertEqual(validator.retained_python(root, "build-env"), python.resolve())

    def test_wheel_assets_and_dependency_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "valpas.whl"
            with zipfile.ZipFile(path, "w") as archive:
                for name in validator.ASSETS:
                    archive.writestr("valpas/comparison/assets/" + name, "asset")
                for name in validator.MODULES:
                    archive.writestr("valpas/comparison/" + name, "module")
                archive.writestr("valpas-1.2.3.dist-info/METADATA", "Name: valpas\nVersion: 1.2.3\nRequires-Python: >=3.12\nRequires-Dist: torch\n")
            record = validator.inspect_wheel(path)
            self.assertEqual(record["requires_dist"], ["torch"])
            self.assertEqual(record["version"], "1.2.3")

    def test_wheel_rejects_missing_b2_assets_and_modules(self):
        members = ["assets/" + n for n in validator.ASSETS] + list(validator.MODULES)
        for omitted in ("assets/sessions.js", *validator.MODULES):
            with self.subTest(omitted=omitted), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "bad.whl"
                with zipfile.ZipFile(path, "w") as archive:
                    for name in members:
                        if name != omitted:
                            archive.writestr("valpas/comparison/" + name, "content")
                with self.assertRaises(KeyError):
                    validator.inspect_wheel(path)

    def test_command_failure_is_recorded_and_propagates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = validator.Runner(root, 10)
            with self.assertRaisesRegex(RuntimeError, "exited 7"):
                runner.run([sys.executable, "-I", "-c", "print('diagnostic'); raise SystemExit(7)"])
            record = json.loads((root / "summary.json").read_text())["commands"][0]
            self.assertEqual(record["returncode"], 7)
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["cwd"], str(root))
            self.assertIn("diagnostic", Path(record["log"]).read_text())

    def test_command_timeout_is_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = validator.Runner(Path(temp), 10)
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run([sys.executable, "-I", "-c", "import time; time.sleep(10)"], timeout=0.1)
            self.assertEqual(runner.summary["commands"][0]["status"], "timeout")

    def test_missing_browser_is_not_silent_skip(self):
        with self.assertRaisesRegex(ValueError, "required"):
            validator.find_chrome("/nonexistent/valpas-test-chrome")

    def test_main_failure_returns_nonzero_and_keeps_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            (source / "src/valpas").mkdir(parents=True)
            version = source / "src/valpas/_version.py"
            version.write_bytes(b"preserve user bytes\n")
            code = validator.main(["--source", str(source), "--work-parent", str(root),
                                   "--chrome", "/nonexistent/valpas-test-chrome"])
            self.assertEqual(code, 1)
            record = json.loads(next(root.glob("valpas-distribution-*/summary.json")).read_text())
            self.assertEqual(record["status"], "failed")
            self.assertIn("Chrome", record["error"])
            self.assertEqual(version.read_bytes(), b"preserve user bytes\n")

    def test_direct_url_decodes_development_version_and_checks_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            wheel = Path(temp) / "valpas-1.0+local.whl"
            wheel.write_bytes(b"wheel")
            direct = {"url": wheel.as_uri(), "archive_info": {"hashes": {"sha256": validator.digest(wheel)}}}
            self.assertIn("%2B", direct["url"])
            smoke.check_direct_url(direct, wheel)
            direct["archive_info"]["hashes"]["sha256"] = "wrong"
            with self.assertRaisesRegex(AssertionError, "hash"):
                smoke.check_direct_url(direct, wheel)

    def test_offline_html_rejects_resource_references(self):
        for html in ('<script src="https://example.com/x.js"></script>', '<link href="local.css">',
                     '<img srcset="https://example.com/a.png 2x">'):
            with self.subTest(html=html), self.assertRaises(AssertionError):
                smoke.OfflineHTML().feed(html)

    def test_work_parent_inside_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(SystemExit) as result:
                validator.main(["--source", temp, "--work-parent", temp])
            self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
