from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

DECIMAL_FACTOR = 10**3
BINARY_FACTOR = 2**10

# index of the item in the list determines the exponent for size computation
# e.g. size_in_bytes = value * (DECIMAL_FACTOR ** (index(mega)+1)) = value * (1000 ** (1+1))
PREFIXES_DECIMAL = [
    ["k", "M", "G", "T", "P", "E", "Z", "Y"],
    ["kilo", "mega", "giga", "tera", "peta", "exa", "zetta", "yotta"],
]
PREFIXES_BINARY = [
    ["Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi", "Yi"],
    ["kibi", "mebi", "gibi", "tebi", "pebi", "exbi", "zebi", "yobi"],
]
SUFFIXES = ["bytes", "byte", "B"]


class Size(object):
    """Class for basic manipulation of the sizes in *bytes"""

    def __init__(self, value):
        raw_number, raw_units = self._parse_input(str(value))
        self.factor, self.exponent = self._parse_units(raw_units)
        self.number = self._parse_number(raw_number)

        self.units = raw_units

    def _parse_input(self, value):
        """splits input string into number and unit parts
        returns number part, unit part
        """
        m = re.search("^(.*?)([^0-9]*)$", value)

        raw_number = m.group(1).strip()
        if raw_number == "":
            raise ValueError("The string '%s' does not contain size" % value)

        raw_units = m.group(2).strip()

        return raw_number, raw_units

    def _parse_units(self, raw_units):
        """
        gets string containing size units and
        returns *_FACTOR (BINARY or DECIMAL) and the prefix position (not index!)
        in the PREFIXES_* list
        If no unit is specified defaults to BINARY and Bytes
        """

        prefix = raw_units
        no_suffix_flag = True
        valid_suffix = False
        used_factor = BINARY_FACTOR

        # get rid of possible units suffix ('bytes', 'b' or 'B')
        for suffix in SUFFIXES:
            if raw_units.lower().endswith(suffix.lower()):
                no_suffix_flag = False
                prefix = raw_units[: -len(suffix)]
                break

        if prefix == "":
            # no unit was specified, use default
            return BINARY_FACTOR, 0

        # check the list for units
        idx = -1

        for lst in PREFIXES_DECIMAL:
            lower_lst = [x.lower() for x in lst]
            if prefix.lower() in lower_lst:
                valid_suffix = True
                idx = lower_lst.index(prefix.lower())
                used_factor = DECIMAL_FACTOR
                break

        if idx < 0 or no_suffix_flag:
            if no_suffix_flag:
                used_factor = BINARY_FACTOR

            for lst in PREFIXES_BINARY:
                lower_lst = [x.lower() for x in lst]
                if prefix.lower() in lower_lst:
                    valid_suffix = True
                    idx = lower_lst.index(prefix.lower())
                    used_factor = BINARY_FACTOR
                    break

        if idx < 0 or not valid_suffix:
            raise ValueError("Unable to identify unit '%s'" % raw_units)

        return used_factor, idx + 1

    def _parse_number(self, raw_number):
        """parse input string containing number
        return float
        """
        return float(raw_number)

    def _get_unit(self, factor, exponent, unit_type=0):
        """based on decimal or binary factor and exponent
        obtain and return correct unit
        """

        if unit_type == 0:
            suffix = "B"
        else:
            suffix = "bytes"

        if exponent == 0:
            return suffix

        if factor == DECIMAL_FACTOR:
            prefix_lst = PREFIXES_DECIMAL[unit_type]
        else:
            prefix_lst = PREFIXES_BINARY[unit_type]
        return prefix_lst[exponent - 1] + suffix

    @property
    def bytes(self):
        """returns size value in bytes as int"""
        return int((self.factor**self.exponent) * self.number)

    def _format(self, format_str, factor, exponent):
        result = format_str
        result = result.replace(r"%sb", self._get_unit(factor, exponent, 0))
        result = result.replace(r"%lb", self._get_unit(factor, exponent, 1))

        return result

    def get(self, units="autobin", fmt="%0.1f %sb"):
        """returns size value as a string with given units and format

        "units" parameter allows to select preferred unit:
            for example "KiB" or "megabytes"
            accepted values are also:
            "autobin" (default) - uses the highest human readable unit (binary)
            "autodec" - uses the highest human readable unit (decimal)

        "fmt" parameter allows to specify the output format:
            %sb - will be replaced with the short byte size unit (e.g. MiB)
            %lb - will be replaced with the long byte size unit (e.g. kilobytes)
            value can be formatted using standard string replacements (e.g. %d, %f)

        """

        ftr = BINARY_FACTOR
        if units == "autodec":
            ftr = DECIMAL_FACTOR
        if units in ("autobin", "autodec"):
            exp = 0
            value = float(self.bytes)
            while value + 0.01 > ftr:  # + 0.01 to balance the float comparison
                value /= ftr
                exp += 1
        else:
            ftr, exp = self._parse_units(units.strip())
            value = (
                float(self.factor**self.exponent) / float(ftr**exp)
            ) * self.number

        return self._format(fmt, ftr, exp) % value
