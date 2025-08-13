import sys
import os
from netbox.plugins import PluginConfig

from django.core.signals import request_started


class NetBoxCsafConfig(PluginConfig):
    """
    Plugin config for the CSAF-Plugin initiating the CustomFields and CustomFieldChoiceSets.
    """

    name = 'csaf'
    verbose_name = 'NetBox CSAF'
    description = 'Manage CSAF advisories in NetBox'
    version = '0.1.0'
    base_url = 'csaf'

config = NetBoxCsafConfig


