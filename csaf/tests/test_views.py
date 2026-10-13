from core.models import ObjectType
from dcim.models import DeviceType, Manufacturer, ModuleType
from django.test import TestCase
from extras.choices import CustomFieldTypeChoices
from extras.models import CustomField

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
