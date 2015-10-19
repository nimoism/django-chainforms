from collections import OrderedDict
import re
from django import forms
from django.core.exceptions import ValidationError
from django.views.generic.base import TemplateView
from django.utils.translation import ugettext as _
from formtools.wizard.forms import ManagementForm
from formtools.wizard.storage import get_storage
from formtools.wizard.views import WizardView, StepsHelper
from chainforms.forms import ChainForm


class ChainWizardView(WizardView):
    prefix = None
    storage = None
    steps = None

    step_re = re.compile(r'^(\d+)(_(\d+))?$')

    def dispatch(self, request, *args, **kwargs):
        self.prefix = self.get_prefix(request, *args, **kwargs)
        self.storage = get_storage(self.storage_name, self.prefix, request, getattr(self, 'file_storage', None))
        self.steps = StepsHelper(self)
        response = TemplateView.dispatch(self, request, *args, **kwargs)

        # update the response (e.g. adding cookies)
        self.storage.update_response(response)
        return response

    def get(self, request, *args, **kwargs):
        """
        This method handles GET requests.

        If a GET request reaches this point, the wizard assumes that the user
        just starts at the first step or wants to restart the process.
        The data of the wizard will be resetted before rendering the first step
        """
        self.storage.reset()

        # reset the current step to the first step.
        step = self.normalize_step(self.steps.first)
        self.storage.current_step = step
        return self.render(self.get_form())

    def has_next_step(self, step):
        top_step, sub_step = self.step_parts(step)
        return top_step < len(self.get_form_list())

    def post(self, *args, **kwargs):
        """
        This method handles POST requests.

        The wizard will render either the current step (if form validation
        wasn't successful), the next step (if the current step was stored
        successful) or the done view (if no more steps are available)
        """
        # Look for a wizard_goto_step element in the posted data which
        # contains a valid step name. If one was found, render the requested
        # form. (This makes stepping back a lot easier).
        wizard_goto_step = self.request.POST.get('wizard_goto_step', None)
        if wizard_goto_step and wizard_goto_step in self.get_form_list():
            return self.render_goto_step(wizard_goto_step)

        # Check if form was refreshed
        management_form = ManagementForm(self.request.POST, prefix=self.prefix)
        if not management_form.is_valid():
            raise ValidationError(
                _('ManagementForm data is missing or has been tampered.'),
                code='missing_management_form',
            )

        form_current_step = management_form.cleaned_data['current_step']
        if (form_current_step != self.steps.current and
                self.storage.current_step is not None):
            # form refreshed, change current step
            self.storage.current_step = form_current_step
        # get the form for the current step
        step = self.storage.current_step
        form = self.get_form(step=step, data=self.request.POST, files=self.request.FILES)
        # and try to validate
        if form.is_valid():
            # if the form is valid, store the cleaned data and files.
            self.storage.set_step_data(step, self.process_step(form))
            self.storage.set_step_files(step, self.process_step_files(form))

            # check if the current step is the last step
            if self.has_next_step(step) or self.has_next_sub_step(step, form):
                return self.render_next_step(form)
            else:
                return self.render_done(form, **kwargs)
        return self.render(form)

    def normalize_step(self, step):
        top_step, sub_step = self.step_parts(step)
        if self.is_chain_step(step):
            if sub_step is None:
                sub_step = u'0'
                step = u'%s_%s' % (top_step, sub_step)
        else:
            step = top_step
        return step

    def is_chain_step(self, step):
        top_step, sub_step = self.step_parts(step)
        form_class = self.get_form_class(top_step)
        return issubclass(form_class, ChainForm)

    def get_form(self, step=None, data=None, files=None):
        """
        Constructs the form for a given `step`. If no `step` is defined, the
        current step will be determined automatically.

        The form will be initialized using the `data` argument to prefill the
        new form. If needed, instance or queryset (for `ModelForm` or
        `ModelFormSet`) will be added too.
        """
        if step is None:
            step = self.steps.current
        top_step, sub_step = self.step_parts(step)
        form_class = self.form_list[top_step]
        kwargs = self.get_form_kwargs(step)
        if data:
            kwargs.update(
                data=data
            )
        if files:
            kwargs.update(
                files=files
            )
        if issubclass(form_class, (forms.ModelForm,
                                   forms.models.BaseInlineFormSet)):
            kwargs.setdefault('instance', self.get_form_instance(step))
        elif issubclass(form_class, forms.models.BaseModelFormSet):
            kwargs.setdefault('queryset', self.get_form_instance(step))
        return form_class(**kwargs)

    def get_form_kwargs(self, step=None):
        kwargs = super(ChainWizardView, self).get_form_kwargs(step)
        kwargs.update({
            'prefix': self.get_form_prefix(step),
            'data': self.storage.get_step_data(step),
            'files': self.storage.get_step_files(step),
            'initial': self.get_form_initial(step),
        })
        return kwargs

    def render_next_step(self, form, **kwargs):
        """
        This method gets called when the next step/form should be rendered.
        `form` contains the last/current form.
        """
        # get the form instance based on the data from the storage backend
        # (if available).
        step = self.steps.current
        if self.has_next_sub_step(step, form):
            next_step = self.get_next_step(step, next_sub_step=True)
            form_kwargs = self.get_form_kwargs(next_step)
            form_kwargs.update(kwargs)
            new_form = form.get_next_form(**form_kwargs)
        else:
            next_step = self.get_next_step(step, next_sub_step=False)
            new_form = self.get_form(next_step,
                                     data=self.storage.get_step_data(next_step),
                                     files=self.storage.get_step_files(next_step))
        self.storage.current_step = next_step
        return self.render(new_form, **kwargs)

    def render_done(self, form, **kwargs):
        """
        This method gets called when all forms passed. The method should also
        re-validate all steps to prevent manipulation. If any form fails to
        validate, `render_revalidation_failure` should get called.
        If everything is fine call `done`.
        """
        final_forms = OrderedDict()
        # walk through the form list and try to validate the data again.
        forms = OrderedDict()
        for form_key in self.get_form_list():
            top_step = form_key
            step = self.normalize_step(top_step)
            if self.is_chain_step(step):
                form_obj = self.get_form(step=step, data=self.storage.get_step_data(step),
                                         files=self.storage.get_step_files(step))
                while True:
                    forms[step] = form_obj
                    if not form_obj.has_next_form():
                        break
                    step = self.get_next_step(step, next_sub_step=True)
                    form_kwargs = self.get_form_kwargs(step)
                    form_kwargs.update(
                        data=self.storage.get_step_data(step),
                        files=self.storage.get_step_files(step)
                    )
                    form_obj = form_obj.get_next_form(**form_kwargs)
            else:
                form_obj = self.get_form(step=step, data=self.storage.get_step_data(step),
                                         files=self.storage.get_step_files(step))
                forms[step] = form_obj
        for step, form_obj in forms.iteritems():
            if not form_obj.is_valid():
                return self.render_revalidation_failure(step, form_obj, **kwargs)
            final_forms[step] = form_obj

        # render the done view and reset the wizard before returning the
        # response. This is needed to prevent from rendering done with the
        # same data twice.
        done_response = self.done(final_forms.values(), form_dict=final_forms, **kwargs)
        # self.storage.reset()
        return done_response

    def has_next_sub_step(self, step, form):
        return self.is_chain_step(step) and form.has_next_form()

    def get_next_step(self, step=None, next_sub_step=False):
        if step is None:
            step = self.steps.current
        top_step, sub_step = self.step_parts(step)
        if next_sub_step:
            sub_step = unicode(int(sub_step) + 1)
        else:
            top_step = unicode(int(top_step) + 1)
            sub_step = u'0'
        next_step = u'%s_%s' % (top_step, sub_step)
        return next_step

    def get_prev_step(self, step=None):
        if step is None:
            step = self.steps.current
        top_step, sub_step = self.step_parts(step)
        if int(sub_step) > 0:
            sub_step = unicode(int(sub_step) - 1)
        elif int(top_step) > 0:
            top_step = unicode(int(top_step) - 1)
            sub_step = u'0'
        prev_step = u'%s_%s' % (top_step, sub_step)
        return prev_step

    @classmethod
    def step_parts(cls, step):
        match = cls.step_re.match(step)
        if not match:
            raise AttributeError("Invalid step attribute")
        top_step = match.group(1)
        sub_step = match.group(3)
        return top_step, sub_step

    def get_form_class(self, step):
        top_step, sub_step = self.step_parts(step)
        return self.get_form_list().get(top_step)
