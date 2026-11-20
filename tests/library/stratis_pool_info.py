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
module: stratis_pool_info

short_description: Get information about a Stratis pool

version_added: "2.13.0"

description:
    - "WARNING: Do not use this module directly! It is only for role internal use."
    - "Gathers information about a Stratis pool using the stratis DBus API."

requirements: [pygobject]

options:
    pool_name:
        description:
            - Name of the Stratis pool
        required: true
        type: str

author:
    - Vojtech Trefny (@vtrefny)
'''

EXAMPLES = '''
- name: Get information about the Stratis pool foo
  stratis_pool_info:
    pool_name: foo
  register: storage_test_stratis_report

- name: Print the pool information
  debug:
    msg: "{{ storage_test_stratis_report.pool_info }}"
'''

RETURN = '''
pool_info:
    description:
        - Information about the pool, C(null) if the pool does not exist
    type: dict
    returned: success
    contains:
        name:
            description: Name of the pool
            type: str
            returned: always
        encrypted:
            description: Whether the pool is encrypted
            type: bool
            returned: always
        key_desc:
            description: Kernel keyring description of the pool key
            type: str
            returned: always
        clevis_pin:
            description: Name of the Clevis pin used by the pool
            type: str
            returned: always
        clevis_args:
            description: Clevis configuration of the pool
            type: dict
            returned: always
'''

import json
from collections import namedtuple

try:
    import gi  # pylint: disable=import-error
    gi.require_version("GLib", "2.0")
    gi.require_version("Gio", "2.0")
    from gi.repository import GLib, Gio  # pylint: disable=import-error
    HAS_GI = True
except ImportError:
    HAS_GI = False

from ansible.module_utils.basic import AnsibleModule

STRATIS_SERVICE = "org.storage.stratis3"
STRATIS_PATH = "/org/storage/stratis3"
STRATIS_POOL_INTF = STRATIS_SERVICE + ".pool.r0"

# Code for working with DBus, taken from blivet/safe_dbus.py
DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"


class SafeDBusError(Exception):
    """Class for exceptions defined in this module."""


class DBusCallError(SafeDBusError):
    """Class for the errors related to calling methods over DBus."""


class DBusPropertyError(DBusCallError):
    """Class for the errors related to getting property values over DBus."""


def get_new_system_connection():
    """Return a new connection to the system bus."""

    return Gio.DBusConnection.new_for_address_sync(
        Gio.dbus_address_get_for_bus_sync(Gio.BusType.SYSTEM, None),
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None, None)


def call_sync(service, obj_path, iface, method, args, connection=None, fds=None):
    if not connection:
        try:
            connection = get_new_system_connection()
        except GLib.GError as gerr:
            raise DBusCallError("Unable to connect to system bus: %s" % gerr)

    if connection.is_closed():
        raise DBusCallError("Connection is closed")

    try:
        ret = connection.call_with_unix_fd_list_sync(service, obj_path, iface, method,
                                                     args, None, Gio.DBusCallFlags.NONE,
                                                     -1, fds, None)
    except GLib.GError as gerr:
        msg = "Failed to call %s method on %s with %s arguments: %s" % \
              (method, obj_path, args, gerr.message)  # pylint: disable=no-member
        raise DBusCallError(msg)

    if ret is None:
        msg = "No return from %s method on %s with %s arguments" % (method, obj_path,
                                                                    args)
        raise DBusCallError(msg)

    return ret[0].unpack()


def get_properties_sync(service, obj_path, iface, connection=None):
    args = GLib.Variant('(s)', (iface,))
    ret = call_sync(service, obj_path, DBUS_PROPS_IFACE, "GetAll", args,
                    connection)
    return ret


# Extracting Stratis pool information
StratisPoolInfo = namedtuple("StratisPoolInfo", ["name", "encrypted", "key_desc",
                                                 "clevis_pin", "clevis_args"])


def _get_pool_info(pool_path):
    try:
        properties = get_properties_sync(STRATIS_SERVICE,
                                         pool_path,
                                         STRATIS_POOL_INTF)[0]
    except DBusPropertyError:
        return None

    if not properties:
        return None

    description = properties.get("KeyDescription", None)
    if not description or not description[0] or not description[1][0]:
        key_desc = None
    else:
        key_desc = description[1][1]

    clevis_info = properties.get("ClevisInfo", None)
    if not clevis_info or not clevis_info[0] or not clevis_info[1][0]:
        clevis = None
    else:
        clevis = clevis_info[1][1]

    if clevis:
        clevis_pin = clevis[0]
        clevis_args = json.loads(clevis[1])
    else:
        clevis_pin = None
        clevis_args = {}

    return StratisPoolInfo(name=properties["Name"],
                           encrypted=properties["Encrypted"],
                           key_desc=key_desc,
                           clevis_pin=clevis_pin,
                           clevis_args=clevis_args)


def get_pool_info(pool_name):
    """Return information about the given Stratis pool or None."""

    objects = call_sync(STRATIS_SERVICE,
                        STRATIS_PATH,
                        "org.freedesktop.DBus.ObjectManager",
                        "GetManagedObjects",
                        None)[0]

    for path, interfaces in objects.items():
        if STRATIS_POOL_INTF in interfaces:
            pool_info = _get_pool_info(path)
            if pool_info and pool_info.name == pool_name:
                return pool_info._asdict()

    return None


def run_module():
    module_args = dict(
        pool_name=dict(type='str', required=True),
    )

    result = dict(
        changed=False,
        pool_info=None,
    )

    module = AnsibleModule(argument_spec=module_args,
                           supports_check_mode=True)

    if not HAS_GI:
        module.fail_json(msg="This module requires PyGObject "
                             "(the python gi module) to be installed")

    try:
        result['pool_info'] = get_pool_info(module.params['pool_name'])
    except DBusCallError as e:
        module.fail_json(msg="Unable to get Stratis pool information: %s" % e)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
