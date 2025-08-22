"""
 This file simply creates the navigation menu items for the CSAF-Plugin in NetBox.
"""

from django.conf import settings
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

plugin_settings = settings.PLUGINS_CONFIG["csaf"]


csafDocumentItem = PluginMenuItem(
    link='plugins:csaf:csafdocument_list',
    link_text='CSAF Documents',
    buttons=()
)
csafMatchItem = PluginMenuItem(
    link='plugins:csaf:csafmatch_list',
    link_text='CSAF Matches',
    buttons=()
)
devicesWithMatches = PluginMenuItem(
    link='dcim:device_withmatches',
    link_text='Devices with Matches',
    buttons=()
)

_menu_items_models = (
    csafDocumentItem, csafMatchItem, devicesWithMatches
)


menu = PluginMenu(
    label="CSAF",
    groups=(
        ("Models", (csafDocumentItem, csafMatchItem, devicesWithMatches,)),
    ),
    icon_class="mdi mdi-gamma",
)
