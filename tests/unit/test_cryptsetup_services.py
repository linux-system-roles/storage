# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.1 Sol
"""The actual role expressions must preserve pre-existing service masks."""
import os
import unittest

import jinja2
import yaml
from ansible.plugins.test.core import TestModule as AnsibleTestModule


class TestCryptsetupServices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        with open(os.path.join(root, 'tasks', 'main-blivet.yml')) as stream:
            tasks = yaml.safe_load(stream)
        cls.block = next(task for task in tasks if task['name'] == 'Manage storage devices and check for errors')
        cls.env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        cls.env.tests.update(AnsibleTestModule().tests())

    def services(self, facts):
        expression = self.block['vars']['storage_cryptsetup_services'].strip()[2:-2]
        return self.env.compile_expression(expression)(ansible_facts=facts)

    def test_absent_facts(self):
        self.assertEqual(self.services({}), [])

    def test_only_unmasked_cryptsetup_services_are_selected(self):
        rows = [dict(name='systemd-cryptsetup@' + status + '.service', status=status)
                for status in ('generated', 'enabled', 'masked', 'masked-runtime', 'not-found', 'failed')]
        rows += [dict(name='unrelated.service', status='enabled'), {}, dict(name='missing-status.service')]
        selected = self.services(dict(services=dict(enumerate(rows))))
        self.assertEqual(selected, ['systemd-cryptsetup@generated.service', 'systemd-cryptsetup@enabled.service'])

    def test_cached_facts_do_not_skip_refresh(self):
        task = self.block['block'][0]
        for condition in task['when']:
            evaluate = self.env.compile_expression(condition)
            self.assertTrue(evaluate(ansible_facts=dict(services={}), storage_skip_checks=[]))
            self.assertFalse(evaluate(ansible_facts=dict(services={}), storage_skip_checks=['cryptsetup_services']))

    def test_protection_and_cleanup_are_real_in_check_mode(self):
        mask = self.block['block'][1]
        unmask = self.block['always'][0]
        self.assertIs(mask['check_mode'], False)
        self.assertIs(unmask['check_mode'], False)
        self.assertEqual(mask['loop'], unmask['loop'])
        self.assertIs(mask['systemd']['masked'], True)
        self.assertIs(unmask['systemd']['masked'], False)
