#!/usr/bin/python

DOCUMENTATION = '''
---
module: find_unused_disk
short_description: Gets unused disks
description:
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
    option-name: max_return
    description: Sets the maximum number of unused disks to return.
    default: 10
    type: int
'''

EXAMPLES = '''
- name: test finding first unused device module
  hosts: localhost
  tasks:
    - name: run module
      find_unused_disk:
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
            samples: ["sda1", "dm-0", "dm-3"]
                     ["sda"]
        none:
            description: No unused disks were found
            returned: On success
            type: string
            sample: "Unable to find unused disk"
'''


import os

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import facts


def no_signature(run_command, disk_path):
    """Return true if no known signatures exist on the disk."""
    signatures = run_command(['blkid', '-p', disk_path])
    return not 'UUID' in signatures[1]


def no_holders(disk):
    """Return true if the disk has no holders."""
    holders = os.listdir('/sys/class/block/' + disk + '/holders/')
    return len(holders) == 0


def can_open(disk_path):
    """Return true if the device can be opened with exclusive access."""
    try:
        os.open(disk_path, os.O_EXCL)
        return True
    except OSError:
        return False


def run_module():
    """Create the module"""
    module_args = dict(
        max_return=dict(type='int', required=False, default=10)
    )

    result = dict(
        changed=False,
        disks=[]
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    ansible_facts = facts.ansible_facts(module)
    run_command = module.run_command
    for disk in ansible_facts['devices'].keys():
        # If partition table exists but contains no partitions -> no partitions.
        no_partitions = not bool(ansible_facts['devices'][disk]['partitions'])

        if no_partitions and no_signature(run_command, '/dev/' + disk) and no_holders(disk) and can_open('/dev/' + disk):
            result['disks'].append(disk)
            if len(result['disks']) >= module.params['max_return']:
                break

    if not result['disks']:
        result['disks'] = "Unable to find unused disk"
    module.exit_json(**result)


def main():
    """Execute the module"""
    run_module()


if __name__ == '__main__':
    main()
