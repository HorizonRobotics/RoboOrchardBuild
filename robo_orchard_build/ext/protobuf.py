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
import subprocess
from typing import List, Optional, Set, Type, cast

import google.protobuf.message
from google.protobuf.descriptor import FileDescriptor
from google.protobuf.descriptor_pb2 import FileDescriptorSet

from robo_orchard_build.ext.build_ext import (
    RoboOrcahrdExtension,
    content_replace,
    find_files,
)

__all__ = ["ProtocolExtension"]


def _build_file_descriptor_set(
    message_classes: List[Type[google.protobuf.message.Message]],
) -> FileDescriptorSet:
    file_descriptor_set = FileDescriptorSet()
    seen_dependencies: Set[str] = set()

    def append_file_descriptor(file_descriptor: FileDescriptor):
        for dep in file_descriptor.dependencies:
            if dep.name not in seen_dependencies:
                seen_dependencies.add(dep.name)
                append_file_descriptor(dep)
        hd = file_descriptor_set.file.add()
        file_descriptor.CopyToProto(hd)  # type: ignore

    for message_class in message_classes:
        # Python and upb descriptors expose the same public descriptor API.
        append_file_descriptor(
            cast(FileDescriptor, message_class.DESCRIPTOR.file)
        )
    return file_descriptor_set


def build_proto_files(
    proto_files: List[str],
    output_dir: str,
    import_dirs: List[str],
    dependent_message_classes: List[Type[google.protobuf.message.Message]],
    package_name_mapping: Optional[dict[str, str]] = None,
    pydantic_output_dir: Optional[str] = None,
):
    """Build proto files to python files."""

    # generate dependent file descriptor set
    fds = _build_file_descriptor_set(dependent_message_classes)
    dep_dfs_path = os.path.join(output_dir, "dep_dfs.pb")
    with open(dep_dfs_path, "wb") as f:
        f.write(fds.SerializeToString())

    cmds = ["python3", "-m", "grpc_tools.protoc"]
    cmds += [f"--proto_path={import_dir}" for import_dir in import_dirs]
    cmds.extend(
        [
            f"--descriptor_set_in={dep_dfs_path}",
            f"--python_out={output_dir}",
            f"--mypy_out={output_dir}",
        ]
    )
    if pydantic_output_dir:
        cmds.extend(
            [
                f"--protobuf-to-pydantic_out={pydantic_output_dir}",
            ]
        )

    for proto_file in proto_files:
        # we cannot call grpc_tools.protoc directly, need to use
        # python -m grpc_tools.protoc
        print("try to run: ", cmds + [proto_file])
        if subprocess.run(cmds + [proto_file]).returncode != 0:
            raise RuntimeError(
                f"protoc failed on {proto_file}. "
                f"You can use following command to debug: "
                f"{' '.join(cmds + [proto_file])}"
            )

    if os.path.exists(dep_dfs_path):
        os.remove(dep_dfs_path)

    if package_name_mapping is not None:
        # replace package name in generated files since protobuf does not
        # support it.
        # https://github.com/protocolbuffers/protobuf/issues/7061
        mapping_dict = {}
        for k, v in package_name_mapping.items():
            mapping_dict.update(
                {
                    f"from {k}": f"from {v}",
                    f"import {k}": f"import {v}",
                    f" {k}.": f" {v}.",
                }
            )

        for file in find_files(
            output_dir, exts=(".py", ".pyi"), recursive=True
        ):
            if file.endswith("pb2.py") or file.endswith("pb2.pyi"):
                content_replace(file, mapping_dict)


class ProtocolExtension(RoboOrcahrdExtension):
    """ProtocolExtension is used to build proto files to python files.

    Args:
        name (str): The name of extension.
        proto_files (List[str]): The proto files to build.
        output_dir (str): The output directory of generated files.
        import_dirs (List[str]): the import directories of proto files.
        dependencies (List[Type[google.protobuf.message.Message]]): The
            dependent message classes.
        package_name_mapping (Optional[Dict[str, str]]): the mapping of
            package names.
        pydantic_output_dir (Optional[str]): the output directory of pydantic
            models.

    """

    SKIP_RUN: bool = True

    def __init__(
        self,
        name: str,
        proto_files: List[str],
        output_dir: str,
        import_dirs: List[str],
        dependencies: List[Type[google.protobuf.message.Message]] | None,
        package_name_mapping: Optional[dict[str, str]] = None,
        pydantic_output_dir: Optional[str] = None,
    ) -> None:
        super(ProtocolExtension, self).__init__(name, sources=[])

        # Preparing files should be done in __init__
        if dependencies is None:
            dependencies = []

        build_proto_files(
            proto_files,
            output_dir,
            import_dirs,
            dependent_message_classes=dependencies,
            package_name_mapping=package_name_mapping,
            pydantic_output_dir=pydantic_output_dir,
        )

    def before_run(self):
        pass

    def after_run(self):
        pass
