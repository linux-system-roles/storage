from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import pytest

import resolve_blockdev


blkid_data = [('LABEL=target', '/dev/sdx3'),
              ('UUID=6c75fa75-e5ab-4a12-a567-c8aa0b4b60a5', '/dev/sdaz'),
              ('LABEL=missing', '')]

path_data = ['/dev/md/unreal',
             '/dev/mapper/fakevg-fakelv',
             '/dev/adisk',
             '/dev/disk/by-id/wwn-0x123456789abc']

canonical_paths = {"/dev/sda": "/dev/sda",
                   "/dev/dm-3": "/dev/mapper/vg_system-lv_data",
                   "/dev/md127": "/dev/md/userdb",
                   "/dev/notfound": ""}


@pytest.mark.parametrize('spec,device', blkid_data)
def test_key_value_pair(spec, device, monkeypatch):
    def run_cmd(args):
        for _spec, _dev in blkid_data:
            if _spec in args:
                break
        else:
            _dev = ''
        return (0, _dev, '')

    monkeypatch.setattr(os.path, 'exists', lambda p: True)
    assert resolve_blockdev.resolve_blockdev(spec, run_cmd) == device


@pytest.mark.parametrize('name', [os.path.basename(p) for p in path_data])
def test_device_names(name, monkeypatch):
    """ Test return values for basename specs, assuming all paths are real. """
    def path_exists(path):
        return next((data for data in path_data if data == path), False)

    expected = next((data for data in path_data if os.path.basename(data) == name), '')
    monkeypatch.setattr(os.path, 'exists', path_exists)
    assert resolve_blockdev.resolve_blockdev(name, None) == expected


def test_device_name(monkeypatch):
    assert os.path.exists('/dev/xxx') is False

    monkeypatch.setattr(os.path, 'exists', lambda p: True)
    assert resolve_blockdev.resolve_blockdev('xxx', None) == '/dev/xxx'

    monkeypatch.setattr(os.path, 'exists', lambda p: False)
    assert resolve_blockdev.resolve_blockdev('xxx', None) == ''


def test_full_path(monkeypatch):
    path = "/dev/idonotexist"
    monkeypatch.setattr(os.path, 'exists', lambda p: True)
    assert resolve_blockdev.resolve_blockdev(path, None) == path

    monkeypatch.setattr(os.path, 'exists', lambda p: False)
    assert resolve_blockdev.resolve_blockdev(path, None) == ''

    path = "/dev/disk/by-label/alabel"
    monkeypatch.setattr(os.path, 'exists', lambda p: True)
    assert resolve_blockdev.resolve_blockdev(path, None) == path

    monkeypatch.setattr(os.path, 'exists', lambda p: False)
    assert resolve_blockdev.resolve_blockdev(path, None) == ''


@pytest.mark.parametrize('device', list(canonical_paths.keys()))
def test_canonical_path(device, monkeypatch):
    def _get_name(device):
        name = os.path.basename(canonical_paths[device])
        if not name:
            raise Exception("failed to find name")
        return name

    monkeypatch.setattr(resolve_blockdev, '_get_dm_name_from_kernel_dev', _get_name)
    monkeypatch.setattr(resolve_blockdev, '_get_md_name_from_kernel_dev', _get_name)

    canonical = canonical_paths[device]
    if canonical:
        assert resolve_blockdev.canonical_device(device) == canonical
