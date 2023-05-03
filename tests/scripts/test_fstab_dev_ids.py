import json
import subprocess
import sys


def find_dev_in_fstab(dev, fstab):
    # check whether some device representation is present in the fstab
    if not dev:
        raise ValueError("No device given")

    # dev can be represented by string starting with description followed by '=' (e.g. UUID=<something>)
    pair = dev.split('=')
    prefix = "/dev/disk/by-*/"

    if len(pair) == 1:
        dev_id = pair[0]
        if dev_id.startswith('/'):
            prefix = ""
    else:
        dev_id = pair[1]

    cmd_output = subprocess.run("lsblk --list -Jno PATH,UUID,PARTUUID,LABEL,PARTLABEL %s%s" % (prefix, dev_id),
                                shell=True,
                                stdout=subprocess.PIPE,
                                text=True,
                                check=False)

    if cmd_output.stderr:
        raise ValueError("Lsblk command failed: %s" % cmd_output.stderr)

    blockdevices = json.loads(cmd_output.stdout)['blockdevices']

    exact_matches = 0
    partial_matches = 0

    for bdev in blockdevices:
        for key in ['path', 'uuid', 'partuuid', 'label', 'partlabel']:
            if bdev[key] is not None and bdev[key] in fstab:
                if dev_id == bdev[key]:
                    exact_matches += 1
                else:
                    partial_matches += 1

    return exact_matches, partial_matches


def main(args):
    if len(args) < 2:
        raise ValueError("Missing arguments")

    dev = args[1]

    # This is an ugly stuff but it will work for the testing purposes
    fstab = ' '.join(args[2:])

    exact_matches, partial_matches = find_dev_in_fstab(dev, fstab)

    print(exact_matches, partial_matches)


if __name__ == "__main__":
    main(sys.argv)
