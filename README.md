Linux Storage Role
==================

This role allows users to configure local storage with minimal input.

As of now, the role supports managing file systems and mount entries on
- unpartitioned disks
- lvm (unpartitioned whole-disk physical volumes only)


Role Variables
--------------

#### `device_type`
The `device_type` specifies the type of device on which the file system will reside.
Valid values for `device_type`: `lvm`(the default) or `disk`.

#### `disks`
The `disks` specifies the set of disks to use as backing storage for the file system.
This is relevant for all values of `device_type`.

#### `size`
The `size` specifies the size of the file system. The format for this is intended to
be human-readable, eg: "10g", "50 GiB", or "100%" (use all available space on the
specified disks).

#### `device_name`
The `device_name` specifies the name of the block device. This is only applicable
for values of `device_type` that allow user-specified names, such as `lvm`.

#### `fs_type`
The `fs_type` indicates the desired file system type to use, eg: "xfs"(the default),
"ext4", "swap".

#### `fs_label`
The `fs_label` is a string to be used for a file system label.

#### `fs_create_options`
The `fs_create_options` specifies custom arguments to `mkfs` as a string.

#### `mount_point`
The `mount_point` specifies the directory on which the file system will be mounted.

#### `mount_options`
The `mount_options` specifies custom mount options as a string, eg: 'ro'.

#### `lvm_vg`
The `lvm_vg` specifies the name of the LVM volume group to manage/create as a
string.


Example Playbook
----------------

```yaml

---
- hosts: all

  tasks:
    - include_role:
        name: storage
      vars:
        device_name: "shared"
        size: "100g"
        #device_type: lvm
        disks: "{{ app_data_wwns }}"
        #fs_type: "xfs"
        mount_point: "{{ app_root }}/shared"
        lvm_vg: "{{ app_name }}"
        state: present

    - include_role:
        name: storage
      vars:
        device_name: "users"
        size: "400g"
        disks: "{{ app_data_wwns }}"
        fs_type: "ext4"
        fs_mount_point: {{ app_root }}/users
        lvm_vg: "{{ app_name }}"
        state: present

    - include_role:
        name: storage
      vars:
        disks: ["mpathc"]
        mount_point: "/opt/images"
        fs_label: "images"
```


License
-------

MIT
