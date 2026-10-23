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

from google.protobuf import descriptor_pool
from google.protobuf.type_pb2 import Type

from robo_orchard_build.ext.protobuf import _build_file_descriptor_set


def test_native_descriptors_form_a_loadable_dependency_set():
    """Real descriptors serialize with complete, ordered dependencies."""
    descriptors = _build_file_descriptor_set([Type])
    names = [file.name for file in descriptors.file]
    assert names[-1] == Type.DESCRIPTOR.file.name
    assert len(names) == len(set(names))

    pool = descriptor_pool.DescriptorPool()
    for file in descriptors.file:
        pool.Add(file)
    assert (
        pool.FindMessageTypeByName(Type.DESCRIPTOR.full_name).full_name
        == Type.DESCRIPTOR.full_name
    )
