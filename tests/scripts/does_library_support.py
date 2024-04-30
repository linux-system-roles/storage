#!/usr/bin/env python

# This script checks for blivet compatibility by trying to access
# blivet parts specified by given parameter
# Returns True if part is found, False otherwise

# The script is meant to be a supporting tool for the storage role tests
import sys
import importlib


def is_supported(var):

    parts = var.split('.')
    imports = ''
    obj = sys.modules[__name__]

    try:
        # create a variable named parts[0] so the subsequent imports work
        globals()[parts[0]] = importlib.import_module(parts[0])
    except ImportError:
        return False

    # try to import each part
    while parts:
        part = parts.pop(0)
        imports += part + '.'

        try:
            importlib.import_module(imports.rstrip('.'))
        except ImportError:
            break

        # generate access to the object for later use
        obj = getattr(obj, part)

    else:
        # break did not happen in the cycle
        # it means the whole string was importable
        return True

    # part of the string was not importable, the rest can be attributes

    # get part back to parts to simplify the following loop
    parts = [part] + parts

    while parts:
        part = parts.pop(0)
        obj = getattr(obj, part, None)

        if obj is None:
            return False

    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python %s <parameter>" % sys.argv[0])
        sys.exit(-1)

    print(is_supported(sys.argv[1]))
