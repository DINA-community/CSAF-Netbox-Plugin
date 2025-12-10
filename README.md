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
      'username': '<user name for KeyCloak>',
      'password': '<user password for KeyCloak>'
    },
    'synchronisers': {
      'username': '<user name for synchronisers/matchers>',
      'password': '<password for synchronisers/matchers>',
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
          'isMatcher': True,
          'netboxBaseUrl': 'http://localhost:8000',
        },
      ]
    }
  }
}
```

The `username` and `password` for Synchronisers and Matcher can be overridden on a per-matcher basis.
The `netboxBaseUrl` of the CSAF Matcher must be set to the url of Netbox as the Matcher sees it.
