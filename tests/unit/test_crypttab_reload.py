# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.1 Sol
"""Crypttab changes must reach systemd during the same role invocation."""
import os
import unittest

import jinja2
import yaml
from ansible.plugins.test.core import TestModule as AnsibleTestModule


class TestCrypttabReload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        with open(os.path.join(root, 'tasks', 'main-blivet.yml')) as stream:
            cls.tasks = yaml.safe_load(stream)
        cls.crypttab_index = next(i for i, task in enumerate(cls.tasks)
                                  if task['name'] == 'Manage /etc/crypttab to account for changes we just made')
        cls.reload_indices = [i for i, task in enumerate(cls.tasks)
                              if task.get('systemd', {}).get('daemon_reload')]
        cls.env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        cls.env.tests.update(AnsibleTestModule().tests())

    def test_final_reload_follows_crypttab(self):
        self.assertEqual(len(self.reload_indices), 2)
        self.assertLess(self.reload_indices[0], self.crypttab_index)
        self.assertGreater(self.reload_indices[-1], self.crypttab_index)

    def test_crypttab_changes_are_registered(self):
        self.assertEqual(self.tasks[self.crypttab_index]['register'], '__storage_crypttab_update')

    def test_reload_covers_mounts_and_crypttab_only_changes(self):
        reload_task = self.tasks[self.reload_indices[-1]]
        condition = self.env.compile_expression(reload_task['when'])
        for mounts, changed, expected in [([], False, False), ([], True, True),
                                          ([{}], False, True), ([{}], True, True)]:
            self.assertEqual(condition(**{'blivet_output': dict(mounts=mounts),
                                          '__storage_crypttab_update': dict(changed=changed)}), expected)

    def test_reload_respects_check_mode(self):
        self.assertNotIn('check_mode', self.tasks[self.reload_indices[-1]])
