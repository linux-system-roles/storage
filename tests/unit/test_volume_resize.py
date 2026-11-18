"""Exercise resize planning without a block device or a Blivet installation."""
# Assisted by OpenCode using model GPT-6.1 Sol
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import logging
from collections import namedtuple

import pytest

import blivet


class Bytes(float):
    def convert_to(self):
        return self


class Format(object):
    def __init__(self, name, refreshed, supported=True):
        self.type = name
        self.refreshed = refreshed
        self.supported = supported
        self.ready = False
        self.status = True
        self.mountable = name != "luks"
        self._resize_support = 1
        self.unmounted = False

    @property
    def resizable(self):
        return self.ready and self.supported

    def update_size_info(self):
        self.refreshed.append(self.type)
        self.ready = True

    def teardown(self):
        self.unmounted = True


class Device(object):
    def __init__(self, name, size, fmt, raw=None):
        self.name = name
        self.type = "luks/dm-crypt" if raw else "lvmlv"
        self.size = Bytes(size)
        self.sector_size = 1
        self.format = fmt
        self.raw_device = raw if raw else self
        self.parents = [raw] if raw else []
        self.min_size = Bytes(size)
        self.max_size = Bytes(200 if raw is None else 190)
        self.exists = True

    @property
    def resizable(self):
        return self.format.resizable and (
            self.raw_device is self or self.raw_device.resizable)


class Backend(object):
    def __init__(self):
        self.calls = []

    def resize_device(self, device, size):
        self.calls.append((device, size))


class FsLib(object):
    class FSResize(object):
        ONLINE_GROW = 1
        ONLINE_SHRINK = 2


@pytest.fixture
def volume(monkeypatch):
    monkeypatch.setattr(blivet, "log", logging.getLogger(__name__), raising=False)
    monkeypatch.setattr(blivet, "fslib", FsLib, raising=False)
    monkeypatch.setattr(blivet, "safe_mode", True)
    refreshed = []
    raw = Device("vg-lv", 100, Format("luks", refreshed))
    raw.path = "/dev/vg/lv"
    raw.format._header_size = Bytes(10)
    info = namedtuple("LUKSInfo", ["metadata_size"])(10)
    monkeypatch.setattr(blivet, "BlockDev", type("BD", (), {"crypto_luks_info": staticmethod(lambda path: info)}), raising=False)
    monkeypatch.setattr(blivet, "Size", Bytes, raising=False)
    fs = Device("custom-map", 90, Format("xfs", refreshed), raw)
    volume = blivet.BlivetVolume(Backend(), dict(name="lv"))
    volume._device = fs
    volume._get_size = lambda: Bytes(120)
    return volume, raw, fs, refreshed


def test_encrypted_resize_refreshes_both_layers_and_targets_raw(volume):
    v, raw, fs, refreshed = volume
    v._resize()
    assert refreshed == ["luks", "xfs"]
    assert v._blivet.calls == [(raw, 120)]
    assert not fs.format.unmounted


def test_matching_raw_size_is_unchanged(volume):
    v, raw, fs, refreshed = volume
    v._get_size = lambda: raw.size
    v._resize()
    assert not refreshed
    assert not v._blivet.calls


# Assisted by OpenCode using model GPT-6.2 Astra
def test_legacy_header_size_blocks_resize_but_not_unchanged_volume(volume, monkeypatch):
    v, raw, fs, refreshed = volume
    del raw.format._header_size
    crypto = type("Crypto", (), {"LUKS_METADATA_SIZE": Bytes(2)})
    monkeypatch.setattr(blivet, "devicelibs", type("Libs", (), {"crypto": crypto}), raising=False)
    monkeypatch.setattr(blivet.BlockDev, "crypto_luks_get_metadata_size", staticmethod(lambda path: 10), raising=False)
    with pytest.raises(blivet.BlivetAnsibleError, match="Blivet assumes a LUKS data offset"):
        v._resize()
    v._get_size = lambda: raw.size
    v._resize()
    assert not refreshed and not fs.format.unmounted and not v._blivet.calls


def test_matching_raw_target_with_short_mapping_is_not_converged(volume):
    v, raw, fs, refreshed = volume
    raw.size = Bytes(120)
    with pytest.raises(blivet.BlivetAnsibleError, match="LUKS mapping.*payload"):
        v._resize()
    assert not refreshed and not fs.format.unmounted and not v._blivet.calls


def test_unmappable_tail_is_not_a_short_mapping(volume):
    v, raw, fs, refreshed = volume
    fs.sector_size = 4
    fs.size = Bytes(88)  # 90 bytes of payload, 88 whole-sector bytes.
    v._get_size = lambda: raw.size
    v._resize()
    assert not refreshed and not v._blivet.calls


def test_inferred_size_preserves_raw_volume(volume):
    v, raw, fs, refreshed = volume
    assert v._update_from_device("size")
    assert v._volume["size"] == raw.size
    v._get_size = lambda: Bytes(v._volume["size"])
    v._resize()
    assert not v._blivet.calls


@pytest.mark.parametrize("layer", ["luks", "xfs"])
def test_unresizable_mismatch_fails_without_unmount(volume, layer):
    v, raw, fs, refreshed = volume
    (raw if layer == "luks" else fs).format.supported = False
    with pytest.raises(blivet.BlivetAnsibleError, match="cannot be resized"):
        v._resize()
    assert not fs.format.unmounted
    assert not v._blivet.calls


@pytest.mark.parametrize("target", [50, 250])
def test_invalid_limits_fail_before_unmount(volume, target):
    v, raw, fs, refreshed = volume
    v._get_size = lambda: Bytes(target)
    with pytest.raises(blivet.BlivetAnsibleError, match="cannot be resized"):
        v._resize()
    assert not fs.format.unmounted
    assert not v._blivet.calls


def test_filesystem_limit_includes_luks_metadata(volume):
    v, raw, fs, refreshed = volume
    fs.max_size = Bytes(105)
    # Raw target 120 would require payload 110, exceeding the filesystem limit.
    with pytest.raises(blivet.BlivetAnsibleError, match="cannot be resized"):
        v._resize()
    assert not v._blivet.calls


@pytest.mark.parametrize("target,safe", [(120, True), (80, True), (80, False)])
def test_mounted_offline_resize(volume, monkeypatch, target, safe):
    v, raw, fs, refreshed = volume
    fs.format._resize_support = 0
    raw.min_size, fs.min_size = Bytes(40), Bytes(30)
    v._get_size = lambda: Bytes(target)
    monkeypatch.setattr(blivet, "safe_mode", safe)
    if safe:
        with pytest.raises(blivet.BlivetAnsibleError, match="must be unmounted"):
            v._resize()
        assert not fs.format.unmounted
        assert not v._blivet.calls
    else:
        def resize_after_unmount(device, size):
            assert fs.format.unmounted
            v._blivet.calls.append((device, size))
        monkeypatch.setattr(v._blivet, "resize_device", resize_after_unmount)
        v._resize()
        assert v._blivet.calls == [(raw, target)]


def test_plain_volume_still_targets_itself(volume):
    v, raw, fs, refreshed = volume
    raw.format = fs.format
    v._device = raw
    v._resize()
    assert refreshed == ["xfs"]
    assert v._blivet.calls == [(raw, 120)]


@pytest.mark.parametrize("operation,state", [
    ("create", "present"), ("destroy", "absent"),
    ("resize", None), ("configure", None),
])
def test_only_luks_lifecycle_actions_change_crypttab(volume, operation, state):
    v, raw, fs, refreshed = volume
    raw.path = "/dev/vg/lv"
    raw.format.map_name = "custom-map"
    raw.format.key_file = None
    action = type("Action", (object,), dict(
        is_format=True, format=raw.format, device=raw,
        is_create=operation == "create", is_destroy=operation == "destroy"))()
    result = blivet.get_crypt_info([action])
    if state is None:
        assert result == []
    else:
        assert result == [dict(backing_device=raw.path, name="custom-map",
                               password="-", state=state)]
