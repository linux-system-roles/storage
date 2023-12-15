#!/usr/bin/python
"""Generates unique, default names for a volume group and logical volume"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: lvm_gensym
short_description: Generate default names for lvm variables
version_added: "2.13.0"
description:
    - "WARNING: Do not use this module directly! It is only for role internal use."
    - "Module accepts two input strings consisting of a file system type and
       a mount point path, and outputs names based on system information"
options:
    fs_type:
        description:
            - String describing the desired file system type
        required: true
        type: str
    mount:
        description:
            - String describing the mount point path
        required: true
        type: str
author:
    - Tim Flannagan (@timflannagan)
'''

EXAMPLES = '''
- name: Generate names
  lvm_gensym:
    fs_type: "{{ fs_type }}"
    mount: "{{ mount_point }}"
  register: lvm_results
  when: lvm_vg == "" and mount_point != "" and fs_type != ""
'''

RETURN = '''
vg_name:
    description: The default generated name for an unspecified volume group
    type: str
    returned: success
lv_name:
    description: The default generated name for an unspecified logical volume
    type: str
    returned: success
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import facts


def get_os_name():
    """Search the host file and return the name in the ID column"""
    os_name = None
    with open('/etc/os-release') as f:
        for line in f.readlines():
            if not line.find('ID='):
                os_name = line[3:]
                break

    if os_name:
        os_name = os_name.replace('\n', '').replace('"', '')
    return os_name


def name_is_unique(name, used_names):
    """Check if name is contained in the used_names list and return boolean value"""
    if name not in used_names:
        return True

    return False


def get_unique_name_from_base(base_name, used_names):
    """Generate a unique name given a base name and a list of used names, and return that unique name"""
    counter = 0
    while not name_is_unique(base_name, used_names):
        if counter == 0:
            base_name = base_name + '_' + str(counter)
        else:
            base_name = base_name[:-2] + '_' + str(counter)
        counter += 1

    return base_name


def get_vg_name_base(host_name, os_name):
    """Return a base name for a volume group based on the host and os names"""
    if host_name is not None and len(host_name) != 0:
        vg_default = os_name + '_' + host_name
    else:
        vg_default = os_name

    return vg_default


def get_vg_name(host_name, lvm_facts):
    """Generate a base volume group name, verify its uniqueness, and return that unique name"""
    used_vg_names = lvm_facts['vgs'].keys()
    os_name = get_os_name()
    name = get_vg_name_base(host_name, os_name)

    return get_unique_name_from_base(name, used_vg_names)


def get_lv_name_base(fs_type, mount_point):
    """Return a logical volume base name using given parameters"""
    if 'swap' in fs_type.lower():
        lv_default = 'swap'
    elif mount_point.startswith('/'):
        if mount_point == '/':
            lv_default = 'root'
        else:
            lv_default = mount_point[1:].replace('/', '_')
    else:
        lv_default = 'lv'

    return lv_default


def get_lv_name(fs_type, mount_point, lvm_facts):
    """Return a unique logical volume name based on specified file system type, mount point, and system facts"""
    used_lv_names = lvm_facts['lvs'].keys()
    name = get_lv_name_base(fs_type, mount_point)

    return get_unique_name_from_base(name, used_lv_names)


def run_module():
    """Setup and initialize all relevant ansible module data"""
    module_args = dict(
        mount=dict(type='str', required=True),
        fs_type=dict(type='str', required=True)
    )

    result = dict(
        changed=False,
        vg_name='',
        lv_name=''
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    lvm_facts = facts.ansible_facts(module)['lvm']
    host_name = facts.ansible_facts(module)['nodename'].lower().replace('.', '_').replace('-', '_')

    result['lv_name'] = get_lv_name(module.params['fs_type'], module.params['mount'], lvm_facts)
    result['vg_name'] = get_vg_name(host_name, lvm_facts)

    if result['lv_name'] != '' and result['vg_name'] != '':
        module.exit_json(**result)
    else:
        module.fail_json(msg="Unable to initialize both group and volume names")


def main():
    run_module()


if __name__ == '__main__':
    main()
