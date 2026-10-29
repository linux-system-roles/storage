"""This module tests the order of the mounts returned by get_mount_info in blivet.py"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

import blivet


class FakeFstab(object):
    def lookup(self, key, value):
        return None


def make_volume(name, mount_point, fs_type="ext4", state="present"):
    return dict(name=name,
                state=state,
                fs_type=fs_type,
                mount_point=mount_point,
                mount_options="defaults",
                mount_check=0,
                mount_passno=0,
                mount_user=None,
                mount_group=None,
                mount_mode=None,
                _device="/dev/%s" % name,
                _mount_id="UUID=%s" % name)


def make_pool(name, volumes, state="present"):
    return dict(name=name, state=state, volumes=volumes)


def paths(mount_info):
    return [mount["path"] for mount in mount_info]


def test_pool_with_children_before_pool_with_root():
    """The /boot and /boot/efi partitions come before the pool holding /"""
    pools = [
        make_pool("/dev/vda", [make_volume("vda1", "/boot"),
                               make_volume("vda2", "/boot/efi", fs_type="efi")]),
        make_pool("vg.rh", [make_volume("swap", None, fs_type="swap"),
                            make_volume("root", "/")]),
    ]

    mount_info = blivet.get_mount_info(pools, [], [], FakeFstab())

    assert paths(mount_info) == ["none", "/", "/boot", "/boot/efi"]
    assert [mount["state"] for mount in mount_info] == ["present", "mounted", "mounted", "mounted"]


def test_nested_mounts_in_reverse_order():
    pools = [make_pool("pool", [make_volume("a", "/var/lib/data"),
                                make_volume("b", "/var/lib"),
                                make_volume("c", "/var"),
                                make_volume("d", "/")])]

    mount_info = blivet.get_mount_info(pools, [], [], FakeFstab())

    assert paths(mount_info) == ["/", "/var", "/var/lib", "/var/lib/data"]


def test_standalone_volumes_are_ordered_too():
    volumes = [make_volume("a", "/boot/efi"), make_volume("b", "/")]
    pools = [make_pool("pool", [make_volume("c", "/boot")])]

    mount_info = blivet.get_mount_info(pools, volumes, [], FakeFstab())

    assert paths(mount_info) == ["/", "/boot", "/boot/efi"]


def test_same_depth_keeps_configured_order():
    pools = [make_pool("pool", [make_volume("b", "/srv"),
                                make_volume("a", "/data"),
                                make_volume("c", "/opt")])]

    mount_info = blivet.get_mount_info(pools, [], [], FakeFstab())

    assert paths(mount_info) == ["/srv", "/data", "/opt"]


def test_trailing_slash_and_absent_volumes():
    pools = [make_pool("pool", [make_volume("a", "/boot/"),
                                make_volume("b", "/"),
                                make_volume("c", "/gone", state="absent")]),
             make_pool("removed", [make_volume("d", "/removed")], state="absent")]

    mount_info = blivet.get_mount_info(pools, [], [], FakeFstab())

    assert paths(mount_info) == ["/", "/boot/"]


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 2, 0)])
def test_result_independent_of_configured_order(order):
    mounts = ["/", "/boot", "/boot/efi"]
    pools = [make_pool("pool%d" % i, [make_volume("v%d" % i, mounts[i])]) for i in order]

    mount_info = blivet.get_mount_info(pools, [], [], FakeFstab())

    assert paths(mount_info) == mounts
