#!/usr/bin/python

from __future__ import absolute_import, division, print_function

__metaclass__ = type

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
    - "WARNING: Do not use this module directly! It is only for role internal use."
    - "This module collects information about block devices"
options: {}
author:
    - David Lehman (@dwlehman)
'''

EXAMPLES = '''
- name: Get info about block devices
  blockdev_info:
  register: blk_info

'''

RETURN = '''
info:
    description: dict w/ device path keys and device info dict values
    returned: success
    type: dict
'''

import os
import shlex

from ansible.module_utils.basic import AnsibleModule


LSBLK_DEVICE_TYPES = {"part": "partition"}
DEV_MD_DIR = '/dev/md'


def fixup_md_path(path):
    if not path.startswith("/dev/md"):
        return path

    if not os.path.exists(DEV_MD_DIR):
        return path

    ret = path
    for md in os.listdir(DEV_MD_DIR):
        md_path = "%s/%s" % (DEV_MD_DIR, md)
        if os.path.realpath(md_path) == os.path.realpath(path):
            ret = md_path
            break

    return ret


def get_block_info(module):
    buf = module.run_command(["lsblk", "-o", "NAME,FSTYPE,LABEL,UUID,TYPE,SIZE", "-p", "-P", "-a"])[1]
    info = dict()
    for line in buf.splitlines():
        dev = dict()
        for pair in shlex.split(line):
            try:
                key, _eq, value = pair.partition("=")
            except ValueError:
                module.log(pair)
                raise
            if key:
                if key.lower() == "name":
                    value = fixup_md_path(value)

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
        result['info'] = get_block_info(module)
    except Exception:
        module.fail_json(msg="Failed to collect block device info.")

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
