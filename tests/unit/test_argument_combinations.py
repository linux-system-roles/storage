from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest
import storage_lsr.argument_validator as av

def test_validate_item():

    spec = {'key': {'default': 'default_value'}}

    # Test list type value
    # Any non-list variable should be converted to single item list
    spec['key']['type'] = 'list'
    param = {'key': 'yes'}
    assert av.ArgValidator.validate_item(spec, param, 'key') == [param['key']]

    # Test int type value
    spec['key']['type'] = 'int'
    param = {'key': 32767}
    assert av.ArgValidator.validate_item(spec, param, 'key') == param['key']

    param = {'key': 'yes'}
    with pytest.raises(TypeError) as e:
        av.ArgValidator.validate_item(spec, param, 'key')
    assert "has to be an integer" in str(e.value)

    # Test float type value
    spec['key']['type'] = 'float'
    param = {'key': 2.5}
    assert av.ArgValidator.validate_item(spec, param, 'key') == param['key']

    param = {'key': 'yes'}
    with pytest.raises(TypeError) as e:
        av.ArgValidator.validate_item(spec, param, 'key')
    assert "has to be a float" in str(e.value)

    # Test bool type value
    # Acceptable values like 'yes', 'off', 1, 'n'... should be normalized to True/False
    spec['key']['type'] = 'bool'
    param = {'key': 'no'}
    assert av.ArgValidator.validate_item(spec, param, 'key') == False

    param = {'key': 'probably'}
    with pytest.raises(TypeError) as e:
        av.ArgValidator.validate_item(spec, param, 'key')
    assert "has to be convertable to a bool" in str(e.value)


    spec['key']['choices'] = ['yes', 'no']
    spec['key']['type'] = 'str'
    param = {'key': 'yes'}
    assert av.ArgValidator.validate_item(spec, param, 'key') == param['key']

    param = {}
    assert av.ArgValidator.validate_item(spec, param, 'key') == spec['key']['default']

    param = {'key': 'whatever'}
    with pytest.raises(ValueError) as e:
        av.ArgValidator.validate_item(spec, param, 'key')
    assert "has to be one of" in str(e.value)

def test_validate_list():

    # Verify that list values are normalized (mainly for bool vars; e.g. 'yes' => True)
    spec_type = 'bool'
    assert all(av.ArgValidator.validate_list(spec_type, av.BOOLEANS_TRUE))
    assert not any(av.ArgValidator.validate_list(spec_type, av.BOOLEANS_FALSE))

    invalid_bool_list = ['maybe', 'probably', 'nah']
    with pytest.raises(TypeError) as e:
        av.ArgValidator.validate_list(spec_type, invalid_bool_list)
    assert "has to be convertable to a bool" in str(e.value)

def test__validate_parameters():

    arg_spec = dict(
        pools=dict(type='list', elements='dict',
                   options=dict(disks=dict(type='list', elements='str', default=list()),
                                encryption=dict(type='bool'),
                                state=dict(type='str', default='present', choices=['present', 'absent']),
                                type=dict(type='str'))))

    parameters = {'pools': [{'name': 'pool1'}]}
    error_log, updated_params = av._validate_parameters(arg_spec, parameters)
    assert error_log == []
    assert updated_params == {'pools': [{'disks': [], 'encryption': None, 'state': 'present', 'type': None}]}

    parameters = {}
    error_log, updated_params = av._validate_parameters(arg_spec, parameters)
    assert error_log == []
    assert updated_params == {'pools': []}

    parameters = {'pools': [{'encryption': 'invalid'}]}
    error_log, updated_params = av._validate_parameters(arg_spec, parameters)
    assert "has to be convertable to a bool" in str(error_log[0])
    assert updated_params == {'pools': [{'disks': [], 'encryption': 'ERROR', 'state': 'present', 'type': None}]}

def test_locate_parameter():

    params = {'pools': [{'disks': [{'name': 'disk1', 'type': 'xfs'}, {'name': 'disk2', 'type': 'xfs'}], 'type': None}]}

    # Check for multiple different value matches
    path = ['pools', 'disks', 'name']
    values = ['disk1', 'disk2']
    assert av.locate_parameter(params, path, values) == {'path': ['pools', 'disks', 'name'], 'indices': [[0, 1, None], [0, 0, None]]}

    # Check for multiple same value matches
    # Also make sure duplicate parameter names (i.e. 'pools.type') are not included in the result
    path = ['pools', 'disks', 'type']
    values = ['xfs']
    assert av.locate_parameter(params, path, values) == {'path': ['pools', 'disks', 'type'], 'indices': [[0, 1, None], [0, 0, None]]}

    # Check for parameter, any value
    path = ['pools', 'disks', 'name']
    values = []
    assert av.locate_parameter(params, path, values) == {'path': ['pools', 'disks', 'name'], 'indices': [[0, 1, None], [0, 0, None]]}

    # Check for parameter, non-present value
    path = ['pools', 'disks', 'name']
    values = ['unused_disk_name']
    assert av.locate_parameter(params, path, values) is None

    # Check for unused parameter, specific values
    path = ['pools', 'unused_param_name']
    values = ['Anthony', 'J.', 'Crowley']
    assert av.locate_parameter(params, path, values) is None

    # Check for unused parameter, any value
    path = ['pools', 'unused_param_name']
    values = []
    assert av.locate_parameter(params, path, values) is None

def test_generate_combinations():
    # Verify that function produces all combinations of indices but prunes out
    # 'invalid' ones
    # Example: 
    #   Forbidden combo: pools.encryption and pools.volumes.vdo
    #   Input: pools.encryption found at pool[0].encryption and
    #                                    pool[1].encryption
    #          pools.disks.vdo found at pool[0].volumes[1].vdo and
    #                                   pool[1].volumes[0].vdo
    #   All combinations based on indices:
    #          [0,None]+[0,1,None] => possible combo => include to result
    #          [0,None]+[1,0,None] => different first index (pool) => skip
    #          [1,None]+[0,1,None] => different first index (pool) => skip
    #          [1,None]+[1,0,None] => possible combo => include to result
    match = [{'path': ['pools', 'encryption'], 'indices': [[0, None], [1, None]],
              'backtrack_indices':[]},
             {'path': ['pools', 'volumes', 'vdo'], 'indices': [[0, 1, None], [1, 0, None]],
              'backtrack_indices':[]}]

    assert av.generate_combinations(match) == [[{'path': ['pools', 'encryption'],
                                              'indices': [1, None], 'backtrack_indices': []},
                                             {'path': ['pools', 'volumes', 'vdo'],
                                              'indices': [1, 0, None], 'backtrack_indices': []}],
                                            [{'path': ['pools', 'encryption'],
                                              'indices': [0, None], 'backtrack_indices': []},
                                             {'path': ['pools', 'volumes', 'vdo'],
                                              'indices': [0, 1, None], 'backtrack_indices': []}]]

def test_check_param_combos():

    arg_spec = dict(
        pools=dict(type='list', elements='dict',
                   options=dict(volumes=dict(type='list', elements='dict',
                                             options=dict(vdo=dict(type='bool'))),
                                encryption=dict(type='bool'),
                                state=dict(type='str', default='present', choices=['present', 'absent']),
                                type=dict(type='str'))))

    parameters = {'pools': [{'encryption': 'yes', 'volumes': [{'vdo': 'false'}, {'vdo': 'true'}]},
                            {'encryption': 'yes', 'volumes': [{'vdo': 'yes'}]}]}

    errors, up_params = av._validate_parameters(arg_spec, parameters)

    av.UNSUPPORTED_COMBOS = [{'options': {'pools.encryption': av.BOOLEANS_TRUE,
                                       'pools.volumes.vdo': av.BOOLEANS_TRUE},
                          'err_msg': "Deduplication is not supported on encrypted volumes"}]

    assert av.check_param_combos(up_params) == [{'matches': [['pools[1].encryption', 'pools[1].volumes[0].vdo'],
                                                             ['pools[0].encryption', 'pools[0].volumes[1].vdo']],
                                                 'msg': 'Deduplication is not supported on encrypted volumes'}]

