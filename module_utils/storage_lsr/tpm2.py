# SPDX-License-Identifier: MIT
# Assisted by OpenCode using model GPT-6.2 Astra
"""Opt-in systemd TPM2 enrollment for a volume's own LUKS2 header."""
from __future__ import absolute_import, division, print_function

import binascii
import errno
import json
import os
import re
import stat
import subprocess
import uuid

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


class PendingKey(object):
    """A bootstrap slot must remain recoverable across controller and host restarts.

    Before Blivet formats a device, persist and fsync a TPM-sealed credential.
    Put its random, non-secret identifier in the *new* LUKS2 subsystem field at
    format time. Never identify a pending credential by /dev/sdX or a volume name.
    """

    directory = '/var/lib/storage-lsr-tpm2'
    pattern = re.compile(r'^lsr-tpm2-[0-9a-f]{32}\Z')

    def __init__(self, marker=None):
        self.marker = marker or 'lsr-tpm2-' + uuid.uuid4().hex
        if not self.pattern.match(self.marker):
            raise TPM2Error("invalid pending TPM enrollment identifier")
        self.path = os.path.join(self.directory, self.marker + '.cred')
        self.password = None if marker else binascii.hexlify(os.urandom(32)).decode('ascii')

    @staticmethod
    def sync_dir(path):
        fd = os.open(path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def private_dir(self, create=False):
        if create:
            try:
                os.mkdir(self.directory, 0o700)
                self.sync_dir(os.path.dirname(self.directory))
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
        st = os.lstat(self.directory)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
            raise TPM2Error("pending TPM credential directory is not private")

    def decrypt(self, blob):
        return command(['systemd-creds', 'decrypt', '--name=' + self.marker, '-', '-'], blob).decode('ascii')

    def persist(self, pcrs):
        self.private_dir(create=True)
        blob = command(['systemd-creds', 'encrypt', '--with-key=tpm2', '--name=' + self.marker,
                        '--tpm2-pcrs=' + '+'.join(str(p) for p in pcrs), '-', '-'], self.password.encode('ascii'))
        if self.decrypt(blob) != self.password:
            raise TPM2Error("cannot verify the sealed bootstrap credential before formatting")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        self.sync_dir(self.directory)

    def bound_path(self, luks_uuid):
        return os.path.join(self.directory, '%s-%s.cred' % (self.marker, uuid.UUID(luks_uuid)))

    def bind(self, luks_uuid):
        # Record proof of ownership durably *after* the random key passed a
        # slot-specific unlock test, *before* its slot can disappear.
        bound = self.bound_path(luks_uuid)
        if self.path != bound:
            if os.path.lexists(bound):
                raise TPM2Error("conflicting pending TPM credential")
            os.rename(self.path, bound)
            self.path = bound
            self.sync_dir(self.directory)

    def recover(self, luks_uuid, exclusive):
        self.private_dir()
        bound = self.bound_path(luks_uuid)
        if os.path.lexists(bound):
            self.path = bound
        elif exclusive:
            raise TPM2Error("no verified bootstrap transaction for this LUKS UUID")
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            st = os.fstat(stream.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
                raise TPM2Error("invalid pending TPM credential")
            self.password = self.decrypt(stream.read())
        if not re.match(r'^[0-9a-f]{64}\Z', self.password):
            raise TPM2Error("invalid sealed bootstrap key")

    def discard(self):
        os.unlink(self.path)
        self.sync_dir(self.directory)


class Enrollment(object):
    """One request, from Blivet discovery through the post-commit verification."""

    def __init__(self, spec, check_mode):
        self.spec = spec
        self.check_mode = check_mode
        policy = spec['encryption_tpm2']
        self.pcrs = sorted(policy['pcrs'])
        self.only = policy.get('mode') == 'only'
        self.pending = None
        if len(set(self.pcrs)) != len(self.pcrs) or any(p < 0 or p > 23 for p in self.pcrs):
            raise TPM2Error("encryption_tpm2.pcrs must contain unique PCR indices from 0 to 23")
        if spec.get('encryption') is False or spec.get('encryption_luks_version') not in (None, 'luks2'):
            raise TPM2Error("encryption_tpm2 requires a LUKS2 volume")
        if self.only and (spec.get('encryption_key') or spec.get('encryption_password')):
            raise TPM2Error("TPM-only creation cannot be combined with a user password or key file")
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
        if self.pending:
            return '/proc/self/fd/0', self.pending.password.encode('ascii')
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
        marker = self.marker()
        if PendingKey.pattern.match(marker):
            if not self.only:
                raise TPM2Error("unfinished TPM-only enrollment; resume with the original policy")
            self.pending = PendingKey(marker)
            self.pending.recover(self.uuid, self.exclusively_tpm(header))
        if self.only and not self.pending and not self.exclusively_tpm(header):
            raise TPM2Error("refusing to convert existing keyslots to TPM-only")
        if self.token is not None:
            self.token_open()
        if self.pending:
            self.check_pending_slots(header)
        if self.token is None or (self.pending and not self.exclusively_tpm(header)):
            path, data = self.credential()
            command(['cryptsetup', 'open', '--type', 'luks2', '--test-passphrase', '--batch-mode',
                     '--disable-external-tokens', '--key-file', path, self.path], data)

    def marker(self):
        fields = command(['blkid', '-p', '-o', 'export', self.path]).splitlines()
        return next((line[10:].decode('ascii', 'replace') for line in fields if line.startswith(b'SUBSYSTEM=')), '')

    def exclusively_tpm(self, header):
        return self.token is not None and len(header['tokens']) == 1 and set(header['keyslots']) == set(header['tokens'][self.token]['keyslots'])

    def check_pending_slots(self, header):
        if ((self.token is None and (header['tokens'] or len(header['keyslots']) != 1))
                or (self.token is not None and (len(header['tokens']) != 1 or len(header['keyslots']) not in (1, 2)))):
            raise TPM2Error("unexpected keyslots during TPM-only enrollment; refusing to modify the header")

    def new(self, path):
        self.path = path
        self.is_new = True
        if self.only:
            if b'--tpm2-pcrs=' not in command(['systemd-creds', '--help']):
                raise TPM2Error("TPM-only creation requires systemd-creds with TPM2 PCR support")
            self.pending = PendingKey()
        self.credential()

    def before_commit(self):
        if self.is_new and self.pending and not self.check_mode:
            self.pending.persist(self.pcrs)

    def finish_only(self, result):
        # Only a freshly formatted header bearing our original transaction ID
        # can lose a slot. luksRemoveKey proves possession of the random key;
        # never wipe a slot by number or by class.
        if self.marker() != self.pending.marker:
            raise TPM2Error("pending TPM credential does not belong to this header")
        self.check_identity()
        header = self.header()
        if matching_token(header, self.pcrs) != self.token:
            raise TPM2Error("TPM token changed during enrollment")
        if not self.exclusively_tpm(header):
            if len(header['tokens']) != 1 or len(header['keyslots']) != 2:
                raise TPM2Error("unexpected keyslots during TPM-only enrollment; refusing removal")
            # Explicitly prove the bootstrap secret unlocks the *other* slot.
            other, = set(header['keyslots']) - set(header['tokens'][self.token]['keyslots'])
            data = self.pending.password.encode('ascii')
            command(['cryptsetup', 'open', '--type', 'luks2', '--test-passphrase', '--batch-mode',
                     '--disable-external-tokens', '--key-slot', other, '--key-file', '-', self.path], data)
            self.token_open()
            self.pending.bind(self.uuid)
            command(['cryptsetup', 'luksRemoveKey', '--key-file', '-', self.path], data)
            result['changed'] = True
            header = self.header()
            if matching_token(header, self.pcrs) != self.token or not self.exclusively_tpm(header):
                raise TPM2Error("could not verify exclusive TPM enrollment")
        self.token_open()
        command(['cryptsetup', 'config', '--subsystem=', self.path])
        result['changed'] = True
        self.pending.discard()

    def finish(self, result):
        if self.token is not None and not self.pending:
            return
        if self.check_mode:
            result['changed'] = True
            return
        self.check_identity()
        if self.pending and self.marker() != self.pending.marker:
            raise TPM2Error("pending TPM credential does not belong to this header")
        # Re-read the real header even on a freshly created device.
        before = self.header()
        self.token = matching_token(before, self.pcrs)
        if self.pending:
            self.check_pending_slots(before)
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
        if self.pending:
            self.finish_only(result)
