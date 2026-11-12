# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.1 Sol
"""Temporary LUKS mappings must be closed before reporting module results."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import unittest

import blivet


class ModuleFinished(Exception):
    def __init__(self, failed, result):
        self.failed = failed
        self.result = result


class FakeModule(object):
    def __init__(self, events):
        self.events = events
        self.check_mode = True
        self.params = dict(pools=[dict(name="test")], volumes=[],
                           disklabel_type=None, use_partitions=False,
                           destroy_partition_device=True, safe_mode=True,
                           diskvolume_mkfs_option_map={}, pool_defaults={},
                           volume_defaults={}, uses_kmod_kvdo=False)

    def exit_json(self, **result):
        self.events.append("exit")
        raise ModuleFinished(False, result)

    def fail_json(self, **result):
        self.events.append("fail")
        raise ModuleFinished(True, result)


class FakeFormat(object):
    def __init__(self, name, events, fail=False):
        self.map_name = name
        self.events = events
        self.fail = fail

    def teardown(self):
        self.events.append("close:" + self.map_name)
        if self.fail:
            raise RuntimeError("mapping is busy")


class TestLUKSCheckModeCleanup(unittest.TestCase):
    def patch(self, name, value):
        missing = object()
        old = getattr(blivet, name, missing)

        def restore():
            if old is missing:
                delattr(blivet, name)
            else:
                setattr(blivet, name, old)

        self.addCleanup(restore)
        setattr(blivet, name, value)

    def setUp(self):
        self.events = []
        module = FakeModule(self.events)
        self.patch("AnsibleModule", lambda **kwargs: module)
        self.patch("validate_parameters", lambda spec, params: ([], params))
        self.patch("BLIVET_PACKAGE", "test")
        self.patch("temporary_luks_formats", [])
        for name in ("disklabel_type", "use_partitions", "destroy_partition_device",
                     "safe_mode", "diskvolume_mkfs_option_map", "pool_defaults",
                     "volume_defaults", "uses_kmod_kvdo", "check_mode"):
            self.patch(name, getattr(blivet, name, None))

    def run_worker(self, fail_probe=False, fail_close=False):
        def worker(module, result):
            self.events.append("probe")
            blivet.temporary_luks_formats.extend([
                FakeFormat("first", self.events),
                FakeFormat("second", self.events, fail=fail_close)])
            if fail_probe:
                raise blivet.BlivetAnsibleError("probe failed")

        self.patch("_run_storage", worker)
        with self.assertRaises(ModuleFinished) as raised:
            blivet.run_module()
        self.assertEqual(self.events[:3], ["probe", "close:second", "close:first"])
        self.assertEqual(blivet.temporary_luks_formats, [])
        return raised.exception

    def test_success_closes_before_json(self):
        result = self.run_worker()
        self.assertFalse(result.failed)
        self.assertEqual(self.events[-1], "exit")

    def test_probe_failure_still_closes_before_json(self):
        result = self.run_worker(fail_probe=True)
        self.assertTrue(result.failed)
        self.assertEqual(result.result["msg"], "probe failed")
        self.assertEqual(self.events[-1], "fail")

    def test_cleanup_failure_is_reported_and_other_mappings_are_closed(self):
        result = self.run_worker(fail_probe=True, fail_close=True)
        self.assertTrue(result.failed)
        self.assertIn("probe failed", result.result["msg"])
        self.assertIn("failed to close temporary LUKS mapping 'second'", result.result["msg"])
        self.assertEqual(self.events[-1], "fail")
