# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.2 Astra
"""Report completed actions on failure, but still predict changes in check mode."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

try:
    from unittest import mock
except ImportError:  # Python 2
    import mock

import pytest

import blivet


@pytest.mark.parametrize("completed,failed,check_mode,changed", [
    (False, True, False, False),
    (True, True, False, True),
    (False, False, True, True),
])
def test_action_result(monkeypatch, completed, failed, check_mode, changed):
    action = mock.Mock(is_destroy=False, is_format=False, is_create=False, is_configure=False,
                       type_desc_str="create device")
    action.device.path = "/dev/test"
    b = mock.Mock(packages=[])
    b.devicetree.devices = []
    b.devicetree.leaves = []
    b.devicetree.actions.find.return_value = [action]
    monkeypatch.setattr(blivet, "Blivet", lambda: b, raising=False)
    monkeypatch.setattr(blivet, "FSTab", lambda unused: None)
    monkeypatch.setattr(blivet, "CryptTab", lambda unused: None)
    hooks = []
    callbacks = mock.Mock()
    callbacks.action_executed.add.side_effect = hooks.append
    monkeypatch.setattr(blivet, "callbacks", callbacks, raising=False)

    def process(devices, dry_run):
        assert dry_run == check_mode
        if completed:
            for notify in hooks:
                notify(action)
        if failed:
            raise RuntimeError("action failed")

    b.devicetree.actions.process.side_effect = process
    module = mock.Mock(check_mode=check_mode, params=dict(packages_only=False, pools=[], volumes=[]))
    result = dict(changed=False, actions=[])
    if failed:
        with pytest.raises(blivet.BlivetAnsibleError, match="Failed to commit changes to disk: action failed"):
            blivet._run_storage(module, result)
    else:
        blivet._run_storage(module, result)
    assert result['changed'] is changed
    assert result['actions'] == ([dict(action="create device", fs_type=None, device="/dev/test")] if completed else [])
