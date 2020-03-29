# SPDX-License-Identifier: MIT
#
# Use this file to specify custom configuration for a project. Generally, this
# involves the modification of the content of LSR_* environment variables, see
#
#   * .travis/preinstall:
#
#       - LSR_EXTRA_PACKAGES
#
#   * .travis/runtox:
#
#       - LSR_ANSIBLES
#       - LSR_MSCENARIOS
#
#   * .travis/runcoveralls.sh:
#
#       - LSR_PUBLISH_COVERAGE
#       - LSR_TESTSDIR
#       - function lsr_runcoveralls_hook
#
# Environment variables that not start with LSR_* but have influence on CI
# process:
#
#   * .travis/runpylint.sh:
#
#       - RUN_PYLINT_INCLUDE
#       - RUN_PYLINT_EXCLUDE
#       - RUN_PYLINT_DISABLED
#
#   * .travis/runblack.sh:
#
#       - RUN_BLACK_INCLUDE
#       - RUN_BLACK_EXCLUDE
#       - RUN_BLACK_DISABLED
#       - RUN_BLACK_EXTRA_ARGS
#
#   * .travis/runflake8.sh:
#
#       - RUN_FLAKE8_DISABLED
#       - RUN_FLAKE8_IGNORE
#
#   * .travis/runsyspycmd.sh:
#
#       - function lsr_runsyspycmd_hook

RUN_BLACK_DISABLED=true
RUN_FLAKE8_DISABLED=true

# do not run pytest with python 2.6

case $0 in
    *runpytest.sh) if lsr_check_python_version python -lt 2.7 ; then
                       exit 0
                   fi ;;
esac
