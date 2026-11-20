"""This module tests the stratis_pool_info Ansible module"""

# Assisted by goose using model(s) glm-5-3

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

# pylint: disable=wrong-import-position
import stratis_pool_info


POOL_PATH = "/org/storage/stratis3/1"
POOL_PROPERTIES = {
    "Name": "foo",
    "Encrypted": True,
    # (valid, (valid, description))
    "KeyDescription": (True, (True, "foo_keydesc")),
    # (valid, (valid, (pin, json config)))
    "ClevisInfo": (True, (True, ("tang", '{"url": "http://tang.example.com"}'))),
}

POOL_PROPERTIES_UNENCRYPTED = {
    "Name": "foo",
    "Encrypted": False,
    "KeyDescription": (False, (False, "")),
    "ClevisInfo": (False, (False, ("", "{}"))),
}


@pytest.fixture
def managed_objects(monkeypatch):
    """Mock the DBus calls and return the managed objects."""

    objects = {
        POOL_PATH: {stratis_pool_info.STRATIS_POOL_INTF: {}},
        "/org/storage/stratis3/2": {
            "org.storage.stratis3.filesystem.r0": {},
        },
    }

    def fake_call_sync(service, obj_path, iface, method, args,
                       connection=None, fds=None):
        assert method == "GetManagedObjects"
        return (objects,)

    def fake_get_properties_sync(service, obj_path, iface, connection=None):
        assert iface == stratis_pool_info.STRATIS_POOL_INTF
        return (dict(POOL_PROPERTIES),)

    monkeypatch.setattr(stratis_pool_info, "call_sync", fake_call_sync)
    monkeypatch.setattr(stratis_pool_info, "get_properties_sync",
                        fake_get_properties_sync)
    return objects


def test_get_pool_info(managed_objects):
    pool_info = stratis_pool_info.get_pool_info("foo")

    assert pool_info == {
        "name": "foo",
        "encrypted": True,
        "key_desc": "foo_keydesc",
        "clevis_pin": "tang",
        "clevis_args": {"url": "http://tang.example.com"},
    }


def test_get_pool_info_not_found(managed_objects):
    assert stratis_pool_info.get_pool_info("bar") is None


def test_get_pool_info_unencrypted(managed_objects, monkeypatch):
    def fake_get_properties_sync(service, obj_path, iface, connection=None):
        return (dict(POOL_PROPERTIES_UNENCRYPTED),)

    monkeypatch.setattr(stratis_pool_info, "get_properties_sync",
                        fake_get_properties_sync)

    pool_info = stratis_pool_info.get_pool_info("foo")

    assert pool_info == {
        "name": "foo",
        "encrypted": False,
        "key_desc": None,
        "clevis_pin": None,
        "clevis_args": {},
    }
