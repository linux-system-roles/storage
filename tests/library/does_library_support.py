# Assisted by goose using model(s) glm-5-3

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: does_library_support

short_description: Check for library compatibility with a given symbol

version_added: "2.13.0"

description:
    - "WARNING: Do not use this module directly! It is only for role internal use."
    - "Checks whether the given dotted name (a Python module with optional
       attributes) can be resolved, e.g. to check whether the installed blivet
       version supports a given feature."

options:
    name:
        description:
            - Dotted name of the module and its attributes, e.g.
              I(blivet.formats.lvmpv.LVMPhysicalVolume.grow_to_fill)
        required: true
        type: str

author:
    - Jan Pokorny (@japokorn)
    - Vojtech Trefny (@vtrefny)
'''

EXAMPLES = '''
- name: Check that blivet supports PV grow to fill
  does_library_support:
    name: blivet.formats.lvmpv.LVMPhysicalVolume.grow_to_fill
  register: grow_supported

- name: Do something when it is supported
  debug:
    msg: Blivet supports grow_to_fill
  when: grow_supported.supported
'''

RETURN = '''
supported:
    description:
        - Whether the given name could be resolved to a module attribute
    type: bool
    returned: success
'''

import importlib

from ansible.module_utils.basic import AnsibleModule


def is_supported(name):
    """Return True if the dotted name resolves to a module attribute."""
    parts = name.split('.')

    # find the longest importable prefix of the dotted name
    obj = None
    for idx in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module('.'.join(parts[:idx]))
            break
        except ImportError:
            continue

    if obj is None:
        # even the top level module cannot be imported
        return False

    # the rest of the name has to be a chain of attributes
    for part in parts[idx:]:
        obj = getattr(obj, part, None)

        if obj is None:
            return False

    return True


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
    )

    result = dict(
        changed=False,
        supported=False,
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if not module.params['name']:
        module.fail_json(msg="The name parameter must not be empty")

    try:
        result['supported'] = is_supported(module.params['name'])
    except Exception as e:  # pylint: disable=broad-except
        module.fail_json(msg="Error checking library support for '%s': %s" %
                         (module.params['name'], str(e)))

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
