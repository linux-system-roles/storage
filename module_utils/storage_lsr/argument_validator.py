from __future__ import absolute_import, division, print_function

import sys

__metaclass__ = type

# pylint: disable=undefined-variable
STRING_TYPE = str if sys.version_info.major == 3 else basestring  # noqa:F821

BOOLEANS_TRUE = ['y', 'yes', 'on', '1', 'true', 't', 1, 1.0, True]
BOOLEANS_FALSE = ['n', 'no', 'off', '0', 'false', 'f', 0, 0.0, False]

# Combinations of parameters (and their values) that will raise exception
# use [] if value does not matter

# example: {'options': {'pools.encryption:[True]', pools.volumes.deduplication:[True]}, 'err_msg:' 'deduplication cannot be used with encryption'}
UNSUPPORTED_COMBOS = [{'options': {'pools.volumes.encryption': BOOLEANS_TRUE,
                                   'pools.volumes.deduplication': BOOLEANS_TRUE},
                       'err_msg': "Deduplication is not supported on encrypted volumes"},
                      {'options': {'pools.volumes.encryption': BOOLEANS_TRUE,
                                   'pools.volumes.compression': BOOLEANS_TRUE},
                       'err_msg': "Compression is not supported on encrypted volumes"},
                      {'options': {'pools.volumes.thin': BOOLEANS_TRUE,
                                   'pools.volumes.compression': BOOLEANS_TRUE},
                       'err_msg': "Dedupliation is not supported on thin pool volumes"},
                      {'options': {'pools.volumes.thin': BOOLEANS_TRUE,
                                   'pools.volumes.deduplication': BOOLEANS_TRUE},
                       'err_msg': "Compression is not supported on thin pool volumes"}]


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


def _validate_parameters(argument_spec, parameters, error_log=None, updated_params=None):
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
                errors, up_params = _validate_parameters(value['options'], parameters[spec])
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
                    errors, up_params = _validate_parameters(value['options'], item)
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


def generate_combinations(input_list):
    # Create list of all valid combinations of parameters
    # (Note: 'valid' means 'worth exploring')

    # Fill in the stack with the first item to expand
    stack = [[{'path': input_list[0]['path'],
               'indices': x,
               'backtrack_indices': input_list[0]['backtrack_indices']}]
             for x in input_list[0]['indices']]

    result = []

    while stack:
        sequence = stack.pop()
        for item in input_list[len(sequence)]['indices']:
            new_sequence = sequence + [{'path': input_list[len(sequence)]['path'],
                                        'indices': item,
                                        'backtrack_indices': input_list[len(sequence)]['backtrack_indices']}]
            if len(new_sequence) < len(input_list):
                stack.append(new_sequence)
            else:
                # sequence is complete, now to make sure the combination is valid

                # 'valid' means that all the same path roots have the same indices
                indices_pairs = {}
                for rule in new_sequence:
                    encountered_index = indices_pairs.get(rule['path'][0], -1)
                    if encountered_index == -1:
                        # path not yet encountered
                        indices_pairs[rule['path'][0]] = rule['indices'][0]
                    elif encountered_index != rule['indices'][0]:
                        # invalid combination
                        break
                else:
                    # for loop ended without break - combination is valid
                    result.append(new_sequence)

    return result


def locate_parameter(params, path, param_value):
    # path: complete path of searched parameter e.g. "['pools', 'volumes', 'deduplication']"
    # param_value: list of searched values or [] if value doesn't matter
    # returns list of "hash" of matching items or [] when not found

    # Stack. Each item consists of
    # - "value"   - (part of) nested dictionary
    # - "level"   - depth of nest (e.g. for "pool[1].volume[0].size": level=1 ~ "pool[1].volume[0]")
    # - "indices" - list of indices (e.g. for "pool[1].volume[0].size": indices == [1, 0, None])
    stack = [{'value': params, 'level': 0, 'indices': []}]
    result = {'path': path, 'indices': []}

    while stack:

        stack_item = stack.pop()

        if stack_item['level'] < len(path):

            path_step = path[stack_item['level']]
            # Expand stack item
            item = stack_item['value'].get(path_step)

            if isinstance(item, list):
                # Push each list item back into the stack
                for idx in range(len(item)):
                    stack.append({'value': item[idx],
                                  'level': stack_item['level'] + 1,
                                  'indices': stack_item['indices'] + [idx]})
            else:
                # Push expanded item back into the stack
                stack.append({'value': item,
                              'level': stack_item['level'] + 1,
                              'indices': stack_item['indices'] + [None]})
        else:
            # The end of given path
            if param_value == list() or stack_item['value'] in param_value:
                result['indices'].append(stack_item['indices'])

    if result['indices'] == []:
        return None

    return result


def format_result(combo):
    rules_list = list()
    for rule in combo:
        path_list = rule['path'][0].split('.')
        indices = rule['backtrack_indices']

        rule_str = ""
        for i in range(len(path_list)):
            rule_str += path_list[i]
            if i < len(indices) and indices[i] is not None:
                rule_str += '[' + str(indices[i]) + ']'
            rule_str += '.'
        rules_list.append(rule_str[:-1])
    return rules_list


def check_param_combos(params):
    all_combos = list()

    for combo in UNSUPPORTED_COMBOS:

        found_combos = list()
        recorded_matches = list()

        for key, value in combo['options'].items():
            found = locate_parameter(params, key.split('.'), value)
            if found is None:
                # Locate found nothing => the whole combo is clean, no need to continue
                break
            else:
                recorded_matches.append(found)
        else:
            # No break happened in loop => need to check result combinations

            for match in recorded_matches:
                match['backtrack_indices'] = list()

            stack = [recorded_matches]

            while stack:
                match = stack.pop()
                combinations = generate_combinations(match)

                # It is now possible to dive by shifting the root one level
                for combination in combinations:
                    shifted_combo = list()
                    combo_found = True
                    for rule in combination:
                        if len(rule['path']) > 1:
                            path = rule['path'][1:]
                            path[0] = rule['path'][0] + '.' + path[0]
                            indices = [rule['indices'][1:]]
                            backtrack_indices = rule['backtrack_indices'] + [rule['indices'][0]]
                            combo_found = False
                        else:
                            path = rule['path']
                            indices = [rule['indices']]
                            backtrack_indices = rule['backtrack_indices']

                        shifted_combo.append({'path': path,
                                              'indices': indices,
                                              'backtrack_indices': backtrack_indices})

                    if combo_found:
                        # Forbidden combination of parameters confirmed
                        found_combos.append(format_result(combination))
                    else:
                        stack.append(shifted_combo)
        if found_combos != list():
            all_combos.append({'matches': found_combos, 'msg': combo['err_msg']})

    return all_combos


def validate_parameters(argument_spec, parameters, error_log=None, updated_params=None):

    errors, up_params = _validate_parameters(argument_spec, parameters)

    found_combos = check_param_combos(up_params)
    for combo in found_combos:
        errors.append('%s: %s' % (combo['msg'], combo['matches']))

    return errors, up_params
