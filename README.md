Linux Storage Role
==================

This role allows users to configure local storage with minimal input.

As of now, the role supports managing file systems and mount entries on
- unpartitioned disks
- lvm (unpartitioned whole-disk physical volumes only)


Role Variables
--------------

#### `storage_pools`
The `storage_pools` variable is a list of pools to manage. Each pool contains a
nested list of `volume` dicts as described below, as well as the following
keys:

##### `name`
This specifies the name of the pool to manage/create as a string. (One
example of a pool is an LVM volume group.)

##### `type`
This specifies the type of pool to manage.
Valid values for `type`: `lvm`.

##### `disks`
A list which specifies the set of disks to use as backing storage for the pool.
Supported identifiers include: device node (like `/dev/sda` or `/dev/mapper/mpathb`),
device node basename (like `sda` or `mpathb`), /dev/disk/ symlink
(like `/dev/disk/by-id/wwn-0x5000c5005bc37f3f`).

##### `volumes`
This is a list of volumes that belong to the current pool. It follows the
same pattern as the `storage_volumes` variable, explained below.


#### `storage_volumes`
The `storage_volumes` variable is a list of volumes to manage. Each volume has the following
variables:

##### `name`
This specifies the name of the volume.

##### `type`
This specifies the type of volume on which the file system will reside.
Valid values for `type`: `lvm` or `disk`.
The default is determined according to the OS and release (currently `lvm`).

##### `disks`
This specifies the set of disks to use as backing storage for the file system.
This is currently only relevant for volumes of type `disk`, where the list
must contain only a single item.

##### `size`
The `size` specifies the size of the file system. The format for this is intended to
be human-readable, e.g.: "10g", "50 GiB".

##### `fs_type`
This indicates the desired file system type to use, e.g.: "xfs", "ext4", "swap".
The default is determined according to the OS and release
(currently `xfs` for all the supported systems).

##### `fs_label`
The `fs_label` is a string to be used for a file system label.

##### `fs_create_options`
The `fs_create_options` specifies custom arguments to `mkfs` as a string.

##### `mount_point`
The `mount_point` specifies the directory on which the file system will be mounted.

##### `mount_options`
The `mount_options` specifies custom mount options as a string, e.g.: 'ro'.


Example Playbook
----------------

```yaml
- hosts: all

  roles:
    - name: linux-system-roles.storage
      storage_pools:
        - name: app
          disks:
            - sdb
            - sdc
          volumes:
            - name: shared
              size: "100 GiB"
              mount_point: "/mnt/app/shared"
              #fs_type: xfs
              state: present
            - name: users
              size: "400g"
              fs_type: ext4
              mount_point: "/mnt/app/users"
      storage_volumes:
        - name: images
          type: disk
          disks: ["mpathc"]
          mount_point: /opt/images
          fs_label: images

```


License
-------

MIT
