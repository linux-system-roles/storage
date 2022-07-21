Linux Storage Role
==================
![CI Testing](https://github.com/linux-system-roles/storage/workflows/tox/badge.svg)


This role allows users to configure local storage with minimal input.

As of now, the role supports managing file systems and mount entries on
- unpartitioned disks
- lvm (unpartitioned whole-disk physical volumes only)

Requirements
------------

The role requires the `mount` module from `ansible.posix`.  If you are using
`ansible-core`, you must install the `ansible.posix` collection.
```
ansible-galaxy collection install -vv -r meta/collection-requirements.yml
```
If you are using Ansible Engine 2.9, or are using an Ansible bundle which
includes these collections/modules, you should have to do nothing.

Role Variables
--------------

__NOTE__: Beginning with version 1.3.0, unspecified parameters are interpreted
differently for existing and non-existing pools/volumes. For new/non-existent
pools and volumes, any omitted parameters will use the default value as
described in `defaults/main.yml`. For existing pools and volumes, omitted
parameters will inherit whatever setting the pool or volume already has.
This means that to change/override role defaults in an existing pool or volume,
you must explicitly specify the new values/settings in the role variables.

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

For LVM pools this can be also used to add and remove disks to/from an existing pool.
Disks in the list that are not used by the pool will be added to the pool.
Disks that are currently used by the pool but not present in the list will be removed
from the pool only if `storage_safe_mode` is set to `false`.

##### `raid_level`
When used with `type: lvm` it manages a volume group with a mdraid array of given level
on it. Input `disks` are in this case used as RAID members.
Accepted values are: `linear`, `raid0`, `raid1`, `raid4`, `raid5`, `raid6`, `raid10`

##### `volumes`
This is a list of volumes that belong to the current pool. It follows the
same pattern as the `storage_volumes` variable, explained below.

##### `encryption`
This specifies whether the pool will be encrypted using LUKS.
__WARNING__: Toggling encryption for a pool is a destructive operation, meaning
             the pool itself will be removed as part of the process of
             adding/removing the encryption layer.

##### `encryption_password`
This string specifies a password or passphrase used to unlock/open the LUKS volume(s).

##### `encryption_key`
This string specifies the full path to the key file on the managed nodes used to unlock
the LUKS volume(s).  It is the responsibility of the user of this role to securely copy
this file to the managed nodes, or otherwise ensure that the file is on the managed
nodes.

##### `encryption_cipher`
This string specifies a non-default cipher to be used by LUKS.

##### `encryption_key_size`
This integer specifies the LUKS key size (in bytes).

##### `encryption_luks_version`
This integer specifies the LUKS version to use.


#### `storage_volumes`
The `storage_volumes` variable is a list of volumes to manage. Each volume has the following
variables:

##### `name`
This specifies the name of the volume.

##### `type`
This specifies the type of volume on which the file system will reside.
Valid values for `type`: `lvm`, `disk` or `raid`.
The default is determined according to the OS and release (currently `lvm`).

##### `disks`
This specifies the set of disks to use as backing storage for the file system.
This is currently only relevant for volumes of type `disk`, where the list
must contain only a single item.

##### `size`
The `size` specifies the size of the file system. The format for this is intended to
be human-readable, e.g.: "10g", "50 GiB". The size of LVM volumes can be specified as a
percentage of the pool/VG size, eg: "50%" as of v1.4.2.

When using `compression` or `deduplication`, `size` can be set higher than actual available space,
e.g.: 3 times the size of the volume, based on duplicity and/or compressibility of stored data.

__NOTE__: The requested volume size may be reduced as necessary so the volume can
          fit in the available pool space, but only if the required reduction is
          not more than 2% of the requested volume size.

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

##### `raid_level`
Specifies RAID level. LVM RAID can be created as well.
"Regular" RAID volume requires type to be `raid`.
LVM RAID needs that volume has `storage_pools` parent with type `lvm`,
`raid_disks` need to be specified as well.
Accepted values are:
* for LVM RAID volume: `raid0`, `raid1`, `raid4`, `raid5`, `raid6`, `raid10`, `striped`, `mirror`
* for RAID volume: `linear`, `raid0`, `raid1`, `raid4`, `raid5`, `raid6`, `raid10`

__WARNING__: Changing `raid_level` for a volume is a destructive operation, meaning
             all data on that volume will be lost as part of the process of
             removing old and adding new RAID. RAID reshaping is currently not
             supported.

##### `raid_device_count`
When type is `raid` specifies number of active RAID devices.

##### `raid_spare_count`
When type is `raid` specifies number of spare RAID devices.

##### `raid_metadata_version`
When type is `raid` specifies RAID metadata version as a string, e.g.: '1.0'.

##### `raid_chunk_size`
When type is `raid` specifies RAID chunk size as a string, e.g.: '512 KiB'.
Chunk size has to be multiple of 4 KiB.

##### `raid_disks`
Specifies which disks should be used for LVM RAID volume.
`raid_level` needs to be specified and volume has to have `storage_pools` parent with type `lvm`.
Accepts sublist of `disks` of parent `storage_pools`.
In case multiple LVM RAID volumes within the same storage pool, the same disk can be used
in multiple `raid_disks`.

##### `encryption`
This specifies whether the volume will be encrypted using LUKS.
__WARNING__: Toggling encryption for a volume is a destructive operation, meaning
             all data on that volume will be removed as part of the process of
             adding/removing the encryption layer.

##### `encryption_password`
This string specifies a password or passphrase used to unlock/open the LUKS volume.

##### `encryption_key`
This string specifies the full path to the key file on the managed nodes used to unlock
the LUKS volume(s).  It is the responsibility of the user of this role to securely copy
this file to the managed nodes, or otherwise ensure that the file is on the managed
nodes.

##### `encryption_cipher`
This string specifies a non-default cipher to be used by LUKS.

##### `encryption_key_size`
This integer specifies the LUKS key size (in bits).

##### `encryption_luks_version`
This integer specifies the LUKS version to use.

##### `deduplication`
This specifies whether the Virtual Data Optimizer (VDO) will be used.
When set, duplicate data stored on storage volume will be
deduplicated resulting in more storage capacity.
Can be used together with `compression` and `vdo_pool_size`.
Volume has to be part of the LVM `storage_pool`.
Limit one VDO `storage_volume` per `storage_pool`.
Underlying volume has to be at least 9 GB (bare minimum is around 5 GiB).

##### `compression`
This specifies whether the Virtual Data Optimizer (VDO) will be used.
When set, data stored on storage volume will be
compressed resulting in more storage capacity.
Volume has to be part of the LVM `storage_pool`.
Can be used together with `deduplication` and `vdo_pool_size`.
Limit one VDO `storage_volume` per `storage_pool`.

##### `vdo_pool_size`
When Virtual Data Optimizer (VDO) is used, this specifies the actual size the volume
will take on the device. Virtual size of VDO volume is set by `size` parameter.
`vdo_pool_size` format is intended to be human-readable,
e.g.: "30g", "50GiB".
Default value is equal to the size of the volume.

#### `cached`
This specifies whether the volume should be cached or not.
This is currently supported only for LVM volumes where dm-cache
is used.

#### `cache_size`
Size of the cache. `cache_size` format is intended to be human-readable,
e.g.: "30g", "50GiB".

#### `cache_mode`
Mode for the cache. Supported values include `writethrough` (default) and `writeback`.

#### `cache_devices`
List of devices that will be used for the cache. These should be either physical volumes or
drives these physical volumes are allocated on. Generally you want to select fast devices like
SSD or NVMe drives for cache.

#### `thin`
Whether the volume should be thinly provisioned or not.
This is supported only for LVM volumes.

#### `thin_pool_name`
For `thin` volumes, this can be used to specify the name of the LVM thin pool that will be used
for the volume. If the pool with the provided name already exists, the volume will be added to that
pool. If it doesn't exist a new pool named `thin_pool_name` will be created.
If not specified:
* if there are no existing thin pools present, a new thin pool will be created with an automatically
  generated name,
* if there is exactly one existing thin pool, the thin volume will be added to it and
* if there are multiple thin pools present an exception will be raised.

#### `thin_pool_size`
Size for the thin pool. `thin_pool_size` format is intended to be human-readable,
e.g.: "30g", "50GiB".

#### `storage_safe_mode`
When true (the default), an error will occur instead of automatically removing existing devices and/or formatting.

#### `storage_udevadm_trigger`
When true (the default is false), the role will use udevadm trigger
to cause udev changes to take effect immediately.  This may help on some
platforms with "buggy" udev.

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
