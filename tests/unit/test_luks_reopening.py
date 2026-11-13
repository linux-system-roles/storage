# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.1 Sol
"""Existing mapping names and unrelated swap behavior survive LUKS inspection."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import io
import unittest

import blivet


class PatchTestCase(unittest.TestCase):
    def patch(self, obj, name, value):
        missing = object()
        old = getattr(obj, name, missing)

        def restore():
            if old is missing:
                delattr(obj, name)
            else:
                setattr(obj, name, old)

        self.addCleanup(restore)
        setattr(obj, name, value)


class FakeLUKSError(Exception):
    pass


class FakeFormat(object):
    def __init__(self, fmt_type='luks'):
        self.type = fmt_type
        self.map_name = 'luks-test-uuid'
        self.passphrase = None
        self.key_file = None
        self.status = False
        self.setup_calls = 0

    @property
    def has_key(self):
        return bool(self.passphrase or self.key_file)

    def setup(self):
        self.setup_calls += 1
        if self.passphrase == 'wrong':
            raise FakeLUKSError('incorrect credential')
        self.status = True


class FakeDevice(object):
    def __init__(self, path, fmt_type='luks', raw_device=None):
        self.path = path
        self.format = FakeFormat(fmt_type)
        self.original_format = FakeFormat(fmt_type)
        self.children = []
        self.raw_device = raw_device or self
        self.status = True
        self.fstab_spec = 'UUID=inner-uuid'

    @property
    def isleaf(self):
        return not self.children


class FakeTree(object):
    def __init__(self, device):
        self.device = device
        self.entries = {'volume': device, 'UUID=test-uuid': device, device.path: device}

    def resolve_device(self, spec):
        return self.entries.get(spec)

    def populate(self):
        if self.device.format.status and not self.device.children:
            self.device.children.append(FakeDevice('/dev/mapper/' + self.device.format.map_name,
                                                   fmt_type='xfs', raw_device=self.device))


class FakeBlivet(object):
    def __init__(self, device):
        self.devicetree = FakeTree(device)


class TestLUKSMapNames(PatchTestCase):
    def setUp(self):
        self.device = FakeDevice('/dev/test-raw')
        self.b = FakeBlivet(self.device)
        self.patch(blivet.os.path, 'exists', lambda path: True)
        self.patch(blivet.os.path, 'lexists', lambda path: False)
        self.patch(blivet, 'open', lambda path: io.StringIO(self.text))
        self.patch(blivet, 'temporary_luks_formats', [])
        self.patch(blivet, 'check_mode', False)
        self.patch(blivet, 'LUKSError', FakeLUKSError)
        self.text = u'custom UUID=test-uuid - luks,tpm2-device=auto\n'

    def lookup(self, **options):
        spec = dict(name='volume', encryption=True, encryption_password='correct')
        spec.update(options)
        volume = blivet.BlivetVolume(self.b, spec)
        volume._look_up_device()
        return volume

    def test_uuid_entry_preserves_both_format_names(self):
        volume = self.lookup()
        self.assertEqual(volume._device.path, '/dev/mapper/custom')
        self.assertEqual(self.device.format.map_name, 'custom')
        self.assertEqual(self.device.original_format.map_name, 'custom')

    def test_path_and_two_field_entry(self):
        self.text = u'custom /dev/test-raw\n'
        self.assertEqual(self.lookup()._device.path, '/dev/mapper/custom')

    def test_key_file_reopening_preserves_the_name(self):
        volume = self.lookup(encryption_password=None, encryption_key='/root/existing.key')
        self.assertEqual(volume._device.path, '/dev/mapper/custom')
        self.assertEqual(self.device.format.key_file, '/root/existing.key')
        self.assertEqual(self.device.original_format.key_file, '/root/existing.key')

    def test_comments_blank_and_unrelated_entries(self):
        self.text = u'\n  # ignored UUID=test-uuid\nmalformed\nother /dev/missing - luks\n'
        self.assertEqual(self.lookup()._device.path, '/dev/mapper/luks-test-uuid')

    def test_missing_crypttab_keeps_default(self):
        self.patch(blivet.os.path, 'exists', lambda path: False)
        self.assertEqual(self.lookup()._device.path, '/dev/mapper/luks-test-uuid')

    def test_unreadable_crypttab_fails_before_setup(self):
        def unreadable(path):
            raise IOError('cannot read crypttab')

        self.patch(blivet, 'open', unreadable)
        with self.assertRaises(IOError):
            self.lookup()
        self.assertEqual(self.device.format.setup_calls, 0)

    def test_identical_duplicate_entry_is_unambiguous(self):
        self.text += u'custom /dev/test-raw\n'
        self.assertEqual(self.lookup()._device.path, '/dev/mapper/custom')

    def test_two_names_for_same_device_fail_before_setup(self):
        self.text += u'other /dev/test-raw\n'
        with self.assertRaises(blivet.BlivetAnsibleError):
            self.lookup()
        self.assertEqual(self.device.format.setup_calls, 0)

    def test_reused_name_for_unresolved_device_fails_before_setup(self):
        self.text += u'custom /dev/missing\n'
        with self.assertRaises(blivet.BlivetAnsibleError):
            self.lookup()
        self.assertEqual(self.device.format.setup_calls, 0)

    def test_tree_collision_fails_before_setup(self):
        self.b.devicetree.entries['/dev/mapper/custom'] = FakeDevice('/dev/other')
        with self.assertRaises(blivet.BlivetAnsibleError):
            self.lookup()
        self.assertEqual(self.device.format.setup_calls, 0)

    def test_unresolved_mapper_node_collision_fails_before_setup(self):
        self.patch(blivet.os.path, 'lexists', lambda path: path == '/dev/mapper/custom')
        with self.assertRaises(blivet.BlivetAnsibleError):
            self.lookup()
        self.assertEqual(self.device.format.setup_calls, 0)

    def test_invalid_mapping_name_fails_before_setup(self):
        for name in ('.', '..', '/dev/other', 'bad\x00name'):
            self.text = name + u' /dev/test-raw\n'
            with self.assertRaises(blivet.BlivetAnsibleError):
                self.lookup()
        self.assertEqual(self.device.format.setup_calls, 0)

    def test_already_open_mapping_is_not_renamed(self):
        self.device.format.status = True
        self.device.children.append(FakeDevice('/dev/mapper/active-name', fmt_type='xfs', raw_device=self.device))
        self.text += u'conflicting /dev/test-raw\n'
        self.assertEqual(self.lookup()._device.path, '/dev/mapper/active-name')
        self.assertEqual(self.device.format.map_name, 'luks-test-uuid')
        self.assertEqual(self.device.format.setup_calls, 0)

    def test_leaf_already_open_keeps_its_name(self):
        self.device.format.status = True
        self.text += u'conflicting /dev/test-raw\n'
        self.assertEqual(self.lookup()._device.path, '/dev/mapper/luks-test-uuid')

    def test_closed_check_tracks_the_configured_mapping(self):
        self.patch(blivet, 'check_mode', True)
        self.lookup()
        self.assertEqual(blivet.temporary_luks_formats, [self.device.format])
        self.assertEqual(blivet.temporary_luks_formats[0].map_name, 'custom')

    def test_wrong_key_is_not_registered_as_an_open_mapping(self):
        self.patch(blivet, 'check_mode', True)
        with self.assertRaises(blivet.BlivetAnsibleError):
            self.lookup(encryption_password='wrong')
        self.assertEqual(blivet.temporary_luks_formats, [])
        self.assertFalse(self.device.format.status)


class TestSwapActivation(PatchTestCase):
    def setUp(self):
        self.patch(blivet, 'check_mode', True)
        self.raw = FakeDevice('/dev/test-raw')
        self.device = FakeDevice('/dev/mapper/test', fmt_type='swap', raw_device=self.raw)
        self.b = FakeBlivet(self.device)
        self.b.devicetree.entries[self.device.fstab_spec] = self.device
        self.volume = dict(name='swap', state='present', encryption=True, _device=self.device.path,
                           _mount_id=self.device.fstab_spec, _raw_device=self.raw.path)
        self.patch(blivet, 'temporary_luks_formats', [self.raw.format])

    def activate(self):
        blivet.update_fstab_identifiers(self.b, [], [self.volume])
        blivet.activate_swaps(self.b, [], [self.volume])

    def test_temporary_encrypted_swap_is_not_activated(self):
        self.activate()
        self.assertEqual(self.device.format.setup_calls, 0)
        self.assertIn('_kernel_device', self.volume)
        self.assertIn('_raw_kernel_device', self.volume)

    def test_already_open_encrypted_swap_still_activates(self):
        del blivet.temporary_luks_formats[:]
        self.activate()
        self.assertEqual(self.device.format.setup_calls, 2)
        self.assertIn('_kernel_device', self.volume)
        self.assertIn('_raw_kernel_device', self.volume)

    def test_plain_swap_still_activates(self):
        self.device.raw_device = self.device
        self.activate()
        self.assertEqual(self.device.format.setup_calls, 2)

    def test_normal_mode_still_activates_swap(self):
        self.patch(blivet, 'check_mode', False)
        self.activate()
        self.assertEqual(self.device.format.setup_calls, 2)
