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
    - "Module ___"

options:
    pools:
        description:
            - list of dicts describing pools
    volumes:
        description:
            - list of dicts describing volumes

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
    description: list of strings describing actions taken
    type: list of str
leaves:
    description: list of paths to leaf devices
    type: list of str
mounts:
    description: list of dicts describing mounts to set up
    type: list of dict
removed_mounts:
    description: list of mount points of removed mounts
    type: list of str
'''

from blivet import Blivet
from blivet.callbacks import callbacks
from blivet.flags import flags as blivet_flags
from blivet.formats import get_format
from blivet.size import Size
from blivet.util import set_up_logging

from ansible.module_utils.basic import AnsibleModule
#from ansible.module_utils.size import Size

blivet_flags.debug = True
set_up_logging()
import logging
log = logging.getLogger("blivet.ansible")

def manage_volume(b, volume):
    ## try looking up an existing device
    if volume['type'] == 'disk':
        device = b.devicetree.resolve_device(volume['disks'][0])
    else:
        if volume['type'] == 'lvm':
            name = "%s-%s" % (volume['pool'], volume['name'])
        else:
            name = volume['name']

        device = b.devicetree.get_device_by_name(name)

    fmt = get_format(volume['fs_type'], mountpoint=volume.get('mount_point'))

    ## schedule creation or destruction of the volume as needed
    if device is None and volume['state'] != 'absent':
        if volume['type'] == 'lvm':
            parent = b.devicetree.get_device_by_name(volume['pool'])
            size = Size(volume['size'])
            try:
                device = b.new_lv(name=volume['name'], parents=[parent], size=size, fmt=fmt)
            except Exception as e:
                raise RuntimeError("failed to create lv '%s': %s" % (volume['name'], str(e)))
            b.create_device(device)
    else:
        if volume['state'] == 'absent':
            if device is not None:
                b.devicetree.recursive_remove(device)

    if device is None:
        raise RuntimeError("failed to look up or create device '%s'" % volume['name'])

    ## schedule reformatting of the volume as needed
    if device.format.type != fmt.type:
        if device.format.status:
            device.format.teardown()
        b.format_device(device, fmt)

    if volume['mount_point']:
        volume['_device'] = device.path
        volume['_mount_id'] = device.fstab_spec

    ## schedule resize of the volume as needed
    size = Size(volume['size'])
    if device.exists and size and device.resizable and device.size != size:
        if device.format.resizable:
            device.format.update_size_info()

        try:
            b.resize_device(device, size)
        except ValueError as e:
            raise RuntimeError("device '%s' is not resizable (%s -> %s): %s" % (device.name, device.size, size, str(e)))


def look_up_disks(b, specs):
    """ return a list of blivet devices matching the given device ids """
    disks = list()
    for spec in specs:
        device = b.devicetree.resolve_device(spec)
        if device is not None:
            disks.append(device)

    return disks

def remove_leaves(b, device):
    """ schedule destroy actions for leaf devices recursively """
    if device.is_disk:
        return

    b.destroy_device(device)
    for p in device.parents:
        if p.isleaf:
            remove_leaves(p)

def manage_pool(b, pool):
    ## try to look up an existing pool device
    device = b.devicetree.get_device_by_name(pool['name'])

    ## schedule create or destroy actions as needed
    if device is None and pool['state'] != 'absent':
        disks = look_up_disks(b, pool['disks'])
        for disk in disks:
            b.devicetree.recursive_remove(disk)
            b.format_device(disk, get_format("lvmpv", device=disk.path))

        pool_device = b.new_vg(name=pool['name'], parents=disks)
        b.create_device(pool_device)
    else:
        if pool['state'] == 'absent':
            if device is not None:
                b.devicetree.recursive_remove(device)
                for p in device.parents:
                    remove_leaves(b, p)

            return

        # adjust pvs
        pass

    ## manage the pool's volumes
    for volume in pool['volumes']:
        manage_volume(b, volume)


def get_fstab_mounts(b):
    mounts = {}
    for line in open('/etc/fstab').readlines():
        if line.lstrip().startswith("#"):
            continue

        fields = line.split()
        if len(fields) < 6:
            continue

        device_id = fields[0]
        mount_point = fields[1]
        device = b.devicetree.resolve_device(device_id)
        if device is not None:
            mounts[device.name] = mount_point

    return mounts


def run_module():
    # available arguments/parameters that a user can pass
    module_args = dict(
        pools=dict(type='list'),
        volumes=dict(type='list'),
        exclusive=dict(type='bool', default=False))

    # seed the result dict in the object
    result = dict(
        changed=False,
        actions=list(),
        leaves=list(),
        mounts=list()
    )

    module = AnsibleModule(argument_spec=module_args,
                           supports_check_mode=True)

    if not module.params['exclusive'] and not module.params['pools'] and not module.params['volumes']:
        module.exit_json(**result)

    b = Blivet()
    b.reset()
    actions = list()
    initial_mounts = get_fstab_mounts(b)
    def record_action(action):
        if action.is_format and action.format.type is None:
            return

        actions.append(action)

    def action_string(action):
        action_desc = '{act}'
        if action.is_format:
            action_desc += ' {fmt} on'
        action_desc += ' {dev}'
        return action_desc.format(act=action.type_desc_str, fmt=action.format.type, dev=action.device.path)

    for pool in module.params['pools']:
        manage_pool(b, pool)

    for volume in module.params['volumes']:
        manage_volume(b, volume)

    scheduled = b.devicetree.actions.find()
    for action in scheduled:
        if action.is_destroy and action.is_format:
            action.format.teardown()

    if scheduled:
        ## execute the scheduled actions, committing changes to disk
        callbacks.action_executed.add(record_action)
        b.devicetree.actions.process()
        result['changed'] = True
        result['actions'] = [action_string(a) for a in actions]

        ## build a list of mounts to remove
        for action in actions:
            if action.is_destroy and action.is_format and action.format.type is not None:
                mount = initial_mounts.get(action.device.name)
                if mount is not None:
                    result['mounts'].append({"path": mount, "device": action.device.path, 'state': 'absent'})

    mount_vols = list()
    for pool in module.params['pools']:
        for volume in pool['volumes']:
            if pool['state'] == 'present' and volume['state'] != 'absent' and volume['mount_point']:
                mount_vols.append(volume.copy())

    for volume in module.params['volumes']:
        if volume['state'] == 'present' and volume['mount_point']:
            mount_vols.append(volume)

    for volume in mount_vols:
        result['mounts'].append({'src': volume['_device'],
                                 'path': volume['mount_point'],
                                 'fstype': volume['fs_type'],
                                 'opts': volume['mount_options'],
                                 'dump': volume['mount_check'],
                                 'passno': volume['mount_passno'],
                                 'state': 'mounted'})

    result['leaves'] = [d.path for d in b.devicetree.leaves]

    # success - return result
    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()
