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
module: resolve_blockdev
short_description: Resolve block device specification to device node path.
version_added: "2.5"
description:
    - "WARNING: Do not use this module directly! It is only for role internal use."
    - "This module accepts various forms of block device identifiers and
       resolves them to the correct block device node path."
options:
    spec:
        description:
            - String describing a block device
        required: true
        type: str
author:
    - David Lehman (@dwlehman)
'''

EXAMPLES = '''
- name: Resolve device by label
  resolve_blockdev:
    spec: LABEL=MyData

- name: Resolve device by name
  resolve_blockdev:
    spec: mpathb

- name: Resolve device by /dev/disk/by-id symlink name
  resolve_blockdev:
    spec: wwn-0x5000c5005bc37f3f
'''

RETURN = '''
device:
    description: Path to block device node
    type: str
    returned: success
'''

import glob
import os
import re

from ansible.module_utils.basic import AnsibleModule

DEV_MD = "/dev/md"
DEV_MAPPER = "/dev/mapper"
SYS_CLASS_BLOCK = "/sys/class/block"
SEARCH_DIRS = ['/dev', DEV_MAPPER, DEV_MD] + glob.glob("/dev/disk/by-*")
MD_KERNEL_DEV = re.compile(r'/dev/md\d+(p\d+)?$')


def resolve_blockdev(spec, run_cmd):
    if "=" in spec:
        device = run_cmd("blkid -t %s -o device" % spec)[1].strip()
    elif not spec.startswith('/'):
        for devdir in SEARCH_DIRS:
            device = "%s/%s" % (devdir, spec)
            if os.path.exists(device):
                break
            else:
                device = ''
    else:
        device = spec

    if not device or not os.path.exists(device):
        return ''

    return canonical_device(os.path.realpath(device))


def _get_dm_name_from_kernel_dev(kdev):
    return open("%s/%s/dm/name" % (SYS_CLASS_BLOCK, os.path.basename(kdev))).read().strip()


def _get_md_name_from_kernel_dev(kdev):
    minor = os.minor(os.stat(kdev).st_rdev)
    return next(name for name in os.listdir(DEV_MD)
                if os.minor(os.stat("%s/%s" % (DEV_MD, name)).st_rdev) == minor)


def canonical_device(device):
    if device.startswith("/dev/dm-"):
        device = "%s/%s" % (DEV_MAPPER, _get_dm_name_from_kernel_dev(device))
    elif MD_KERNEL_DEV.match(device):
        device = "%s/%s" % (DEV_MD, _get_md_name_from_kernel_dev(device))
    return device


def run_module():
    module_args = dict(
        spec=dict(type='str', required=True)
    )

    result = dict(
        device=None,
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    try:
        result['device'] = resolve_blockdev(module.params['spec'], run_cmd=module.run_command)
    except Exception:
        pass

    if not result['device'] or not os.path.exists(result['device']):
        module.fail_json(msg="The {0} device spec could not be resolved".format(module.params['spec']))

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
