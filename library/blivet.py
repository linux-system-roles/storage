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

def manage_volume(b, volume):
    mounts = list()
    if volume['type'] == 'disk':
        device = b.devicetree.resolve_device(volume['disks'][0])
    else:
        if volume['type'] == 'lvm':
            name = "%s-%s" % (volume['pool'], volume['name'])
        else:
            name = volume['name']

        device = b.devicetree.get_device_by_name(name)

    fmt = get_format(volume['fs_type'])

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
            return mounts

    if device is None:
        raise RuntimeError("failed to look up or create device '%s'" % volume['name'])

    if device.format.type != fmt.type:
        if device.format.status:
            device.format.teardown()
        b.format_device(device, fmt)

    if volume['mount_point']:
        mounts.append({'src': device.fstab_spec,
                       'path': volume['mount_point'],
                       'fstype': volume['fs_type'],
                       'opts': volume['mount_options'],
                       'dump': volume['mount_check'],
                       'passno': volume['mount_passno'],
                       'state': 'mounted'})

    size = Size(volume['size'])
    if device.exists and size and device.size != size:
        if True or device.format.resizable:
            device.format.update_size_info()

        try:
            b.resize_device(device, size)
        except ValueError as e:
            raise RuntimeError("device '%s' is not resizable (%s -> %s): %s" % (device.name, device.size, size, str(e)))

    return mounts

def look_up_disks(b, specs):
    disks = list()
    for spec in specs:
        device = b.devicetree.resolve_device(spec)
        if device is not None:
            disks.append(device)

    return disks

def remove_leaves(b, device):
    if device.is_disk:
        return

    b.destroy_device(device)
    for p in device.parents:
        if p.isleaf:
            remove_leaves(p)

def manage_pool(b, pool):
    mounts = list()
    device = b.devicetree.get_device_by_name(pool['name'])
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

            return mounts

        # adjust pvs
        pass

    for volume in pool['volumes']:
        mounts.extend(manage_volume(b, volume))

    return mounts


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
        removed_mounts=list(),
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
    added_mounts = list()
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
        added_mounts.extend(manage_pool(b, pool))

    for volume in module.params['volumes']:
        added_mounts.extend(manage_volume(b, volume))

    if b.devicetree.actions.find():
        callbacks.action_executed.add(record_action)
        b.devicetree.actions.process()
        result['changed'] = True
        result['actions'] = [action_string(a) for a in actions]
        for action in actions:
            if action.is_destroy and action.is_format and action.format.type is not None:
                mount = initial_mounts.get(action.device.name)
                if mount is not None:
                    result['removed_mounts'].append(mount)

    # handle mount point changes w/o any changes to the block device or its formatting
    for added_mount in added_mounts:
        initial_mount = initial_mounts.get(added_mount['src'].split('/')[-1])
        if initial_mount:
            result['removed_mounts'].append(initial_mount)

    result['mounts'] = added_mounts
    result['leaves'] = [d.path for d in b.devicetree.leaves]

    # success - return result
    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()
