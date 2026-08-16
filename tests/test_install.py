"""Tests for install.py — the CLI / macOS app installer.

Every test redirects the installer at a temporary directory, so the real
~/.local/bin and ~/Applications are never touched.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import install


class TestPackageVersion(unittest.TestCase):
    def test_reads_version_from_package(self):
        from glean_code import __version__
        self.assertEqual(install.package_version(), __version__)

    def test_version_is_dotted(self):
        self.assertRegex(install.package_version(), r"^\d+\.\d+")


class TestTilde(unittest.TestCase):
    def test_home_paths_are_abbreviated(self):
        self.assertEqual(install._tilde(Path.home() / "x" / "y"), "~/x/y")

    def test_outside_home_left_absolute(self):
        self.assertEqual(install._tilde(Path("/usr/local/bin")), "/usr/local/bin")


class TestLaunchScript(unittest.TestCase):
    def test_snapshot_mode_runs_bundled_pyz(self):
        body = install._launch_script(dev=False)
        self.assertIn("glean-code.pyz", body)
        self.assertNotIn("-m glean_code", body)

    def test_dev_mode_runs_from_source_tree(self):
        body = install._launch_script(dev=True)
        self.assertIn("-m glean_code", body)
        self.assertIn(str(install.REPO_ROOT), body)

    def test_both_modes_are_zsh_scripts(self):
        for dev in (True, False):
            self.assertTrue(install._launch_script(dev).startswith("#!/bin/zsh"))


class TestBuildZipapp(unittest.TestCase):
    def test_builds_an_executable_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = install.build_zipapp(Path(tmp) / "glean-code.pyz")
            self.assertTrue(out.exists())
            self.assertTrue(out.stat().st_mode & 0o111, "should be executable")
            self.assertGreater(out.stat().st_size, 10_000)

    def test_archive_actually_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = install.build_zipapp(Path(tmp) / "glean-code.pyz")
            proc = subprocess.run(
                [sys.executable, str(out)],
                input="/exit\n", capture_output=True, text=True, timeout=60,
            )
            self.assertIn("Glean Code", proc.stdout)

    def test_excludes_caches_and_markers(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            out = install.build_zipapp(Path(tmp) / "glean-code.pyz")
            names = zipfile.ZipFile(out).namelist()
            self.assertTrue(any(n.endswith("cli.py") for n in names))
            for junk in ("__pycache__", ".DS_Store", ".metadata_never_index"):
                self.assertFalse([n for n in names if junk in n], f"{junk} leaked in")


class TestInstallCli(unittest.TestCase):
    def test_copies_as_executable_named_glean(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pyz = install.build_zipapp(tmp_path / "src.pyz")
            dest = install.install_cli(tmp_path / "bin", pyz)
            self.assertEqual(dest.name, "glean")
            self.assertTrue(dest.exists())
            self.assertTrue(dest.stat().st_mode & 0o111)

    def test_creates_missing_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pyz = install.build_zipapp(tmp_path / "src.pyz")
            dest = install.install_cli(tmp_path / "a" / "b" / "c", pyz)
            self.assertTrue(dest.parent.is_dir())


class TestOnPath(unittest.TestCase):
    def test_detects_directory_on_path(self):
        with mock.patch.dict("os.environ", {"PATH": "/opt/x:/opt/y"}):
            self.assertTrue(install.on_path(Path("/opt/x")))
            self.assertFalse(install.on_path(Path("/opt/z")))


class TestMacosAppBundle(unittest.TestCase):
    def _build(self, tmp, dev=False):
        app_dir = Path(tmp) / "Glean.app"
        pyz = install.build_zipapp(Path(tmp) / "src.pyz")
        with mock.patch.object(install, "APP_DIR", app_dir):
            return install.install_macos_app(pyz, dev=dev), app_dir

    def test_creates_full_bundle_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, app = self._build(tmp)
            self.assertTrue((app / "Contents" / "Info.plist").exists())
            self.assertTrue((app / "Contents" / "MacOS" / "Glean").exists())
            self.assertTrue((app / "Contents" / "Resources" / "glean-code.pyz").exists())
            self.assertTrue(
                (app / "Contents" / "Resources" / "glean-launch.command").exists()
            )

    def test_executables_have_exec_bit(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, app = self._build(tmp)
            for rel in ("Contents/MacOS/Glean",
                        "Contents/Resources/glean-launch.command"):
                self.assertTrue((app / rel).stat().st_mode & 0o111, rel)

    def test_plist_declares_an_application_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, app = self._build(tmp)
            plist = (app / "Contents" / "Info.plist").read_text()
            self.assertIn("<string>APPL</string>", plist)
            self.assertIn(install.BUNDLE_ID, plist)
            self.assertIn(install.package_version(), plist)

    def test_plist_is_valid_xml(self):
        import plistlib
        with tempfile.TemporaryDirectory() as tmp:
            _, app = self._build(tmp)
            data = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
            self.assertEqual(data["CFBundleName"], "Glean")
            self.assertEqual(data["CFBundleExecutable"], "Glean")
            self.assertEqual(data["CFBundlePackageType"], "APPL")

    def test_dev_mode_changes_only_the_launch_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, app = self._build(tmp, dev=True)
            body = (app / "Contents" / "Resources" / "glean-launch.command").read_text()
            self.assertIn("-m glean_code", body)


class TestArgParsing(unittest.TestCase):
    def test_uninstall_dispatches_to_uninstall(self):
        with mock.patch.object(install, "do_uninstall", return_value=0) as m:
            install.main(["--uninstall"])
            m.assert_called_once()

    def test_verify_dispatches_to_verify(self):
        with mock.patch.object(install, "do_verify", return_value=0) as m:
            install.main(["--verify"])
            m.assert_called_once()

    def test_default_dispatches_to_install(self):
        with mock.patch.object(install, "do_install", return_value=0) as m:
            install.main([])
            m.assert_called_once()

    def test_prefix_flag_is_passed_through(self):
        with mock.patch.object(install, "do_install", return_value=0) as m:
            install.main(["--prefix", "/tmp/somewhere"])
            self.assertEqual(m.call_args[0][0].prefix, "/tmp/somewhere")


if __name__ == "__main__":
    unittest.main()
