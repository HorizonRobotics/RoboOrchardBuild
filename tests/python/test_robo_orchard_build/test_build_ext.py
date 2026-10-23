# Project RoboOrchard
#
# Copyright (c) 2024-2026 Horizon Robotics. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

import importlib.util
import shutil
import sysconfig
from pathlib import Path

import pytest
from setuptools import Distribution, Extension
from setuptools.command.build_ext import build_ext

from robo_orchard_build.ext.build_ext import (
    RoboOrcahrdExtension,
    RoboOrchardBuildExt,
)


class _CustomExtension(RoboOrcahrdExtension):
    def __init__(self, name, output, events, *, skip=False, fail=False):
        super().__init__(name, sources=[])
        self.output = output
        self.events = events
        self.SKIP_RUN = skip
        self.fail = fail

    def before_run(self):
        self.events.append(f"before:{self.name}")

    def after_run(self):
        self.events.append(f"after:{self.name}")

    def build(self, command):
        self.events.append(f"build:{self.name}")
        if self.fail:
            raise RuntimeError("custom build failed")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"custom output")


def _command(extensions, tmp_path):
    command = RoboOrchardBuildExt(Distribution({"ext_modules": extensions}))
    command.build_lib = str(tmp_path / "default-lib")
    command.build_temp = str(tmp_path / "objects")
    command.ensure_finalized()
    return command


def test_custom_output_does_not_fall_through_to_setuptools(
    tmp_path, monkeypatch
):
    """A custom build outside the default output never invokes setuptools."""
    events = []
    output = tmp_path / "package" / "_C" / "custom.so"
    extension = _CustomExtension("custom", output, events)
    command = _command([extension], tmp_path)
    default_output = Path(command.get_ext_fullpath(extension.name))

    def unexpected_build(self, ext):
        pytest.fail("custom extension reached the setuptools builder")

    monkeypatch.setattr(build_ext, "build_extension", unexpected_build)
    assert extension.sources == []
    assert not default_output.exists()
    command.build_extension(extension)

    assert events == ["build:custom"]
    assert output.read_bytes() == b"custom output"
    assert not default_output.exists()


def test_ordinary_extension_delegates_once(tmp_path, monkeypatch):
    """An ordinary Extension still reaches the parent exactly once."""
    extension = Extension("ordinary", sources=["ordinary.c"])
    command = _command([extension], tmp_path)
    calls = []

    def record_build(self, ext):
        calls.append((self, ext))

    monkeypatch.setattr(build_ext, "build_extension", record_build)
    command.build_extension(extension)
    assert calls == [(command, extension)]


def test_custom_failure_propagates_without_fallback(tmp_path, monkeypatch):
    """A failed custom build propagates its error without a fallback build."""
    events = []
    extension = _CustomExtension(
        "custom", tmp_path / "custom.so", events, fail=True
    )
    command = _command([extension], tmp_path)

    def unexpected_build(self, ext):
        pytest.fail("failed custom extension reached the parent builder")

    monkeypatch.setattr(build_ext, "build_extension", unexpected_build)
    with pytest.raises(RuntimeError, match="custom build failed"):
        command.build_extension(extension)
    assert events == ["build:custom"]


@pytest.mark.parametrize("fail", [False, True])
def test_custom_lifecycle_and_skip_run(tmp_path, monkeypatch, fail):
    """Skipped hooks retain their order; build failure stops after hooks."""
    events = []
    active = _CustomExtension(
        "active", tmp_path / "active.so", events, fail=fail
    )
    skipped = _CustomExtension(
        "skipped", tmp_path / "skipped.so", events, skip=True
    )
    command = _command([active, skipped], tmp_path)

    def run_extensions(self):
        assert self.extensions == [active]
        for extension in self.extensions:
            self.build_extension(extension)

    monkeypatch.setattr(build_ext, "run", run_extensions)
    if fail:
        with pytest.raises(RuntimeError, match="custom build failed"):
            command.run()
    else:
        command.run()

    expected = ["before:active", "before:skipped", "build:active"]
    if not fail:
        expected.extend(["after:active", "after:skipped"])
    assert events == expected
    assert not skipped.output.exists()


def _write_native_source(path, module_name, answer):
    path.write_text(
        f"""#include <Python.h>
static PyObject *answer(PyObject *self, PyObject *args) {{
    return PyLong_FromLong({answer});
}}
static PyMethodDef methods[] = {{
    {{"answer", answer, METH_NOARGS, NULL}},
    {{NULL, NULL, 0, NULL}}
}};
static struct PyModuleDef module = {{
    PyModuleDef_HEAD_INIT, "{module_name}", NULL, -1, methods
}};
PyMODINIT_FUNC PyInit_{module_name}(void) {{
    return PyModule_Create(&module);
}}
"""
    )


def test_custom_and_ordinary_native_outputs_are_loadable(
    tmp_path, monkeypatch
):
    """Real custom and standard C extensions build once and load correctly."""
    if shutil.which("cc") is None:
        pytest.skip("a C compiler is required for native integration")
    if not (Path(sysconfig.get_path("include")) / "Python.h").is_file():
        pytest.skip("Python development headers are required")

    custom_name = "_dispatch_custom_probe"
    ordinary_name = "_dispatch_ordinary_probe"
    custom_source = tmp_path / "custom.c"
    ordinary_source = tmp_path / "ordinary.c"
    _write_native_source(custom_source, custom_name, 42)
    _write_native_source(ordinary_source, ordinary_name, 7)
    events = []
    custom_output = (
        tmp_path
        / "package"
        / "_C"
        / f"{custom_name}{sysconfig.get_config_var('EXT_SUFFIX')}"
    )

    class NativeCustomExtension(_CustomExtension):
        def build(self, command):
            self.events.append(f"build:{self.name}")
            self.output.parent.mkdir(parents=True, exist_ok=True)
            objects = command.compiler.compile(
                [str(custom_source)],
                output_dir=command.build_temp,
                include_dirs=[sysconfig.get_path("include")],
            )
            command.compiler.link_shared_object(objects, str(self.output))

    custom = NativeCustomExtension(custom_name, custom_output, events)
    ordinary = Extension(ordinary_name, sources=[str(ordinary_source)])
    command = _command([custom, ordinary], tmp_path)
    parent_build = build_ext.build_extension
    parent_calls = []

    def record_parent(self, extension):
        parent_calls.append(extension.name)
        return parent_build(self, extension)

    monkeypatch.setattr(build_ext, "build_extension", record_parent)
    command.run()

    assert parent_calls == [ordinary_name]
    assert events == [
        f"before:{custom_name}",
        f"build:{custom_name}",
        f"after:{custom_name}",
    ]
    assert not Path(command.get_ext_fullpath(custom_name)).exists()
    ordinary_output = Path(command.get_ext_fullpath(ordinary_name))
    for name, output, expected in [
        (custom_name, custom_output, 42),
        (ordinary_name, ordinary_output, 7),
    ]:
        spec = importlib.util.spec_from_file_location(name, output)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.answer() == expected
