Linux Storage Role
==================

This role allows users to configure local storage with minimal input.

As of now, the role supports managing file systems and mount entries on
- unpartitioned disks
- lvm (unpartitioned whole-disk physical volumes only)


Role Variables
--------------

#### `volume_type`
The `volume_type` specifies the type of device on which the file system will reside.
Valid values for `volume_type`: `lvm`(the default) or `disk`.

#### `disks`
The `disks` specifies the set of disks to use as backing storage for the file system.
This is relevant for all values of `volume_type`.

#### `size`
The `size` specifies the size of the file system. The format for this is intended to
be human-readable, eg: "10g", "50 GiB", or "100%" (use all available space on the
specified disks).

#### `volume_name`
The `volume_name` specifies the name of the block device. This is only applicable
for values of `volume_type` that allow user-specified names, such as `lvm`.

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

#### `pool_name`
The `pool_name` specifies the name of the pool to manage/create as a string. (One
example of a pool is an LVM volume group.)


Example Playbook
----------------

```yaml

---
- hosts: all

  tasks:
    - include_role:
        name: storage
      vars:
        volume_name: "shared"
        size: "100g"
        #volume_type: lvm
        disks: "{{ app_data_wwns }}"
        #fs_type: "xfs"
        mount_point: "{{ app_root }}/shared"
        pool_name: "{{ app_name }}"
        state: present

    - include_role:
        name: storage
      vars:
        volume_name: "users"
        size: "400g"
        disks: "{{ app_data_wwns }}"
        fs_type: "ext4"
        fs_mount_point: {{ app_root }}/users
        pool_name: "{{ app_name }}"
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
