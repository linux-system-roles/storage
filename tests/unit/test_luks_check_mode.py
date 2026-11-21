# SPDX-License-Identifier: MIT
# Assisted by OpenCode using models GPT-6.1 Sol, GPT-6.2 Astra
"""Temporary LUKS mappings must be closed before reporting module results."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import tempfile
import unittest

try:
    from unittest import mock
except ImportError:  # Python 2
    import mock

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


class TestCheckModeLUKSUdev(unittest.TestCase):
    def setUp(self):
        self.module = mock.Mock()
        self.module.run_command.return_value = (0, '', '')
        self.guard = blivet.CheckModeLUKSUdev(self.module)
        self.guard.rules_dir = self.guard.systemd_dir = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, self.guard.rules_dir)

    def test_multiple_names_stay_literal_and_no_rule_survives_cleanup(self):
        names = ('first', 'second*[x]"')
        for name in names:
            self.guard.protect(name)
        self.assertEqual(self.module.run_command.call_count, 1)
        with open(self.guard.rule) as stream:
            text = stream.read()
        # Only this invocation's actual map names match the udev predicate.
        predicate = text.split('TEST=="')[1].split('"')[0]
        for name in names:
            self.assertTrue(os.path.isfile(predicate.replace('$env{DM_NAME}', name)))
        self.assertFalse(os.path.exists(predicate.replace('$env{DM_NAME}', 'unrelated')))
        self.guard.restore()
        self.assertEqual(os.listdir(self.guard.rules_dir), [])
        self.assertEqual(self.module.run_command.call_count, 2)

    def test_reload_failure_leaves_the_rule_owned_for_cleanup(self):
        self.module.run_command.side_effect = [(1, '', 'udev unavailable'), (0, '', '')]
        with self.assertRaises(blivet.BlivetAnsibleError):
            self.guard.protect('first')
        self.guard.restore()
        self.assertEqual(os.listdir(self.guard.rules_dir), [])

    def test_no_systemd_does_not_install_a_rule(self):
        self.guard.systemd_dir = os.path.join(self.guard.rules_dir, 'absent')
        self.guard.protect('first')
        self.guard.restore()
        self.assertFalse(self.module.run_command.called)
        self.assertEqual(os.listdir(self.guard.rules_dir), [])


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
        events = self.events

        class Guard(object):
            def restore(self):
                events.append("restore")

        self.patch("CheckModeLUKSUdev", lambda module: Guard())
        self.patch("temporary_luks_udev", None)

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
        self.assertEqual(self.events[:4], ["probe", "close:second", "close:first", "restore"])
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
