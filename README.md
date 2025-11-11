# CSAF-Netbox-Plugin

## Configuration

It is important to add the `csaf` plugin before the `d3c` plugin in the Netbox configuration:

```
PLUGINS = ["csaf","d3c"]
```

The following options must be configured as well:

```
PLUGINS_CONFIG = {
  'csaf': {
    'isduba': {
      'keycloak_url': '<Base URL of KeyCloak used by IsDuBa>',
      'keycloak_verify_ssl': False,
      'username': '<user name>',
      'password': '<user password>'
    },
    'synchronisers': {
      'username': 'admin',
      'password': 'admin',
      'verify_ssl': False,
      'urls': [
        {
          'name': 'ISDuBA Sync',
          'url': 'http://127.0.0.1:8991/'
        },
        {
          'name': 'Netbox Sync',
          'url': 'http://127.0.0.1:8992/'
        },
        {
          'name': 'CSAF Matcher',
          'url': 'http://127.0.0.1:8998/',
          'type': 'matcher'
        },
      ]
    }
  }
}
```
