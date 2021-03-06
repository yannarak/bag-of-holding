from datetime import date, timedelta

import os
import phonenumbers
import random
import re
import string

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import ugettext as _
from django.utils.timezone import now as timezone_now

from .behaviors import TimeStampedModel
from . import helpers, managers


def create_random_string(length=30):
    if length <= 0:
        length = 30

    symbols = string.ascii_lowercase + string.ascii_uppercase + string.digits
    return ''.join([random.choice(symbols) for x in range(length)])


def upload_to(instance, filename):
    now = timezone_now()
    filename_base, filename_ext = os.path.splitext(filename)
    return 'uploads/{}_{}{}'.format(
        now.strftime("%Y/%m/%d/%Y%m%d%H%M%S"),
        create_random_string(),
        filename_ext.lower()
    )

class Tag(models.Model):
    """Associated with application for search and categorization."""
    color_regex = RegexValidator(regex=r'^[0-9A-Fa-f]{6}$', message=_("Color must be entered in the 6 character hex format."))
    name = models.CharField(max_length=64, unique=True, help_text=_('A unique name for this tag.'))
    color = models.CharField(max_length=6, validators=[color_regex], help_text=_('Specify a 6 character hex color value. (e.g., \'d94d59\')'))
    description = models.CharField(max_length=64, blank=True, help_text=_('A short description of this tag\'s purpose to be shown in tooltips.'))

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.color = self.color.lower()  # Convert color to lowercase
        super(Tag, self).save(*args, **kwargs)


class CustomField(TimeStampedModel, models.Model):
    def validate_regex(value):
        try:
            re.compile(value)
        except re.error:
            raise ValidationError(_('%(value)s is not a valid regular expression'), params={'value': value})

    key_regex = RegexValidator(regex=r'^[0-9a-z_]+$', message=_('Key must be lowercase with no spaces. Underscores may be used to seperate words.'))

    name = models.CharField(max_length=64, verbose_name=_('custom field name'), help_text=_('A name for this custom field'))
    description = models.TextField(blank=True, help_text=_('Information about the custom field\'s purpose.'))
    key = models.CharField(max_length=64, unique=True, validators=[key_regex], help_text=_('A unique key for this field. (e.g., \'custom_id\')'))
    validation_regex = models.CharField(max_length=255, blank=True, validators=[validate_regex], help_text=_('A regular expression to validate on save. (e.g. \'[0-9]{5}$\' is a regex for a number with a length of 5)'))
    validation_description = models.CharField(max_length=128, blank=True, help_text=_('A brief description of the validation expression to be shown to users.'))

    class Meta:
        ordering = ['name']
        verbose_name = _('Custom Field')
        verbose_name_plural = _('Custom Fields')

    def __str__(self):
        return self.name


class CustomFieldValue(TimeStampedModel, models.Model):
    custom_field = models.ForeignKey(CustomField, on_delete=models.DO_NOTHING)
    value = models.CharField(max_length=255)

    class Meta:
        abstract = True
        ordering = ['custom_field', 'value']

    def __str__(self):
        return self.value

    def clean(self):
        if not re.match(self.custom_field.validation_regex, self.value):
            if self.custom_field.validation_description:
                raise ValidationError({'value': self.custom_field.validation_description})
            else:
                raise ValidationError({'value': _('Value does not match custom field regex.')})


class Person(models.Model):
    """Information about a person."""

    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$', message=_("Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."))

    DEVELOPER_ROLE = 'developer'
    QUALITY_ASSURANCE_ROLE = 'qa'
    OPERATIONS_ROLE = 'operations'
    MANAGER_ROLE = 'manager'
    SECURITY_OFFICER_ROLE = 'security officer'
    TECHNICAL_LEAD_ROLE = 'technical lead'
    PRODUCER_ROLE = 'producer'
    SECURITY_CHAMPION_ROLE = 'security champion'
    ROLE_CHOICES = (
        (PRODUCER_ROLE, _('Producer')),
        (TECHNICAL_LEAD_ROLE, _('Technical Lead')),
        (DEVELOPER_ROLE, _('Developer')),
        (QUALITY_ASSURANCE_ROLE, _('Quality Assurance')),
        (OPERATIONS_ROLE, _('Operations')),
        (MANAGER_ROLE, _('Manager')),
        (SECURITY_OFFICER_ROLE, _('Security Officer')),
    )

    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)
    email = models.EmailField(max_length=128, unique=True, default='')
    slack_id = models.CharField(max_length=128, unique=True, default='')
    role = models.CharField(max_length=17, choices=ROLE_CHOICES)
    phone_work = models.CharField(max_length=15, validators=[phone_regex], blank=True)
    phone_mobile = models.CharField(max_length=15, validators=[phone_regex], blank=True)
    job_title = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ['slack_id', 'last_name', 'first_name']
        verbose_name_plural = 'People'

    def __str__(self):
        return self.first_name + ' ' + self.last_name

    def save(self, *args, **kwargs):
        if self.phone_work:
            self.phone_work = phonenumbers.format_number(phonenumbers.parse(self.phone_work, 'US'), phonenumbers.PhoneNumberFormat.E164)
        if self.phone_mobile:
            self.phone_mobile = phonenumbers.format_number(phonenumbers.parse(self.phone_mobile, 'US'), phonenumbers.PhoneNumberFormat.E164)
        self.email = self.email.lower()
        super(Person, self).save(*args, **kwargs)


class Organization(models.Model):
    """Entities under which applications belong."""

    name = models.CharField(max_length=32, unique=True, help_text=_('A unique name for the organization.'))
    description = models.TextField(blank=True, help_text=_('Information about the organization\'s purpose, history, and structure.'))

    people = models.ManyToManyField(Person, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class DataElement(models.Model):
    """An individual data element stored within an application. Used for data classification."""

    GLOBAL_CATEGORY = 'global'
    PERSONAL_CATEGORY = 'personal'
    COMPANY_CATEGORY = 'company'
    GOVERNMENT_CATEGORY = 'government'
    PCI_CATEGORY = 'pci'
    MEDICAL_CATEGORY = 'medical'
    CATEGORY_CHOICES = (
        (GLOBAL_CATEGORY, _('Global')),
        (PERSONAL_CATEGORY, _('Personal')),
        (COMPANY_CATEGORY, _('Company')),
        (GOVERNMENT_CATEGORY, _('Government')),
        (PCI_CATEGORY, _('Payment Card Industry')),
        (MEDICAL_CATEGORY, _('Medical')),
    )

    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    weight = models.PositiveIntegerField()

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Technology(models.Model):
    """Architectural details for an application."""
    PROGRAMMING_LANGUAGE_CATEGORY = 'language'
    OPERATING_SYSTEM_CATEGORY = 'operating system'
    DATA_STORE_CATEGORY = 'data store'
    FRAMEWORK_CATEGORY = 'framework'
    THIRD_PARTY_COMPONENT = 'third-party component'
    WEB_SERVER_CATEGORY = 'web server'
    APPLICATION_SERVER_CATEGORY = 'application server'
    HOSTING_PROVIDER_CATEGORY = 'hosting provider'
    DENIAL_OF_SERVICE_CATEGORY = 'denial of service'
    FIREWALL_CATEGORY = 'firewall'
    CATEGORY_CHOICES = (
        (PROGRAMMING_LANGUAGE_CATEGORY, _('Language')),
        (OPERATING_SYSTEM_CATEGORY, _('Operating System')),
        (DATA_STORE_CATEGORY, _('Data Store')),
        (FRAMEWORK_CATEGORY, _('Framework')),
        (THIRD_PARTY_COMPONENT, _('Third-Party Component')),
        (APPLICATION_SERVER_CATEGORY, _('Application Server')),
        (WEB_SERVER_CATEGORY, _('Web Server')),
        (HOSTING_PROVIDER_CATEGORY, _('Hosting Provider')),
        (DENIAL_OF_SERVICE_CATEGORY, _('DDoS Protection')),
        (FIREWALL_CATEGORY, _('Firewall')),
    )

    name = models.CharField(max_length=64, help_text=_('The name of the technology.'))
    category = models.CharField(max_length=21, choices=CATEGORY_CHOICES, help_text=_('The type of technology.'))
    description = models.CharField(max_length=256, blank=True, help_text=_('Information about the technology.'))
    reference = models.URLField(blank=True, help_text=_('An external URL for more information.'))

    class Meta:
        ordering = ['category', 'name']
        verbose_name_plural = _('Technologies')

    def __str__(self):
        return self.get_category_display() + ' :: ' + self.name


class Regulation(models.Model):
    """Regulations applicable to applications."""
    PRIVACY_CATEGORY = 'privacy'
    FINANCE_CATEGORY = 'finance'
    EDUCATION_CATEGORY = 'education'
    MEDICAL_CATEGORY = 'medical'
    OTHER_CATEGORY = 'other'
    CATEGORY_CHOICES = (
        (PRIVACY_CATEGORY, _('Privacy')),
        (FINANCE_CATEGORY, _('Finance')),
        (EDUCATION_CATEGORY, _('Education')),
        (MEDICAL_CATEGORY, _('Medical')),
        (OTHER_CATEGORY, _('Other')),
    )

    name = models.CharField(max_length=128, help_text=_('The name of the legislation.'))
    acronym = models.CharField(max_length=20, unique=True, help_text=_('A shortened representation of the name.'))
    category = models.CharField(max_length=9, choices=CATEGORY_CHOICES, help_text=_('The subject of the regulation.'))
    jurisdiction = models.CharField(max_length=64, help_text=_('The territory over which the regulation applies.'))
    description = models.TextField(blank=True, help_text=_('Information about the regulation\'s purpose.'))
    reference = models.URLField(blank=True, help_text=_('An external URL for more information.'))

    class Meta:
        ordering = ['jurisdiction', 'category', 'name']

    def __str__(self):
        return self.acronym + ' (' + self.jurisdiction + ')'


class ServiceLevelAgreement(models.Model):
    """Service Level Agreements to be applied to applications."""
    name = models.CharField(max_length=64, help_text=_('The name of the service level agreement.'))
    description = models.CharField(max_length=256, blank=True, help_text=_('Information about this service level agreement\'s scope, quality, and responsibilities.'))

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ThreadFix(models.Model):
    """ThreadFix server connection information."""

    name = models.CharField(max_length=32, unique=True, help_text=_('A unique name describing the ThreadFix service.'))
    host = models.URLField(help_text=_('The URL for the ThreadFix server. (e.g., http://localhost:8080/threadfix/)'))
    api_key = models.CharField(max_length=50, help_text=_('The API key can be generated on the ThreadFix API Key page.'))  # https://github.com/denimgroup/threadfix/blob/dev/threadfix-main/src/main/java/com/denimgroup/threadfix/service/APIKeyServiceImpl.java#L103
    verify_ssl = models.BooleanField(default=True, help_text=_('Specify if API requests will verify the host\'s SSL certificate. If disabled, API requests could be intercepted by third-parties.'))

    class Meta:
        verbose_name = 'ThreadFix'
        verbose_name_plural = 'ThreadFix'

    def __str__(self):
        return self.name + ' - ' + self.host


class Application(TimeStampedModel, models.Model):
    """Contains information about a software application."""

    WEB_PLATFORM = 'web'
    DESKTOP_PLATFORM = 'desktop'
    MOBILE_PLATFORM = 'mobile'
    WEB_SERVICE_PLATFORM = 'web service'
    COMMAND_LINE_PLATFORM = 'command line'
    PLATFORM_CHOICES = (
        (WEB_PLATFORM, _('Web')),
        (DESKTOP_PLATFORM, _('Desktop')),
        (COMMAND_LINE_PLATFORM, _('Command Line')),
        (MOBILE_PLATFORM, _('Mobile')),
        (WEB_SERVICE_PLATFORM, _('Web Service')),
    )

    IDEA_LIFECYCLE = 'idea'
    EXPLORE_LIFECYCLE = 'explore'
    VALIDATE_LIFECYCLE = 'validate'
    GROW_LIFECYCLE = 'grow'
    SUSTAIN_LIFECYCLE = 'sustain'
    RETIRE_LIFECYCLE = 'retire'
    LIFECYCLE_CHOICES = (
        (IDEA_LIFECYCLE, _('Idea')),
        (EXPLORE_LIFECYCLE, _('Explore')),
        (VALIDATE_LIFECYCLE, _('Validate')),
        (GROW_LIFECYCLE, _('Grow')),
        (SUSTAIN_LIFECYCLE, _('Sustain')),
        (RETIRE_LIFECYCLE, _('Retire')),
    )

    THIRD_PARTY_LIBRARY_ORIGIN = 'third party library'
    PURCHASED_ORIGIN = 'purchased'
    CONTRACTOR_ORIGIN = 'contractor'
    INTERNALLY_DEVELOPED_ORIGIN = 'internal'
    OPEN_SOURCE_ORIGIN = 'open source'
    OUTSOURCED_ORIGIN = 'outsourced'
    ORIGIN_CHOICES = (
        (THIRD_PARTY_LIBRARY_ORIGIN, _('Third Party Library')),
        (PURCHASED_ORIGIN, _('Purchased')),
        (CONTRACTOR_ORIGIN, _('Contractor Developed')),
        (INTERNALLY_DEVELOPED_ORIGIN, _('Internally Developed')),
        (OPEN_SOURCE_ORIGIN, _('Open Source')),
        (OUTSOURCED_ORIGIN, _('Outsourced')),
    )

    CRITICAL_APPLICATION = 'Critical'
    IMPORTANT_APPLICATION = 'Important'
    STRATEGIC_APPLICATION = 'Strategic'
    INTERNAL_SUPPORTING_APPLICATION = 'Internal Support'
    GENERAL_SUPPORT_APPLICATION = 'General Support'
    NONE_CRITICALITY = 'none'
    BUSINESS_CRITICALITY_CHOICES = (
        (CRITICAL_APPLICATION, _('Critical Application')),
        (IMPORTANT_APPLICATION, _('Important Application')),
        (STRATEGIC_APPLICATION, _('Strategic Application')),
        (INTERNAL_SUPPORTING_APPLICATION, _('Internal Support Application')),
        (GENERAL_SUPPORT_APPLICATION, _('General Support Application')),
        (NONE_CRITICALITY, _('None')),
    )

    HIGH_RISK = 'High Risk'
    MEDIUM_RISK = 'Medium Risk'
    LOW_RISK = 'Low Risk'
    RISK_CATEGORY_CHOICES = (
        (None, _('Not Specified')),
        (LOW_RISK, _('Low Risk')),
        (MEDIUM_RISK, _('Medium Risk')),
        (HIGH_RISK, _('High Risk')),
    )

    HIGHLY_SENSITIVE_DATA_CLASSIFICATION = 4
    SENSITIVE_DATA_CLASSIFICATION = 3
    CONFIDENTIAL_DATA_CLASSIFICATION = 2
    PRIVATE_DATA_CLASSIFICATION = 1
    PUBLIC_DATA_CLASSIFICATION = 0
    DATA_CLASSIFICATION_CHOICES = (
        (None, _('Not Specified')),
        (PUBLIC_DATA_CLASSIFICATION, 'Public'),
        (PRIVATE_DATA_CLASSIFICATION, 'Private'),
        (CONFIDENTIAL_DATA_CLASSIFICATION, 'Confidential'),
        (SENSITIVE_DATA_CLASSIFICATION, 'Sensitive'),
        (HIGHLY_SENSITIVE_DATA_CLASSIFICATION, 'Highly Sensitive'),
    )

    ASVS_0 = 0
    ASVS_1 = 1
    ASVS_2 = 2
    ASVS_3 = 3
    ASVS_CHOICES = (
        (None, _('Not Specified')),
        (ASVS_0, '0'),
        (ASVS_1, '1'),
        (ASVS_2, '2'),
        (ASVS_3, '3'),
    )

    # General
    name = models.CharField(max_length=128, unique=True, help_text=_('A unique name for the application.'))
    description = models.TextField(blank=True, help_text=_('Information about the application\'s purpose, history, and design.'))
    threats = models.TextField(blank=True, help_text=_('Potential threats that could affect the application.'))
    # Metadata
    business_criticality = models.CharField(max_length=30, choices=BUSINESS_CRITICALITY_CHOICES, blank=True, null=True)
    authentication = models.TextField(blank=True, help_text=_('Does application implement any kind of authentication? If yes, provide additional details.'))
    authorization = models.TextField(blank=True, help_text=_('Does application implement any kind of authorization? If yes, provide additional details.'))
    plugins = models.TextField(blank=True, help_text=_('Is this application developed as a plug-in or extension for other application? If yes, please provide additional details on what all applications it will be working with.'))
    platform = models.CharField(max_length=11, choices=PLATFORM_CHOICES, blank=True, null=True)
    lifecycle = models.CharField(max_length=8, choices=LIFECYCLE_CHOICES, blank=True, null=True)
    origin = models.CharField(max_length=19, choices=ORIGIN_CHOICES, blank=True, null=True)
    user_records = models.PositiveIntegerField(blank=True, null=True, help_text=_('Estimate the number of user records within the application.'))
    revenue = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, help_text=_('Estimate the application\'s revenue in JPY.'))
    external_audience = models.BooleanField(default=False, help_text=_('Specify if the application is used by people outside the organization.'))
    internet_accessible = models.BooleanField(default=False, help_text=_('Specify if the application is accessible from the public internet.'))
    requestable = models.NullBooleanField(default=True, help_text=_('Specify if activities can be externally requested for this application.'))

    repository = models.URLField(blank=True, help_text=_('Specify the URL of the source code repository'))
    dependencies = models.ManyToManyField('self', blank=True)
    technologies = models.ManyToManyField(Technology, blank=True)
    regulations = models.ManyToManyField(Regulation, blank=True)
    service_level_agreements = models.ManyToManyField(ServiceLevelAgreement, blank=True)
    risk_category = models.CharField(max_length=20, choices=RISK_CATEGORY_CHOICES, blank=True, null=True)


    # Data Classification
    # TODO Move to Data Classification Benchmark
    data_elements = models.ManyToManyField(DataElement, blank=True)
    override_dcl = models.IntegerField(choices=DATA_CLASSIFICATION_CHOICES, blank=True, null=True, help_text=_('Overrides the calculated data classification level.'))
    override_reason = models.TextField(blank=True, help_text=_('Specify why the calculated data classification level is being overridden.'))

    # ThreadFix
    threadfix = models.ForeignKey(ThreadFix, blank=True, null=True, on_delete=models.DO_NOTHING, help_text=_('The ThreadFix service to connect to this application.'))
    threadfix_team_id = models.PositiveIntegerField(blank=True, null=True, help_text=_('The unique team identifier used within ThreadFix.'))
    threadfix_application_id = models.PositiveIntegerField(blank=True, null=True, help_text=_('The unique application identifier used within ThreadFix.'))

    # OWASP
    # TODO Move to OWASP ASVS Benchmark
    asvs_level = models.IntegerField(choices=ASVS_CHOICES,blank=True, null=True, help_text=_('Assessed ASVS Level'))
    asvs_level_percent_achieved = models.PositiveIntegerField(blank=True, null=True, help_text=_('Percent compliant to the targeted ASVS level.'))
    asvs_level_target = models.IntegerField(choices=ASVS_CHOICES,blank=True, null=True, help_text=_('Targeted ASVS level for this application.'))
    asvs_doc_url = models.URLField(blank=True, help_text=_('URL to the detailed ASVS assessment.'))

    # Misc
    organization = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, help_text=_('The organization containing this application.'))
    people = models.ManyToManyField(Person, through='Relation', blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    custom_fields = models.ManyToManyField(CustomField, through='ApplicationCustomFieldValue')
    objects = managers.ApplicationManager.from_queryset(managers.ApplicationQuerySet)()

    class Meta:
        get_latest_by = 'modified_date'
        ordering = ['name']

    def __str__(self):
        return self.name

    def data_classification_level(self):
        """Returns the data classification level of the selected data elements."""
        if self.override_dcl is not None:
            return self.override_dcl
        else:
            return helpers.data_classification_level(self.data_sensitivity_value())

    def default_data_classification_level(self):
        """Returns the data classification level of the selected data elements."""
        return helpers.data_classification_level(self.data_sensitivity_value())

    def data_classification_level_display(self):
        return helpers.data_classification_level_display(self.data_classification_level())

    def default_data_classification_level_display(self):
        return helpers.data_classification_level_display(self.default_data_classification_level())

    def data_sensitivity_value(self):
        """Returns the calculated data sensitivity value of the selected data elements."""
        return helpers.data_sensitivity_value(self.data_elements.all())


class ApplicationCustomFieldValue(CustomFieldValue):
    application = models.ForeignKey(Application, on_delete=models.DO_NOTHING)

    class Meta:
        unique_together = ('application', 'custom_field', 'value')


class ThreadFixMetrics(TimeStampedModel, models.Model):
    """Point in time metrics from ThreadFix for an application."""

    critical_count = models.PositiveIntegerField(default=0)
    high_count = models.PositiveIntegerField(default=0)
    medium_count = models.PositiveIntegerField(default=0)
    low_count = models.PositiveIntegerField(default=0)
    informational_count = models.PositiveIntegerField(default=0)

    application = models.ForeignKey(Application, on_delete=models.DO_NOTHING)

    class Meta:
        get_latest_by = 'created_date'
        verbose_name = _('ThreadFix metrics')
        verbose_name_plural = _('ThreadFix metrics')

    def total(self):
        return self.critical_count + self.high_count + self.medium_count + self.low_count + self.informational_count


class Relation(models.Model):
    """Associates a person with an application with a role."""

    owner = models.BooleanField(default=False, help_text=_('Specify if this person is an application owner.'))
    emergency = models.BooleanField(default=False, help_text=_('Specify if this person is an emergency contact.'))
    security_champion = models.BooleanField(default=False, help_text=_('Specify if this person is a security champion.'))
    technical_lead = models.BooleanField(default=False, help_text=_('Specify if this person is a technical lead.'))
    notes = models.TextField(blank=True, help_text=_('Any notes about this person\'s connection to the application.'))
    person = models.ForeignKey(Person, on_delete=models.DO_NOTHING, help_text=_('The person associated with the application.'))
    application = models.ForeignKey(Application, on_delete=models.DO_NOTHING)

    class Meta:
        unique_together = ('person', 'application')

    def __str__(self):
        return self.person.first_name + ' ' + self.person.last_name + ' - ' + self.application.name


class Environment(models.Model):
    """Container for information about a web server environment."""

    DEVELOPMENT_ENVIRONMENT = 'dev'
    INTEGRATION_ENVIRONMENT = 'int'
    QUALITY_ASSURANCE_ENVIRONMENT = 'qa'
    PRE_PRODUCTION_ENVIRONMENT = 'ppe'
    CUSTOMER_ACCEPTANCE_ENVIRONMENT = 'cat'
    PRODUCTION_ENVIRONMENT = 'prod'
    ENVIRONMENT_CHOICES = (
        (DEVELOPMENT_ENVIRONMENT, _('Development')),
        (INTEGRATION_ENVIRONMENT, _('Integration')),
        (QUALITY_ASSURANCE_ENVIRONMENT, _('Quality Assurance')),
        (PRE_PRODUCTION_ENVIRONMENT, _('Pre-Production')),
        (CUSTOMER_ACCEPTANCE_ENVIRONMENT, _('Customer Acceptance')),
        (PRODUCTION_ENVIRONMENT, _('Production')),
    )

    environment_type = models.CharField(max_length=4, choices=ENVIRONMENT_CHOICES, help_text=_('Specify the type of environment.'))
    description = models.TextField(blank=True, help_text=_('Information about the environment\'s purpose, physical location, hardware, and deployment.'))
    testing_approved = models.BooleanField(default=False, help_text=_('Specify if security testing has been approved for this environment.'))

    application = models.ForeignKey(Application, on_delete=models.DO_NOTHING)

    class Meta:
        ordering = ['-testing_approved', 'environment_type']

    def __str__(self):
        return self.application.name + ' (' + dict(Environment.ENVIRONMENT_CHOICES)[self.environment_type] + ')'


class EnvironmentLocation(models.Model):
    """URL for a specific environment"""

    location = models.URLField(help_text=_('A URL for the environment. (e.g., http://www.google.com/, https://www.owasp.org/)'))
    notes = models.TextField(blank=True, help_text=_('Information about the location\'s purpose, physical location, and deployment.'))

    environment = models.ForeignKey(Environment, on_delete=models.DO_NOTHING)

    def __str__(self):
        return self.location


class EnvironmentCredentials(TimeStampedModel, models.Model):
    """Credentials for a specific environment."""

    username = models.CharField(max_length=128, blank=True)
    password = models.CharField(max_length=128, blank=True)
    role_description = models.CharField(max_length=128, blank=True, help_text=_('A brief description of the user\'s role or permissions. (e.g., Guest, Admin)'))
    notes = models.TextField(blank=True, help_text=_('Additional information about these credentials.'))

    environment = models.ForeignKey(Environment, on_delete=models.DO_NOTHING)

    class Meta:
        verbose_name_plural = 'Environment credentials'
        ordering = ['username', 'password']


class Engagement(TimeStampedModel, models.Model):
    """Container for activities performed for an application over a duration."""

    PENDING_STATUS = 'pending'
    ONGOING_STATUS = 'ongoing'
    OPEN_STATUS = 'open'
    CLOSED_STATUS = 'closed'
    STATUS_CHOICES = (
        (PENDING_STATUS, _('Pending')),
        (OPEN_STATUS, _('Open')),
        (ONGOING_STATUS, _('Ongoing')),
        (CLOSED_STATUS, _('Closed'))
    )

    status = models.CharField(max_length=7, choices=STATUS_CHOICES, default=PENDING_STATUS)
    start_date = models.DateField(help_text=_('The date the engagement is scheduled to begin.'))
    end_date = models.DateField(help_text=_('The date the engagement is scheduled to complete.'))
    description = models.TextField(blank=True)
    version = models.CharField(max_length=128,blank=True,null=True,)

    open_date = models.DateTimeField(blank=True, null=True, help_text=_('The date and time when the status is changed to open.'))
    close_date = models.DateTimeField(blank=True, null=True, help_text=_('The date and time when the status is changed to closed.'))
    duration = models.DurationField(blank=True, null=True)

    requestor = models.ForeignKey(Person, on_delete=models.DO_NOTHING, blank=True, null=True, help_text=_('Specify who requested this engagement.'))
    application = models.ForeignKey(Application, on_delete=models.DO_NOTHING)

    objects = managers.EngagementManager.from_queryset(managers.EngagementQuerySet)()
    metrics = managers.EngagementMetrics.from_queryset(managers.EngagementQuerySet)()

    class Meta:
        get_latest_by = 'close_date'
        ordering = ['start_date']

    def save(self, *args, **kwargs):
        """Automatically sets the open and closed dates when the status changes."""
        if self.pk is not None:
            engagement = Engagement.objects.get(pk=self.pk)
            now = timezone.now()
            if engagement.status != self.status:
                if self.status == Engagement.PENDING_STATUS:
                    self.open_date = None
                    self.close_date = None
                elif self.status == Engagement.OPEN_STATUS:
                    self.open_date = now
                    self.close_date = None
                elif self.status == Engagement.CLOSED_STATUS:
                    if self.open_date is None:
                        self.open_date = now
                    self.close_date = now

        if self.open_date is not None and self.close_date is not None:
            self.duration = self.close_date - self.open_date
        super(Engagement, self).save(*args, **kwargs)

    def is_pending(self):
        return self.status == Engagement.PENDING_STATUS

    def is_open(self):
        return self.status == Engagement.OPEN_STATUS

    def is_closed(self):
        return self.status == Engagement.CLOSED_STATUS

    def is_ready_for_work(self):
        """If the engagement is pending on or after the start date."""
        return self.status == Engagement.PENDING_STATUS and date.today() >= self.start_date

    def is_past_due(self):
        """If the engagement is not closed by the end date."""
        return (self.status == Engagement.PENDING_STATUS or self.status == Engagement.OPEN_STATUS) \
            and date.today() > self.end_date


class ActivityType(TimeStampedModel, models.Model):
    """Types of work."""

    name = models.CharField(max_length=128, unique=True, help_text=_('A unique name for this activity type.'))
    documentation = models.TextField(blank=True, help_text=_('Guidelines, procedures, and techniques for this activity type.'))

    objects = managers.ActivityTypeManager.from_queryset(managers.ActivityTypeQuerySet)()
    metrics = managers.ActivityTypeMetrics.from_queryset(managers.ActivityTypeQuerySet)()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Activity(models.Model):
    """A unit of work performed for an application over a duration."""

    OPEN_STATUS = 'open'
    PENDING_STATUS = 'pending'
    ONGOING_STATUS = 'ongoing'
    CANCELLED_STATUS = 'cancelled'
    CLOSED_STATUS = 'Closed'
    STATUS_CHOICES = (
        (OPEN_STATUS, 'Open'),
        (PENDING_STATUS, 'Pending'),
        (ONGOING_STATUS, 'Ongoing'),
        (CANCELLED_STATUS, 'Cancelled'),
        (CLOSED_STATUS, 'Closed')
    )

    status = models.CharField(max_length=7, choices=STATUS_CHOICES, default=PENDING_STATUS)
    description = models.TextField(blank=True)
    open_date = models.DateTimeField(blank=True, null=True, help_text='The date and time when the status is changed to open.')
    close_date = models.DateTimeField(blank=True, null=True, help_text='The date and time when the status is changed to closed.')
    duration = models.DurationField(blank=True, null=True)

    activity_type = models.ForeignKey(ActivityType, on_delete=models.DO_NOTHING)
    engagement = models.ForeignKey(Engagement, on_delete=models.DO_NOTHING)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)

    objects = managers.ActivityManager.from_queryset(managers.ActivityQuerySet)()

    class Meta:
        ordering = ['engagement__start_date']
        verbose_name_plural = _('Activities')

    def __str__(self):
        return self.activity_type.name

    def save(self, *args, **kwargs):
        """
        Automatically sets the open and closed dates when the status changes.
        Opens parent engagement if child activity is opened.
        Closes parent engagement if all child activities are closed.
        """
        if self.pk is not None:
            activity = Activity.objects.get(pk=self.pk)
            if activity.status != self.status:  # When status changed
                now = timezone.now()
                if self.status == Activity.PENDING_STATUS:
                    self.open_date = None
                    self.close_date = None
                elif self.status == Activity.OPEN_STATUS:
                    self.open_date = now
                    self.close_date = None

                    # Open the parent engagement if the activity is opened
                    if self.engagement.status is not Engagement.OPEN_STATUS:
                        self.engagement.status = Engagement.OPEN_STATUS
                        self.engagement.save()
                elif self.status == Activity.CLOSED_STATUS:
                    if self.open_date is None:
                        self.open_date = now
                    self.close_date = now

                    # If all of the parent engagement activities are closed, close the parent engagement
                    close = True
                    for current_activity in self.engagement.activity_set.exclude(id=self.id):
                        if current_activity.status != Activity.CLOSED_STATUS:
                            close = False
                            break
                    if close:
                        self.engagement.status = Engagement.CLOSED_STATUS
                        self.engagement.save()
        if self.open_date is not None and self.close_date is not None:
            self.duration = self.close_date - self.open_date
        super(Activity, self).save(*args, **kwargs)

    def is_pending(self):
        return self.status == Activity.PENDING_STATUS

    def is_open(self):
        return self.status == Activity.OPEN_STATUS

    def is_ongoing(self):
        return self.status == Activity.ONGOING_STATUS

    def is_cancelled(self):
        return self.status == Activity.CANCELLED_STATUS

    def is_closed(self):
        return self.status == Activity.CLOSED_STATUS

    def is_ready_for_work(self):
        """If the activity is pending on or after the parent engagement's start date."""
        return self.status == Activity.PENDING_STATUS \
            and date.today() >= self.engagement.start_date

    def is_past_due(self):
        """If the activity is not closed by the parent engagement's end date."""
        return (self.status == Activity.PENDING_STATUS or self.status == Activity.OPEN_STATUS) \
               and date.today() > self.engagement.end_date


class Comment(TimeStampedModel, models.Model):
    """Abstract message about an engagement or activity."""

    message = models.TextField()

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING)

    def __str__(self):
        return self.message

    class Meta:
        abstract = True


class EngagementComment(Comment):
    """Comment for a specific engagement."""

    engagement = models.ForeignKey(Engagement, on_delete=models.DO_NOTHING)


class ActivityComment(Comment):
    """Comment for a specific activity."""

    activity = models.ForeignKey(Activity, on_delete=models.DO_NOTHING)


class VulnerabilityClass(models.Model):
    cwe_id = models.CharField(unique=True, blank=False, max_length=10, help_text='Specify the Common Weakness Enumeration ID')
    name = models.CharField(max_length=256, blank=False, help_text='Specify the name of the vulnerability classification')
    url = models.URLField(blank=False, help_text='Specify the URL to the CWE definition page')

    def __str__(self):
        return self.cwe_id + ' - ' + self.name


class Vulnerability(TimeStampedModel, models.Model):
    INFORMATIONAL_SEVERITY = 0
    LOW_SEVERITY = 1
    MEDIUM_SEVERITY = 2
    HIGH_SEVERITY = 3
    CRITICAL_SEVERITY = 4
    SEVERITY_CHOICES = (
        (INFORMATIONAL_SEVERITY, _('Informational')),
        (LOW_SEVERITY, _('Low')),
        (MEDIUM_SEVERITY, _('Medium')),
        (HIGH_SEVERITY, _('High')),
        (CRITICAL_SEVERITY, _('Critical')),
    )

    OPEN_STATUS = 'Open'
    REOPENED_STATUS = 'Re-Opened'
    FIXING_STATUS = 'Fixing'
    FIXED_STATUS = 'Fixed'
    PENDING_STATUS = 'Pending'
    RISK_ACCEPTED_STATUS = 'Risk-Accepted'
    MITIGATED_STATUS = 'Mitigated'
    INVALID_STATUS = 'Invalid'
    STATUS_CHOICES = (
        (OPEN_STATUS, _('Open')),
        (REOPENED_STATUS, _('Re-Opened')),
        (FIXING_STATUS, _('Fixing')),
        (PENDING_STATUS, _('Pending')),
        (MITIGATED_STATUS, _('Mitigated')),
        (RISK_ACCEPTED_STATUS, _('Risk-Accepted')),
        (FIXED_STATUS, _('Fixed')),
        (INVALID_STATUS, _('Invalid')),
    )

    MANUAL_DETECTION_METHOD = 'Manual'
    AUTOMATED_DETECTION_METHOD = 'Automated'
    OTHER_DETECTION_METHOD = 'Other'
    DETECTION_METHOD_CHOICES = (
        (MANUAL_DETECTION_METHOD, _('Manual')),
        (AUTOMATED_DETECTION_METHOD, _('Automated')),
        (OTHER_DETECTION_METHOD, _('Other')),
    )

    # General
    name = models.CharField(blank=False, max_length=256, help_text=_('Specify the name of the vulnerability.'))
    description = models.TextField(blank=False, help_text=_('Specify the detailed description of the issue explaining the vulnerability, including the impact to the user(s) or system.'))
    solution = models.TextField(blank=False, help_text=_('Specify the solution to fix the vulnerability.'))
    affected_app = models.ForeignKey(Application, on_delete=models.DO_NOTHING, blank=False, help_text=_('Specify the application that is affected by this vulenerability.'), verbose_name=_('Affected Application'))
    affected_version = models.CharField(max_length=256, blank=True, help_text=_('Specify the version of the application that is affected by this vulenerability.') , verbose_name=_('Affected Version(s)'))
    environment = models.TextField(blank=True, help_text=_('Specify the environment used during the test, including device, OS, network conection type, target hosts, etc.'))
    severity = models.IntegerField(choices=SEVERITY_CHOICES, blank=False, null=False, default=MEDIUM_SEVERITY)
    pre_conditions = models.TextField(blank=True, help_text=_('If any, specify the pre-conditions to exploit this vulnerablity.'), verbose_name=_('Pre-condition(s)'))
    reproduction_steps = models.TextField(blank=True, help_text=_('Specify the steps to reproduce.'), verbose_name=_('Steps to Reproduce'))
    attack_vector = models.TextField(blank=True,  help_text=_('Specify the attack vectors, including affected pages/screens, input parameters, a test HTTP Request with attack payloads together with its response, etc.)'),  verbose_name=_('Attack Vector(s)'))
    reporter = models.ForeignKey(Person, on_delete=models.DO_NOTHING, help_text=_('Specify a person who reported this vulnerability'))
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=OPEN_STATUS)
    fixed_at = models.DateTimeField(blank=True, null=True)
    deadline = models.DateField(blank=True, null=True)
    vulnerability_classes = models.ManyToManyField(VulnerabilityClass, blank=True,  verbose_name=_('Vulnerability Classification(s)'))
    activity = models.ForeignKey(Activity, on_delete=models.DO_NOTHING, null=True, blank=True)
    detection_method = models.CharField(max_length=15, choices=DETECTION_METHOD_CHOICES, default=MANUAL_DETECTION_METHOD,  verbose_name=_('Detection Method'))
    tags = models.ManyToManyField(Tag, blank=True)

    class Meta:
        ordering = ['-severity', 'status', '-created_date']
        verbose_name_plural = 'Vulnerabilities'

    def is_editable(self):
        return self.status != Vulnerability.INVALID_STATUS and self.status != Vulnerability.FIXED_STATUS

    def is_fixed(self):
        return self.status == Vulnerability.FIXED_STATUS

    def save(self, *args, **kwargs):
        """Automatically sets the open and closed dates when the status changes."""
        if self.pk is not None:
            vulnerability = Vulnerability.objects.get(pk=self.pk)
            now = timezone.now()
            if vulnerability.status != self.status \
                and self.status == Vulnerability.FIXED_STATUS:
                    self.fixed_at = now
        else:
            self.status = Vulnerability.OPEN_STATUS

        super(Vulnerability, self).save(*args, **kwargs)


class Attachment(models.Model):
    file_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text=_('Description of the attachment'))
    attachment = models.FileField()


class VulnerabilityAttachment(Attachment):
    """Attachment for a specific vulnerability."""
    vulnerability = models.ForeignKey(Vulnerability, on_delete=models.DO_NOTHING)


class VulnerabilityComment(Comment):
    """Comment for a specific engagement."""

    vulnerability = models.ForeignKey(Vulnerability, on_delete=models.DO_NOTHING)

# These two auto-delete files from filesystem when they are unneeded:

@receiver(models.signals.post_delete, sender=Attachment)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """
    Deletes file from filesystem
    when corresponding `Attachment` object is deleted.
    """
    if instance.attachment and os.path.isfile(instance.attachment.path):
        os.remove(instance.attachment.path)

@receiver(models.signals.pre_save, sender=Attachment)
def auto_delete_file_on_change(sender, instance, **kwargs):
    """
    Deletes old file from filesystem
    when corresponding `Attachment` object is updated
    with new file.
    """
    if not instance.pk:
        return False

    try:
        old_file = Attachment.objects.get(pk=instance.pk).attachment
    except Attachment.DoesNotExist:
        return False

    new_file = instance.attachment
    if not old_file == new_file and os.path.isfile(old_file.path):
        os.remove(old_file.path)
