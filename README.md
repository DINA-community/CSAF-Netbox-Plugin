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
      'isduba_keycloak_url': '<Base URL of KeyCloak used by IsDuBa>',
      'isduba_keycloak_verify_ssl': False,
      'isduba_username': 'user',
      'isduba_password': 'user'
  }
}
```
