from __future__ import absolute_import, division, print_function

import sys

__metaclass__ = type

# pylint: disable=undefined-variable
STRING_TYPE = str if sys.version_info.major == 3 else basestring  # noqa:F821


class ArgValidator(object):

    @classmethod
    def _validate_list(cls, value):
        if isinstance(value, list):
            return value

        if isinstance(value, STRING_TYPE):
            return value.split(",")

        if isinstance(value, int) or isinstance(value, float):
            return [value]

        raise TypeError("'%s' has to be a list" % value)

    @classmethod
    def _validate_str(cls, value):
        return str(value)

    @classmethod
    def _validate_bool(cls, value):
        BOOLEANS_TRUE = ['y', 'yes', 'on', '1', 'true', 't', 1, 1.0, True]
        BOOLEANS_FALSE = ['n', 'no', 'off', '0', 'false', 'f', 0, 0.0, False]

        if value in BOOLEANS_TRUE:
            return True
        if value in BOOLEANS_FALSE:
            return False
        if value is None:
            return None
        raise TypeError("'%s' has to be convertable to a bool" % value)

    @classmethod
    def _validate_int(cls, value):
        try:
            return int(value)
        except ValueError:
            raise TypeError("'%s' has to be an integer" % value)

    @classmethod
    def _validate_float(cls, value):
        try:
            return float(value)
        except ValueError:
            raise TypeError("'%s' has to be a float" % value)

    @classmethod
    def validate_item(cls, spec, param, key):
        # validate and return normalized value of a given parameter based on spec
        # raises TypeError, ValueError on failure

        if key not in param or param[key] is None:
            # if the parameter is not specified, use default if defined
            return spec[key].get('default', None)

        choices = spec[key].get('choices')
        if choices is not None and param[key] not in choices:
            raise ValueError("'%s' has to be one of: %s" % (param[key], ', '.join(choices)))

        validate = cls.VALIDATION_TYPE_DISPATCHER[spec[key].get('type', 'str')]

        normalized_value = validate(param[key])

        return normalized_value

    @classmethod
    def validate_list(cls, spec_type, values):
        # raises TypeError, ValueError on failure

        normalized_list = list()
        for value in values:
            validate = cls.VALIDATION_TYPE_DISPATCHER[spec_type]
            normalized_value = validate(value)
            normalized_list.append(normalized_value)

        return normalized_list


ArgValidator.VALIDATION_TYPE_DISPATCHER = dict(list=ArgValidator._validate_list,
                                               str=ArgValidator._validate_str,
                                               bool=ArgValidator._validate_bool,
                                               int=ArgValidator._validate_int,
                                               float=ArgValidator._validate_float)


def validate_parameters(argument_spec, parameters, error_log=None, updated_params=None):
    # recursively validate and normalize all parameters based on argument specifications

    if error_log is None:
        error_log = list()
    if updated_params is None:
        updated_params = dict()

    for spec, value in argument_spec.items():

        if spec not in parameters:
            # normalize unused parameters
            try:
                # value is not defined, try to use default
                updated_params[spec] = value['default']
                # cannot use value.get('default', *); * could be the default
            except KeyError:
                # value is not defined and has no default value
                if value['type'] == 'list':
                    updated_params[spec] = list()
                elif value['type'] == 'dict':
                    updated_params[spec] = dict()
                else:
                    updated_params[spec] = None

        elif value.get('type') == 'dict':
            if 'options' not in value:
                # generic dict, no way to check its contents
                updated_params[spec] = parameters[spec]
            else:
                # nested dict
                errors, up_params = validate_parameters(value['options'], parameters[spec])
                if errors:
                    # recursion will build prefixes of the error messages
                    errors = [spec + '->' + x for x in errors]
                    error_log.extend(errors)
                updated_params[spec] = up_params

        elif value.get('type') == 'list':
            if 'options' in value and value.get('elements', '') == 'dict':
                # nested list of dicts
                updated_params[spec] = list()
                for item in parameters[spec]:
                    errors, up_params = validate_parameters(value['options'], item)
                    if errors:
                        # recursion will build prefixes of the error messages
                        errors = [spec + '->' + x for x in errors]
                        error_log.extend(errors)
                    updated_params[spec].append(up_params)
            elif 'elements' not in value:
                # generic list, no way to check its contents
                updated_params[spec] = parameters[spec]
            else:
                # list of items of defined type
                try:
                    normalized_list = ArgValidator.validate_list(value['elements'], parameters[spec])
                except (TypeError, ValueError) as e:
                    normalized_list = "ERROR"
                    error_log.append(spec + ': ' + str(e))

                updated_params[spec] = normalized_list

        else:
            # ordinary type
            try:
                normalized_value = ArgValidator.validate_item(argument_spec, parameters, spec)
            except (TypeError, ValueError) as e:
                normalized_value = "ERROR"
                error_log.append(spec + ': ' + str(e))

            updated_params[spec] = normalized_value

    return (error_log, updated_params)
