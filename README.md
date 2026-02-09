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
          'netboxBaseUrl': 'http://localhost:8000', # The base URL of Netbox as the Matcher sees it.
           'isdubaBaseUrl': 'http://localhost:5371',  # The base URL of ISDuBA as the Matcher sees it.
        },
      ]
    }
  }
}
```

The `username` and `password` for Synchronisers and Matcher can be overridden on a per-matcher basis.
The `netboxBaseUrl` of the CSAF Matcher must be set to the url of Netbox as the Matcher sees it.


## Installation of the CSAF Plugin

As the CSAF plugin is a standard NetBox plugin, it can be installed according to the [NetBox documentation](https://docs.netbox.dev/en/stable/plugins/#installing-plugins).
This plugin is compatible with NetBox version 4.3.1.

This plugin depends on the [DDDC Plugin](https://github.com/DINA-community/DDDC-Netbox-plugin/).


## Adding the plugin to an existing netbox-docker installation

### Set the proper netbox docker version

The CSAF Plugin is only compatible with NetBox 4.3 and therefore with netbox-docker 3.2.1.
For a new install, clone from tag 3.2.1:

   ```bash
   git clone -b 3.2.1 https://github.com/netbox-community/netbox-docker.git
   ```

For existing installations, switch to tag 3.2.1 before continuing:

   ```bash
   git checkout 3.2.1
   ```

### Add plugin

The Plugin can be added to any existing or new setup of netbox-docker by following their [plugin instructions](https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins).

1. Create the file `plugin_requirements.txt` with the following content:

   ```bash
   git+https://github.com/DINA-community/DDDC-Netbox-plugin.git
   git+https://github.com/DINA-community/CSAF-Netbox-Plugin.git
   ```

2. Create the file `Dockerfile-Plugins` with the content from the [netbox-docker documentation](https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins#dockerfile-plugins).
   Add this snippet before the line `RUN /usr/local/bin/uv pip`:

   ```bash
   RUN apt-get update && DEBIAN_FRONTEND="noninteractive" apt install -y git
   ```

   Also, replace

   ```bash
   FROM netboxcommunity/netbox:latest
   ```

   with

   ```bash
   FROM netboxcommunity/netbox:v4.3-3.3.0
   ```

   Matching the version of netbox-docker.

3. Create the file `docker-compose.override.yml` with the content from the [netbox-docker documentation](https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins#user-content-docker-composeoverrideyml).

   You can also create a superuser by adding these lines with meaningful values. Alternatively, create the superuser in step 6.

   ```yaml
         environment:
            SKIP_SUPERUSER: "false"
            #SUPERUSER_API_TOKEN: ""
            SUPERUSER_EMAIL: ""
            SUPERUSER_NAME: ""
            SUPERUSER_PASSWORD: ""
   ```

   Also, change the image versions

   ```yaml
      image: netbox:v4.3-3.3.0
   ```

   for all services

4. Add this to `configuration/plugins.py`:

   ```python
   PLUGINS = ["csaf", "d3c"]
   ```

   You can also add a section `PLUGINS_CONFIG` for d3c and csaf here. See above for the configuration example.

5. Build and run it (see [Troubleshoot](./troubleshoot.md)):

   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```

6. Access your local netbox by [http://127.0.0.1:8000](http://127.0.0.1:8000). To create an admin user, run this command:

   ```bash
   docker compose exec netbox /opt/netbox/netbox/manage.py createsuperuser
   ```


### Notes regarding the installation of this plugin via the provided files

The installation will provide a warning message since the installation is using the default security token:

```text
⚠️ Warning: You have the old default admin token in your database. This token is widely known; please remove it.
```

In theory, you can add an alternative security token in the file netbox.env by adding the following line:

```python
SUPERUSER_API_TOKEN=<Token>
```

However, an important aspect of an installation in a production environment is the creation of users, tokens, and their permissions. This must be done for each NetBox installation separately and in accordance with the specific requirements in place.


## Help

This section contains links for familiarizing yourself with Django, NetBox, and plugins.

### General

- Installation of NetBox as a standalone, self-hosted application: <https://docs.netbox.dev/en/stable/installation/>
- Community driven Docker image for netbox: <https://github.com/netbox-community/netbox-docker>
- Using NetBox Plugins in Docker: <https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins>

### Development

- Official plugin development documentation of NetBox: <https://docs.netbox.dev/en/stable/plugins/development/>
- NetBox plugin development Tutorial: <https://github.com/netbox-community/netbox-plugin-tutorial>
- Setting up a development environment with Docker for NetBox plugins: <https://github.com/netbox-community/netbox-docker/discussions/746>
- django-table2 Documentation used by the Plugin and NetBox: <https://django-tables2.readthedocs.io/en/latest/>

