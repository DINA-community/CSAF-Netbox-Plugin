from django.db.models.signals import post_migrate
from django.urls import reverse
from netbox.plugins import PluginConfig

class NetBoxCsafConfig(PluginConfig):
    """
    Plugin config for the CSAF-Plugin initiating the CustomFields and CustomFieldChoiceSets.
    """

    name = 'csaf'
    verbose_name = 'NetBox CSAF'
    description = 'Manage CSAF advisories in NetBox'
    version = '0.1.0'
    base_url = 'csaf'

    def ready(self):
        """ Initializes the Plugin."""
        post_migrate.connect(init_custom_links)

        return super().ready()

config = NetBoxCsafConfig


def init_custom_links(signal, sender, **kwargs):
    from core.models import ObjectType
    from dcim.models.devices import Device, DeviceType
    from extras.models import CustomLink
    from extras.choices import CustomLinkButtonClassChoices

    try:
        synchronisers_url = reverse('plugins:csaf:synchronisers')
        cl, created = CustomLink.objects.update_or_create(
            name='startRunForDeviceType',
            defaults={
                'link_text': 'Trigger CSAF Matching',
                'link_url': f'{synchronisers_url}?trigger=1&deviceType={{{{ object.id }}}}',
                'button_class': CustomLinkButtonClassChoices.CYAN,
            })
        cl.object_types.set([ObjectType.objects.get_for_model(DeviceType)])

        cl, created = CustomLink.objects.update_or_create(
            name='startRunForDevice',
            defaults={
                'link_text': 'Trigger CSAF Matching',
                'link_url': f'{synchronisers_url}?trigger=1&device={{{{ object.id }}}}',
                'button_class': CustomLinkButtonClassChoices.CYAN,
            })
        cl.object_types.set([ObjectType.objects.get_for_model(Device)])
    except Exception as e:
        print("Failed to create custom link")
        print(e)
