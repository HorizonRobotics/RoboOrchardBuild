# Project RoboOrchard
#
# Copyright (c) 2025 Horizon Robotics. All Rights Reserved.
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

import os
from abc import abstractmethod
from typing import Iterable, List, Optional

from setuptools.command.build_ext import build_ext
from setuptools.extension import Extension

__all__ = [
    "find_files",
    "content_replace",
    "get_file_content",
    "RoboOrcahrdExtension",
    "RoboOrchardBuildExt",
]


def find_files(
    src_fold: str,
    exts: Iterable[str] = (".c", ".cc", ".cpp"),
    recursive: bool = True,
    exclude_dir: Iterable[str] = (),
    followlinks: bool = True,
) -> List[str]:
    """Find files with specified extensions in source folder.

    Args:
        src_fold (str): the source folder.
        exts (Iterable[str]): the extensions of files to find.
        recursive (bool): whether to search recursively.
        exclude_dir (Iterable[str]): the directories to exclude. If the root
            of the directory contains any of the exclude_dir, the directory
            will be excluded.
        followlinks (bool): whether to follow symbolic links. Default is True.
    """

    assert os.path.exists(src_fold)

    source = []
    for root, folder, files in os.walk(src_fold, followlinks=followlinks):
        if not recursive:
            folder.clear()
        exclude_flag = False
        for dir in exclude_dir:
            if root.startswith(dir):
                exclude_flag = True
                break

        if exclude_flag:
            continue
        for f in files:
            for ext in exts:
                if f.endswith(ext):
                    source.append(os.path.join(root, f))
                    break
    return source


def content_replace(file: str, replace_mapping: dict[str, str]):
    """Replace content in files.

    Args:
        file (str): file path
        replace_mapping (Dict[str, str]): the mapping of content to replace.

    """
    with open(file, "r") as f:
        content = f.read()

    for k, v in replace_mapping.items():
        content = content.replace(k, v)

    with open(file, "w") as f:
        f.write(content)


def get_file_content(path: str) -> Optional[str]:
    """Get file content.

    Args:
        path (str): the path of the file

    Returns:
        Optional[str]: the content of the file
    """
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        content = f.read()
    return content


class RoboOrcahrdExtension(Extension):
    SKIP_RUN: bool = False

    @abstractmethod
    def before_run(self):
        pass

    @abstractmethod
    def after_run(self):
        pass

    def build(self, build_ext: "RoboOrchardBuildExt"):
        """Build the complete custom extension, including output placement.

        Subclasses own compilation and linking. After this method succeeds,
        the command does not run the ordinary setuptools compiler for this
        extension. Lifecycle hooks are managed by the command's ``run()``.
        """
        if self.SKIP_RUN:
            raise RuntimeError("This extension should not be run")

    def run(self, build_ext: Optional["RoboOrchardBuildExt"] = None):
        """Run the extension.

        This method will call before_run, build and after_run in order.
        If build_ext is None, it will only call before_run and after_run.
        """

        self.before_run()
        if build_ext is not None:
            self.build(build_ext)
        self.after_run()


class RoboOrchardBuildExt(build_ext):
    """Run custom builds alongside ordinary setuptools extensions.

    Custom extensions own their complete build through ``build()``. Their
    ``before_run()`` hook runs before the build command and ``after_run()``
    runs after that command succeeds. ``SKIP_RUN`` extensions run only those
    hooks. Build failures propagate without running the remaining hooks.
    """

    def run(self):
        if not self.extensions:
            return

        source_extension = self.extensions

        ext_list = []
        for ext in self.extensions:
            if isinstance(ext, RoboOrcahrdExtension):
                ext.before_run()
                if not ext.SKIP_RUN:
                    ext_list.append(ext)
            else:
                ext_list.append(ext)
        self.extensions = ext_list
        super(RoboOrchardBuildExt, self).run()

        for ext in source_extension:
            if isinstance(ext, RoboOrcahrdExtension):
                ext.after_run()

    def build_extension(self, ext: Extension) -> None:
        """Dispatch each extension to its custom or setuptools builder."""
        if isinstance(ext, RoboOrcahrdExtension):
            assert ext.SKIP_RUN is False, "SKIP_RUN must be False"
            ext.build(self)
            return
        super(RoboOrchardBuildExt, self).build_extension(ext)
