# vim: expandtab
# -*- coding: utf-8 -*-
from collections import OrderedDict
from dateutil.relativedelta import relativedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import smart_text
from django.contrib.sessions.models import Session
from multiselectfield import MultiSelectFormField

from poleno.attachments.forms import AttachmentsField
from poleno.workdays import workdays
from poleno.utils.models import after_saved
from poleno.utils.urls import reverse
from poleno.utils.forms import AutoSuppressedSelect
from poleno.utils.date import local_date, local_today
from chcemvediet.apps.wizards import Wizard, WizardStep
from chcemvediet.apps.obligees.forms import ObligeeWithAddressInput, ObligeeAutocompleteField
from chcemvediet.apps.inforequests.models import Action, InforequestEmail

class ObligeeActionStep(WizardStep):
    template = u'inforequests/obligee_action/wizard.html'
    form_template = u'main/snippets/form_horizontal.html'

class ReasonsMixin(ObligeeActionStep):
    refusal_reason = MultiSelectFormField(
            label=u' ',
            choices=Action.REFUSAL_REASONS._choices + [
                (u'none', _(u'inforequests:obligee_action:ReasonsMixin:none')),
                ],
            )

    def clean(self):
        cleaned_data = super(ReasonsMixin, self).clean()

        refusal_reason = cleaned_data.get(u'refusal_reason', None)
        if refusal_reason is not None:
            if u'none' in refusal_reason and len(refusal_reason) != 1:
                msg = _(u'inforequests:obligee_action:ReasonsMixin:error:none_contradiction')
                self.add_error(u'refusal_reason', msg)

        return cleaned_data

    def values(self):
        res = super(ReasonsMixin, self).values()
        if u'none' in self.cleaned_data[u'refusal_reason']:
            res[u'result_refusal_reason'] = []
        else:
            res[u'result_refusal_reason'] = self.cleaned_data[u'refusal_reason']
        return res

# Prologue

class BasicsStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/basics.html'

    branch = forms.TypedChoiceField(
            label=_(u'inforequests:obligee_action:BasicsStep:branch:label'),
            empty_value=None,
            widget=AutoSuppressedSelect(
                attrs={
                    u'class': u'span5',
                    },
                suppressed_attrs={
                    u'class': u'suppressed-control',
                    }),
            )
    delivered_date = forms.DateField(
            label=_(u'inforequests:obligee_action:BasicsStep:delivered_date:label'),
            localize=True,
            widget=forms.DateInput(attrs={
                u'placeholder': _('inforequests:obligee_action:BasicsStep:delivered_date:placeholder'),
                u'class': u'datepicker',
                }),
            )
    attachments = AttachmentsField(
            label=_(u'inforequests:obligee_action:BasicsStep:attachments:label'),
            upload_url_func=(lambda: reverse(u'inforequests:upload_attachment')),
            download_url_func=(lambda a: reverse(u'inforequests:download_attachment', args=[a.pk])),
            )

    def __init__(self, *args, **kwargs):
        super(BasicsStep, self).__init__(*args, **kwargs)

        # branch: we assume that converting a Branch to a string gives its ``pk``
        field = self.fields[u'branch']
        field.choices = [(branch, branch.historicalobligee.name)
                for branch in self.wizard.inforequest.branches]
        if len(field.choices) > 1:
            field.choices.insert(0, (u'', u''))

        def coerce(val):
            for o, v in self.fields[u'branch'].choices:
                if o and smart_text(o.pk) == val:
                    return o
            raise ValueError
        field.coerce = coerce

        # delivered_date
        if self.wizard.email:
            del self.fields[u'delivered_date']

        # attachments
        if self.wizard.email:
            del self.fields[u'attachments']
        else:
            field = self.fields[u'attachments']
            session = Session.objects.get(session_key=self.wizard.request.session.session_key)
            field.attached_to = (self.wizard.draft, session)

    def clean(self):
        cleaned_data = super(BasicsStep, self).clean()

        branch = cleaned_data.get(u'branch', None)
        delivered_date = cleaned_data.get(u'delivered_date', None)
        if delivered_date is not None:
            try:
                if branch and delivered_date < branch.last_action.legal_date:
                    raise ValidationError(_(u'inforequests:obligee_action:BasicsStep:delivered_date:error:older_than_previous'))
                if delivered_date > local_today():
                    raise ValidationError(_(u'inforequests:obligee_action:BasicsStep:delivered_date:error:from_future'))
                if delivered_date < local_today() - relativedelta(months=1):
                    raise ValidationError(_(u'inforequests:obligee_action:BasicsStep:delivered_date:error:older_than_month'))
            except ValidationError as e:
                self.add_error(u'delivered_date', e)

        return cleaned_data

    def commit(self):
        super(BasicsStep, self).commit()

        @after_saved(self.wizard.draft)
        def deferred(draft):
            for attachment in self.cleaned_data.get(u'attachments', []):
                attachment.generic_object = draft
                attachment.save()

    def values(self):
        res = super(BasicsStep, self).values()
        res[u'result_branch'] = self.cleaned_data[u'branch']
        res[u'result_delivered_date'] = self.cleaned_data[u'delivered_date'] if not self.wizard.email else local_date(self.wizard.email.processed)
        res[u'result_attachments'] = self.cleaned_data[u'attachments'] if not self.wizard.email else None
        return res

# Pre Appeal

class IsQuestionStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/is_question.html'

    is_question = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:IsQuestionStep:yes')),
                (0, _(u'inforequests:obligee_action:IsQuestionStep:no')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        return not result and branch and branch.can_add_clarification_request

    def values(self):
        res = super(IsQuestionStep, self).values()
        if self.cleaned_data[u'is_question']:
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.CLARIFICATION_REQUEST
        return res

class IsConfirmationStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/is_confirmation.html'

    is_confirmation = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:IsConfirmationStep:yes')),
                (0, _(u'inforequests:obligee_action:IsConfirmationStep:no')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        return not result and branch and branch.can_add_confirmation

    def values(self):
        res = super(IsConfirmationStep, self).values()
        if self.cleaned_data[u'is_confirmation']:
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.CONFIRMATION
        return res

class IsOnTopicStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/is_on_topic.html'

    is_on_topic = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:IsOnTopicStep:yes')),
                (0, _(u'inforequests:obligee_action:IsOnTopicStep:no')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        return not result and branch and branch.can_add_refusal

class ContainsInfoStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/contains_info.html'

    contains_info = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (Action.DISCLOSURE_LEVELS.FULL, _(u'inforequests:obligee_action:ContainsInfoStep:full')),
                (Action.DISCLOSURE_LEVELS.PARTIAL, _(u'inforequests:obligee_action:ContainsInfoStep:partial')),
                (Action.DISCLOSURE_LEVELS.NONE, _(u'inforequests:obligee_action:ContainsInfoStep:none')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_on_topic = wizard.values.get(u'is_on_topic', True)
        return not result and branch and branch.can_add_refusal and is_on_topic

    def values(self):
        res = super(ContainsInfoStep, self).values()
        res[u'result_disclosure_level'] = self.cleaned_data[u'contains_info']
        if self.cleaned_data[u'contains_info'] == Action.DISCLOSURE_LEVELS.FULL:
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.DISCLOSURE
        return res

class IsDecisionStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/is_decision.html'

    is_decision = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:IsDecisionStep:yes')),
                (0, _(u'inforequests:obligee_action:IsDecisionStep:no')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_on_topic = wizard.values.get(u'is_on_topic', True)
        return not result and branch and branch.can_add_refusal and is_on_topic

    def values(self):
        res = super(IsDecisionStep, self).values()
        if self.cleaned_data[u'is_decision']:
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.REFUSAL
        return res

class RefusalReasonsStep(ReasonsMixin, ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/refusal_reasons.html'

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        action = wizard.values.get(u'result_action', None)
        return result == u'action' and action == Action.TYPES.REFUSAL

class IsAdvancementStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/is_advancement.html'

    is_advancement = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:IsAdvancementStep:yes')),
                (0, _(u'inforequests:obligee_action:IsAdvancementStep:no')),
                ),
            widget=forms.RadioSelect(attrs={
                u'class': u'toggle-changed',
                u'data-container': u'form',
                u'data-target-1': u'.control-group:has(.visible-if-advancement)',
                }),
            )
    advanced_to_1 = ObligeeAutocompleteField(
            label=_(u'inforequests:obligee_action:IsAdvancementStep:advanced_to_1:label'),
            required=False,
            widget=ObligeeWithAddressInput(attrs={
                u'placeholder': _(u'inforequests:obligee_action:IsAdvancementStep:advanced_to_1:placeholder'),
                u'class': u'span5 visible-if-advancement',
                }),
            )
    advanced_to_2 = ObligeeAutocompleteField(
            label=_(u'inforequests:obligee_action:IsAdvancementStep:advanced_to_2:label'),
            required=False,
            widget=ObligeeWithAddressInput(attrs={
                u'placeholder': _(u'inforequests:obligee_action:IsAdvancementStep:advanced_to_2:placeholder'),
                u'class': u'span5 visible-if-advancement',
                }),
            )
    advanced_to_3 = ObligeeAutocompleteField(
            label=_(u'inforequests:obligee_action:IsAdvancementStep:advanced_to_3:label'),
            required=False,
            widget=ObligeeWithAddressInput(attrs={
                u'placeholder': _(u'inforequests:obligee_action:IsAdvancementStep:advanced_to_3:placeholder'),
                u'class': u'span5 visible-if-advancement',
                }),
            )
    ADVANCED_TO_FIELDS = [u'advanced_to_1', u'advanced_to_2', u'advanced_to_3']

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_on_topic = wizard.values.get(u'is_on_topic', True)
        return not result and branch and branch.can_add_advancement and is_on_topic

    def clean(self):
        cleaned_data = super(IsAdvancementStep, self).clean()

        is_advancement = cleaned_data.get(u'is_advancement', None)
        if is_advancement and not any(cleaned_data.get(f) for f in self.ADVANCED_TO_FIELDS):
            msg = self.fields[u'advanced_to_1'].error_messages[u'required']
            self.add_error(u'advanced_to_1', msg)

        branch = self.wizard.values[u'branch']
        for i, field in enumerate(self.ADVANCED_TO_FIELDS):
            advanced_to = cleaned_data.get(field, None)
            try:
                if advanced_to and advanced_to == branch.obligee:
                    raise ValidationError(_(u'inforequests:obligee_action:IsAdvancementStep:error:same_obligee'))
                for field_2 in self.ADVANCED_TO_FIELDS[0:i]:
                    advanced_to_2 = cleaned_data.get(field_2, None)
                    if advanced_to_2 and advanced_to_2 == advanced_to:
                        raise ValidationError(_(u'inforequests:obligee_action:IsAdvancementStep:error:duplicate_obligee'))
            except ValidationError as e:
                self.add_error(field, e)

        return cleaned_data

    def values(self):
        res = super(IsAdvancementStep, self).values()
        if self.cleaned_data[u'is_advancement']:
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.ADVANCEMENT
            res[u'result_advanced_to'] = [self.cleaned_data[f] for f in self.ADVANCED_TO_FIELDS]
        return res

class IsExtensionStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/is_extension.html'

    is_extension = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:IsExtensionStep:yes')),
                (0, _(u'inforequests:obligee_action:IsExtensionStep:no')),
                ),
            widget=forms.RadioSelect(attrs={
                u'class': u'toggle-changed',
                u'data-container': u'form',
                u'data-target-1': u'.control-group:has(.visible-if-extension)',
                }),
            )
    extension = forms.IntegerField(
            label=_(u'inforequests:obligee_action:IsExtensionStep:extension:label'),
            initial=8,
            min_value=2,
            max_value=15,
            widget=forms.NumberInput(attrs={
                u'placeholder': _(u'inforequests:obligee_action:IsExtensionStep:extension:placeholder'),
                u'class': u'visible-if-extension',
                }),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_on_topic = wizard.values.get(u'is_on_topic', True)
        return not result and branch and branch.can_add_extension and is_on_topic

    def clean(self):
        cleaned_data = super(IsExtensionStep, self).clean()

        is_extension = cleaned_data.get(u'is_extension', None)
        extension = cleaned_data.get(u'extension', None)
        if not is_extension and not extension:
            msg = self.fields[u'extension'].error_messages[u'required']
            self.add_error(u'extension', msg)

        return cleaned_data

    def values(self):
        res = super(IsExtensionStep, self).values()
        if self.cleaned_data[u'is_extension']:
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.EXTENSION
            res[u'result_extension'] = self.cleaned_data[u'extension']
        return res

class DisclosureReasonsStep(ReasonsMixin, ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/disclosure_reasons.html'

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_on_topic = wizard.values.get(u'is_on_topic', True)
        return not result and branch and branch.can_add_disclosure and is_on_topic

    def values(self):
        res = super(DisclosureReasonsStep, self).values()
        res[u'result'] = u'action'
        res[u'result_action'] = Action.TYPES.DISCLOSURE
        return res

# Post Appeal

class IsAppealDecisionStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/is_appeal_decision.html'

    is_appeal_decision = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:IsAppealDecisionStep:yes')),
                (0, _(u'inforequests:obligee_action:IsAppealDecisionStep:no')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        return not wizard.email and not result and branch and branch.can_add_remandment

class ContainsAppealInfoStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/contains_appeal_info.html'

    contains_appeal_info = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (Action.DISCLOSURE_LEVELS.FULL, _(u'inforequests:obligee_action:ContainsAppealInfoStep:full')),
                (Action.DISCLOSURE_LEVELS.PARTIAL, _(u'inforequests:obligee_action:ContainsAppealInfoStep:partial')),
                (Action.DISCLOSURE_LEVELS.NONE, _(u'inforequests:obligee_action:ContainsAppealInfoStep:none')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_appeal_decision = wizard.values.get(u'is_appeal_decision', True)
        return not wizard.email and not result and branch and branch.can_add_remandment and is_appeal_decision

    def values(self):
        res = super(ContainsAppealInfoStep, self).values()
        res[u'result_disclosure_level'] = self.cleaned_data[u'contains_appeal_info']
        return res

class WasAcceptedStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/was_accepted.html'

    was_accepted = forms.ChoiceField(
            label=u' ',
            choices=(
                (u'all', _(u'inforequests:obligee_action:WasAcceptedStep:all')),
                (u'some', _(u'inforequests:obligee_action:WasAcceptedStep:some')),
                (u'none', _(u'inforequests:obligee_action:WasAcceptedStep:none')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_appeal_decision = wizard.values.get(u'is_appeal_decision', True)
        return not wizard.email and not result and branch and branch.can_add_remandment and is_appeal_decision

    def values(self):
        res = super(WasAcceptedStep, self).values()
        if self.cleaned_data[u'was_accepted'] == u'none':
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.AFFIRMATION
        return res

class WasReturnedStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/was_returned.html'

    was_returned = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:WasReturnedStep:yes')),
                (0, _(u'inforequests:obligee_action:WasReturnedStep:no')),
                ),
            widget=forms.RadioSelect(),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_appeal_decision = wizard.values.get(u'is_appeal_decision', True)
        return not wizard.email and not result and branch and branch.can_add_remandment and is_appeal_decision

    def values(self):
        res = super(WasReturnedStep, self).values()
        if self.cleaned_data[u'was_returned']:
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.REMANDMENT
        elif self.wizard.values[u'result_disclosure_level'] != Action.DISCLOSURE_LEVELS.NONE:
            res[u'result'] = u'action'
            res[u'result_action'] = Action.TYPES.REVERSION
        else:
            res[u'result'] = u'help'
        return res

class ReversionReasonsStep(ReasonsMixin, ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/reversion_reasons.html'

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        action = wizard.values.get(u'result_action', None)
        level = wizard.values.get(u'result_disclosure_level', None)
        return result == u'action' and action == Action.TYPES.REVERSION and level == Action.DISCLOSURE_LEVELS.PARTIAL

class InvalidReversionStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/invalid_reversion.html'

    help_request = forms.CharField(
            label=_(u'inforequests:obligee_action:InvalidReversionStep:help_request:label'),
            widget=forms.Textarea(attrs={
                u'placeholder': _(u'inforequests:obligee_action:InvalidReversionStep:help_request:placeholder'),
                u'class': u'input-block-level',
                }),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        branch = wizard.values.get(u'branch', None)
        is_appeal_decision = wizard.values.get(u'is_appeal_decision', True)
        return not wizard.email and result == u'help' and branch and branch.can_add_remandment and is_appeal_decision

    def values(self):
        res = super(InvalidReversionStep, self).values()
        res[u'result'] = u'help'
        res[u'result_help'] = self.cleaned_data[u'help_request']
        return res

# Epilogue

class NotCategorizedStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/not_categorized.html'

    wants_help = forms.TypedChoiceField(
            label=u' ',
            coerce=int,
            choices=(
                (1, _(u'inforequests:obligee_action:NotCategorizedStep:help')),
                (0, _(u'inforequests:obligee_action:NotCategorizedStep:unrelated')),
                ),
            widget=forms.RadioSelect(attrs={
                u'class': u'toggle-changed',
                u'data-container': u'form',
                u'data-target-1': u'.control-group:has(.visible-if-wants-help)',
                }),
            )
    help_request = forms.CharField(
            label=_(u'inforequests:obligee_action:NotCategorizedStep:help_request:label'),
            required=False,
            widget=forms.Textarea(attrs={
                u'placeholder': _(u'inforequests:obligee_action:NotCategorizedStep:help_request:placeholder'),
                u'class': u'input-block-level visible-if-wants-help',
                }),
            )


    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        return not result

    def clean(self):
        cleaned_data = super(NotCategorizedStep, self).clean()

        wants_help = cleaned_data.get(u'wants_help', None)
        help_request = cleaned_data.get(u'help_request', None)
        if wants_help and not help_request:
            msg = self.fields[u'help_request'].error_messages[u'required']
            self.add_error(u'help_request', msg)

        return cleaned_data

    def values(self):
        res = super(NotCategorizedStep, self).values()
        if self.cleaned_data[u'wants_help']:
            res[u'result'] = u'help'
            res[u'result_help'] = self.cleaned_data[u'help_request']
        else:
            res[u'result'] = u'unrelated'
        return res

class CategorizedStep(ObligeeActionStep):
    text_template = u'inforequests/obligee_action/texts/categorized.html'

    legal_date = forms.DateField(
            label=_(u'inforequests:obligee_action:CategorizedStep:legal_date:label'),
            localize=True,
            widget=forms.DateInput(attrs={
                u'placeholder': _('inforequests:obligee_action:CategorizedStep:legal_date:placeholder'),
                u'class': u'datepicker',
                }),
            )
    file_number = forms.CharField(
            label=_(u'inforequests:obligee_action:CategorizedStep:file_number:label'),
            max_length=255,
            required=False,
            widget=forms.TextInput(attrs={
                u'placeholder': _(u'inforequests:obligee_action:CategorizedStep:file_number:placeholder'),
                u'class': u'span5',
                }),
            )
    last_action_delivered_date = forms.DateField(
            localize=True,
            required=False,
            widget=forms.DateInput(attrs={
                u'placeholder': _('inforequests:obligee_action:CategorizedStep:last_action_delivered_date:placeholder'),
                u'class': u'datepicker',
                }),
            )

    @classmethod
    def applicable(cls, wizard):
        result = wizard.values.get(u'result', None)
        return result == u'action'

    def __init__(self, *args, **kwargs):
        super(CategorizedStep, self).__init__(*args, **kwargs)

        branch = self.wizard.values[u'result_branch']
        if branch.last_action.delivered_date is not None:
            del self.fields[u'last_action_delivered_date']
        elif branch.last_action.type == Action.TYPES.REQUEST:
            self.fields[u'last_action_delivered_date'].label=_(u'inforequests:obligee_action:CategorizedStep:last_action_delivered_date:label:request')
        elif branch.last_action.type == Action.TYPES.CLARIFICATION_RESPONSE:
            self.fields[u'last_action_delivered_date'].label=_(u'inforequests:obligee_action:CategorizedStep:last_action_delivered_date:label:clarification_response')
        elif branch.last_action.type == Action.TYPES.APPEAL:
            self.fields[u'last_action_delivered_date'].label=_(u'inforequests:obligee_action:CategorizedStep:last_action_delivered_date:label:appeal')
        elif branch.last_action.type == Action.TYPES.ADVANCED_REQUEST:
            self.fields[u'last_action_delivered_date'].label=_(u'inforequests:obligee_action:CategorizedStep:last_action_delivered_date:label:advanced_request')
        else:
            del self.fields[u'last_action_delivered_date']

    def clean(self):
        cleaned_data = super(CategorizedStep, self).clean()

        branch = self.wizard.values[u'result_branch']
        delivered_date = self.wizard.values[u'result_delivered_date']
        legal_date = cleaned_data.get(u'legal_date', None)
        last_action_delivered_date = cleaned_data.get(u'last_action_delivered_date', None)
        if legal_date is not None:
            try:
                if legal_date > delivered_date:
                    raise ValidationError(_(u'inforequests:obligee_action:CategorizedStep:legal_date:error:newer_than_delivered_date'))
                if legal_date < branch.last_action.legal_date:
                    raise ValidationError(_(u'inforequests:obligee_action:CategorizedStep:legal_date:error:older_than_previous'))
                if legal_date > local_today():
                    raise ValidationError(_(u'inforequests:obligee_action:CategorizedStep:legal_date:error:from_future'))
                if legal_date < local_today() - relativedelta(months=1):
                    raise ValidationError(_(u'inforequests:obligee_action:CategorizedStep:legal_date:error:older_than_month'))
            except ValidationError as e:
                self.add_error(u'legal_date', e)
        if last_action_delivered_date is not None:
            try:
                if legal_date and last_action_delivered_date > legal_date:
                    raise ValidationError(_(u'inforequests:obligee_action:CategorizedStep:last_action_delivered_date:error:newer_than_legal_date'))
                if last_action_delivered_date < branch.last_action.legal_date:
                    raise ValidationError(_(u'inforequests:obligee_action:CategorizedStep:last_action_delivered_date:error:older_than_last_action_legal_date'))
                if last_action_delivered_date > local_today():
                    raise ValidationError(_(u'inforequests:obligee_action:CategorizedStep:last_action_delivered_date:error:from_future'))
                pass
            except ValidationError as e:
                self.add_error(u'last_action_delivered_date', e)

        return cleaned_data

    def values(self):
        res = super(CategorizedStep, self).values()
        res[u'result_legal_date'] = self.cleaned_data[u'legal_date']
        res[u'result_file_number'] = self.cleaned_data[u'file_number']
        res[u'result_last_action_delivered_date'] = self.cleaned_data.get(u'last_action_delivered_date', None)
        return res

class ObligeeActionWizard(Wizard):
    step_classes = OrderedDict([
            (u'basics', BasicsStep),
            (u'is_question', IsQuestionStep),
            (u'is_confirmation', IsConfirmationStep),
            (u'is_on_topic', IsOnTopicStep),
            (u'contains_info', ContainsInfoStep),
            (u'is_decision', IsDecisionStep),
            (u'refusal_reasons', RefusalReasonsStep),
            (u'is_advancement', IsAdvancementStep),
            (u'is_extension', IsExtensionStep),
            (u'disclosure_reasons', DisclosureReasonsStep),
            (u'is_appeal_decision', IsAppealDecisionStep),
            (u'contains_appeal_info', ContainsAppealInfoStep),
            (u'was_accepted', WasAcceptedStep),
            (u'was_returned', WasReturnedStep),
            (u'reversion_reasons', ReversionReasonsStep),
            (u'invalid_reversion', InvalidReversionStep),
            (u'not_categorized', NotCategorizedStep),
            (u'categorized', CategorizedStep),
            ])

    def __init__(self, request, inforequest, inforequestemail, email):
        super(ObligeeActionWizard, self).__init__(request)
        self.instance_id = u'%s-%s' % (self.__class__.__name__, inforequest.pk)
        self.inforequest = inforequest
        self.inforequestemail = inforequestemail
        self.email = email

    def get_step_url(self, step, anchor=u''):
        return reverse(u'inforequests:obligee_action', kwargs=dict(inforequest=self.inforequest, step=step)) + anchor

    def context(self, extra=None):
        res = super(ObligeeActionWizard, self).context(extra)
        res.update({
                u'inforequest': self.inforequest,
                u'email': self.email,
                })
        return res

    def save_action(self):
        assert self.values[u'result'] == u'action'
        assert self.values[u'result_action'] in Action.OBLIGEE_ACTION_TYPES
        assert not self.email or self.values[u'result_action'] in Action.OBLIGEE_EMAIL_ACTION_TYPES
        assert self.values[u'result_branch'].can_add_action(self.values[u'result_action'])

        branch = self.values[u'result_branch']
        last_action_delivered_date = self.values.get(u'result_last_action_delivered_date', None)
        if last_action_delivered_date and not branch.last_action.delivered_date:
            branch.last_action.delivered_date = last_action_delivered_date
            branch.last_action.save()

        action = Action.create(
                branch=self.values[u'result_branch'],
                type=self.values[u'result_action'],
                email=self.email if self.email else None,
                subject=self.email.subject if self.email else u'',
                content=self.email.text if self.email else u'',
                file_number=self.values.get(u'result_file_number', u''),
                delivered_date=self.values[u'result_delivered_date'],
                legal_date=self.values[u'result_legal_date'],
                extension=self.values.get(u'result_extension', None),
                disclosure_level=self.values.get(u'result_disclosure_level', None),
                refusal_reason=self.values.get(u'result_refusal_reason', None),
                advanced_to=self.values.get(u'result_advanced_to', None),
                attachments=self.email.attachments if self.email else self.values.get(u'result_attachments', None),
                )
        action.save()

        if self.email:
            self.inforequestemail.type = InforequestEmail.TYPES.OBLIGEE_ACTION
            self.inforequestemail.save(update_fields=[u'type'])

        return action

    def save_help(self):
        assert self.values[u'result'] == u'help'
        # FIXME: use wizard.values[u'result_help'] to create a ticket

        if self.email:
            self.inforequestemail.type = InforequestEmail.TYPES.UNKNOWN
            self.inforequestemail.save(update_fields=[u'type'])

    def save_unrelated(self):
        assert self.values[u'result'] == u'unrelated'

        if self.email:
            self.inforequestemail.type = InforequestEmail.TYPES.UNRELATED
            self.inforequestemail.save(update_fields=[u'type'])
