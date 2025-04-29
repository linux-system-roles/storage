#!/usr/bin/env python

# Helper script for gathering information about stratis pools using stratis DBus API.

# The script is meant to be a supporting tool for the storage role tests

import sys
from collections import namedtuple

import json

import gi  # pylint: disable=import-error
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")

from gi.repository import GLib, Gio  # pylint: disable=import-error

STRATIS_SERVICE = "org.storage.stratis3"
STRATIS_PATH = "/org/storage/stratis3"
STRATIS_POOL_INTF = STRATIS_SERVICE + ".pool.r0"

# Code for working with DBus, taken from blivet/safe_dbus.py
DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"
DBUS_INTRO_IFACE = "org.freedesktop.DBus.Introspectable"


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
            raise DBusCallError("Unable to connect to system bus: %s" % gerr) from gerr

    if connection.is_closed():
        raise DBusCallError("Connection is closed")

    try:
        ret = connection.call_with_unix_fd_list_sync(service, obj_path, iface, method,
                                                     args, None, Gio.DBusCallFlags.NONE,
                                                     -1, fds, None)
    except GLib.GError as gerr:
        msg = "Failed to call %s method on %s with %s arguments: %s" % \
              (method, obj_path, args, gerr.message)  # pylint: disable=no-member
        raise DBusCallError(msg) from gerr

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


# Extracting and printing Stratis pool information
StratisPoolInfo = namedtuple("StratisPoolInfo", ["name", "encrypted", "key_desc",
                                                 "clevis_pin", "clevis_args"])


def _print_pool_info_json(pool_info):
    pi_dict = pool_info._asdict()
    pi_json = json.dumps(pi_dict)
    print(pi_json)


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


def main(pool_name):
    objects = call_sync(STRATIS_SERVICE,
                        STRATIS_PATH,
                        "org.freedesktop.DBus.ObjectManager",
                        "GetManagedObjects",
                        None)[0]

    for path, interfaces in objects.items():
        if STRATIS_POOL_INTF in interfaces.keys():
            pool_info = _get_pool_info(path)
            if pool_info and pool_info.name == pool_name:
                _print_pool_info_json(pool_info)
                return True

    print(json.dumps(None))
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python %s <pool name>" % sys.argv[0], file=sys.stderr)
        sys.exit(1)

    succ = main(sys.argv[1])
    sys.exit(0) if succ else sys.exit(1)
