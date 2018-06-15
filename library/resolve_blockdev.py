#!/usr/bin/python

from ansible.module_utils.basic import AnsibleModule

import os

def run_module():
    module_args = dict(
        spec=dict(type='str')
    )

    result = dict(
        device=None,
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if "=" in module.params['spec']:
        result['device'] = os.popen("blkid -t %s -o device" % module.params['spec']).read().strip()
    elif not module.params['spec'].startswith('/'):
        result['device'] = "/dev/%s" % module.params['spec']
        if not os.path.exists(result['device']):
            result['device'] = None
    else:
        result['device'] = module.params['spec']

    if not os.path.exists(result['device']):
        module.fail_json(msg="The {} device spec could not be resolved".format(module.params['spec']))

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
