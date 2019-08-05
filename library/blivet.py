#!/usr/bin/python

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
            - disklabel type string (eg: 'gpt') to use, overriding the built-in logic in blivet

author:
    - David Lehman (dlehman@redhat.com)
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
    type: list of dict
leaves:
    description: list of paths to leaf devices
    type: list of str
mounts:
    description: list of dicts describing mounts to set up
    type: list of dict
pools:
    description: list of dicts describing the pools w/ device path for each volume
    type: list of dict
volumes:
    description: list of dicts describing the volumes w/ device path for each
    type: list of dict
'''

import logging
import traceback

BLIVET_PACKAGE = None

try:
    from blivet3 import Blivet
    from blivet3.callbacks import callbacks
    from blivet3.flags import flags as blivet_flags
    from blivet3.formats import get_format
    from blivet3.partitioning import do_partitioning
    from blivet3.size import Size
    from blivet3.util import set_up_logging
    BLIVET_PACKAGE = 'blivet3'
except ImportError:
    try:
        from blivet import Blivet
        from blivet.callbacks import callbacks
        from blivet.flags import flags as blivet_flags
        from blivet.formats import get_format
        from blivet.partitioning import do_partitioning
        from blivet.size import Size
        from blivet.util import set_up_logging
        BLIVET_PACKAGE = 'blivet'
    except ImportError:
        LIB_IMP_ERR = traceback.format_exc()

from ansible.module_utils.basic import AnsibleModule, missing_required_lib

if BLIVET_PACKAGE:
    blivet_flags.debug = True
    set_up_logging()
    log = logging.getLogger(BLIVET_PACKAGE + ".ansible")

use_partitions = None  # create partitions on pool backing device disks?
disklabel_type = None  # user-specified disklabel type


class BlivetAnsibleError(Exception):
    pass


class BlivetVolume:
    def __init__(self, blivet_obj, volume, bpool=None):
        self._blivet = blivet_obj
        self._volume = volume
        self._blivet_pool = bpool
        self._device = None

    @property
    def ultimately_present(self):
        """ Should this volume be present when we are finished? """
        return (self._volume['state'] == 'present' and
                (self._blivet_pool is None or self._blivet_pool.ultimately_present))

    def _type_check(self):  # pylint: disable=no-self-use
        """ Is self._device of the correct type? """
        return True

    def _get_device_id(self):
        """ Return an identifier by which to try looking the volume up. """
        return self._volume['name']

    def _look_up_device(self):
        """ Try to look up this volume in blivet's device tree. """
        device = self._blivet.devicetree.resolve_device(self._get_device_id())
        if device is None:
            return

        self._device = device

        # check that the type is correct, raising an exception if there is a name conflict
        if not self._type_check():
            self._device = None
            return  # TODO: see if we can create this device w/ the specified name

    def _get_format(self):
        """ Return a blivet.formats.DeviceFormat instance for this volume. """
        fmt = get_format(self._volume['fs_type'],
                         mountpoint=self._volume.get('mount_point'),
                         label=self._volume['fs_label'],
                         options=self._volume['fs_create_options'])
        if not fmt.supported or not fmt.formattable:
            # FAIL: fs type tools are not available
            raise BlivetAnsibleError("required tools for file system '%s' are missing" % self._volume['fs_type'])

        return fmt

    def _create(self):
        """ Schedule actions as needed to ensure the volume exists. """
        pass

    def _destroy(self):
        """ Schedule actions as needed to ensure the volume does not exist. """
        if self._device is None:
            return

        # save device identifiers for use by the role
        self._volume['_device'] = self._device.path
        self._volume['_mount_id'] = self._device.fstab_spec

        # schedule removal of this device and any descendant devices
        self._blivet.devicetree.recursive_remove(self._device)

    def _resize(self):
        """ Schedule actions as needed to ensure the device has the desired size. """
        try:
            size = Size(self._volume['size'])
        except Exception:
            # FAIL: invalid size specification
            raise BlivetAnsibleError("invalid size specification for volume '%s': '%s'" % (self._volume['name'], self._volume['size']))

        if size and self._device.resizable and self._device.size != size:
            if self._device.format.resizable:
                self._device.format.update_size_info()

            if not self._device.min_size <= size <= self._device.max_size:
                # FAIL: resize to specified size not possible
                raise BlivetAnsibleError("volume '%s' cannot be resized to '%s'" % (self._volume['name'], size))

            try:
                self._blivet.resize_device(self._device, size)
            except ValueError as e:
                # FAIL: resize not possible
                raise BlivetAnsibleError("volume '%s' cannot be resized from %s to %s: %s" % (self._device.name,
                                                                                              self._device.size,
                                                                                              size, str(e)))

    def _reformat(self):
        """ Schedule actions as needed to ensure the volume is formatted as specified. """
        fmt = self._get_format()
        if self._device.format.type == fmt.type:
            return

        if self._device.format.status:
            self._device.format.teardown()
        self._blivet.format_device(self._device, fmt)

    def manage(self):
        """ Schedule actions to configure this volume according to the yaml input. """
        # look up the device
        self._look_up_device()

        # schedule destroy if appropriate
        if not self.ultimately_present:
            self._destroy()
            return

        # schedule create if appropriate
        self._create()

        # at this point we should have a blivet.devices.StorageDevice instance
        if self._device is None:
            raise BlivetAnsibleError("failed to look up or create device '%s'" % self._volume['name'])

        # schedule reformat if appropriate
        if self._device.exists:
            self._reformat()

        # schedule resize if appropriate
        if self._device.exists and self._volume['size']:
            self._resize()

        # save device identifiers for use by the role
        self._volume['_device'] = self._device.path
        self._volume['_mount_id'] = self._device.fstab_spec


class BlivetDiskVolume(BlivetVolume):
    def _get_device_id(self):
        return self._volume['disks'][0]

    def _type_check(self):
        return self._device.is_disk


class BlivetPartitionVolume(BlivetVolume):
    def _type_check(self):
        return self._device.type == 'partition'

    def _get_device_id(self):
        return self._blivet_pool._disks[0].name + '1'

    def _create(self):
        if self._device:
            return

        if self._blivet_pool:
            parent = self._blivet_pool._device
        else:
            parent = self._blivet.devicetree.resolve_device(self._volume['pool'])

        if parent is None:
            # FAIL: failed to find pool
            raise BlivetAnsibleError("failed to find pool '%s' for volume '%s'" % (self._blivet_pool['name'], self._volume['name']))

        size = Size("256 MiB")
        try:
            device = self._blivet.new_partition(parents=[parent], size=size, grow=True, fmt=self._get_format())
        except Exception:
            # FAIL: failed to instantiate volume device
            raise BlivetAnsibleError("failed set up volume '%s'" % self._volume['name'])

        self._blivet.create_device(device)
        try:
            do_partitioning(self._blivet)
        except Exception:
            # FAIL: partition allocation failed: not enough space?
            raise BlivetAnsibleError("partition allocation failed for volume '%s'" % self._volume['name'])

        self._device = device


class BlivetLVMVolume(BlivetVolume):
    def _get_device_id(self):
        return "%s-%s" % (self._blivet_pool._device.name, self._volume['name'])

    def _create(self):
        if self._device:
            return

        parent = self._blivet_pool._device
        if parent is None:
            # FAIL: failed to find pool
            raise BlivetAnsibleError("failed to find pool '%s' for volume '%s'" % (self._blivet_pool['name'], self._volume['name']))

        try:
            size = Size(self._volume['size'])
        except Exception:
            # FAIL: invalid size specification
            raise BlivetAnsibleError("invalid size '%s' specified for volume '%s'" % (self._volume['size'], self._volume['name']))

        fmt = self._get_format()
        if size > parent.free_space:
            # FAIL: volume size greater than pool free space
            raise BlivetAnsibleError("specified size for volume '%s' exceeds available space in pool '%s' (%s)" % (size,
                                                                                                                   parent.name,
                                                                                                                   parent.free_space))

        try:
            device = self._blivet.new_lv(name=self._volume['name'],
                                         parents=[parent], size=size, fmt=fmt)
        except Exception:
            # FAIL: failed to create volume
            raise BlivetAnsibleError("failed to set up volume '%s'" % self._volume['name'])

        self._blivet.create_device(device)
        self._device = device


_BLIVET_VOLUME_TYPES = {
    "disk": BlivetDiskVolume,
    "lvm": BlivetLVMVolume,
    "partition": BlivetPartitionVolume
}


def _get_blivet_volume(blivet_obj, volume, bpool=None):
    """ Return a BlivetVolume instance appropriate for the volume dict. """
    volume_type = volume.get('type', bpool._pool['type'] if bpool else None)
    if volume_type not in _BLIVET_VOLUME_TYPES:
        raise BlivetAnsibleError("Volume '%s' has unknown type '%s'" % (volume['name'], volume_type))

    return _BLIVET_VOLUME_TYPES[volume_type](blivet_obj, volume, bpool=bpool)


class BlivetPool:
    def __init__(self, blivet_obj, pool):
        self._blivet = blivet_obj
        self._pool = pool
        self._device = None
        self._disks = list()
        self._blivet_volumes = list()

    @property
    def ultimately_present(self):
        """ Should this pool be present when we are finished? """
        return self._pool['state'] == 'present'

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

    def _type_check(self):  # pylint: disable=no-self-use
        return True

    def _look_up_disks(self):
        """ Look up the pool's disks in blivet's device tree. """
        if not self._pool['disks']:
            # FAIL: no disks specified for pool
            raise BlivetAnsibleError("no disks specified for pool '%s'" % self._pool['name'])  # sure about this one?
        elif not isinstance(self._pool['disks'], list):
            raise BlivetAnsibleError("pool disks must be specified as a list")

        disks = list()
        for spec in self._pool['disks']:
            device = self._blivet.devicetree.resolve_device(spec)
            if device is not None:  # XXX fail if any disk isn't resolved?
                disks.append(device)

        if self._pool['disks'] and not disks:
            # FAIL: failed to find any disks
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

    def _get_format(self):
        raise NotImplementedError()

    def _create_members(self):
        """ Schedule actions as needed to ensure pool member devices exist. """
        members = list()
        for disk in self._disks:
            if not disk.isleaf:
                self._blivet.devicetree.recursive_remove(disk)

            if use_partitions:
                label = get_format("disklabel", device=disk.path)
                self._blivet.format_device(disk, label)
                member = self._blivet.new_partition(parents=[disk], size=Size("256MiB"), grow=True)
                self._blivet.create_device(member)
            else:
                member = disk

            self._blivet.format_device(member, self._get_format())
            members.append(member)

        if use_partitions:
            try:
                do_partitioning(self._blivet)
            except Exception:
                # FAIL: problem allocating partitions for pool backing devices
                raise BlivetAnsibleError("failed to allocation partitions for pool '%s'" % self._pool['name'])

        return members

    def _get_volumes(self):
        """ Set up BlivetVolume instances for this pool's volumes. """
        for volume in self._pool['volumes']:
            bvolume = _get_blivet_volume(self._blivet, volume, self)
            self._blivet_volumes.append(bvolume)

    def _manage_volumes(self):
        """ Schedule actions as needed to configure this pool's volumes. """
        self._get_volumes()
        for bvolume in self._blivet_volumes:
            bvolume.manage()

    def manage(self):
        """ Schedule actions to configure this pool according to the yaml input. """
        # look up the device
        self._look_up_disks()
        self._look_up_device()

        # schedule destroy if appropriate, including member type change
        if not self.ultimately_present:  # TODO: member type changes
            self._manage_volumes()
            self._destroy()
            return

        # schedule create if appropriate
        self._create()
        self._manage_volumes()


class BlivetPartitionPool(BlivetPool):
    def _type_check(self):
        return self._device.partitionable

    def _look_up_device(self):
        self._device = self._disks[0]

    def _create(self):
        if self._device.format.type != "disklabel" or \
           self._device.format.label_type != disklabel_type:
            self._blivet.devicetree.recursive_remove(self._device, remove_device=False)

            label = get_format("disklabel", device=self._device.path, label_type=disklabel_type)
            self._blivet.format_device(self._device, label)


class BlivetLVMPool(BlivetPool):
    def _type_check(self):
        return self._device.type == "lvmvg"

    def _get_format(self):
        fmt = get_format("lvmpv")
        if not fmt.supported or not fmt.formattable:
            # FAIL: lvm tools are not available
            raise BlivetAnsibleError("required tools for managing LVM are missing")

        return fmt

    def _create(self):
        if self._device:
            return

        members = self._create_members()
        try:
            pool_device = self._blivet.new_vg(name=self._pool['name'], parents=members)
        except Exception:
            # FAIL: failed to instantiate pool device
            raise BlivetAnsibleError("failed to set up pool '%s'" % self._pool['name'])

        self._blivet.create_device(pool_device)
        self._device = pool_device


_BLIVET_POOL_TYPES = {
    "disk": BlivetPartitionPool,
    "lvm": BlivetLVMPool
}


def _get_blivet_pool(blivet_obj, pool):
    """ Return an appropriate BlivetPool instance for the pool dict. """
    if pool['type'] not in _BLIVET_POOL_TYPES:
        raise BlivetAnsibleError("Pool '%s' has unknown type '%s'" % (pool['name'], pool['type']))

    return _BLIVET_POOL_TYPES[pool['type']](blivet_obj, pool)


def manage_volume(b, volume):
    """ Schedule actions as needed to manage a single standalone volume. """
    bvolume = _get_blivet_volume(b, volume)
    bvolume.manage()
    volume['_device'] = bvolume._volume.get('_device', '')
    volume['_mount_id'] = bvolume._volume.get('_mount_id', '')


def manage_pool(b, pool):
    """ Schedule actions as needed to manage a single pool and its volumes. """
    bpool = _get_blivet_pool(b, pool)
    bpool.manage()
    for (volume, bvolume) in zip(pool['volumes'], bpool._blivet_volumes):
        volume['_device'] = bvolume._volume.get('_device', '')
        volume['_mount_id'] = bvolume._volume.get('_mount_id', '')


class FSTab:
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

        for line in open('/etc/fstab').readlines():
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
                    mount_info.append({"path": mount['mount_point'], 'state': 'absent'})

    def handle_new_mount(volume, fstab):
        replace = None
        mounted = False

        mount = fstab.lookup('device_path', volume['_device'])
        if volume['mount_point']:
            mounted = True

        # handle removal of existing mounts of this volume
        if mount and mount['mount_point'] != volume['mount_point']:
            replace = mount['mount_point']

        return mounted, replace

    # account for mounts that we set up or are replacing in pools
    for pool in pools:
        for volume in pool['volumes']:
            if pool['state'] == 'present' and volume['state'] == 'present':
                mounted, replace = handle_new_mount(volume, fstab)
                if replace:
                    mount_info.append({"path": replace, 'state': 'absent'})
                if mounted:
                    mount_vols.append(volume)

    # account for mounts that we set up or are replacing in standalone volumes
    for volume in volumes:
        if volume['state'] == 'present':
            mounted, replace = handle_new_mount(volume, fstab)
            if replace:
                mount_info.append({"path": replace, 'state': 'absent'})
            if mounted:
                mount_vols.append(volume)

    for volume in mount_vols:
        mount_info.append({'src': volume['_mount_id'],
                           'path': volume['mount_point'],
                           'fstype': volume['fs_type'],
                           'opts': volume['mount_options'],
                           'dump': volume['mount_check'],
                           'passno': volume['mount_passno'],
                           'state': 'mounted'})

    return mount_info


def run_module():
    # available arguments/parameters that a user can pass
    module_args = dict(
        pools=dict(type='list'),
        volumes=dict(type='list'),
        packages_only=dict(type='bool', required=False, default=False),
        disklabel_type=dict(type='str', required=False, default=None),
        use_partitions=dict(type='bool', required=False, default=True))

    # seed the result dict in the object
    result = dict(
        changed=False,
        actions=list(),
        leaves=list(),
        mounts=list(),
        pools=list(),
        volumes=list(),
        packages=list(),
    )

    module = AnsibleModule(argument_spec=module_args,
                           supports_check_mode=True)
    if not BLIVET_PACKAGE:
        module.fail_json(msg=missing_required_lib("blivet"),
                         exception=LIB_IMP_ERR)

    if not module.params['pools'] and not module.params['volumes']:
        module.exit_json(**result)

    global disklabel_type
    disklabel_type = module.params['disklabel_type']

    global use_partitions
    use_partitions = module.params['use_partitions']

    b = Blivet()
    b.reset()
    fstab = FSTab(b)
    actions = list()

    def record_action(action):
        if action.is_format and action.format.type is None:
            return

        actions.append(action)

    def action_dict(action):
        return dict(action=action.type_desc_str,
                    fs_type=action.format.type if action.is_format else None,
                    device=action.device.path)

    for pool in module.params['pools']:
        try:
            manage_pool(b, pool)
        except BlivetAnsibleError as e:
            module.fail_json(msg=str(e), **result)

    for volume in module.params['volumes']:
        try:
            manage_volume(b, volume)
        except BlivetAnsibleError as e:
            module.fail_json(msg=str(e), **result)

    scheduled = b.devicetree.actions.find()
    result['packages'] = b.packages[:]

    if module.params['packages_only']:
        module.exit_json(**result)

    for action in scheduled:
        if action.is_destroy and action.is_format and action.format.exists:
            action.format.teardown()

    if scheduled:
        ## execute the scheduled actions, committing changes to disk
        callbacks.action_executed.add(record_action)
        try:
            b.devicetree.actions.process(devices=b.devicetree.devices, dry_run=module.check_mode)
        except Exception:
            module.fail_json(msg="Failed to commit changes to disk", **result)
        finally:
            result['changed'] = True
            result['actions'] = [action_dict(a) for a in actions]

    result['mounts'] = get_mount_info(module.params['pools'], module.params['volumes'], actions, fstab)
    result['leaves'] = [d.path for d in b.devicetree.leaves]
    result['pools'] = module.params['pools']
    result['volumes'] = module.params['volumes']

    # success - return result
    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()
