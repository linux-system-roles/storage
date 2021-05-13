from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest
import find_unused_disk
import os


blkid_data_pttype = [('/dev/sdx', '/dev/sdx: PTTYPE=\"dos\"'),
                     ('/dev/sdy', '/dev/sdy: PTTYPE=\"test\"')]

blkid_data = [('/dev/sdx', 'UUID=\"hello-1234-56789\" TYPE=\"crypto_LUKS\"'),
              ('/dev/sdy', 'UUID=\"this-1s-a-t3st-f0r-ansible\" VERSION=\"LVM2 001\" TYPE=\"LVM2_member\" USAGE=\"raid\"'),
              ('/dev/sdz', 'LABEL=\"/data\" UUID=\"a12bcdef-345g-67h8-90i1-234j56789k10\" VERSION=\"1.0\" TYPE=\"ext4\" USAGE=\"filesystem\"')]

holders_data_none = [('/dev/sdx', ''),
                     ('/dev/dm-99', '')]

holders_data = [('/dev/sdx', 'dm-0'),
                ('/dev/dm-99', 'dm-2 dm-3 dm-4')]


@pytest.mark.parametrize('disk, blkid', blkid_data_pttype)
def test_no_signature_true(disk, blkid):
    def run_command(args):
        return [0, blkid, '']
    assert find_unused_disk.no_signature(run_command, disk) is True


@pytest.mark.parametrize('disk, blkid', blkid_data)
def test_no_signature_false(disk, blkid):
    def run_command(args):
        return [0, blkid, '']
    assert find_unused_disk.no_signature(run_command, disk) is False


@pytest.mark.parametrize('disk, holders', holders_data_none)
def test_no_holders_true(disk, holders, monkeypatch):
    def mock_return(args):
        return holders
    monkeypatch.setattr(os, 'listdir', mock_return)
    assert find_unused_disk.no_holders(disk) is True


@pytest.mark.parametrize('disk, holders', holders_data)
def test_no_holders_false(disk, holders, monkeypatch):
    def mock_return(args):
        return holders
    monkeypatch.setattr(os, 'listdir', mock_return)
    assert find_unused_disk.no_holders(disk) is False


def test_can_open_true(monkeypatch):
    def mock_return(args, flag):
        return True
    monkeypatch.setattr(os, 'open', mock_return)
    assert find_unused_disk.can_open('/hello') is True


def test_can_open_false(monkeypatch):
    def mock_return(args, flag):
        raise OSError
    monkeypatch.setattr(os, 'open', mock_return)
    assert find_unused_disk.can_open('/hello') is False


def test_is_ignored(monkeypatch):
    def mock_realpath(path):
        return path
    monkeypatch.setattr(os.path, 'realpath', mock_realpath)
    assert find_unused_disk.is_ignored('/dev/sda') is False
    assert find_unused_disk.is_ignored('/dev/vda') is False
    assert find_unused_disk.is_ignored('/dev/mapper/mpatha') is False
    assert find_unused_disk.is_ignored('/dev/md/Volume0') is False
    assert find_unused_disk.is_ignored('/dev/nullb0') is True
