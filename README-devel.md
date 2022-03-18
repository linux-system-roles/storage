# Developer Guide
## Architecture
### Overview
The majority of the role's logic is in `library/blivet.py`, which is a module
that does the heavy lifting of managing the actual storage configuration. The
next biggest piece is in `tasks/`, followed by `defaults/`. Storage role python
imports are located at `module_utils/storage_lsr`.

### Defaults
This is where we define the structure of the vars available to users to specify
how they want the storage to be layed out. There are two top-level lists:
`storage_pools` is a list of pools, which contain volumes, and
`storage_volumes`, which are volumes that are not associated with any pool.
Examples of pools include LVM volume groups and disks with partition tables.
Most volumes will exist within a pool, except for whole-disk file-systems.

### Tasks
This is the ansible logic to take the user's specification and translate it
into a storage configuration. For the most part, it applies defaults as needed
and then delegates the real work to the embedded `blivet` module and ansible's
`mount` module.

### Modules
The `blivet` module does most of the actual work of modifying the storage
configuration. It provides an interface to `blivet`, which is a python module
for storage management used by the Fedora and Red Hat OS installer (anaconda).
It accepts a list of pools and a list of standalone volumes, manages the
storage configuration accordingly, then returns several pieces of data: a
slightly enhanced copy of the pool/volume lists, a list of actions it took,
and a list of mounts to manage using ansible's built-in `mount` module.

The `bsize` module translates human-readable size specifications into a
flexible format.

The `blockdev_info` module gathers information about the storage devices in the
system, and is only used for test result validation.

The `find_unused_disk` module lists unused disks that match a set of user-
provided constraints.

### Tests
There are unit tests for the embedded modules in `tests/unit/` and integration
tests for the role in `tests/`.

### Generated Tests
For each existing test file, there are two more generated tests that use NVMe
and SCSI drives instead of the default VirtIO ones. When adding a new test
file, make sure these are generated too, `tests/scripts` contains a script to
generate the tests and also commit hooks to do this automatically for each
git commit.

## Running Tests
All of the integration tests are designed to use extra/unused disks in a vm.
Keep in mind that containers do not provide any storage isolation, and so are
not appropriate for testing of storage management.

Here is the command line I have been using to run individual integration tests
from the command line in a virtual machine running Fedora 29:

`ansible-playbook -K --flush-cache -i inventory tests/tests_change_fs.yml`

Here's what the inventory file contains:

`localhost	ansible_connection=local ansible_python_interpreter=/usr/bin/python3`

## Debugging
There is more than enough output on the console to overrun the buffers, so it
is often useful to redirect/duplicate to a log by setting `ANSIBLE_LOG_PATH`.

There is also `/tmp/blivet.log` in case there are problems doing the actual
storage management.
