"""Tests for utils.dependency_check module."""
from __future__ import annotations

from unittest import mock

import pytest

from utils.dependency_check import (
    check_and_install_dependencies,
    check_package,
    install_package,
)


class TestCheckPackage:
    """Tests for check_package()."""

    def test_stdlib_module_found(self):
        assert check_package("os") is True

    def test_missing_module(self):
        assert check_package("nonexistent_fake_pkg_xyz") is False


class TestInstallPackage:
    """Tests for install_package()."""

    def test_success(self):
        completed = mock.Mock(returncode=0, stderr="")
        with mock.patch("utils.dependency_check.subprocess.run", return_value=completed) as run_mock:
            assert install_package("some-pkg") is True
            run_mock.assert_called_once()

    def test_failure_nonzero(self):
        completed = mock.Mock(returncode=1, stderr="error")
        with mock.patch("utils.dependency_check.subprocess.run", return_value=completed):
            assert install_package("bad-pkg") is False

    def test_timeout(self):
        import subprocess
        with mock.patch(
            "utils.dependency_check.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=5),
        ):
            assert install_package("slow-pkg", timeout=5) is False


class TestCheckAndInstallDependencies:
    """Tests for check_and_install_dependencies()."""

    def test_all_present(self):
        pkg_map = {"os": "os-pkg", "sys": "sys-pkg"}
        installed, failed = check_and_install_dependencies(auto_install=False, package_map=pkg_map)
        assert installed == []
        assert failed == []

    def test_missing_without_auto_install(self):
        pkg_map = {"nonexistent_xyz": "fake-pkg"}
        installed, failed = check_and_install_dependencies(auto_install=False, package_map=pkg_map)
        assert installed == []
        assert failed == ["fake-pkg"]

    def test_missing_with_auto_install_success(self):
        pkg_map = {"nonexistent_xyz": "fake-pkg"}
        with mock.patch("utils.dependency_check.install_package", return_value=True) as ip:
            installed, failed = check_and_install_dependencies(auto_install=True, package_map=pkg_map)
            ip.assert_called_once_with("fake-pkg")
        assert installed == ["fake-pkg"]
        assert failed == []

    def test_missing_with_auto_install_failure(self):
        pkg_map = {"nonexistent_xyz": "fake-pkg"}
        with mock.patch("utils.dependency_check.install_package", return_value=False):
            installed, failed = check_and_install_dependencies(auto_install=True, package_map=pkg_map)
        assert installed == []
        assert failed == ["fake-pkg"]
