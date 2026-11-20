"""This module tests the does_library_support Ansible module"""

# Assisted by goose using model(s) glm-5-3

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

# pylint: disable=wrong-import-position
import does_library_support


test_data = [
    # a top level module
    ("os", True),
    # a submodule
    ("os.path", True),
    # an attribute (function) of a module
    ("os.path.join", True),
    # an attribute (class) of a module
    ("collections.OrderedDict", True),
    # an attribute of a class
    ("collections.OrderedDict.update", True),
    # a missing attribute of an existing module
    ("os.no_such_attribute", False),
    # a missing attribute of an existing submodule
    ("os.path.no_such_attribute", False),
    # a missing top level module
    ("no_such_module", False),
    # a missing submodule
    ("os.no_such_module", False),
    # an attribute of a missing module
    ("no_such_module.attribute", False),
]


@pytest.mark.parametrize('name,expected', test_data)
def test_is_supported(name, expected):
    assert does_library_support.is_supported(name) == expected
