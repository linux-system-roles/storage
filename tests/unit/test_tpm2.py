# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.2 Astra
"""The TPM policy must never replace an operator's credential."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
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
        self.marker = ''
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
        if argv[0] == 'blkid':
            return ('SUBSYSTEM=' + self.marker + '\n').encode()
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
        elif argv[1] == 'luksRemoveKey':
            assert data == b'temporary'
            assert self.header['tokens']['5']['keyslots'] == ['1']
            del self.header['keyslots']['0']
        elif argv[1] == 'config':
            self.marker = ''
        else:
            pytest.fail('unexpected command: %s' % argv[0:2])
        return b''


def token():
    return {'type': 'systemd-tpm2', 'keyslots': ['1'], 'tpm2-pcrs': [7, 11]}


def request(d, mode='enroll', check=False, password=None):
    e = tpm2.Enrollment(dict(encryption_tpm2=dict(mode=mode, pcrs=[11, 7]), encryption_password=password), check)
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


def test_refuse_existing_password_slot_even_with_working_token(monkeypatch):
    d = Device(monkeypatch, {'5': token()}, slots=['0', '1'])
    before = copy.deepcopy(d.header)
    with pytest.raises(tpm2.TPM2Error, match='refusing to convert'):
        request(d, mode='only')
    assert before == d.header
    del d.header['keyslots']['0']
    result = dict(changed=False)
    request(d, mode='only').finish(result)
    assert not result['changed']


def test_failed_token_proof_cannot_remove_bootstrap_key(monkeypatch):
    d = Device(monkeypatch, {'5': token()}, slots=['0', '1'], fail_verify=True)
    d.marker = 'lsr-tpm2-' + '0' * 32
    monkeypatch.setattr(tpm2.PendingKey, 'recover', lambda p, uid, exclusive: setattr(p, 'password', 'temporary'))
    with pytest.raises(tpm2.TPM2Error, match='cannot unseal'):
        request(d, mode='only')
    assert set(d.header['keyslots']) == {'0', '1'}
    assert not any('luksRemoveKey' in a for a, unused in d.calls)


@pytest.mark.parametrize('already_enrolled,already_removed', [(False, False), (True, False), (True, True)])
def test_resume_owned_transaction(monkeypatch, already_enrolled, already_removed):
    slots = (['1'] if already_removed else ['0', '1']) if already_enrolled else ['0']
    d = Device(monkeypatch, {'5': token()} if already_enrolled else {}, slots=slots)
    d.marker = 'lsr-tpm2-' + 'a' * 32
    monkeypatch.setattr(tpm2.PendingKey, 'recover', lambda p, uid, exclusive: setattr(p, 'password', 'temporary'))
    monkeypatch.setattr(tpm2.PendingKey, 'bind', lambda p, uid: None)
    discarded = []
    monkeypatch.setattr(tpm2.PendingKey, 'discard', lambda p: discarded.append(p.marker))
    result = dict(changed=False)
    request(d, mode='only').finish(result)
    assert result['changed'] and list(d.header['keyslots']) == ['1']
    assert not d.marker and discarded
    assert sum('luksRemoveKey' in a for a, unused in d.calls) == (0 if already_removed else 1)


def test_unknown_token_during_resume_preserved(monkeypatch):
    d = Device(monkeypatch, {'5': token(), '6': {'type': 'other', 'keyslots': ['0']}}, slots=['0', '1'])
    d.marker = 'lsr-tpm2-' + '0' * 32
    monkeypatch.setattr(tpm2.PendingKey, 'recover', lambda p, uid, exclusive: setattr(p, 'password', 'temporary'))
    with pytest.raises(tpm2.TPM2Error, match='unexpected keyslots'):
        request(d, mode='only')
    assert set(d.header['keyslots']) == {'0', '1'}


def test_sealed_credential_survives_restart_and_is_bound_before_removal(monkeypatch, tmpdir):
    secret = []

    def creds(argv, data):
        if argv[1] == 'encrypt':
            secret.append(data)
            return b'sealed fixture'
        assert argv[1] == 'decrypt' and data == b'sealed fixture'
        return secret[0]

    monkeypatch.setattr(tpm2, 'command', creds)
    monkeypatch.setattr(tpm2.PendingKey, 'directory', str(tmpdir.join('credentials')))
    fresh = tpm2.PendingKey()
    fresh.persist([7])
    with open(fresh.path, 'rb') as stream:
        assert stream.read() == b'sealed fixture'
    uid = '6d45597a-8ced-48a4-82ca-a013d90b17a0'
    resumed = tpm2.PendingKey(fresh.marker)
    # A marker copied onto a different, already TPM-only volume cannot consume
    # the transaction belonging to the original still password-locked volume.
    with pytest.raises(tpm2.TPM2Error, match='no verified bootstrap'):
        resumed.recover(uid, exclusive=True)
    resumed.recover(uid, exclusive=False)
    assert resumed.password == fresh.password
    resumed.bind(uid)
    after_slot_removal = tpm2.PendingKey(fresh.marker)
    after_slot_removal.recover(uid, exclusive=True)
    assert after_slot_removal.password == fresh.password
    after_slot_removal.discard()
    assert tmpdir.join('credentials').listdir() == []
