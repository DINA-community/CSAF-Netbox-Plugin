"""
 This file simply creates the navigation menu items for the CSAF-Plugin in NetBox.
"""

from django.conf import settings
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

plugin_settings = settings.PLUGINS_CONFIG["csaf"]


csafDocumentItem = PluginMenuItem(
    link='plugins:csaf:csafdocument_list',
    link_text='CSAF Documents',
    permissions=('csaf.view_csafdocument',),
    buttons=()
)
csafMatchItem = PluginMenuItem(
    link='plugins:csaf:csafmatch_list',
    link_text='CSAF Matches',
    permissions=('csaf.view_csafmatch',),
    buttons=()
)
csafVulnerabilityItem = PluginMenuItem(
    link='plugins:csaf:csafvulnerability_list',
    link_text='CSAF Vulnerabilities',
    permissions=('csaf.view_csafvulnerability',),
    buttons=()
)
devicesWithMatches = PluginMenuItem(
    link='dcim:device_withmatches',
    link_text='Devices with Matches',
    permissions=('csaf.view_csafdocument','dcim.view_device'),
    buttons=()
)
modulesWithMatches = PluginMenuItem(
    link='dcim:module_withmatches',
    link_text='Modules with Matches',
    permissions=('csaf.view_csafdocument','dcim.view_module'),
    buttons=()
)
softwareWithMatches = PluginMenuItem(
    link='plugins:d3c:software_withmatches',
    link_text='Software with Matches',
    permissions=('csaf.view_csafdocument',),
    buttons=()
)
dashboard = PluginMenuItem(
    link='plugins:csaf:dashboard',
    link_text='Dashboard',
    permissions=('csaf.view_csafmatch',),
    buttons=()
)
synchronisers = PluginMenuItem(
    link='plugins:csaf:synchronisers',
    link_text='Synchronisers',
    permissions=('csaf.viewSynchronisers_csafmatch',),
    buttons=()
)
configuration = PluginMenuItem(
    link='plugins:csaf:config',
    link_text='Configuration',
    permissions=('csaf.viewConfiguration',),
    buttons=()
)

_menu_items_models = (
    dashboard, csafDocumentItem, csafMatchItem, csafVulnerabilityItem, devicesWithMatches, modulesWithMatches, softwareWithMatches, synchronisers
)


menu = PluginMenu(
    label="CSAF",
    groups=(
        ("Models", (dashboard, csafDocumentItem, csafMatchItem, csafVulnerabilityItem, devicesWithMatches, modulesWithMatches, softwareWithMatches,)),
        ("Synchronisers", (synchronisers, configuration,)),
    ),
    icon_class="mdi mdi-gamma",
)
