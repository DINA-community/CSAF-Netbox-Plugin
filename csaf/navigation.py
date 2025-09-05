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
devicesWithMatches = PluginMenuItem(
    link='dcim:device_withmatches',
    link_text='Devices with Matches',
    permissions=('csaf.view_csafdocument','dcim.view_device'),
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
