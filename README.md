storage
=======

A role to manage storage on linux.

common utils
  resolve device
  size units
    read sizes, eg: 10G, 500m, 500GiB
    format size strings for use by lvm, parted
  partition specs based on final device size
    

disk
  device
  disklabel

partition
  disk
  size
  type
  name
  number
  flags
  alignment: none|minimal|optimal
  *start (in sectors or size units)
  *length (in sectors or size units)

volgroup
  name
  pvs
  pesize

logvol
  name
  size
  *extents
  vg
  pvs
  type: linear|striped|snapshot|mirror|raid|thin|cache|thin-pool|cache-pool
  pool
  origin

md
  name
  level
  members
  spares
  metadata: 0.90|1.0|1.1|1.2|default

luks
  name
  type: luks|luks2
  passphrase
  keyfile
  cipher
  key_size

vdo
  name
  device
  compression
  deduplication
  logicalsize
  emulate512
  writepolicy

filesystem
  device
  type
  options

mount
  device
  type
  mountpoint
  options
  passno
  check


How would this look from a playbook?

```yaml
---

- hosts: all
  tasks:
    disks:
      - name: sdd
	device: /dev/sdd
	label_type: gpt

      - name: sde
	device: /dev/sde
	fs_type: xfs
	fs_label: whole_disk_fs
	fs_mountpoint: /mnt/point

    partitions:
      - name: remove old test data
	disk: /dev/sdf
	fs_label: testdata
	state: absent

      - name: app_pv
	disk: /dev/sdd
	start: 0
	end: 200GiB

      - name: test data
	disk: /dev/sdd
	start: 200GiB
	end: 100%
	fs_type: ext4
	fs_mountpoint: /some/where
	fs_label: testdata
	encryption: true
	encryption_key_file: testdata.keyfile
	encryption_key_size: 256
	encryption_cipher: aes-xts-plain64

      # auto-detect fstype?
      - name: existing web data
	device: LABEL=web_data
	fs_mount_point: /opt/web
	fs_mount_options: noatime

    volgroups:
      - name: app
	pvs: foo_pv
	pesize: 8MiB

    logvols:
      - name: data
	volgroup: app
	size: 20GiB
	fs_type: xfs
	fs_label: app_data
	fs_mount_point: /opt/app/data
	fs_mount_options: nodiscard
	encryption: true
	encryption_key_file: appdata.keyfile
	encryption_key_size: 512
	encryption_cipher: aes-xts-plain64

      - name: backup
	volgroup: app
	size: 100%
	fs_type: xfs
	fs_label: app_backup
	mountpoint: /opt/app/backup
```

Below is a top-down specification. This can save the user a great deal of typing (and knowledge), but it
has the side-effect of dumping all of the type-specific options into a single namespace. This is probably
not an issue in the vast majority of cases, but it does mean there are a great many options to consider.

name  # doubles as fs label?
state
type  # disk|partition|lvm|lvm-thin|lvm-thinpool|lvm-cache|lvm-cachepool|lvm-raid|lvm-snapshot|md
size
disks
raid_level  # raid0|raid1|...
encryption  # true|false
encryption_*
fs_*
compression  # true|false
deduplication  # true|false

Example playbook:
```yaml

---

- hosts: all

  tasks:
    - name: Shared data volume
      blockdev:
        name: shared
        vg_name: {{ app_name }}
        size: 100g
        #type: lvm
        disks: {{ app_data_wwns }}
        #fs_type: xfs
        fs_mount_point: {{ app_root }}/shared
        state: present

    - name: User data volume
      blockdev:
        name: users
        size: 400g
        encryption:
	  key_file: {{ luks_key_file }}
	fs_mount_point: {{ app_root }}/users
        state: present

    - name: Virt Image Repo
      blockdev:
        name: virt_images  # doubles as fs label
        disks: [ {{ ansible_devices.unused_disks[0] }} ]  # unused_disks doesn't exist yet
        compression: true
        deduplication: true
        fs_mount_point: {{ virt_root }}/img/
        state: present

```

TODO: Augment the storage-related facts, simplest variation being to add the output of 'lsblk -J'.

To Do
----- 

- figure out how to split up the work
- decide on delivery phases
  - partitions, lvm (linear), filesystem, mount, encryption
  - vdo, md, lvm (thin, cache, raid)
- module selection logic (action plugin?)
- individual roles/tasks for disk, partition, volgroup, logvol, etc.
- top-level role
- bundled module(s)?
- augment existing storage facts (even 'lsblk -J' would be a modest improvement over current hand-rolled sysfs bundling)


Requirements
------------

Any pre-requisites that may not be covered by Ansible itself or the role should be mentioned here. For instance, if the role uses the EC2 module, it may be a good idea to mention in this section that the boto package is required.

Role Variables
--------------

A description of the settable variables for this role should go here, including any variables that are in defaults/main.yml, vars/main.yml, and any variables that can/should be set via parameters to the role. Any variables that are read from other roles and/or the global scope (ie. hostvars, group vars, etc.) should be mentioned here as well.

```yaml
some_feature:
  option: foo
  location: /tmp/bar
```

Dependencies
------------

A list of other roles hosted on Galaxy should go here, plus any details in regards to parameters that may need to be set for other roles, or variables that are used from other roles.

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

    - hosts: servers
      roles:
         - { role: username.rolename, x: 42 }

License
-------

assign accordingly, default GPLv3

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
