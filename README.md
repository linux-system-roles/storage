Linux Storage Role
==================

This role allows users to configure local storage with minimal input.

As of now, the role supports managing file systems and mount entries on
- unpartitioned disks
- lvm (unpartitioned whole-disk physical volumes only)


Role Variables
--------------

#### `pools`
The `pools` variable is a list of pools to manage. Each pool contains a
nested list of `volume` dicts as described below, as well as the following
keys:

#### `name`
This specifies the name of the pool to manage/create as a string. (One
example of a pool is an LVM volume group.)

#### `type`
This specifies the type of pool to manage.
Valid values for `type`: `lvm`.

#### `disks`
This specifies the set of disks to use as backing storage for the pool.


#### `volumes`
The `volumes` variable is a list of volumes to manage. Each volume has the following
variables:

#### `name`
This specifies the name of the volume.

#### `type`
This specifies the type of volume on which the file system will reside.
Valid values for `type`: `lvm`(the default) or `disk`.

#### `disks`
This specifies the set of disks to use as backing storage for the file system.
This is relevant for volumes of type `disk` or `partition`.

#### `size`
The `size` specifies the size of the file system. The format for this is intended to
be human-readable, eg: "10g", "50 GiB", or "100%" (use all available space on the
specified disks).

#### `fs_type`
This indicates the desired file system type to use, eg: "xfs"(the default), "ext4", "swap".

#### `fs_label`
The `fs_label` is a string to be used for a file system label.

#### `fs_create_options`
The `fs_create_options` specifies custom arguments to `mkfs` as a string.

#### `mount_point`
The `mount_point` specifies the directory on which the file system will be mounted.

#### `mount_options`
The `mount_options` specifies custom mount options as a string, eg: 'ro'.


Example Playbook
----------------

```yaml

---
- hosts: all

  roles:
    - name: storage
      pools:
        - name: "{{ app_name }}"
          disks: "{{ app_data_wwns }}"
          volumes:
            - name: shared
              size: "100 GiB"
              mount_point: "{{ app_root}}/shared"
              #fs_type: xfs
              state: present
            - name: users
              size: "400g"
              fs_type: ext4
              mount_point: "{{ app_root }}/users"
      volumes:
        - name: images
          type: disk
          disks: ["mpathc"]
          mount_point: /opt/images
          fs_label: images

```


License
-------

MIT
