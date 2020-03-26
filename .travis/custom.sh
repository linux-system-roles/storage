#!/bin/bash
# SPDX-License-Identifier: MIT

set -e

ME=$(basename $0)
SCRIPTDIR=$(readlink -f $(dirname $0))

. ${SCRIPTDIR}/utils.sh
. ${SCRIPTDIR}/config.sh

# Write your custom commands here that should be run when `tox -e custom`:
