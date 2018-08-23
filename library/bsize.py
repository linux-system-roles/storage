#!/usr/bin/python

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: bsize

short_description: Module for basic manipulation with byte sizes

version_added: "2.5"

description:
    - "Module accepts byte size strings with the units and produces strings in
      form of input accepted by different storage tools"

options:
    size:
        description:
            - String containing number and byte units
        required: true

author:
    - Jan Pokorny (japokorn@redhat.com)
'''

EXAMPLES = '''
# Obtain sizes in format for various tools
- name: Get 10 KiB size
  bsize:
    size: 10 KiB
'''

RETURN = '''
size:
    description: Size in binary format units
    type: str
bytes:
    description: Size in bytes
    type: int
lvm:
    description: Size in binary format. No space after the number,
                 first letter of unit prefix in lowercase only
    type: str
parted:
    description: Size in binary format. No space after the number
    type: str
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.size import Size

def run_module():
    # available arguments/parameters that a user can pass
    module_args = dict(
        size=dict(type='str', required=True),
    )

    # seed the result dict in the object
    result = dict(
        changed=False
    )

    module = AnsibleModule(argument_spec=module_args,
                           supports_check_mode=True)

    size = Size(module.params['size'])

    result['size'] = size.get(fmt="%d %sb")
    result['bytes'] = size.bytes
    result['lvm'] = size.get(fmt="%d%sb").lower()[:-2]
    result['parted'] = size.get(fmt="%d%sb")

    # use whatever logic you need to determine whether or not this module
    # made any modifications to your target
    result['changed'] = False

    # success - return result
    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()
