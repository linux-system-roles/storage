#!/bin/bash
# SPDX-License-Identifier: MIT

# This script is executed with two arguments passed to it:
#
#   $1 - full path to environment python (python used inside virtual
#        environment created by tox)
#   $2 - full path to system python (python 3.x installed on the system)

set -e

ME=$(basename $0)
SCRIPTDIR=$(readlink -f $(dirname $0))
TOPDIR=$(readlink -f ${SCRIPTDIR}/..)

# Include library and config:
. ${SCRIPTDIR}/utils.sh
. ${SCRIPTDIR}/config.sh

ENVPYTHON=$1
SYSPYTHON=$2
shift 2

# Write your custom commands here that should be run when `tox -e custom`:
