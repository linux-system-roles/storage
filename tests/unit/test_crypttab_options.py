# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.2 Astra
"""Test crypttab planning without requiring block devices or a real /etc/crypttab."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

from collections import namedtuple

import pytest

import blivet


Format = namedtuple('Format', 'type map_name key_file')
Device = namedtuple('Device', 'path format')
Action = namedtuple('Action', 'device format is_format is_create is_destroy')
RAW = Device('/dev/vg/lv', Format('luks', 'luks-generated', '/new.key'))


class Tree(object):
    devices = [RAW]

    def resolve_device(self, spec):
        if spec in (RAW.path, 'UUID=abcd', '/dev/disk/by-uuid/abcd'):
            return RAW
        return None


@pytest.fixture
def table(tmpdir):
    def load(contents):
        path = tmpdir.join('crypttab')
        path.write(contents)
        return blivet.CryptTab(Tree(), str(path))
    return load


@pytest.mark.parametrize('before,options,after', [
    ('alias UUID=abcd none', 'noauto', 'alias UUID=abcd none noauto'),
    ('alias UUID=abcd', 'noauto', 'alias UUID=abcd - noauto'),
    ('alias UUID=abcd', '', None),
    ('alias UUID=abcd - noauto', 'noauto', None),
    ('alias UUID=abcd - noauto', '', 'alias UUID=abcd -'),
    ('alias UUID=abcd - noauto', None, None),
    ('  alias\tUUID=abcd\t/key\\040file\told  # keep', 'tpm2-device=auto,nofail',
     '  alias\tUUID=abcd\t/key\\040file\ttpm2-device=auto,nofail  # keep'),
    ('alias /dev/disk/by-uuid/abcd none  old  # keep', '',
     'alias /dev/disk/by-uuid/abcd none  # keep'),
])
def test_existing_without_storage_actions(table, before, options, after):
    contents = '# comment\nunrelated /dev/other - discard\n' + before + '\n'
    requested = {RAW: options} if options is not None else {}
    changes = blivet.get_crypt_info([], requested, table(contents))
    if after is None:
        assert changes == []
    else:
        entry, = changes
        assert entry['name'] == 'alias'
        assert entry['backing_device'] == before.split()[1]
        assert entry['password'] == after.split()[2]
        assert entry['line'] == after
        assert not blivet.get_crypt_info([], requested, table(contents.replace(before, after)))


@pytest.mark.parametrize('contents', [
    'one UUID=abcd -\ntwo /dev/vg/lv -',
    'one /dev/vg/lv -\none UUID=abcd -',
    'one UUID=abcd -\none /dev/other -',
    'luks-generated /dev/other -',
])
def test_refuse_ambiguous_boot_identity(table, contents):
    with pytest.raises(blivet.BlivetAnsibleError, match='crypttab'):
        blivet.get_crypt_info([], {RAW: 'noauto'}, table(contents))


def test_device_alias_unknown_to_blivet(table, monkeypatch):
    paths = {RAW.path: '/dev/dm-3', '/dev/mapper/vg-lv': '/dev/dm-3'}
    monkeypatch.setattr(blivet.os.path, 'realpath', lambda path: paths.get(path, path))
    change, = blivet.get_crypt_info([], {RAW: 'noauto'}, table('custom /dev/mapper/vg-lv none'))
    assert change['line'] == 'custom /dev/mapper/vg-lv none noauto'


def test_only_present_volumes_can_request_options():
    spec = dict(name='lv', state='present', _raw_device=RAW.path, crypttab_options='noauto')
    gone = dict(spec, state='absent', crypttab_options='discard')
    pools = [dict(state='absent', volumes=[dict(spec, crypttab_options='other')]),
             dict(state='present', volumes=[spec, gone])]
    assert blivet.get_volume_crypttab_options(Tree(), pools, [gone]) == {RAW: 'noauto'}
    with pytest.raises(blivet.BlivetAnsibleError, match='conflicting'):
        blivet.get_volume_crypttab_options(Tree(), pools, [dict(spec, crypttab_options='discard')])


def test_options_do_not_reformat_a_closed_luks_volume(monkeypatch):
    class ClosedDevice(object):
        format = RAW.format

        @property
        def raw_device(self):
            return self

    monkeypatch.setattr(blivet, 'safe_mode', False)
    volume = blivet.BlivetVolume(Tree(), dict(name='lv', encryption=True, crypttab_options='noauto'))
    volume._device = ClosedDevice()
    with pytest.raises(blivet.BlivetAnsibleError, match='closed LUKS'):
        volume.manage()


def test_new_missing_and_replaced_entries(table):
    create = Action(RAW, RAW.format, True, True, False)
    destroy = Action(RAW, Format('luks', 'old', None), True, False, True)
    resize = Action(RAW, RAW.format, True, False, False)
    fresh = table('')
    requested = {RAW: 'noauto'}
    new, = blivet.get_crypt_info([create], requested, fresh)
    assert new['line'] == 'luks-generated /dev/vg/lv /new.key noauto'
    assert blivet.get_crypt_info([], requested, fresh) == [new]
    assert 'line' not in blivet.get_crypt_info([create], {}, fresh)[0]
    existing = table('alias UUID=abcd /old.key noauto')
    assert blivet.get_crypt_info([resize], {}, existing) == []
    old, new_again = blivet.get_crypt_info([create, destroy], requested, existing)
    assert (old['state'], old['name'], old['backing_device']) == ('absent', 'alias', 'UUID=abcd')
    assert new_again == new
