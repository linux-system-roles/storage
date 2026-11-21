# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.2 Astra
"""Opt-in systemd TPM2 enrollment for a volume's own LUKS2 header."""
from __future__ import absolute_import, division, print_function

import json
import os
import re
import subprocess

__metaclass__ = type


class TPM2Error(Exception):
    pass


def command(argv, data=None):
    """Never put unlock material in argv, the environment, logs or error output."""
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                close_fds=True, env=dict(os.environ, LC_ALL='C', SYSTEMD_LOG_LEVEL='err'))
    except OSError:
        raise TPM2Error("cannot execute %s for LUKS2 TPM enrollment" % argv[0])
    out, unused_stderr = proc.communicate(data)
    if proc.returncode:
        raise TPM2Error("%s failed (exit %d); check the TPM, unlock credential and LUKS2 device"
                        % (argv[0], proc.returncode))
    return out


def matching_token(header, pcrs):
    """Recognize only an unambiguous systemd token with a plain PCR policy."""
    tokens = [(idx, t) for idx, t in header['tokens'].items() if t['type'] == 'systemd-tpm2']
    if not tokens:
        return None
    if len(tokens) != 1:
        raise TPM2Error("multiple systemd TPM2 tokens; refusing to choose or replace one")
    idx, token = tokens[0]
    slots = token['keyslots']
    # systemd uses both dashes and underscores in the on-disk token ABI.
    fields = dict((k.replace('_', '-'), v) for k, v in token.items())
    if (not idx.isdigit() or len(slots) != 1 or slots[0] not in header['keyslots']
            or sorted(fields.get('tpm2-pcrs', [-1])) != pcrs
            or any(fields.get(k) for k in ('tpm2-pin', 'tpm2-pubkey', 'tpm2-pubkey-pcrs', 'tpm2-pcrlock', 'tpm2-nv-index'))):
        raise TPM2Error("existing TPM2 token does not match the requested PCR-only policy; refusing to replace it")
    return idx


class Enrollment(object):
    """One request, from Blivet discovery through the post-commit verification."""

    def __init__(self, spec, check_mode):
        self.spec = spec
        self.check_mode = check_mode
        policy = spec['encryption_tpm2']
        self.pcrs = sorted(policy['pcrs'])
        if len(set(self.pcrs)) != len(self.pcrs) or any(p < 0 or p > 23 for p in self.pcrs):
            raise TPM2Error("encryption_tpm2.pcrs must contain unique PCR indices from 0 to 23")
        if spec.get('encryption') is False or spec.get('encryption_luks_version') not in (None, 'luks2'):
            raise TPM2Error("encryption_tpm2 requires a LUKS2 volume")
        self.token = None
        self.path = None
        self.uuid = None
        self.is_new = False
        # Probe the selected target stack before making storage changes. Do not
        # touch the TPM, require extra tools or change behavior for other volumes.
        help_text = command(['systemd-cryptenroll', '--help'])
        if b'--unlock-key-file=' not in help_text or b'--tpm2-public-key=' not in help_text:
            raise TPM2Error("TPM enrollment requires systemd-cryptenroll with --unlock-key-file and --tpm2-public-key")
        self.has_pcrlock = b'--tpm2-pcrlock=' in help_text
        crypto_help = command(['cryptsetup', '--help'])
        plugin = re.search(br'^LUKS2 external token plugin path: (/.+)\.$', crypto_help, re.MULTILINE)
        if not plugin or not os.path.isfile(os.path.join(plugin.group(1), b'libcryptsetup-token-systemd-tpm2.so')):
            raise TPM2Error("cryptsetup with the systemd TPM2 token plugin is required")
        if len([line for line in command(['systemd-cryptenroll', '--tpm2-device=list']).splitlines()
                if line.lstrip().startswith(b'/dev/')]) != 1:
            raise TPM2Error("encryption_tpm2 requires exactly one usable TPM2 device")

    def header(self):
        return json.loads(command(['cryptsetup', 'luksDump', '--dump-json-metadata', self.path]).decode('utf-8'))

    def token_open(self, name=None):
        args = ['cryptsetup', 'open', '--type', 'luks2', '--batch-mode', '--token-only', '--token-id', self.token]
        if name is None:
            args.append('--test-passphrase')
        command(args + [self.path] + ([name] if name is not None else []))

    def credential(self):
        path = self.spec.get('encryption_key')
        if path:
            if not os.path.isabs(path) or not os.path.isfile(path):
                raise TPM2Error("encryption_key must name an existing file on the managed node")
            return path, None
        password = self.spec.get('encryption_password')
        if not password:
            raise TPM2Error("a passphrase or key file is required for first TPM enrollment")
        return '/proc/self/fd/0', password.encode('utf-8')

    def check_identity(self):
        if not self.uuid or command(['cryptsetup', 'luksUUID', self.path]).decode().strip() != self.uuid:
            raise TPM2Error("LUKS UUID changed before TPM enrollment")

    def existing(self, path, expected_uuid):
        self.path = path
        self.uuid = expected_uuid
        self.check_identity()
        header = self.header()
        self.token = matching_token(header, self.pcrs)
        if self.token is not None:
            self.token_open()
        else:
            path, data = self.credential()
            command(['cryptsetup', 'open', '--type', 'luks2', '--test-passphrase', '--batch-mode',
                     '--disable-external-tokens', '--key-file', path, self.path], data)

    def new(self, path):
        self.path = path
        self.is_new = True
        self.credential()

    def finish(self, result):
        if self.token is not None:
            return
        if self.check_mode:
            result['changed'] = True
            return
        self.check_identity()
        # Re-read the real header even on a freshly created device.
        before = self.header()
        self.token = matching_token(before, self.pcrs)
        if self.token is None:
            path, data = self.credential()
            args = ['systemd-cryptenroll', '--unlock-key-file=' + path, '--tpm2-device=auto', '--tpm2-with-pin=no',
                    '--tpm2-pcrs=' + '+'.join(str(p) for p in self.pcrs), '--tpm2-public-key=']
            if self.has_pcrlock:
                args.append('--tpm2-pcrlock=')
            try:
                command(args + [self.path], data)
            finally:
                after = self.header()
                if before != after:
                    result['changed'] = True
            self.token = matching_token(after, self.pcrs)
            if self.token is None:
                raise TPM2Error("no matching TPM2 token after enrollment")
        self.token_open()
