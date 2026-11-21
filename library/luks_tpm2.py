#!/usr/bin/python
# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.2 Astra
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: luks_tpm2
short_description: Enroll a TPM2 token in a LUKS2 volume identified by Blivet
description:
    - Internal module used by the storage role after its device actions complete.
version_added: "1.0.0"
author: "Linux System Roles"
options:
    device:
        description: Path to the backing device, not the cleartext mapping.
        type: path
        required: true
    expected_uuid:
        description: LUKS UUID discovered by the storage module.
        type: str
    planned:
        description: The LUKS header exists only in a dry-run plan.
        type: bool
        default: false
    pcrs:
        description: TPM2 PCR indices to bind.
        required: true
        type: list
        elements: int
    encryption_password:
        description: Existing unlock password, if used.
        type: str
    encryption_key:
        description: Existing unlock key file on the managed node, if used.
        type: path
'''
EXAMPLES = r'''
# The storage role supplies the path and expected UUID from its Blivet plan.
- name: Check an enrolled volume
  luks_tpm2:
    device: /dev/vg/data
    expected_uuid: "{{ luks_uuid }}"
    pcrs: [7]
  check_mode: true
'''
RETURN = r'''{}'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.storage_lsr.tpm2 import Enrollment


def main():
    module = AnsibleModule(
        argument_spec=dict(device=dict(type='path', required=True), expected_uuid=dict(type='str'),
                           planned=dict(type='bool', default=False), pcrs=dict(type='list', elements='int', required=True),
                           encryption_password=dict(type='str', no_log=True), encryption_key=dict(type='path', no_log=False)),
        supports_check_mode=True)
    p = module.params
    result = dict(changed=False)
    try:
        if p['planned']:
            if not module.check_mode:
                module.fail_json(msg="planned headers are valid only in check mode")
            module.exit_json(changed=True)
        spec = dict(encryption_tpm2=dict(pcrs=p['pcrs']),
                    encryption_password=p['encryption_password'], encryption_key=p['encryption_key'])
        request = Enrollment(spec, module.check_mode)
        request.existing(p['device'], p['expected_uuid'])
        request.finish(result)
    except Exception as e:
        module.fail_json(msg=str(e), **result)
    module.exit_json(**result)


if __name__ == '__main__':
    main()
