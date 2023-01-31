#!/usr/bin/python

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = '''
---
module: find_unused_disk
short_description: Gets unused disks
description:
    - "WARNING: Do not use this module directly! It is only for role internal use."
    - Disks are considered in ascending alphanumeric sorted order.
    - Disks that meet all conditions are considered 'empty' and returned (using kernel device name) in a list.
        - 1. No known signatures exist on the disk, with the exception of partition tables.
        - 2. If there is a partition table on the disk, it contains no partitions.
        - 3. The disk has no holders to eliminate the possibility of it being a multipath or dmraid member device.
        - 4. Device can be opened with exclusive access to make sure no other software is using it.
    - If no disks meet all criteria, "Unable to find unused disk" will be returned.
    - Number of returned disks defaults to first 10, but can be specified with 'max_return' argument.
author: Eda Zhou (@edamamez)
options:
    max_return:
        description: Sets the maximum number of unused disks to return.
        default: 10
        type: int

    min_size:
        description: Specifies the minimum disk size to return an unused disk.
        default: '0'
        type: str

    max_size:
        description: Specifies the maximum disk size to return an unused disk.
        default: '0'
        type: str

    with_interface:
        description: Specifies which disk interface will be accepted (scsi, virtio, nvme).
        default: null
        type: str
'''

EXAMPLES = '''
- name: test finding first unused device module
  hosts: localhost
  tasks:
    - name: run module
      find_unused_disk:
        min_size: '10g'
      register: testout

    - name: dump test output
      debug:
        msg: '{{ testout }}'
'''

RETURN = '''
disk_name:
    description: Information about unused disks
    returned: On success
    type: complex
    contains:
        disks:
            description: Unused disk(s) that have been found
            returned: On success
            type: list
            samples: |
              ["sda1", "dm-0", "dm-3"]
        none:
            description: No unused disks were found
            returned: On success
            type: string
            sample: "Unable to find unused disk"
'''


import os
import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.storage_lsr.size import Size


SYS_CLASS_BLOCK = "/sys/class/block/"
IGNORED_DEVICES = [re.compile(r'^/dev/nullb\d+$')]


def is_ignored(disk_path):
    sys_path = os.path.realpath(disk_path)
    return any(ignore.match(sys_path) is not None for ignore in IGNORED_DEVICES)


def is_device_interface(module, path, interface):
    device = path.split('dev/')[-1]
    # command checks if the device uses given interface (virtio, scsi or nvme)
    result = module.run_command(['readlink', '/sys/block/%s/device/device/driver' % device, '/sys/block/%s/device/driver' % device])
    return interface in result[1]


def no_signature(run_command, disk_path):
    """Return true if no known signatures exist on the disk."""
    signatures = run_command(['blkid', '-p', disk_path])
    return 'UUID' not in signatures[1]


def no_holders(disk_path):
    """Return true if the disk has no holders."""
    holders = os.listdir(SYS_CLASS_BLOCK + get_sys_name(disk_path) + '/holders/')
    return len(holders) == 0


def can_open(disk_path):
    """Return true if the device can be opened with exclusive access."""
    try:
        os.open(disk_path, os.O_EXCL)
        return True
    except OSError:
        return False


def get_sys_name(disk_path):
    if not os.path.islink(disk_path):
        return os.path.basename(disk_path)

    node_dir = '/'.join(disk_path.split('/')[-1])
    return os.path.normpath(node_dir + '/' + os.readlink(disk_path))


def get_partitions(disk_path):
    sys_name = get_sys_name(disk_path)
    partitions = list()
    for filename in os.listdir(SYS_CLASS_BLOCK + sys_name):
        if re.match(sys_name + r'p?\d+$', filename):
            partitions.append(filename)

    return partitions


def get_disks(module):
    buf = module.run_command(["lsblk", "-p", "--pairs", "--bytes", "-o", "NAME,TYPE,SIZE,FSTYPE"])[1]
    disks = dict()
    for line in buf.splitlines():
        if not line:
            continue

        m = re.search(r'NAME="(?P<path>[^"]*)" TYPE="(?P<type>[^"]*)" SIZE="(?P<size>\d+)" FSTYPE="(?P<fstype>[^"]*)"', line)
        if m is None:
            module.log(line)
            continue

        if m.group('type') != "disk":
            continue

        disks[m.group('path')] = {"type": m.group('type'), "size": m.group('size'), "fstype": m.group('fstype')}

    return disks


def run_module():
    """Create the module"""
    module_args = dict(
        max_return=dict(type='int', required=False, default=10),
        min_size=dict(type='str', required=False, default='0'),
        max_size=dict(type='str', required=False, default='0'),
        with_interface=dict(type='str', required=False, default=None)
    )

    result = dict(
        changed=False,
        disks=[]
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    max_size = Size(module.params['max_size'])
    for path, attrs in get_disks(module).items():
        if is_ignored(path):
            continue

        interface = module.params['with_interface']

        if interface is not None and not is_device_interface(module, path, interface):
            continue

        if attrs["fstype"]:
            continue

        if Size(attrs["size"]).bytes < Size(module.params['min_size']).bytes:
            continue

        if max_size.bytes > 0 and Size(attrs["size"]).bytes > max_size.bytes:
            continue

        if get_partitions(path):
            continue

        if not no_holders(get_sys_name(path)):
            continue

        if not can_open(path):
            continue

        result['disks'].append(os.path.basename(path))
        if len(result['disks']) >= module.params['max_return']:
            break

    if not result['disks']:
        result['disks'] = "Unable to find unused disk"
    else:
        result['disks'].sort()

    module.exit_json(**result)


def main():
    """Execute the module"""
    run_module()


if __name__ == '__main__':
    main()
