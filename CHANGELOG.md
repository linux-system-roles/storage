Changelog
=========

[1.9.6] - 2023-02-01
--------------------

### New Features

- none

### Bug Fixes

- none

### Other Changes

- fix shellcheck issues (#327)
- Fix issues found by CodeQL (#329)
- restrict swap size to less than 128GB on EL7 (#331)

[1.9.5] - 2023-01-19
--------------------

### New Features

- none

### Bug Fixes

- none

### Other Changes

- ansible-lint 6.x fixes (#317)
- Improve skip tags handling in the tests_lvm_pool_members tests (#319)

[1.9.4] - 2022-12-16
--------------------

### New Features

- none

### Bug Fixes

- none

### Other Changes

- Tests - use a threshold of 2 percent in volume size check (#313)

There seems to be an issue calculating the expected size and the
actual size of the volume.  On some systems, the difference is
greater than 1% but less than 2%.  We are working on a better, more
reliable method of calculating the expected and actual sizes.  In
the meantime, make the threshold 2%.

[1.9.3] - 2022-12-06
--------------------

### New Features

- none

### Bug Fixes

- Thin pool test with large size volume fix (#310)

fixed size calculation for large size thin pools in the test
modified provision.fmf disk size to simulate larger disks in the tests

### Other Changes

- none

[1.9.2] - 2022-11-01
--------------------

### New Features

- none

### Bug Fixes

- Fixed calculation of relative thinp sizes (#299)

percent specified 'size' of thin pool volume is now properly
calculated from size of parent thinpool

- Fixed size and percentage handling for thin pools (#299)

percentage size thin volume now correctly references its parent device
for size calculation
percentage values are now accepted size for thin pool size

### Other Changes

- Add disks_needed for raid test cases (#300)

Creating raid will be failed if we don't have enough unused disks, set
disks_needed earlier.

Set disks_needed=2 for tests_swap.yml

- use block instead of end_play (#302)

Do not use `end_play` with the conditional `when` which uses variables
for the condition.  The problem is that `end_play` is executed in a
different scope where the variables are not defined, even when using
`set_fact`.  The fix is to instead use a `block` and a `when`.

- Modified lvmvdo check

VDO check was failing due to issue in 'vdostats'.
Modified vdo testing so 'lvs' is used to get data instead

[1.9.1] - 2022-07-26
--------------------

### New Features

- none

### Bug Fixes

- Update README.md with latest changes (#290)

* LVM thin provisioning support.
* Support for adding/removing disks to/from existing pools.
* Cache can now be attached to an pre-existing volume.

Fixes: #287
Fixes: #288
Fixes: #289

### Other Changes

- changelog_to_tag action - Use GITHUB_REF_NAME for main branch name

[1.9.0] - 2022-07-19
--------------------

### New Features

- Add support for attaching LVM cache to existing LVs (#273)

Fixes: #252

- Add support for managing pool members (#264)

For LVM pools this adds support for adding and removing members
(PVs) from the pool (VG).

* Do not allow removing members from existing pools in safe mode

### Bug Fixes

- loop variables are scoped local - no need to reset them (#282)

If you use
```yaml
  loop_control:
    loop_var: storage_test_pool
```
Then the variable `storage_test_pool` is scoped local to the task
and is undefined after the task.  In addition, referencing the
variable after the loop causes this warning:
```
[WARNING]: The loop variable 'storage_test_pool' is already in use. You should
set the `loop_var` value in the `loop_control` option for the task to something
else to avoid variable collisions and unexpected behavior.
```

- support ansible-core-2.13 (#278)

Looks like ansible-core-2.13 (or latest jinja3) does not support
constructs like this:
```
var: "{{ [some list] }} + {{ [other list] }}"
```
instead, the entire thing has to be evaluated in the same jinja
evaluation context:
```
var: "{{ [some list] + [other list] }}"
```
In addition - it is an Ansible antipattern to use
```yaml
- set_fact:
    var: "{{ var + item }}"
    loop: "{{ some_list }}"
```
so that was rewritten to use filters instead

### Other Changes

- ensure role works with gather_facts: false (#277)

Ensure tests work when using ANSIBLE_GATHERING=explicit

- ensure cryptsetup is available for testing (#279)

- make min_ansible_version a string in meta/main.yml (#281)

The Ansible developers say that `min_ansible_version` in meta/main.yml
must be a `string` value like `"2.9"`, not a `float` value like `2.9`.

- Skip the entire test_lvm_pool_members playbook with old blivet (#280)

Multiple bugs in blivet were fixed in order to make the feature
work and without the correct version even the most basic test to
remove a PV from a VG will fail so we should skip the entire test
with old versions of blivet.
Skip test on el7 if blivet version is too old
Add support for `is_rhel7`
Refactor EL platform and version checking code
Add a name for the `end_play` task

- Add CHANGELOG.md (#283)

[1.8.1] - 2022-06-12
--------------------

### New Features

- check for thinlv name before assigning to thinlv\_params

### Bug Fixes

- none

### Other Changes

- none

[1.8.0] - 2022-06-02
--------------------

### New Features

- LVM RAID raid0 level support
- Thin pool support

### Bug Fixes

- none

### Other Changes

- none

[1.7.3] - 2022-05-16
--------------------

### New Features

- add support for mount\_options

### Bug Fixes

- none

### Other Changes

- Use meta/collection-requirements.yml for collection dependencies
- bump tox-lsr version to 2.11.0; remove py37; add py310

[1.7.2] - 2022-04-19
--------------------

### New Features

- add xfsprogs for non-cloud-init systems
- allow role to work with gather\_facts: false
- add setup snapshot to install packages into snapshot

### Bug Fixes

- none

### Other Changes

- none

[1.7.1] - 2022-03-18
--------------------

### New Features

- Less verbosity by default

### Bug Fixes

- none

### Other Changes

- README-devel: Add information about the generated tests
- bump tox-lsr version to 2.10.1

[1.7.0] - 2022-01-10
--------------------

### New Features

- Add LVM RAID specific parameters to module\_args
- Added support for LVM RAID volumes
- Add support for creating and managing LVM cache volumes
- Nested module params checking
- Refined safe\_mode condition in create\_members

### Bug Fixes

- none

### Other Changes

- bump tox-lsr version to 2.8.3
- change recursive role symlink to individual role dir symlinks

[1.6.4] - 2021-12-01
--------------------

### New Features

- add support for storage\_udevadm\_trigger
- Add workaround for the service\_facts module for Ansible \< 2.12

### Bug Fixes

- none

### Other Changes

- remove py27 from github CI testing
- add tags to allow skipping lvm tests
- update tox-lsr version to 2.8.0

[1.6.3] - 2021-11-08
--------------------

### New Features

- support python 39, ansible-core 2.12, ansible-plugin-scan
- Add support for Rocky Linux 8

### Bug Fixes

- none

### Other Changes

- update tox-lsr version to 2.7.1
- add meta/requirements.yml; support ansible-core 2.11

[1.6.2] - 2021-10-04
--------------------

### New Features

- Replace crypttab with lineinfile
- replace json\_query with selectattr and map

### Bug Fixes

- none

### Other Changes

- Improve wording
- use apt-get install -y
- use tox-lsr version 2.5.1
- Added skip checks feature to speed up the tests

[1.6.0] - 2021-08-11
--------------------

### New Features

- Raise supported Ansible version to 2.9

### Bug Fixes

- none

### Other Changes

- none

[1.5.3] - 2021-08-07
--------------------

### New Features

- use volume1\_size; check for expected error

### Bug Fixes

- none

### Other Changes

- none

[1.5.2] - 2021-08-03
--------------------

### New Features

- none

### Bug Fixes

- none

### Other Changes

- tag tests that use NVME and SCSI

[1.5.1] - 2021-07-29
--------------------

### New Features

- none

### Bug Fixes

- omit unnecessary conditional - deadcode reported by static scanner

### Other Changes

- none

[1.5.0] - 2021-07-28
--------------------

### New Features

- percentage-based volume size \(lvm only\)

### Bug Fixes

- none

### Other Changes

- Allow a tolerance of up to 1% when verifying volume size in tests.
- skip vdo test if kernel module is not loadable
- Added support for NVME and SCSI HW test setup

[1.4.1] - 2021-07-14
--------------------

### New Features

- none

### Bug Fixes

- Fixed volume relabeling

### Other Changes

- none

[1.4.0] - 2021-06-23
--------------------

### New Features

- LVMVDO support

### Bug Fixes

- none

### Other Changes

- none

[1.3.1] - 2021-05-17
--------------------

### New Features

- Capture inherited volume type in return value.
- Look up pool by name without disk list
- Trim volume size as needed to fit in pool free space
- Be smarter in choosing expected partition name.

### Bug Fixes

- Fix issues found by linters - enable all tests on all repos - remove suppressions
- fix most ansible-test issues, suppress the rest

### Other Changes

- Remove python-26 environment from tox testing
- update to tox-lsr 2.4.0 - add support for ansible-test with docker
- CI: Add support for RHEL-9

[1.3.0] - 2021-02-14
--------------------

### New Features

- remove include\_vars, use public: true to export role vars, defaults
- Updated exception message
- add centos8

### Bug Fixes

- fix indentation in main-blivet.yml
- Fix centos6 repos; use standard centos images
- Confusing error message fix
- Non-existent pool removal fix
- Missing parameters

### Other Changes

- use tox-lsr 2.2.0
- use molecule v3, drop v2
- drop localhost from tests\_deps.yml
- remove ansible 2.7 support from molecule
- use tox for ansible-lint instead of molecule
- use new tox-lsr plugin
- use github actions instead of travis

[1.2.2] - 2020-10-28
--------------------

### New Features

- none

### Bug Fixes

- Fix yamllint warnings in tests

### Other Changes

- issue-67: Create storage\_lsr sub-directory under module\_utils and move size.py there
- lock ansible-lint version at 4.3.5; suppress role name lint warning
- sync collections related changes from template to storage role

[1.2.1] - 2020-09-24
--------------------

### New Features

- Disallow toggling encryption in safe mode

### Bug Fixes

- Make the var load test compatible with old Jinja2 \(2.7\)

### Other Changes

- Lock ansible-lint on version 4.2.0
- collections prep - use FQRN

[1.2.0] - 2020-08-23
--------------------

### New Features

- Pass -F to mke2fs for whole disks in RHEL
- TLS/crypto param and key naming consistency
- Advanced options support for raid pools
- Updated version of \#64
- Add tests for the optional encryption parameters
- Simplify device path checking
- Update supported Fedora versions
- MDRAID support for volumes
- Encrypted Pools
- Encrypted Volumes
- Do not report null\_blk devices as unused disks.
- MDRAID support for pools
- Check for duplicate pool/volume names.
- Streamline dependency gathering
- Determine too\_large\_size dynamically

### Bug Fixes

- Fix of overlooked pylint errors
- Don't try to set up mounts with invalid mount points.
- bug with current implementation of platform/version specific vars/tasks file include/import
- Resize fixes
- Avoid using ansible\_failed\_task in rescue blocks
- update the indent by two spaces
- Correctly Manage Swap Volumes

### Other Changes

- Update condition in tests\_misc.yml
- add 'disks\_needed: 3' to tests\_raid\_volume\_options.yml
- Add new test case for FS resize
- Avoid using Jinja2 template markers in assert
- workaround travis CI docker version issue
- sync with latest template including shellcheck
- Check Volume Size in Tests
- Improved RAID tests
- Add test for the include variable problem
- update to latest template
- use tox; use latest template code
- use molecule v2

[1.1.0] - 2020-01-14
--------------------

### New Features

- Make remaining class new-style \(derive from object\)
- Replace selectattr filter with json\_query filter
- Add flag to prevent implicit removal of existing device/fs.

### Bug Fixes

- Fail if there are not enough disks for testing
- Avoid missing\_required\_lib introduced only in 2.8
- Remove a forgotten `raise` found by Coverity

### Other Changes

- Fix issues found by lgtm.com
- Specify Python 2 for LGTM
- Remove empty files for unsupported OS versions

[1.0.2] - 2019-08-15
--------------------

### New Features

- none

### Bug Fixes

- none

### Other Changes

- Improve the YAML format of the example and of one test. Use the Galaxy prefix in README

[1.0.0] - 2019-08-14
--------------------

### Initial Release
