"""This module tests methods defined in the lvm_gensym.py module using the pytest framework"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest


import lvm_gensym


used_lv_names = ['root', 'root_0', 'root_1', 'root_2', 'root_3', 'swap_0', 'swap', 'swap_1']

test_lv_names = [{'fs_type': 'ext', 'mount': '/'},
                 {'fs_type': 'zfs', 'mount': '/home/user'},
                 {'fs_type': 'swap', 'mount': ''}
                ]  # noqa: E124

used_vg_names = ['linux_host', 'rhel_user0', 'rhel_0_user']

test_vg_names = ['rhel_user', 'rhel_user_0', 'rhel_user_1',
                 'rhel_user_2', 'rhel_user_3', 'linux_user',
                 'fedora_user', 'fedora_user_0', 'fedora_user_1'
                ]  # noqa: E124

lvm_facts = {'lvs': {'Home': '', 'Swap': '', 'Root': '',
                     'Root_0': '', 'root': '', 'root_0': '',
                     'swap': '', 'swap_0': '', 'swap_1': '',
                    },  # noqa: E124
             'vgs': {'rhel_user': '', 'rhel_user_0': '', 'rhel_user_1': ''}
            }  # noqa: E124


def test_unique_base_name():
    """Test whether the returned name is unique using a supplied list of test names"""
    assert lvm_gensym.get_unique_name_from_base('root', used_lv_names) == 'root_4'
    assert lvm_gensym.get_unique_name_from_base('rhel_user', test_vg_names) == 'rhel_user_4'


def test_return_val():
    """Verify that a supplied unique name and a list of used names returns True"""
    for (index, name) in enumerate(test_vg_names):
        assert lvm_gensym.name_is_unique(name[index], used_vg_names)


def test_get_base_vg_name():
    """Check generated base volume group name against the expected base name"""
    assert lvm_gensym.get_vg_name_base('hostname', 'rhel') == 'rhel_hostname'


@pytest.mark.parametrize("os_name", ["foo", "bar", "baz"])
def test_vg_eval(monkeypatch, os_name):
    """Check generated unique volume group name against the expected name"""
    def get_os_name():
        return os_name

    vg_names = [os_name + "_user", os_name + "_user_0", os_name + "_user_1"]
    _lvm_facts = dict(vgs=dict.fromkeys(vg_names), lvs=dict())
    monkeypatch.setattr(lvm_gensym, "get_os_name", get_os_name)
    assert lvm_gensym.get_vg_name('user', _lvm_facts) == os_name + '_user_2'
    assert lvm_gensym.get_vg_name('', _lvm_facts) == os_name


def test_lv_eval():
    """Test the generated unique logical volume name against the expected name"""
    expected = ['root_1', 'home_user', 'swap_2']

    for (ctr, name_inputs) in enumerate(test_lv_names):
        assert lvm_gensym.get_lv_name(name_inputs['fs_type'], name_inputs['mount'], lvm_facts) == expected[ctr]


def test_get_base_lv_name():
    """Test the generated base logical volume name against the expected name"""
    expected = ['root', 'home_user', 'swap']

    for (ctr, names_input) in enumerate(test_lv_names):
        assert lvm_gensym.get_lv_name_base(names_input['fs_type'], names_input['mount']) == expected[ctr]
