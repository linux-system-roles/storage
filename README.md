storage
=======

A role to manage storage on linux.


Example playbook:
```yaml

---

- hosts: all

  roles:
    - storage:
      name: shared
      size: 100g
      #type: lvm
      disks: {{ app_data_wwns }}
      #fs_type: xfs
      fs_mount_point: {{ app_root }}/shared
      lvm_vg_name: {{ app_name }}
      state: present

    - storage:
      name: users
      size: 400g
      luks: true
      luks_key_file: {{ luks_key_file }}
      fs_mount_point: {{ app_root }}/users
      state: present

    - storage:
      name: virt_images
      disks: [ {{ ansible_devices.unused_disks[0] }} ]  # unused_disks doesn't exist yet
      vdo: true
      fs_mount_point: {{ virt_root }}/img/
      state: present

```

To Do
----- 

- decide delivery phases
  - partitions, lvm (linear), filesystem, mount
  - encryption, vdo, md, lvm (thin, cache, raid)
- module selection logic (action plugin?)
- individual roles/tasks for disk, partition, volgroup, logvol, etc.?
- top-level role
- tags for task filtering
- bundled module(s)?
  - resolve device
  - size units
    - read sizes, eg: 10G, 500m, 500GiB
    - format size strings for use by lvm, parted
  - partition specs based on final device size
- augment existing storage facts
  - even 'lsblk -J' would be a modest improvement over current hand-rolled sysfs bundling


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
