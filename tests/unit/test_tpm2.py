# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.2 Astra
"""The TPM policy must never replace an operator's credential."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json

import pytest
from ansible.module_utils.storage_lsr import tpm2


class Device(object):
    path = '/dev/vg/volume'
    uuid = 'discovered-uuid'

    def __init__(self, monkeypatch, tokens=None, slots=('0',), fail_verify=False):
        self.header = dict(tokens=tokens or {}, keyslots=dict((s, {}) for s in slots))
        self.calls = []
        self.fail_verify = fail_verify
        monkeypatch.setattr(tpm2, 'command', self.run)
        real_file = tpm2.os.path.isfile
        monkeypatch.setattr(tpm2.os.path, 'isfile', lambda p: p == b'/plugins/libcryptsetup-token-systemd-tpm2.so' or real_file(p))

    def run(self, argv, data=None):
        self.calls.append((list(argv), data))
        if argv == ['systemd-cryptenroll', '--help']:
            return b'--unlock-key-file= --tpm2-public-key= --tpm2-pcrlock='
        if argv == ['cryptsetup', '--help']:
            return b'LUKS2 external token plugin path: /plugins.\n'
        if argv == ['systemd-cryptenroll', '--tpm2-device=list']:
            return b'PATH DEVICE DRIVER\n/dev/tpmrm0 t d\n'
        if argv[1] == 'luksUUID':
            return self.uuid.encode()
        if argv[1] == 'luksDump':
            return json.dumps(self.header).encode()
        if '--token-only' in argv:
            if self.fail_verify:
                raise tpm2.TPM2Error('cannot unseal')
            assert '--token-id' in argv
        elif argv[1] == 'open':
            assert data in (b'test-secret', b'temporary') and '--key-file' in argv
        elif argv[0] == 'systemd-cryptenroll':
            assert self.header['tokens'] == {} and data in (b'test-secret', b'temporary')
            self.header['tokens']['5'] = token()
            self.header['keyslots']['1'] = {}
        else:
            pytest.fail('unexpected command: %s' % argv[0:2])
        return b''


def token():
    return {'type': 'systemd-tpm2', 'keyslots': ['1'], 'tpm2-pcrs': [7, 11]}


def request(d, check=False, password=None):
    e = tpm2.Enrollment(dict(encryption_tpm2=dict(pcrs=[11, 7]), encryption_password=password), check)
    e.existing(d.path, d.uuid)
    return e


@pytest.mark.parametrize('options', [
    {'tpm2-pcrs': [7]}, {'tpm2-pin': True}, {'tpm2_pubkey_pcrs': [11]}, {'tpm2-pcrlock': True},
    {'keyslots': []}, {'keyslots': ['9']},
])
def test_existing_policy_conflict_is_read_only(monkeypatch, options):
    t = token()
    t.update(options)
    d = Device(monkeypatch, {'5': t}, slots=['0', '1'])
    with pytest.raises(tpm2.TPM2Error, match='refusing to replace'):
        request(d)
    assert not any('--tpm2-device=auto' in a for a, unused in d.calls)


def test_uuid_mismatch_before_header_access(monkeypatch):
    d = Device(monkeypatch)
    e = tpm2.Enrollment(dict(encryption_tpm2=dict(pcrs=[7])), False)
    with pytest.raises(tpm2.TPM2Error, match='UUID'):
        e.existing(d.path, 'different')
    assert not any('luksDump' in a for a, unused in d.calls)


def test_additive_check_apply_and_repeat(monkeypatch):
    d = Device(monkeypatch)
    result = dict(changed=False)
    request(d, check=True, password='test-secret').finish(result)
    assert result['changed'] and not d.header['tokens']
    result['changed'] = False
    request(d, password='test-secret').finish(result)
    assert result['changed'] and sorted(d.header['keyslots']) == ['0', '1']
    result['changed'] = False
    request(d).finish(result)
    assert not result['changed']
    assert sum('--tpm2-device=auto' in a for a, unused in d.calls) == 1
    assert all('test-secret' not in ' '.join(a) for a, unused in d.calls)
