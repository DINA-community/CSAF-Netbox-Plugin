from core.models import ObjectType
from dcim.models import DeviceType, Manufacturer, ModuleType
from django.urls import reverse
from extras.choices import CustomFieldTypeChoices
from extras.models import CustomField
from utilities.testing import ModelViewTestCase, TestCase

import csaf.models as models
from csaf.views import has_custom_field

class HasCustomFieldTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        manufacturer = Manufacturer.objects.create(name='Manufacturer', slug='manufacturer')
        cls.device_type = DeviceType.objects.create(manufacturer=manufacturer, model='Device Type', slug='device-type')

        device_type_field = CustomField.objects.create(name='csaf_test_device_type_field', type=CustomFieldTypeChoices.TYPE_TEXT)
        device_type_field.object_types.set([ObjectType.objects.get_for_model(DeviceType)])
        module_type_field = CustomField.objects.create(name='csaf_test_module_type_field', type=CustomFieldTypeChoices.TYPE_TEXT)
        module_type_field.object_types.set([ObjectType.objects.get_for_model(ModuleType)])

    def test_assigned_field(self):
        self.assertTrue(has_custom_field(self.device_type, 'csaf_test_device_type_field'))

    def test_field_of_other_model(self):
        self.assertFalse(has_custom_field(self.device_type, 'csaf_test_module_type_field'))

    def test_unknown_field(self):
        self.assertFalse(has_custom_field(self.device_type, 'csaf_test_unknown_field'))

    def test_no_object(self):
        self.assertFalse(has_custom_field(None, 'csaf_test_device_type_field'))


class CsafMatchListViewTestCase(TestCase):
    """Check CsafMatchListView and some information about bulk actions."""

    @classmethod
    def setUpTestData(cls):
        cls.csaf_document = models.CsafDocument.objects.create(
            title="Test1",
            docurl="https://example.com/.well-known/csaf/provider-metadata.json"
        )
        cls.csaf_match = models.CsafMatch.objects.create(
            csaf_document=cls.csaf_document, score=0.9
        )

    def test_for_hidden_pk_or_pk2_inputs(self):
        """Get the csaf match list view and check for hidden pk/pk2 inputs."""
        self.add_permissions(
            'csaf.view_csafmatch',
            'csaf.change_csafmatch',
            'csaf.edit_csafmatch')
        response = self.client.get(reverse('plugins:csaf:csafmatch_list'))
        self.assertHttpStatus(response, 200)
        self.assertNotContains(response, 'input type="hidden" name="pk2"')
        self.assertNotContains(response, 'input type="hidden" name="pk"')
