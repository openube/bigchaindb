import copy
from unittest.mock import mock_open, patch

import pytest

import bigchaindb


ORIGINAL_CONFIG = copy.deepcopy(bigchaindb._config)


@pytest.fixture(scope='function', autouse=True)
def clean_config(monkeypatch, request):

    import bigchaindb
    original_config = copy.deepcopy(ORIGINAL_CONFIG)
    backend = request.config.getoption('--database-backend')
    original_config['database'] = bigchaindb._database_map[backend]
    monkeypatch.setattr('bigchaindb.config', original_config)


def test_bigchain_instance_is_initialized_when_conf_provided(request):
    import bigchaindb
    from bigchaindb import config_utils
    assert 'CONFIGURED' not in bigchaindb.config

    config_utils.set_config({'keypair': {'public': 'a', 'private': 'b'}})

    assert bigchaindb.config['CONFIGURED'] is True

    b = bigchaindb.Bigchain()

    assert b.me
    assert b.me_private


def test_bigchain_instance_raises_when_not_configured(request, monkeypatch):
    import bigchaindb
    from bigchaindb import config_utils
    from bigchaindb.common import exceptions
    assert 'CONFIGURED' not in bigchaindb.config

    # We need to disable ``bigchaindb.config_utils.autoconfigure`` to avoid reading
    # from existing configurations
    monkeypatch.setattr(config_utils, 'autoconfigure', lambda: 0)

    with pytest.raises(exceptions.KeypairNotFoundException):
        bigchaindb.Bigchain()


def test_load_consensus_plugin_loads_default_rules_without_name():
    from bigchaindb import config_utils
    from bigchaindb.consensus import BaseConsensusRules

    assert config_utils.load_consensus_plugin() == BaseConsensusRules


def test_load_consensus_plugin_raises_with_unknown_name():
    from pkg_resources import ResolutionError
    from bigchaindb import config_utils

    with pytest.raises(ResolutionError):
        config_utils.load_consensus_plugin('bogus')


def test_load_consensus_plugin_raises_with_invalid_subclass(monkeypatch):
    # Monkeypatch entry_point.load to return something other than a
    # ConsensusRules instance
    from bigchaindb import config_utils
    import time
    monkeypatch.setattr(config_utils,
                        'iter_entry_points',
                        lambda *args: [type('entry_point', (object), {'load': lambda: object})])

    with pytest.raises(TypeError):
        # Since the function is decorated with `lru_cache`, we need to
        # "miss" the cache using a name that has not been used previously
        config_utils.load_consensus_plugin(str(time.time()))


def test_map_leafs_iterator():
    from bigchaindb import config_utils

    mapping = {
        'a': {'b': {'c': 1},
              'd': {'z': 44}},
        'b': {'d': 2},
        'c': 3
    }

    result = config_utils.map_leafs(lambda x, path: x * 2, mapping)
    assert result == {
        'a': {'b': {'c': 2},
              'd': {'z': 88}},
        'b': {'d': 4},
        'c': 6
    }

    result = config_utils.map_leafs(lambda x, path: path, mapping)
    assert result == {
        'a': {'b': {'c': ['a', 'b', 'c']},
              'd': {'z': ['a', 'd', 'z']}},
        'b': {'d': ['b', 'd']},
        'c': ['c']
    }


def test_update_types():
    from bigchaindb import config_utils

    raw = {
        'a_string': 'test',
        'an_int': '42',
        'a_float': '3.14',
        'a_list': 'a:b:c',
    }

    reference = {
        'a_string': 'test',
        'an_int': 42,
        'a_float': 3.14,
        'a_list': ['a', 'b', 'c'],
    }

    result = config_utils.update_types(raw, reference)
    assert result == reference


def test_env_config(monkeypatch):
    monkeypatch.setattr('os.environ', {'BIGCHAINDB_DATABASE_HOST': 'test-host',
                                       'BIGCHAINDB_DATABASE_PORT': 'test-port'})

    from bigchaindb import config_utils

    result = config_utils.env_config({'database': {'host': None, 'port': None}})
    expected = {'database': {'host': 'test-host', 'port': 'test-port'}}

    assert result == expected


def test_autoconfigure_read_both_from_file_and_env(monkeypatch, request):
    # constants
    DATABASE_HOST = 'test-host'
    DATABASE_NAME = 'test-dbname'
    DATABASE_PORT = 4242
    DATABASE_BACKEND = request.config.getoption('--database-backend')
    SERVER_BIND = '1.2.3.4:56'
    KEYRING = 'pubkey_0:pubkey_1:pubkey_2'

    file_config = {
        'database': {
            'host': DATABASE_HOST
        },
        'backlog_reassign_delay': 5
    }
    monkeypatch.setattr('bigchaindb.config_utils.file_config', lambda *args, **kwargs: file_config)
    monkeypatch.setattr('os.environ', {'BIGCHAINDB_DATABASE_NAME': DATABASE_NAME,
                                       'BIGCHAINDB_DATABASE_PORT': str(DATABASE_PORT),
                                       'BIGCHAINDB_DATABASE_BACKEND': DATABASE_BACKEND,
                                       'BIGCHAINDB_SERVER_BIND': SERVER_BIND,
                                       'BIGCHAINDB_KEYRING': KEYRING})

    import bigchaindb
    from bigchaindb import config_utils
    config_utils.autoconfigure()

    database_rethinkdb = {
        'backend': 'rethinkdb',
        'host': DATABASE_HOST,
        'port': DATABASE_PORT,
        'name': DATABASE_NAME,
        'connection_timeout': 5000,
        'max_tries': 3
    }

    database_mongodb = {
        'backend': 'mongodb',
        'host': DATABASE_HOST,
        'port': DATABASE_PORT,
        'name': DATABASE_NAME,
        'connection_timeout': 5000,
        'max_tries': 3,
        'replicaset': 'bigchain-rs',
    }

    database = {}
    if DATABASE_BACKEND == 'mongodb':
        database = database_mongodb
    elif DATABASE_BACKEND == 'rethinkdb':
        database = database_rethinkdb

    assert bigchaindb.config == {
        'CONFIGURED': True,
        'server': {
            'bind': SERVER_BIND,
            'workers': None,
            'threads': None,
        },
        'database': database,
        'keypair': {
            'public': None,
            'private': None,
        },
        'keyring': KEYRING.split(':'),
        'backlog_reassign_delay': 5
    }


def test_autoconfigure_env_precedence(monkeypatch):
    file_config = {
        'database': {'host': 'test-host', 'name': 'bigchaindb', 'port': 28015}
    }
    monkeypatch.setattr('bigchaindb.config_utils.file_config', lambda *args, **kwargs: file_config)
    monkeypatch.setattr('os.environ', {'BIGCHAINDB_DATABASE_NAME': 'test-dbname',
                                       'BIGCHAINDB_DATABASE_PORT': '4242',
                                       'BIGCHAINDB_SERVER_BIND': 'localhost:9985'})

    import bigchaindb
    from bigchaindb import config_utils
    config_utils.autoconfigure()

    assert bigchaindb.config['CONFIGURED']
    assert bigchaindb.config['database']['host'] == 'test-host'
    assert bigchaindb.config['database']['name'] == 'test-dbname'
    assert bigchaindb.config['database']['port'] == 4242
    assert bigchaindb.config['server']['bind'] == 'localhost:9985'


def test_update_config(monkeypatch):
    import bigchaindb
    from bigchaindb import config_utils

    file_config = {
        'database': {'host': 'test-host', 'name': 'bigchaindb', 'port': 28015}
    }
    monkeypatch.setattr('bigchaindb.config_utils.file_config', lambda *args, **kwargs: file_config)
    config_utils.autoconfigure(config=file_config)

    # update configuration, retaining previous changes
    config_utils.update_config({'database': {'port': 28016, 'name': 'bigchaindb_other'}})

    assert bigchaindb.config['database']['host'] == 'test-host'
    assert bigchaindb.config['database']['name'] == 'bigchaindb_other'
    assert bigchaindb.config['database']['port'] == 28016


def test_file_config():
    from bigchaindb.config_utils import file_config, CONFIG_DEFAULT_PATH
    with patch('builtins.open', mock_open(read_data='{}')) as m:
        config = file_config()
    m.assert_called_once_with(CONFIG_DEFAULT_PATH)
    assert config == {}


def test_invalid_file_config():
    from bigchaindb.config_utils import file_config
    from bigchaindb.common import exceptions
    with patch('builtins.open', mock_open(read_data='{_INVALID_JSON_}')):
        with pytest.raises(exceptions.ConfigurationError):
            file_config()


def test_write_config():
    from bigchaindb.config_utils import write_config, CONFIG_DEFAULT_PATH
    m = mock_open()
    with patch('builtins.open', m):
        write_config({})
    m.assert_called_once_with(CONFIG_DEFAULT_PATH, 'w')
    handle = m()
    handle.write.assert_called_once_with('{}')


@pytest.mark.parametrize('env_name,env_value,config_key', (
    ('BIGCHAINDB_DATABASE_BACKEND', 'test-backend', 'backend'),
    ('BIGCHAINDB_DATABASE_HOST', 'test-host', 'host'),
    ('BIGCHAINDB_DATABASE_PORT', 4242, 'port'),
    ('BIGCHAINDB_DATABASE_NAME', 'test-db', 'name'),
))
def test_database_envs(env_name, env_value, config_key, monkeypatch):
    import bigchaindb

    monkeypatch.setattr('os.environ', {env_name: env_value})
    bigchaindb.config_utils.autoconfigure()

    expected_config = copy.deepcopy(bigchaindb.config)
    expected_config['database'][config_key] = env_value

    assert bigchaindb.config == expected_config


def test_database_envs_replicaset(monkeypatch):
    # the replica set env is only used if the backend is mongodb
    import bigchaindb

    monkeypatch.setattr('os.environ', {'BIGCHAINDB_DATABASE_REPLICASET':
                                       'test-replicaset'})
    bigchaindb.config['database'] = bigchaindb._database_mongodb
    bigchaindb.config_utils.autoconfigure()

    expected_config = copy.deepcopy(bigchaindb.config)
    expected_config['database']['replicaset'] = 'test-replicaset'

    assert bigchaindb.config == expected_config
