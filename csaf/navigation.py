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

_menu_items_models = (
    csafDocumentItem
)


menu = PluginMenu(
    label="CSAF",
    groups=(
        ("Models", (csafDocumentItem,)),
    ),
    icon_class="mdi mdi-gamma",
)
