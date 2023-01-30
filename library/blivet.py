#!/usr/bin/python
from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: blivet

short_description: Module for management of linux block device stacks

version_added: "2.5"

description:
    - "WARNING: Do not use this module directly! It is only for role internal use."
    - "Module configures storage pools and volumes to match the state specified
       in input parameters. It does not do any management of /etc/fstab entries."

options:
    pools:
        description:
            - list of dicts describing pools
    volumes:
        description:
            - list of dicts describing volumes
    use_partitions:
        description:
            - boolean indicating whether to create partitions on disks for pool backing devices
    disklabel_type:
        description:
            - |
              disklabel type string (eg: 'gpt') to use, overriding the built-in logic in blivet
    safe_mode:
        description:
            - boolean indicating that we should fail rather than implicitly/automatically
              removing devices or formatting
    diskvolume_mkfs_option_map:
        description:
            - dict which maps filesystem names to additional mkfs options that should be used
              when creating a disk volume (that is, a whole disk filesystem)

author:
    - David Lehman (@dwlehman)
'''

EXAMPLES = '''

- name: Manage devices
  blivet:
    pools:
        - name: "{{ app_pool }}"
          disks: ["sdd", "sde"]
          volumes:
            - name: shared
              size: "10 GiB"
              mount_point: /opt/{{ app_pool }}/shared
            - name: web
              size: 8g
              mount_point: /opt/{{ app_pool }}/web
    volumes:
        - name: whole_disk1
          disks: ['sdc']
          mount_point: /whole_disk1
          fs_type: ext4
          mount_options: journal_checksum,async,noexec
'''

RETURN = '''
actions:
    description: list of dicts describing actions taken
    returned: success
    type: list
    elements: dict
leaves:
    description: list of paths to leaf devices
    returned: success
    type: list
    elements: dict
mounts:
    description: list of dicts describing mounts to set up
    returned: success
    type: list
    elements: dict
crypts:
    description: list of dicts describing crypttab entries to set up
    returned: success
    type: list
    elements: dict
pools:
    description: list of dicts describing the pools w/ device path for each volume
    returned: success
    type: list
    elements: dict
volumes:
    description: list of dicts describing the volumes w/ device path for each
    returned: success
    type: list
    elements: dict
'''

import copy
import logging
import os
import traceback
import inspect

BLIVET_PACKAGE = None
LIB_IMP_ERR3 = ""
LIB_IMP_ERR = ""

try:
    from blivet3 import Blivet
    from blivet3.callbacks import callbacks
    from blivet3 import devicelibs
    from blivet3 import devices
    from blivet3.deviceaction import ActionConfigureFormat, ActionAddMember, ActionRemoveMember
    from blivet3.devicefactory import DEFAULT_THPOOL_RESERVE
    from blivet3.flags import flags as blivet_flags
    from blivet3.formats import get_format
    from blivet3.partitioning import do_partitioning
    from blivet3.size import Size
    from blivet3.udev import trigger
    from blivet3.util import set_up_logging
    BLIVET_PACKAGE = 'blivet3'
except ImportError:
    LIB_IMP_ERR3 = traceback.format_exc()
    try:
        from blivet import Blivet
        from blivet.callbacks import callbacks
        from blivet import devicelibs
        from blivet import devices
        from blivet.deviceaction import ActionConfigureFormat, ActionAddMember, ActionRemoveMember
        from blivet.devicefactory import DEFAULT_THPOOL_RESERVE
        from blivet.flags import flags as blivet_flags
        from blivet.formats import get_format
        from blivet.partitioning import do_partitioning
        from blivet.size import Size
        from blivet.udev import trigger
        from blivet.util import set_up_logging
        BLIVET_PACKAGE = 'blivet'
    except ImportError:
        LIB_IMP_ERR = traceback.format_exc()

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.storage_lsr.argument_validator import validate_parameters

if BLIVET_PACKAGE:
    blivet_flags.debug = True
    set_up_logging()
    log = logging.getLogger(BLIVET_PACKAGE + ".ansible")

    # XXX add support for LVM RAID raid0 level
    devicelibs.lvm.raid_levels.add_raid_level(devicelibs.raid.RAID0)
    if "raid0" not in devicelibs.lvm.raid_seg_types:
        devicelibs.lvm.raid_seg_types.append("raid0")


MAX_TRIM_PERCENT = 2

use_partitions = None  # create partitions on pool backing device disks?
disklabel_type = None  # user-specified disklabel type
safe_mode = None       # do not remove any existing devices or formatting
pool_defaults = dict()
volume_defaults = dict()


def find_duplicate_names(dicts):
    """ Return a list of names that appear more than once in a list of dicts.

        Items can be a list of any dicts with a 'name' key; that's all we're
        looking at. """
    names = list()
    duplicates = list()
    for item in dicts:
        if item['name'] in names and item['name'] not in duplicates:
            duplicates.append(item['name'])
        else:
            names.append(item['name'])

    return duplicates


class BlivetAnsibleError(Exception):
    pass


class BlivetBase(object):
    blivet_device_class = None
    _type = None

    def __init__(self, blivet_obj, spec_dict):
        self._blivet = blivet_obj
        self._spec_dict = spec_dict
        self._device = None

    def _get_format(self):
        # abstract method
        raise NotImplementedError()

    def _manage_one_encryption(self, device):
        ret = device
        # Make sure to handle adjusting both existing stacks and future stacks.
        if device == device.raw_device and self._spec_dict['encryption']:
            # add luks
            luks_name = "luks-%s" % device._name
            if safe_mode and (device.original_format.type is not None
                              or device.original_format.name != get_format(None).name):
                raise BlivetAnsibleError("cannot remove existing formatting on device '%s' in safe mode due to adding encryption" %
                                         device._name)
            if not device.format.exists:
                fmt = device.format
            else:
                fmt = get_format(None)

            self._blivet.format_device(device,
                                       get_format("luks",
                                                  name=luks_name,
                                                  cipher=self._spec_dict.get('encryption_cipher'),
                                                  key_size=self._spec_dict.get('encryption_key_size'),
                                                  luks_version=self._spec_dict.get('encryption_luks_version'),
                                                  passphrase=self._spec_dict.get('encryption_password') or None,
                                                  key_file=self._spec_dict.get('encryption_key') or None))

            if not device.format.has_key:
                raise BlivetAnsibleError("encrypted %s '%s' missing key/password" % (self._type, self._spec_dict['name']))

            luks_device = devices.LUKSDevice(luks_name,
                                             fmt=fmt,
                                             parents=[device])
            self._blivet.create_device(luks_device)
            ret = luks_device
        elif device != device.raw_device and not self._spec_dict['encryption']:
            # remove luks
            if safe_mode and (device.original_format.type is not None
                              or device.original_format.name != get_format(None).name):
                raise BlivetAnsibleError("cannot remove existing formatting on device '%s' in safe mode due to encryption removal" %
                                         device._name)
            if not device.format.exists:
                fmt = device.format
            else:
                fmt = get_format(None)

            ret = self._device.raw_device
            self._blivet.destroy_device(device)
            if fmt.type is not None:
                self._blivet.format_device(ret, fmt)

        # XXX: blivet has to store cipher, key_size, luks_version for existing before we
        #      can support re-encrypting based on changes to those parameters

        return ret

    def _new_mdarray(self, members, raid_name=""):

        if raid_name == "":
            raid_name = self._spec_dict["name"]

        # calculate and verify active and spare devices counts
        active_count = len(members)
        spare_count = 0

        requested_actives = self._spec_dict.get("raid_device_count")
        requested_spares = self._spec_dict.get("raid_spare_count")

        if requested_actives is not None and requested_spares is not None:
            if (requested_actives + requested_spares != len(members)
                or requested_actives < 0 or requested_spares < 0):  # noqa: E129
                raise BlivetAnsibleError("failed to set up '%s': cannot create RAID "
                                         "with %s members (%s active and %s spare)"
                                         % (self._spec_dict["name"], len(members),
                                            requested_actives, requested_spares))

        if requested_actives is not None:
            active_count = requested_actives
            spare_count = len(members) - active_count

        if requested_spares is not None:
            spare_count = requested_spares
            active_count = len(members) - spare_count

        # get chunk_size
        chunk_size = self._spec_dict.get("raid_chunk_size")
        chunk_size = Size(chunk_size) if chunk_size is not None else None

        # chunk size should be divisible by 4 KiB but mdadm ignores that. why?
        if chunk_size is not None and chunk_size % Size("4 KiB") != Size(0):
            raise BlivetAnsibleError("chunk size must be multiple of 4 KiB")

        try:
            raid_array = self._blivet.new_mdarray(name=raid_name,
                                                  level=self._spec_dict["raid_level"],
                                                  member_devices=active_count,
                                                  total_devices=len(members),
                                                  parents=members,
                                                  chunk_size=chunk_size,
                                                  metadata_version=self._spec_dict.get("raid_metadata_version"),
                                                  fmt=self._get_format())
        except ValueError as e:
            raise BlivetAnsibleError("cannot create RAID '%s': %s" % (raid_name, str(e)))

        return raid_array


class BlivetVolume(BlivetBase):
    _type = "volume"

    def __init__(self, blivet_obj, volume, bpool=None):
        super(BlivetVolume, self).__init__(blivet_obj, volume)
        self._blivet_pool = bpool

    @property
    def _volume(self):
        return self._spec_dict

    @property
    def required_packages(self):
        packages = list()
        if not self.ultimately_present:
            return packages

        if self.__class__.blivet_device_class is not None:
            packages.extend(self.__class__.blivet_device_class._packages)

        fmt = get_format(self._volume.get('fs_type'))
        packages.extend(fmt.packages)
        if self._volume.get('encryption'):
            packages.extend(get_format('luks').packages)
        if self._volume.get('compression') or self._volume.get('deduplication'):
            packages.extend(['vdo', 'kmod-kvdo'])
        return packages

    @property
    def ultimately_present(self):
        """ Should this volume be present when we are finished? """
        return (self._volume.get('state', 'present') == 'present'
                and (self._blivet_pool is None or self._blivet_pool.ultimately_present))

    def _type_check(self):  # pylint: disable=no-self-use
        """ Is self._device of the correct type? """
        return True

    def _get_device_id(self):
        """ Return an identifier by which to try looking the volume up. """
        return self._volume['name']

    def _look_up_device(self):
        """ Try to look up this volume in blivet's device tree. """
        if self._device:
            return

        device_id = self._get_device_id()
        if device_id is None:
            return

        device = self._blivet.devicetree.resolve_device(device_id)
        if device is None:
            return

        if device.format.type == 'luks':
            # XXX If we have no key we will always re-encrypt.
            device.format._key_file = self._volume.get('encryption_key')
            device.format.passphrase = self._volume.get('encryption_password')

            # set up the original format as well since it'll get used for processing
            device.original_format._key_file = self._volume.get('encryption_key')
            device.original_format.passphrase = self._volume.get('encryption_password')
            if device.isleaf:
                self._blivet.populate()

            if not device.isleaf:
                device = device.children[0]

        self._device = device

        # check that the type is correct, raising an exception if there is a name conflict
        if not self._type_check():
            self._device = None
            return  # TODO: see if we can create this device w/ the specified name

    def _update_from_device(self, param_name):
        """ Return True if param_name's value was retrieved from a looked-up device. """
        log.debug("Updating volume settings from device: %r", self._device)
        encrypted = "luks" in self._device.type or self._device.format.type == "luks"
        if encrypted and "luks" in self._device.type:
            luks_fmt = self._device.parents[0].format
        elif encrypted:
            luks_fmt = self._device.format

        if param_name == 'size':
            self._volume['size'] = int(self._device.size.convert_to())
        elif param_name == 'fs_type' and (self._device.format.type or self._device.format.name != get_format(None).name):
            self._volume['fs_type'] = self._device.format.type
        elif param_name == 'fs_label':
            self._volume['fs_label'] = getattr(self._device.format, 'label', "") or ""
        elif param_name == 'mount_point':
            self._volume['mount_point'] = getattr(self._device.format, 'mountpoint', None)
        elif param_name == 'disks':
            self._volume['disks'] = [d.name for d in self._device.disks]
        elif param_name == 'encryption':
            self._volume['encryption'] = encrypted
        elif param_name == 'encryption_key_size' and encrypted:
            self._volume['encryption_key_size'] = luks_fmt.key_size
        elif param_name == 'encryption_key_file' and encrypted:
            self._volume['encryption_key_file'] = luks_fmt.key_file
        elif param_name == 'encryption_cipher' and encrypted:
            self._volume['encryption_cipher'] = luks_fmt.cipher
        elif param_name == 'encryption_luks_version' and encrypted:
            self._volume['encryption_luks_version'] = luks_fmt.luks_version
        else:
            return False

        return True

    def _apply_defaults(self):
        for name, default in volume_defaults.items():
            if name in self._volume and self._volume[name] not in [None, list(), dict()]:
                continue

            default = None if default in ('none', 'None', 'null') else default

            if self._device:
                # Apply values from the device if it already exists.
                if not self._update_from_device(name):
                    self._volume[name] = default
            else:
                if self._volume.get(name) is None:
                    self._volume[name] = default

    def _get_format(self):
        """ Return a blivet.formats.DeviceFormat instance for this volume. """
        fmt = get_format(self._volume['fs_type'],
                         mountpoint=self._volume.get('mount_point'),
                         label=self._volume['fs_label'],
                         create_options=self._volume['fs_create_options'])
        if not fmt.supported or not fmt.formattable:
            raise BlivetAnsibleError("required tools for file system '%s' are missing" % self._volume['fs_type'])

        return fmt

    def _get_size(self):
        spec = self._volume['size']
        if isinstance(spec, str) and '%' in spec and self._blivet_pool:
            try:
                percentage = int(spec[:-1].strip())
            except ValueError:
                raise BlivetAnsibleError("invalid percentage '%s' size specified for volume '%s'" % (self._volume['size'], self._volume['name']))

            parent = self._blivet_pool._device
            size = parent.size * (percentage / 100.0)
        else:
            try:
                size = Size(spec)
            except Exception:
                raise BlivetAnsibleError("invalid size specification for volume '%s': '%s'" % (self._volume['name'], self._volume['size']))

        return size

    def _create(self):
        """ Schedule actions as needed to ensure the volume exists. """
        pass

    def _destroy(self):
        """ Schedule actions as needed to ensure the volume does not exist. """
        if self._device is None:
            return

        # save device identifiers for use by the role
        self._volume['_device'] = self._device.path
        self._volume['_raw_device'] = self._device.raw_device.path
        self._volume['_mount_id'] = self._device.fstab_spec

        # schedule removal of this device and any descendant devices
        self._blivet.devicetree.recursive_remove(self._device.raw_device)

    def _manage_encryption(self):
        self._device = self._manage_one_encryption(self._device)

    def _manage_cache(self):
        pass

    def _resize(self):
        """ Schedule actions as needed to ensure the device has the desired size. """
        size = self._get_size()

        if size and self._device.size != size:
            try:
                self._device.format.update_size_info()
            except AttributeError:
                # Error handling is done next.
                pass

            if not self._device.resizable:
                return

            trim_percent = (1.0 - float(self._device.max_size / size)) * 100
            log.debug("resize: size=%s->%s ; trim=%s", self._device.size, size, trim_percent)
            if size > self._device.max_size and trim_percent <= MAX_TRIM_PERCENT:
                log.info("adjusting %s resize target from %s to %s to fit in free space",
                         self._volume['name'],
                         size,
                         self._device.max_size)
                size = self._device.max_size
                if size == self._device.size:
                    return

            if not self._device.min_size <= size <= self._device.max_size:
                raise BlivetAnsibleError("volume '%s' cannot be resized to '%s'" % (self._volume['name'], size))

            try:
                self._blivet.resize_device(self._device, size)
            except ValueError as e:
                raise BlivetAnsibleError("volume '%s' cannot be resized from %s to %s: %s" % (self._device.name,
                                                                                              self._device.size,
                                                                                              size, str(e)))
        elif size and self._device.exists and self._device.size != size and not self._device.resizable:
            raise BlivetAnsibleError("volume '%s' cannot be resized from %s to %s" % (self._device.name, self._device.size, size))

    def _reformat(self):
        """ Schedule actions as needed to ensure the volume is formatted as specified. """
        fmt = self._get_format()

        if self._device.format.type == fmt.type:
            # format is the same, no need to run reformatting
            dev_label = '' if self._device.format.label is None else self._device.format.label
            if dev_label != fmt.label:
                # ...but the label has changed - schedule modification action
                conf_fmt_action = ActionConfigureFormat(self._device, 'label', fmt.label)
                self._blivet.devicetree.actions.add(conf_fmt_action)
            return

        if safe_mode and (self._device.format.type is not None or self._device.format.name != get_format(None).name):
            raise BlivetAnsibleError("cannot remove existing formatting on volume '%s' in safe mode" % self._volume['name'])

        if self._device.format.status and (self._device.format.mountable or self._device.format.type == "swap"):
            self._device.format.teardown()
        if not self._device.isleaf:
            self._blivet.devicetree.recursive_remove(self._device, remove_device=False)
        self._blivet.format_device(self._device, fmt)

    def manage(self):
        """ Schedule actions to configure this volume according to the yaml input. """
        # look up the device
        self._look_up_device()

        self._apply_defaults()

        # schedule destroy if appropriate
        if not self.ultimately_present:
            self._destroy()
            return

        # schedule create if appropriate
        self._create()

        # at this point we should have a blivet.devices.StorageDevice instance
        if self._device is None:
            raise BlivetAnsibleError("failed to look up or create device '%s'" % self._volume['name'])

        self._manage_encryption()
        self._manage_cache()

        # schedule reformat if appropriate
        if self._device.raw_device.exists:
            self._reformat()

        if self.ultimately_present and self._volume['mount_point'] and not self._device.format.mountable:
            raise BlivetAnsibleError("volume '%s' has a mount point but no mountable file system" % self._volume['name'])

        # schedule resize if appropriate
        if self._device.raw_device.exists and self._volume['size']:
            self._resize()

        # save device identifiers for use by the role
        self._volume['_device'] = self._device.path
        self._volume['_raw_device'] = self._device.raw_device.path
        self._volume['_mount_id'] = self._device.fstab_spec


class BlivetDiskVolume(BlivetVolume):
    blivet_device_class = devices.DiskDevice

    def _get_device_id(self):
        return self._volume['disks'][0]

    def _type_check(self):
        return self._device.raw_device.is_disk

    def _get_format(self):
        fmt = super(BlivetDiskVolume, self)._get_format()
        # pass -F to mke2fs on whole disks in RHEL7
        mkfs_options = diskvolume_mkfs_option_map.get(self._volume['fs_type'])
        if mkfs_options:
            if fmt.create_options:
                fmt.create_options += " "
            else:
                fmt.create_options = ""
            fmt.create_options += mkfs_options

        return fmt

    def _create(self):
        self._reformat()

    def _look_up_device(self):
        super(BlivetDiskVolume, self)._look_up_device()
        if not self._get_device_id():
            raise BlivetAnsibleError("no disks specified for volume '%s'" % self._volume['name'])
        elif not isinstance(self._volume['disks'], list):
            raise BlivetAnsibleError("volume disks must be specified as a list")

        if self._device is None:
            raise BlivetAnsibleError("unable to resolve disk specified for volume '%s' (%s)" % (self._volume['name'], self._volume['disks']))


class BlivetPartitionVolume(BlivetVolume):
    blivet_device_class = devices.PartitionDevice

    def _type_check(self):
        return self._device.raw_device.type == 'partition'

    def _get_device_id(self):
        device_id = None
        if self._blivet_pool._disks[0].partitioned and len(self._blivet_pool._disks[0].children) == 1:
            device_id = self._blivet_pool._disks[0].children[0].name

        return device_id

    def _resize(self):
        pass

    def _manage_cache(self):
        if self._volume['cached']:
            raise BlivetAnsibleError("caching is not supported for partition volumes")

    def _create(self):
        if self._device:
            return

        if self._blivet_pool:
            parent = self._blivet_pool._device
        else:
            parent = self._blivet.devicetree.resolve_device(self._volume['pool'])

        if parent is None:
            raise BlivetAnsibleError("failed to find pool '%s' for volume '%s'" % (self._blivet_pool['name'], self._volume['name']))

        size = Size("256 MiB")
        maxsize = None
        if isinstance(self._volume['size'], str) and '%' in self._volume['size']:
            maxsize = self._get_size()

        try:
            device = self._blivet.new_partition(parents=[parent], size=size, maxsize=maxsize, grow=True, fmt=self._get_format())
        except Exception:
            raise BlivetAnsibleError("failed set up volume '%s'" % self._volume['name'])

        self._blivet.create_device(device)
        try:
            do_partitioning(self._blivet)
        except Exception:
            raise BlivetAnsibleError("partition allocation failed for volume '%s'" % self._volume['name'])

        self._device = device


class BlivetLVMVolume(BlivetVolume):
    blivet_device_class = devices.LVMLogicalVolumeDevice

    def _get_device_id(self):
        if not self._blivet_pool._device:
            return None
        return "%s-%s" % (self._blivet_pool._device.name, self._volume['name'])

    def _get_size(self):

        spec = self._volume['size']
        if self._volume['thin'] and isinstance(spec, str) and '%' in spec:
            try:
                percentage = int(spec[:-1].strip())
            except ValueError:
                raise BlivetAnsibleError("invalid percentage '%s' size specified for thin volume '%s'" % (self._volume['size'], self._volume['name']))

            parent = self._get_parent_thinpool_by_name(self._volume.get('thin_pool_name'))
            size = parent.size * (percentage / 100.0)
        else:
            size = super(BlivetLVMVolume, self)._get_size()

        if isinstance(self._volume['size'], str) and '%' in self._volume['size']:
            size = self._blivet_pool._device.align(size, roundup=True)
        return size

    def _trim_size(self, size, parent_device):

        trim_percent = (1.0 - float(parent_device.free_space / size)) * 100
        log.debug("size: %s ; %s", size, trim_percent)

        if size > parent_device.free_space:
            if trim_percent > MAX_TRIM_PERCENT:
                raise BlivetAnsibleError("specified size for volume '%s' '%s' exceeds available space in pool '%s' (%s)" % (self._volume['name'],
                                                                                                                            size,
                                                                                                                            parent_device.name,
                                                                                                                            parent_device.free_space))
            else:
                log.info("adjusting %s size from %s to %s to fit in %s free space",
                         self._volume['name'],
                         size,
                         parent_device.free_space,
                         parent_device.name)
                return parent_device.free_space
        return size

    def _get_params_create_vdo(self):
        # Create parent vdopool and return vdo specific parameters for LV creation
        parent_device = self._blivet_pool._device
        size = self._get_size()

        pool_size = parent_device.free_space if size > parent_device.free_space else size

        if self._volume['vdo_pool_size']:
            try:
                pool_size = self._trim_size(Size(self._volume['vdo_pool_size']), parent_device)
            except BlivetAnsibleError:
                # Literally the same error just more specific description
                raise BlivetAnsibleError("specified 'vdo_pool_size' for volume '%s' "
                                         "exceeds available space in pool '%s' (%s)" % (pool_size,
                                                                                        parent_device.name,
                                                                                        parent_device.free_space))

        try:
            vdopool = self._blivet.new_lv(name='vdopool', vdo_pool=True,
                                          parents=[parent_device], compression=self._volume['compression'],
                                          deduplication=self._volume['deduplication'],
                                          size=pool_size)
        except Exception as e:
            raise BlivetAnsibleError("failed to set up VDO pool '%s': %s" % (self._volume['name'], str(e)))

        self._blivet.create_device(vdopool)

        return dict(vdo_lv=True, parents=[vdopool])

    def _get_params_lvmraid(self):
        # Return lvmraid specific parameters for LV creation
        parent_device = self._blivet_pool._device

        if self._volume['raid_disks']:
            pvs = list()

            for path in self._volume['raid_disks']:
                disk = self._blivet.devicetree.resolve_device(path)
                for pv in parent_device.pvs:
                    if disk in pv.parents:
                        pvs.append(pv)

        else:
            pvs = parent_device.pvs

        return dict(seg_type=self._volume['raid_level'], pvs=pvs)

    def _detach_cache(self):
        """ Detach cache from the volume and remove the unused cache pool """
        try:
            cpool_name = self._device.cache.detach()
        except Exception as e:
            raise BlivetAnsibleError("failed to detach cache from volume '%s': %s" % (self._device.name, str(e)))

        # full reset is needed for the cache pool to be added to the devicetree so we can remove it
        self._blivet.reset()

        cpool_name = cpool_name.rstrip("_cpool")
        cpool_device = self._blivet.devicetree.resolve_device("%s-%s" % (self._device.vg.name, cpool_name))

        self._blivet.destroy_device(cpool_device)

    def _get_cache_pvs(self):
        parent = self._blivet_pool._device
        fast_pvs = []
        for cache_spec in self._volume['cache_devices']:
            cache_device = self._blivet.devicetree.resolve_device(cache_spec)
            if cache_device is None:
                raise BlivetAnsibleError("cache device '%s' not found" % cache_spec)

            pv_device = next((pv for pv in parent.pvs if cache_device.name in [an.name for an in pv.ancestors]),
                             None)
            if pv_device is None:
                raise BlivetAnsibleError("cache device '%s' doesn't seems to be a physical volume or its parent" % cache_spec)
            fast_pvs.append(pv_device)

        return fast_pvs

    def _attach_cache(self):
        """ Create a new cache pool and attach it to the volume """

        if not hasattr(devices.lvm, "LVMCachePoolMixin"):
            raise BlivetAnsibleError("adding cache to an existing volume is currently not supported")

        fast_pvs = self._get_cache_pvs()
        cpool = self._blivet.new_lv(size=Size(self._volume['cache_size']),
                                    parents=[self._blivet_pool._device],
                                    cache_mode=self._volume['cache_mode'],
                                    pvs=fast_pvs,
                                    cache_pool=True,
                                    attach_to=self._device)
        self._blivet.create_device(cpool)

    def _manage_cache(self):
        if not self._device:
            # cache for newly created LVs is managed in _create
            return

        if self._volume['cached'] and not self._device.raw_device.cached:
            self._attach_cache()
        if not self._volume['cached'] and self._device.raw_device.cached:
            self._detach_cache()

    def _get_params_lvmcache(self):
        fast_pvs = self._get_cache_pvs()
        cache_request = devices.lvm.LVMCacheRequest(size=Size(self._volume['cache_size']),
                                                    mode=self._volume['cache_mode'],
                                                    pvs=fast_pvs)

        return dict(cache_request=cache_request)

    def _get_parent_thinpool_by_name(self, thin_pool_name):

        if thin_pool_name is None:
            if len(self._blivet_pool._thinpools) != 1:
                raise BlivetAnsibleError("cannot determine thinpool for assigning volume '%s' " % self._volume.get('name'))
            else:
                return self._blivet_pool._thinpools[0]

        for thinp in self._blivet_pool._thinpools:
            if thin_pool_name == thinp.lvname:
                return thinp
        return None

    def _create(self):
        if self._device:
            return

        thin_pool = self._volume.get('thin')
        use_vdo = self._volume['deduplication'] or self._volume['compression']
        use_lvmraid = self._volume['raid_level']

        if thin_pool:
            parent_device = self._get_parent_thinpool_by_name(self._volume.get('thin_pool_name'))
            if parent_device is None:
                raise BlivetAnsibleError("failed to find thin pool '%s' for volume '%s'" % (self._volume.get('thin_pool_name'), self._volume['name']))
        else:
            parent_device = self._blivet_pool._device
            if parent_device is None:
                raise BlivetAnsibleError("failed to find pool '%s' for volume '%s'" % (self._blivet_pool._device.name, self._volume['name']))

        if use_vdo:
            # VDO size is technically unlimited, so no size checks needed when it is used
            size = self._get_size()
        else:
            size = self._trim_size(self._get_size(), parent_device)

        # generic arguments preparation for blivet.new_lv call
        newlv_arguments = dict(fmt=self._get_format(),
                               name=self._volume['name'],
                               parents=[parent_device],
                               size=size)

        if thin_pool:
            thin_arguments = dict(thin_volume=True)
            newlv_arguments.update(thin_arguments)

        if use_vdo:
            vdo_arguments = self._get_params_create_vdo()
            newlv_arguments.update(vdo_arguments)

        if use_lvmraid:
            lvmraid_arguments = self._get_params_lvmraid()
            newlv_arguments.update(lvmraid_arguments)

        if self._volume['cached']:
            lvmcache_arguments = self._get_params_lvmcache()
            newlv_arguments.update(lvmcache_arguments)

        try:
            device = self._blivet.new_lv(**newlv_arguments)
        except Exception as e:
            raise BlivetAnsibleError("failed to set up volume '%s': %s" % (self._volume['name'], str(e)))

        self._blivet.create_device(device)
        self._device = device


class BlivetMDRaidVolume(BlivetVolume):

    def _process_device_numbers(self, members_count, requested_actives, requested_spares):

        active_count = members_count
        spare_count = 0

        if requested_actives is not None and requested_spares is not None:
            if (requested_actives + requested_spares != members_count
                or requested_actives < 0 or requested_spares < 0):  # noqa: E129
                raise BlivetAnsibleError("failed to set up volume '%s': cannot create RAID "
                                         "with %s members (%s active and %s spare)"
                                         % (self._volume['name'], members_count,
                                            requested_actives, requested_spares))

        if requested_actives is not None:
            active_count = requested_actives
            spare_count = members_count - active_count

        if requested_spares is not None:
            spare_count = requested_spares
            active_count = members_count - spare_count

        return members_count, active_count

    def _create_raid_members(self, member_names):
        members = list()

        for member_name in member_names:
            member_disk = self._blivet.devicetree.resolve_device(member_name)
            if member_disk is not None:
                if use_partitions:
                    # create partition table
                    label = get_format("disklabel", device=member_disk.path)
                    self._blivet.format_device(member_disk, label)

                    # create new partition
                    member = self._blivet.new_partition(parents=[member_disk], grow=True)
                    self._blivet.create_device(member)
                    self._blivet.format_device(member, fmt=get_format("mdmember"))
                    members.append(member)
                else:
                    self._blivet.format_device(member_disk, fmt=get_format("mdmember"))
                    members.append(member_disk)

        return members

    def _update_from_device(self, param_name):
        """ Return True if param_name's value was retrieved from a looked-up device. """
        if param_name == 'raid_level':
            self._volume['raid_level'] = self._device.level.name
        elif param_name == 'raid_chunk_size':
            self._volume['raid_chunk_size'] = str(self._device.chunk_size)
        elif param_name == 'raid_device_count':
            self._volume['raid_device_count'] = self._device.member_devices
        elif param_name == 'raid_spare_count':
            self._volume['raid_spare_count'] = self._device.spares
        elif param_name == 'raid_metadata_version':
            self._volume['raid_metadata_version'] = self._device.metadata_version
        else:
            return super(BlivetMDRaidVolume, self)._update_from_device(param_name)

        return True

    def _create(self):
        if self._device:
            return

        if safe_mode:
            raise BlivetAnsibleError("cannot create new RAID in safe mode")

        # begin creating the devices
        members = self._create_raid_members(self._volume["disks"])

        if use_partitions:
            try:
                do_partitioning(self._blivet)
            except Exception as e:
                raise BlivetAnsibleError("failed to allocate partitions for mdraid '%s': %s" % (self._volume['name'], str(e)))

        raid_array = self._new_mdarray(members)

        self._blivet.create_device(raid_array)

        self._device = raid_array

    def _destroy(self):
        """ Schedule actions as needed to ensure the pool does not exist. """

        if self._device is None:
            return

        ancestors = self._device.ancestors
        self._blivet.devicetree.recursive_remove(self._device)
        ancestors.remove(self._device)

        leaves = [a for a in ancestors if a.isleaf]
        while leaves:
            for ancestor in leaves:
                log.info("scheduling destruction of %s", ancestor.name)
                if ancestor.is_disk:
                    self._blivet.devicetree.recursive_remove(ancestor)
                else:
                    self._blivet.destroy_device(ancestor)

                ancestors.remove(ancestor)

            leaves = [a for a in ancestors if a.isleaf]


_BLIVET_VOLUME_TYPES = {
    "disk": BlivetDiskVolume,
    "lvm": BlivetLVMVolume,
    "partition": BlivetPartitionVolume,
    "raid": BlivetMDRaidVolume
}


def _get_blivet_volume(blivet_obj, volume, bpool=None):
    """ Return a BlivetVolume instance appropriate for the volume dict. """
    volume_type = volume.get('type', None)
    if volume_type is None:
        volume_type = bpool._pool['type'] if bpool else volume_defaults['type']
    if volume_type not in _BLIVET_VOLUME_TYPES:
        raise BlivetAnsibleError("Volume '%s' has unknown type '%s'" % (volume['name'], volume_type))

    volume['type'] = volume_type
    return _BLIVET_VOLUME_TYPES[volume_type](blivet_obj, volume, bpool=bpool)


class BlivetPool(BlivetBase):
    _type = "pool"

    def __init__(self, blivet_obj, pool):
        super(BlivetPool, self).__init__(blivet_obj, pool)
        self._disks = list()
        self._blivet_volumes = list()

    @property
    def _pool(self):
        return self._spec_dict

    @property
    def required_packages(self):
        packages = list()
        if self.ultimately_present and self.__class__.blivet_device_class is not None:
            packages.extend(self.__class__.blivet_device_class._packages)

        if self._pool.get('encryption'):
            packages.extend(get_format('luks').packages)
        return packages

    @property
    def ultimately_present(self):
        """ Should this pool be present when we are finished? """
        return self._pool.get('state', 'present') == 'present'

    @property
    def _is_raid(self):
        return self._pool.get('raid_level') not in [None, "null", ""]

    def _member_management_is_destructive(self):
        return False

    def _create(self):
        """ Schedule actions as needed to ensure the pool exists. """
        pass

    def _destroy(self):
        """ Schedule actions as needed to ensure the pool does not exist. """
        if self._device is None:
            return

        ancestors = self._device.ancestors  # ascending distance ordering
        log.debug("%s", [a.name for a in ancestors])
        self._blivet.devicetree.recursive_remove(self._device)
        ancestors.remove(self._device)
        leaves = [a for a in ancestors if a.isleaf]
        while leaves:
            for ancestor in leaves:
                log.info("scheduling destruction of %s", ancestor.name)
                if ancestor.is_disk:
                    self._blivet.devicetree.recursive_remove(ancestor)
                else:
                    self._blivet.destroy_device(ancestor)

                ancestors.remove(ancestor)

            leaves = [a for a in ancestors if a.isleaf]

        self._device = None

    def _type_check(self):  # pylint: disable=no-self-use
        return True

    def _look_up_disks(self):
        """ Look up the pool's disks in blivet's device tree. """
        if self._disks:
            return

        if not self._device and not self._pool['disks']:
            raise BlivetAnsibleError("no disks specified for pool '%s'" % self._pool['name'])
        elif not isinstance(self._pool['disks'], list):
            raise BlivetAnsibleError("pool disks must be specified as a list")

        disks = list()
        for spec in self._pool['disks']:
            device = self._blivet.devicetree.resolve_device(spec)
            if device is not None:  # XXX fail if any disk isn't resolved?
                disks.append(device)

        if self._pool['disks'] and not self._device and not disks:
            raise BlivetAnsibleError("unable to resolve any disks specified for pool '%s' (%s)" % (self._pool['name'], self._pool['disks']))

        self._disks = disks

    def _look_up_device(self):
        """ Look up the pool in blivet's device tree. """
        device = self._blivet.devicetree.resolve_device(self._pool['name'])
        if device is None:
            return

        self._device = device

        # check that the type is correct, raising an exception if there is a name conflict
        if not self._type_check():
            self._device = None
            return  # TODO: see if we can create this device w/ the specified name

        # Apply encryption keys as appropriate
        if any(d.encrypted for d in self._device.parents):
            passphrase = self._pool.get("encryption_passphrase")
            key_file = self._pool.get("encryption_key_file")
            for member in self._device.parents:
                if member.parents[0].format.type == "luks":
                    if passphrase:
                        member.parents[0].format.passphrase = passphrase
                        member.parents[0].original_format.passphrase = passphrase
                    if key_file:
                        member.parents[0].format.key_file = key_file
                        member.parents[0].original_format.key_file = key_file

    def _update_from_device(self, param_name):
        """ Return True if param_name's value was retrieved from a looked-up device. """
        # We wouldn't have the pool device if the member devices weren't unlocked, so we do not
        # have to consider the case where the devices are unlocked like we do for volumes.
        encrypted = bool(self._device.parents) and all("luks" in d.type for d in self._device.parents)
        raid = len(self._device.parents) == 1 and hasattr(self._device.parents[0].raw_device, 'level')
        log.debug("BlivetPool._update_from_device: %s", self._device)

        if param_name == 'disks':
            self._pool['disks'] = [d.name for d in self._device.disks]
        elif param_name == 'encryption':
            self._pool['encryption'] = encrypted
        elif param_name == 'encryption_key_size' and encrypted:
            self._pool['encryption_key_size'] = self._device.parents[0].parents[0].format.key_size
        elif param_name == 'encryption_key_file' and encrypted:
            self._pool['encryption_key_file'] = self._device.parents[0].parents[0].format.key_file
        elif param_name == 'encryption_cipher' and encrypted:
            self._pool['encryption_cipher'] = self._device.parents[0].parents[0].format.cipher
        elif param_name == 'encryption_luks_version' and encrypted:
            self._pool['encryption_luks_version'] = self._device.parents[0].parents[0].format.luks_version
        elif param_name == 'raid_level' and raid:
            self._pool['raid_level'] = self._device.parents[0].raw_device.level.name
        elif param_name == 'raid_chunk_size' and raid:
            self._pool['raid_chunk_size'] = str(self._device.parents[0].raw_device.chunk_size)
        elif param_name == 'raid_device_count' and raid:
            self._pool['raid_device_count'] = self._device.parents[0].raw_device.member_devices
        elif param_name == 'raid_spare_count' and raid:
            self._pool['raid_spare_count'] = self._device.parents[0].raw_device.spares
        elif param_name == 'raid_metadata_version' and raid:
            self._pool['raid_metadata_version'] = self._device.parents[0].raw_device.metadata_version
        else:
            return False

        return True

    def _apply_defaults(self):
        for name, default in pool_defaults.items():
            if name in self._pool and self._pool[name] not in [None, list(), dict()]:
                continue

            default = None if default in ('none', 'None', 'null') else default

            if self._device:
                if not self._update_from_device(name):
                    self._pool[name] = default
            else:
                if self._pool.get(name) is None:
                    self._pool[name] = default

    def _create_one_member(self, disk):
        if not disk.isleaf or disk.format.type is not None:
            if safe_mode and disk.format.name != get_format(None).name:
                raise BlivetAnsibleError(
                    "cannot remove existing formatting (%s) and/or devices on disk '%s' (pool '%s') in safe mode" %
                    (disk.format.type, disk.name, self._pool['name'])
                )
            else:
                self._blivet.devicetree.recursive_remove(disk)

        if use_partitions:
            label = get_format("disklabel", device=disk.path)
            self._blivet.format_device(disk, label)
            member = self._blivet.new_partition(parents=[disk], size=Size("256MiB"), grow=True)
            self._blivet.create_device(member)
        else:
            member = disk

        if self._is_raid:
            self._blivet.format_device(member, fmt=get_format("mdmember"))
        else:
            self._blivet.format_device(member, self._get_format())

        if use_partitions:
            try:
                do_partitioning(self._blivet)
            except Exception:
                raise BlivetAnsibleError("failed to allocate partitions for pool '%s'" % self._pool['name'])

        return member

    def _create_members(self):
        """ Schedule actions as needed to ensure pool member devices exist. """
        members = list()

        for disk in self._disks:
            member = self._create_one_member(disk)
            members.append(member)

        if self._is_raid:
            raid_name = "%s-1" % self._pool['name']

            raid_array = self._new_mdarray(members, raid_name=raid_name)

            self._blivet.create_device(raid_array)
            result = [raid_array]
        else:
            result = members

        return result

    def _get_volumes(self):
        """ Set up BlivetVolume instances for this pool's volumes. """
        for volume in self._pool.get('volumes', []):
            bvolume = _get_blivet_volume(self._blivet, volume, self)
            self._blivet_volumes.append(bvolume)

    def _manage_volumes(self):
        """ Schedule actions as needed to configure this pool's volumes. """
        self._get_volumes()
        for bvolume in self._blivet_volumes:
            bvolume.manage()

    def _manage_members(self):
        """ Schedule actions as needed to configure this pool's members. """

    def manage(self):
        """ Schedule actions to configure this pool according to the yaml input. """
        # look up the device
        self._look_up_device()
        self._apply_defaults()
        self._look_up_disks()

        # schedule destroy if appropriate, including member type change
        if not self.ultimately_present:
            self._manage_volumes()
            self._destroy()
            return
        elif self._member_management_is_destructive():
            if safe_mode:
                raise BlivetAnsibleError("cannot remove and recreate existing pool '%s' in safe mode" % self._pool['name'])
            else:
                self._destroy()

        # schedule create if appropriate
        self._create()

        if self._device:
            self._manage_members()

        self._manage_volumes()


class BlivetPartitionPool(BlivetPool):
    def _type_check(self):
        return self._device.partitionable

    def _look_up_device(self):
        self._look_up_disks()
        self._device = self._disks[0]

    def _create(self):
        if self._device.format.type != "disklabel" or \
           (disklabel_type and self._device.format.label_type != disklabel_type):
            if safe_mode:
                raise BlivetAnsibleError("cannot remove existing formatting and/or devices on disk '%s' "
                                         "(pool '%s') in safe mode" % (self._device.name, self._pool['name']))
            else:
                self._blivet.devicetree.recursive_remove(self._device, remove_device=False)

            label = get_format("disklabel", device=self._device.path, label_type=disklabel_type)
            self._blivet.format_device(self._device, label)


class BlivetLVMPool(BlivetPool):
    blivet_device_class = devices.LVMVolumeGroupDevice

    def _type_check(self):
        return self._device.type == "lvmvg"

    def _member_management_is_destructive(self):
        if self._device is None:
            return False

        if self._pool['encryption'] and not all(m.encrypted for m in self._device.parents):
            return True
        elif not self._pool['encryption'] and any(m.encrypted for m in self._device.parents):
            return True

        return False

    def _get_format(self):
        fmt = get_format("lvmpv")
        if not fmt.supported or not fmt.formattable:
            raise BlivetAnsibleError("required tools for managing LVM are missing")

        return fmt

    def _manage_encryption(self, members):
        managed_members = list()
        for member in members:
            managed_members.append(self._manage_one_encryption(member))

        return managed_members

    def _manage_thin_pools(self, pool_device):

        def str_to_size(spec, hundredpercent=None):
            # Convert given 'spec' string to Size. When input string can be in percent
            # (e.g. '50%'), use the optional parameter (type Size) as a reference
            if isinstance(spec, str) and ('%' in spec):
                try:
                    percentage = int(spec[:-1].strip())
                except ValueError:
                    raise BlivetAnsibleError("invalid percentage '%s' size specified in pool '%s'" % (spec, pool_device.name))

                size = Size(hundredpercent * (percentage / 100.0))
            else:
                try:
                    size = Size(spec)
                except Exception:
                    raise BlivetAnsibleError("invalid size specification '%s' in pool '%s'" % (spec, pool_device.name))

            return size

        existing_thinlvs_obj = [d for d in pool_device.children if d.is_thin_pool]

        existing_thinlvs = list()

        for thinlv_obj in existing_thinlvs_obj:
            name = thinlv_obj.name.split(self._pool['name'] + '-')[-1]
            size = thinlv_obj.size
            existing_thinlvs.append({'name': name, 'size': size})

        thinlvs_to_create = list()
        new_thinlvs_obj = list()

        # Calculate auto size of thin LVs as follows:
        # <available space for all autos> = <size of VG> - <20% of VG for thin metadata> - <all user given sizes>
        # <auto size> = <available space for all autos> / (<count of thinLVs> + <count of regular LVs>)
        auto_size_dev_count = 0
        reserved_space = Size(0)

        # Thin pool will take 20% of VG space as a safety spare. At least 1GiB, at most 100GiB
        thin_meta_space = DEFAULT_THPOOL_RESERVE.percent * (pool_device.size * 0.01)
        if thin_meta_space < DEFAULT_THPOOL_RESERVE.min:
            thin_meta_space = DEFAULT_THPOOL_RESERVE.min
        elif thin_meta_space > DEFAULT_THPOOL_RESERVE.max:
            thin_meta_space = DEFAULT_THPOOL_RESERVE.max

        available_space = pool_device.size - thin_meta_space

        for volume in self._pool.get('volumes'):
            if not volume['state']:
                continue

            if volume['thin']:
                thin_name = volume.get('thin_pool_name')
                thin_size = volume.get('thin_pool_size')
                if thin_size is not None:
                    thin_size = str_to_size(thin_size, available_space)

                if thin_name not in [t['name'] for t in thinlvs_to_create] + [d['name'] for d in existing_thinlvs]:
                    thinlvs_to_create.append({'name': thin_name, 'size': thin_size})

                if thin_size is None:
                    auto_size_dev_count += 1
                else:
                    reserved_space += thin_size
            else:
                # regular LV just take its size
                vol_size = volume.get('size')
                if vol_size is None:
                    auto_size_dev_count += 1
                else:
                    reserved_space += str_to_size(vol_size, pool_device.size)

        if auto_size_dev_count > 0:
            calculated_thinlv_size = available_space / auto_size_dev_count

        for thinlv in thinlvs_to_create:

            if thinlv['size'] is None:
                tlv_size = Size(calculated_thinlv_size)
            else:
                tlv_size = thinlv['size']

            thinlv_params = dict(thin_pool=True, size=tlv_size, parents=[pool_device])

            if thinlv['name'] is not None:
                thinlv_params.update(dict(name=thinlv['name']))

            try:
                new_thinlv_obj = self._blivet.new_lv(**thinlv_params)
            except Exception as e:
                raise BlivetAnsibleError("failed to set up thin pool '%s': %s" % (self._pool['name'], str(e)))
            self._blivet.create_device(new_thinlv_obj)
            new_thinlvs_obj.append(new_thinlv_obj)

        return existing_thinlvs_obj + new_thinlvs_obj

    def _manage_members(self):
        """ Schedule actions as needed to configure this pool's members. """
        if not self._device:
            return

        add_disks = [d for d in self._disks if d not in self._device.ancestors]
        remove_disks = [pv for pv in self._device.pvs if not any(d in pv.ancestors for d in self._disks)]

        if not (add_disks or remove_disks):
            return

        if remove_disks and safe_mode:
            raise BlivetAnsibleError("cannot remove members '%s' from pool '%s' in safe mode" %
                                     (", ".join(d.name for d in remove_disks),
                                      self._device.name))

        if self._is_raid:
            raise BlivetAnsibleError("managing pool members is not supported with RAID")

        for disk in add_disks:
            member = self._create_one_member(disk)
            member = self._manage_one_encryption(member)

            try:
                ac = ActionAddMember(self._device, member)
                self._blivet.devicetree.actions.add(ac)
            except Exception as e:
                raise BlivetAnsibleError("failed to add disk '%s' to pool '%s': %s" % (disk.name,
                                                                                       self._pool['name'],
                                                                                       str(e)))

        for disk in remove_disks:
            if self._device.free_space < disk.size:
                raise BlivetAnsibleError("disk '%s' cannot be removed from pool '%s'" % (disk.name,
                                                                                         self._pool['name']))

            try:
                ac = ActionRemoveMember(self._device, disk)
                # XXX: scheduling ActionRemoveMember is currently broken, we need to execute
                # the action now manually, see https://bugzilla.redhat.com/show_bug.cgi?id=2076956
                # self._blivet.devicetree.actions.add(ac)
                ac.apply()
                ac.execute()
            except Exception as e:
                raise BlivetAnsibleError("failed to remove disk '%s' from pool '%s': %s" % (disk.name,
                                                                                            self._pool['name'],
                                                                                            str(e)))
            # XXX workaround for https://github.com/storaged-project/blivet/pull/1040
            disk.format.vg_name = None

            self._blivet.devicetree.recursive_remove(disk.raw_device)

    def _create(self):
        if not self._device:
            members = self._manage_encryption(self._create_members())
            try:
                pool_device = self._blivet.new_vg(name=self._pool['name'], parents=members)
            except Exception as e:
                raise BlivetAnsibleError("failed to set up pool '%s': %s" % (self._pool['name'], str(e)))

            self._blivet.create_device(pool_device)
            self._device = pool_device

        self._thinpools = self._manage_thin_pools(self._device)

    def _look_up_device(self):
        self._thinpools = list()
        super(BlivetLVMPool, self)._look_up_device()
        if self._device:
            self._thinpools = [d for d in self._device.children if d.type == 'lvmthinpool']


_BLIVET_POOL_TYPES = {
    "partition": BlivetPartitionPool,
    "lvm": BlivetLVMPool
}


def _get_blivet_pool(blivet_obj, pool):
    """ Return an appropriate BlivetPool instance for the pool dict. """
    if 'type' not in pool or pool['type'] is None:
        pool['type'] = pool_defaults['type']

    if pool['type'] not in _BLIVET_POOL_TYPES:
        raise BlivetAnsibleError("Pool '%s' has unknown type '%s'" % (pool['name'], pool['type']))

    return _BLIVET_POOL_TYPES[pool['type']](blivet_obj, pool)


def manage_volume(b, volume):
    """ Schedule actions as needed to manage a single standalone volume. """
    bvolume = _get_blivet_volume(b, volume)
    bvolume.manage()
    volume['_device'] = bvolume._volume.get('_device', '')
    volume['_raw_device'] = bvolume._volume.get('_raw_device', '')
    volume['_mount_id'] = bvolume._volume.get('_mount_id', '')


def manage_pool(b, pool):
    """ Schedule actions as needed to manage a single pool and its volumes. """
    bpool = _get_blivet_pool(b, pool)
    bpool.manage()
    for (volume, bvolume) in zip(pool['volumes'], bpool._blivet_volumes):
        volume['_device'] = bvolume._volume.get('_device', '')
        volume['_raw_device'] = bvolume._volume.get('_raw_device', '')
        volume['_mount_id'] = bvolume._volume.get('_mount_id', '')


class FSTab(object):
    def __init__(self, blivet_obj):
        self._blivet = blivet_obj
        self._entries = list()
        self.parse()

    def lookup(self, key, value):
        return next((e for e in self._entries if e.get(key) == value), None)

    def reset(self):
        self._entries = list()

    def parse(self):
        if self._entries:
            self.reset()

        with open('/etc/fstab') as f:
            for line in f.readlines():
                if line.lstrip().startswith("#"):
                    continue

                fields = line.split()
                if len(fields) < 6:
                    continue

                device = self._blivet.devicetree.resolve_device(fields[0])
                self._entries.append(dict(device_id=fields[0],
                                          device_path=getattr(device, 'path', None),
                                          fs_type=fields[2],
                                          mount_point=fields[1],
                                          mount_options=fields[3]))


def get_mount_info(pools, volumes, actions, fstab):
    """ Return a list of argument dicts to pass to the mount module to manage mounts.

        The overall approach is to remove existing mounts associated with file systems
        we are removing and those with changed mount points, re-adding them with the
        new mount point later.

        Removed mounts go directly into the mount_info list, which is the return value,
        while added/active mounts to a list that gets appended to the mount_info list
        at the end to ensure that removals happen first.
    """
    mount_info = list()
    mount_vols = list()

    # account for mounts removed by removing or reformatting volumes
    if actions:
        for action in actions:
            if action.is_destroy and action.is_format and action.format.type is not None:
                mount = fstab.lookup('device_path', action.device.path)
                if mount is not None:
                    mount_info.append({"src": mount['device_id'], "path": mount['mount_point'],
                                       'state': 'absent', 'fstype': mount['fs_type']})

    def handle_new_mount(volume, fstab):
        replace = None
        mounted = False

        mount = fstab.lookup('device_path', volume['_device'])
        if (volume['mount_point'] and volume['mount_point'].startswith('/')) \
           or volume['fs_type'] == 'swap':
            mounted = True

        # handle removal of existing mounts of this volume
        if mount and mount['fs_type'] != 'swap' and mount['mount_point'] != volume['mount_point']:
            replace = dict(path=mount['mount_point'], state="absent")
        elif mount and mount['fs_type'] == 'swap':
            replace = dict(src=mount['device_id'], fstype="swap", path="none", state="absent")

        return mounted, replace

    # account for mounts that we set up or are replacing in pools
    for pool in pools:
        for volume in pool['volumes']:
            if pool['state'] == 'present' and volume['state'] == 'present':
                mounted, replace = handle_new_mount(volume, fstab)
                if replace:
                    mount_info.append(replace)
                if mounted:
                    mount_vols.append(volume)

    # account for mounts that we set up or are replacing in standalone volumes
    for volume in volumes:
        if volume['state'] == 'present':
            mounted, replace = handle_new_mount(volume, fstab)
            if replace:
                mount_info.append(replace)
            if mounted:
                mount_vols.append(volume)

    for volume in mount_vols:
        mount_info.append({'src': volume['_mount_id'],
                           'path': volume['mount_point'] if volume['fs_type'] != "swap" else "none",
                           'fstype': volume['fs_type'],
                           'opts': volume['mount_options'],
                           'dump': volume['mount_check'],
                           'passno': volume['mount_passno'],
                           'state': 'mounted' if volume['fs_type'] != "swap" else "present"})

    return mount_info


def get_crypt_info(actions):
    info = list()
    for action in actions:
        if not (action.is_format and action.format.type == 'luks'):
            continue

        info.append(dict(backing_device=action.device.path,
                         name=action.format.map_name,
                         password=action.format.key_file or '-',
                         state='present' if action.is_create else 'absent'))

    return sorted(info, key=lambda e: e['state'])


def get_required_packages(b, pools, volumes):
    packages = list()
    for pool in pools:
        bpool = _get_blivet_pool(b, pool)
        packages.extend(bpool.required_packages)
        bpool._get_volumes()
        for bvolume in bpool._blivet_volumes:
            packages.extend(bvolume.required_packages)

    for volume in volumes:
        bvolume = _get_blivet_volume(b, volume)
        packages.extend(bvolume.required_packages)

    return sorted(list(set(packages)))


def update_fstab_identifiers(b, pools, volumes):
    """ Update fstab device identifiers.

        This is to pick up new UUIDs for newly-formatted devices.
    """
    all_volumes = volumes[:]
    for pool in pools:
        if not pool['state'] == 'present':
            continue

        all_volumes += pool['volumes']

    for volume in all_volumes:
        if volume['state'] == 'present':
            device = b.devicetree.resolve_device(volume['_mount_id'])
            if device is None and volume['encryption']:
                device = b.devicetree.resolve_device(volume['_raw_device'])
                if device is not None and not device.isleaf:
                    device = device.children[0]
                    volume['_device'] = device.path

            if device is None:
                raise BlivetAnsibleError("failed to look up device for volume %s (%s/%s)" % (volume['name'], volume['_device'], volume['_mount_id']))
            volume['_mount_id'] = device.fstab_spec
            if device.format.type == 'swap':
                device.format.setup()

            if device.status:
                volume['_kernel_device'] = os.path.realpath(device.path)
            if device.raw_device.status:
                volume['_raw_kernel_device'] = os.path.realpath(device.raw_device.path)


def activate_swaps(b, pools, volumes):
    """ Activate all swaps specified as present. """
    all_volumes = volumes[:]
    for pool in pools:
        if not pool['state'] == 'present':
            continue

        all_volumes += pool['volumes']

    for volume in all_volumes:
        if volume['state'] == 'present':
            device = b.devicetree.resolve_device(volume['_mount_id'])
            if device.format.type == 'swap':
                device.format.setup()


def run_module():
    # available arguments/parameters that a user can pass
    common_volume_opts = dict(encryption=dict(type='bool'),
                              encryption_cipher=dict(type='str'),
                              encryption_key=dict(type='str'),
                              encryption_key_size=dict(type='int'),
                              encryption_luks_version=dict(type='str'),
                              encryption_password=dict(type='str'),
                              fs_create_options=dict(type='str'),
                              fs_label=dict(type='str', default=''),
                              fs_type=dict(type='str'),
                              mount_options=dict(type='str'),
                              mount_point=dict(type='str'),
                              name=dict(type='str'),
                              raid_level=dict(type='str'),
                              size=dict(type='str'),
                              state=dict(type='str', default='present', choices=['present', 'absent']),
                              type=dict(type='str'))
    volume_opts = copy.deepcopy(common_volume_opts)
    volume_opts.update(
        dict(disks=dict(type='list'),
             raid_device_count=dict(type='int'),
             raid_spare_count=dict(type='int'),
             raid_metadata_version=dict(type='str')))
    pool_volume_opts = copy.deepcopy(common_volume_opts)
    pool_volume_opts.update(
        dict(cached=dict(type='bool'),
             cache_devices=dict(type='list', elements='str', default=list()),
             cache_mode=dict(type='str'),
             cache_size=dict(type='str'),
             compression=dict(type='bool'),
             deduplication=dict(type='bool'),
             raid_disks=dict(type='list', elements='str', default=list()),
             thin_pool_name=dict(type='str'),
             thin_pool_size=dict(type='str'),
             thin=dict(type='bool', default=False),
             vdo_pool_size=dict(type='str')))

    module_args = dict(
        pools=dict(type='list', elements='dict',
                   options=dict(disks=dict(type='list', elements='str', default=list()),
                                encryption=dict(type='bool'),
                                encryption_cipher=dict(type='str'),
                                encryption_key=dict(type='str'),
                                encryption_key_size=dict(type='int'),
                                encryption_luks_version=dict(type='str'),
                                encryption_password=dict(type='str'),
                                name=dict(type='str'),
                                raid_level=dict(type='str'),
                                raid_device_count=dict(type='int'),
                                raid_spare_count=dict(type='int'),
                                raid_metadata_version=dict(type='str'),
                                state=dict(type='str', default='present', choices=['present', 'absent']),
                                type=dict(type='str'),
                                volumes=dict(type='list', elements='dict', default=list(),
                                             options=pool_volume_opts))),
        volumes=dict(type='list', elements='dict',
                     options=volume_opts),
        packages_only=dict(type='bool', required=False, default=False),
        disklabel_type=dict(type='str', required=False, default=None),
        safe_mode=dict(type='bool', required=False, default=True),
        pool_defaults=dict(type='dict', required=False),
        volume_defaults=dict(type='dict', required=False),
        use_partitions=dict(type='bool', required=False),
        diskvolume_mkfs_option_map=dict(type='dict', required=False, default={}))

    # seed the result dict in the object
    result = dict(
        changed=False,
        actions=list(),
        leaves=list(),
        mounts=list(),
        crypts=list(),
        pools=list(),
        volumes=list(),
        packages=list(),
    )

    module = AnsibleModule(argument_spec=module_args,
                           supports_check_mode=True)

    errors, updated_params = validate_parameters(module_args, module.params)
    if errors:
        module.fail_json(msg="Parameter check failed: %s" % errors)

    module.params.update(updated_params)

    if not BLIVET_PACKAGE:
        module.fail_json(msg="Failed to import the blivet or blivet3 Python modules",
                         exception=inspect.cleandoc("""
                         blivet3 exception:
                         {}
                         blivet exception:
                         {}""").format(LIB_IMP_ERR3, LIB_IMP_ERR))

    if not module.params['pools'] and not module.params['volumes']:
        module.exit_json(**result)

    global disklabel_type
    disklabel_type = module.params['disklabel_type']

    global use_partitions
    use_partitions = module.params['use_partitions']

    global safe_mode
    safe_mode = module.params['safe_mode']

    global diskvolume_mkfs_option_map
    diskvolume_mkfs_option_map = module.params['diskvolume_mkfs_option_map']

    global pool_defaults
    if 'pool_defaults' in module.params:
        pool_defaults = module.params['pool_defaults']

    global volume_defaults
    if 'volume_defaults' in module.params:
        volume_defaults = module.params['volume_defaults']

    b = Blivet()
    b.reset()
    fstab = FSTab(b)
    actions = list()

    if module.params['packages_only']:
        try:
            result['packages'] = get_required_packages(b, module.params['pools'], module.params['volumes'])
        except BlivetAnsibleError as e:
            module.fail_json(msg=str(e), **result)
        module.exit_json(**result)

    def record_action(action):
        if action.is_format and action.format.type is None:
            return

        actions.append(action)

    def ensure_udev_update(action):
        if action.is_create or action.is_configure:
            sys_path = action.device.path
            if os.path.islink(sys_path):
                sys_path = os.readlink(action.device.path)
            trigger(action='change', subsystem='block', name=os.path.basename(sys_path))

    def action_dict(action):
        return dict(action=action.type_desc_str,
                    fs_type=action.format.type if action.is_format else None,
                    device=action.device.path)

    duplicates = find_duplicate_names(module.params['pools'])
    if duplicates:
        module.fail_json(msg="multiple pools with the same name: {0}".format(",".join(duplicates)),
                         **result)
    for pool in module.params['pools']:
        duplicates = find_duplicate_names(pool.get('volumes', list()))
        if duplicates:
            module.fail_json(msg="multiple volumes in pool '{0}' with the "
                                 "same name: {1}".format(pool['name'], ",".join(duplicates)),
                             **result)
        try:
            manage_pool(b, pool)
        except BlivetAnsibleError as e:
            module.fail_json(msg=str(e), **result)

    duplicates = find_duplicate_names(module.params['volumes'])
    if duplicates:
        module.fail_json(msg="multiple volumes with the same name: {0}".format(",".join(duplicates)),
                         **result)
    for volume in module.params['volumes']:
        try:
            manage_volume(b, volume)
        except BlivetAnsibleError as e:
            module.fail_json(msg=str(e), **result)

    scheduled = b.devicetree.actions.find()
    result['packages'] = b.packages[:]

    for action in scheduled:
        if (action.is_destroy or action.is_resize) and action.is_format and action.format.exists and \
           (action.format.mountable or action.format.type == "swap"):
            action.format.teardown()

    if scheduled:
        # execute the scheduled actions, committing changes to disk
        callbacks.action_executed.add(record_action)
        callbacks.action_executed.add(ensure_udev_update)
        try:
            b.devicetree.actions.process(devices=b.devicetree.devices, dry_run=module.check_mode)
        except Exception as e:
            module.fail_json(msg="Failed to commit changes to disk: %s" % str(e), **result)
        finally:
            result['changed'] = True
            result['actions'] = [action_dict(a) for a in actions]

    update_fstab_identifiers(b, module.params['pools'], module.params['volumes'])
    activate_swaps(b, module.params['pools'], module.params['volumes'])

    result['mounts'] = get_mount_info(module.params['pools'], module.params['volumes'], actions, fstab)
    result['crypts'] = get_crypt_info(actions)
    result['leaves'] = [d.path for d in b.devicetree.leaves]
    result['pools'] = module.params['pools']
    result['volumes'] = module.params['volumes']

    # success - return result
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
