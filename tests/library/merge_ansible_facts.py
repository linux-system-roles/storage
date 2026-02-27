# -*- coding: utf-8 -*-
#
# Ansible module to merge saved facts with current Ansible facts.
# The result is saved_facts with any keys/values overridden by current_ansible_facts.
#
# Created by Claude AI running in Cursor

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule


DOCUMENTATION = r'''
---
module: merge_ansible_facts
short_description: Merge saved facts with current Ansible facts
version_added: "1.0.0"
description:
  - Does O(saved_ansible_facts.update(current_ansible_facts)) and returns the result.
author:
  - Linux System Roles
options:
  current_ansible_facts:
    description: Current Ansible facts.
    type: dict
    required: true
  saved_ansible_facts:
    description: Previously saved facts.
    type: dict
    required: true
'''

EXAMPLES = r'''
- name: Update saved facts with current facts
  merge_ansible_facts:
    current_ansible_facts: "{{ ansible_facts }}"
    saved_ansible_facts: "{{ saved_ansible_facts }}"
  register: merged

- name: Use updated facts
  set_fact:
    ansible_facts: "{{ merged.ansible_facts }}"
'''

RETURN = r'''
ansible_facts:
  description: saved_facts with keys/values overridden by current_ansible_facts.
  returned: success
  type: dict
'''


def run_module():
    module_args = dict(
        current_ansible_facts=dict(type='dict', required=True),
        saved_ansible_facts=dict(type='dict', required=True),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    current = module.params['current_ansible_facts']
    saved = module.params['saved_ansible_facts']

    saved.update(current)
    module.exit_json(ansible_facts=saved)


def main():
    run_module()


if __name__ == '__main__':
    main()
