#!/usr/bin/python

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: blockdev_info
short_description: Collect info about block devices in the system.
version_added: "2.5"
description:
    - "This module collects information about block devices"
options:
author:
    - David Lehman (dlehman@redhat.com)
'''

EXAMPLES = '''
- name: Get info about block devices
  blockdev_info:
  register: blk_info

'''

RETURN = '''
info:
    description: dict w/ device path keys and device info dict values
    type: dict
'''

import shlex

from ansible.module_utils.basic import AnsibleModule


LSBLK_DEVICE_TYPES = {"part": "partition"}

def get_block_info(run_cmd):
    buf = run_cmd(["lsblk", "-o", "NAME,FSTYPE,LABEL,UUID,TYPE", "-p", "-P", "-a"])[1]
    info = dict()
    for line in buf.splitlines():
        dev = dict()
        for pair in shlex.split(line):
            try:
                key, _eq, value = pair.partition("=")
            except ValueError:
                print(pair)
                raise
            if key:
                dev[key.lower()] = LSBLK_DEVICE_TYPES.get(value, value)
        if dev:
            info[dev['name']] = dev

    return info


def run_module():
    module_args = dict()

    result = dict(
        info=None,
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    try:
        result['info'] = get_block_info(module.run_command)
    except Exception:
        module.fail_json(msg="Failed to collect block device info.")

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
