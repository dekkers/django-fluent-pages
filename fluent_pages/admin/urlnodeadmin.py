from django.contrib import admin
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import render_to_response
from django.template.context import RequestContext
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from mptt.admin import MPTTModelAdmin
from mptt.forms import MPTTAdminForm
from fluent_pages.models import UrlNode, Page
from fluent_pages.forms.fields import RelativeRootPathField


class UrlNodeAdminForm(MPTTAdminForm):
    """
    The admin form for the main fields (the ``UrlNode`` object).
    """

    # Using a separate formfield to display the full URL in the override_url field:
    # - The override_url is stored relative to the URLConf root,
    #   which makes the site easily portable to another path or root.
    # - Users don't have to know or care about this detail.
    #   They only see the absolute external URLs, so make the input reflect that as well.
    override_url = RelativeRootPathField(max_length=300, required=False)


    def __init__(self, *args, **kwargs):
        super(UrlNodeAdminForm, self).__init__(*args, **kwargs)
        # Copy the fields/labels from the model field, to avoid repeating the labels.
        modelfield = [f for f in UrlNode._meta.fields if f.name == 'override_url'][0]
        self.fields['override_url'].label = modelfield.verbose_name
        self.fields['override_url'].help_text = modelfield.help_text


    def clean(self):
        """
        Extend valiation of the form, checking whether the URL is unique.
        Returns all fields which are valid.
        """
        # As of Django 1.3, only valid fields are passed in cleaned_data.
        cleaned_data = super(UrlNodeAdminForm, self).clean()

        # See if the current
        all_objects = UrlNode.objects.all().non_polymorphic()

        if self.instance and self.instance.id:
            # Editing an existing page
            current_id = self.instance.id
            other_objects = all_objects.exclude(id=current_id)
            parent = UrlNode.objects.non_polymorphic().get(pk=current_id).parent
        else:
            # Creating new page!
            parent = cleaned_data['parent']
            other_objects = all_objects

        # If fields are filled in, and still valid, check for unique URL.
        # Determine new URL (note: also done in UrlNode model..)
        if cleaned_data.get('override_url'):
            new_url = cleaned_data['override_url']

            if other_objects.filter(_cached_url=new_url).count():
                self._errors['override_url'] = self.error_class([_('This URL is already taken by an other page.')])
                del cleaned_data['override_url']

        elif cleaned_data.get('slug'):
            new_slug = cleaned_data['slug']
            if parent:
                new_url = '%s%s/' % (parent._cached_url, new_slug)
            else:
                new_url = '/%s/' % new_slug

            if other_objects.filter(_cached_url=new_url).count():
                self._errors['slug'] = self.error_class([_('This slug is already used by an other page at the same level.')])
                del cleaned_data['slug']

        return cleaned_data



class UrlNodeAdmin(MPTTModelAdmin):
    """
    The admin screen for the ``UrlNode`` objects.
    """

    # Config list page:
    list_display = ('title', 'status_column', 'modification_date', 'actions_column')
    #list_filter = ('status', 'parent')
    search_fields = ('slug', 'title')
    actions = ['make_published']
    change_list_template = None  # Restore Django's default search behavior, no admin/mptt_change_list.html


    # Expose fieldsets for subclasses to reuse
    FIELDSET_GENERAL = (None, {
        'fields': ('title', 'slug', 'status',),
    })
    FIELDSET_MENU = (_('Menu structure'), {
        'fields': ('sort_order', 'parent', 'in_navigation'),
        'classes': ('collapse',),
    })
    FIELDSET_PUBLICATION = (_('Publication settings'), {
        'fields': ('publication_date', 'expire_date', 'override_url'),
        'classes': ('collapse',),
    })


    # Config add/edit:
    prepopulated_fields = { 'slug': ('title',), }
    raw_id_fields = ['parent']

    base_form = UrlNodeAdminForm
    base_fieldsets = (
        FIELDSET_GENERAL,
        FIELDSET_MENU,
        FIELDSET_PUBLICATION
    )
    radio_fields = {'status': admin.HORIZONTAL}


    class Media:
        css = {
            'screen': ('fluent_pages/admin.css',)
        }


    def save_model(self, request, obj, form, change):
        # Automatically store the user in the author field.
        if not change:
            obj.author = request.user
        obj.save()



    # ---- Improving the form/fieldset default display ----


    def get_form(self, request, obj=None, **kwargs):
        # The django admin validation requires the form to have a 'class Meta: model = ..'
        # attribute, or it will complain that the fields are missing.
        # However, this enforces all derived ModelAdmin classes to redefine the model as well,
        # because they need to explicitly set the model again - it will stick with the base model.
        #
        # Instead, pass the form unchecked here, because the standard ModelForm will just work.
        # If the derived class sets the model explicitly, respect that setting.
        if self.form == UrlNodeAdmin.form:
            kwargs['form'] = self.base_form
        return super(UrlNodeAdmin, self).get_form(request, obj, **kwargs)


    def get_fieldsets(self, request, obj=None):
        # If subclass declares fieldsets, this is respected
        if self.declared_fieldsets:
            return super(UrlNodeAdmin, self).get_fieldsets(request, obj)

        # Have a reasonable default fieldsets,
        # where the subclass fields are automatically included.
        other_fields = self.get_subclass_fields(request, obj)

        if other_fields:
            return (
               self.base_fieldsets[0],
               (_("Contents"), {'fields': other_fields}),
            ) + self.base_fieldsets[1:]
        else:
            return self.base_fieldsets


    def get_subclass_fields(self, request, obj=None):
        # Find out how many fields would really be on the form,
        # if it weren't restricted by declared fields.
        exclude = list(self.exclude or [])
        exclude.extend(self.get_readonly_fields(request, obj))

        # By not declaring the fields/form in the base class,
        # get_form() will populate the form with all available fields.
        form = self.get_form(request, obj, exclude=exclude)
        subclass_fields = form.base_fields.keys() + list(self.get_readonly_fields(request, obj))

        # Find which fields are not part of the common fields.
        for fieldset in self.base_fieldsets:
            for field in fieldset[1]['fields']:
                subclass_fields.remove(field)
        return subclass_fields



    # ---- list actions ----

    STATUS_ICONS = (
        (UrlNode.PUBLISHED, 'img/admin/icon-yes.gif'),
        (UrlNode.DRAFT,     'img/admin/icon-unknown.gif'),
    )

    def status_column(self, urlnode):
        status = urlnode.status
        title = [rec[1] for rec in UrlNode.STATUSES if rec[0] == status].pop()
        icon  = [rec[1] for rec in self.STATUS_ICONS  if rec[0] == status].pop()
        return u'<img src="{admin}{icon}" width="10" height="10" alt="{title}" title="{title}" />'.format(
            admin=settings.ADMIN_MEDIA_PREFIX, icon=icon, title=title)

    status_column.allow_tags = True
    status_column.short_description = _('Status')


    def actions_column(self, urlnode):
        return u' '.join(self._actions_column_icons(urlnode))

    actions_column.allow_tags = True
    actions_column.short_description = _('actions')


    def _actions_column_icons(self, urlnode):
        actions = [
            u'<a href="add/?{parentattr}={id}" title="{title}"><img src="{static}fluent_pages/img/admin/page_new.gif" width="16" height="16" alt="{title}" /></a>'.format(
                parentattr=self.model._mptt_meta.parent_attr, id=urlnode.pk, title=_('Add child'), static=settings.STATIC_URL)
        ]

        if hasattr(urlnode, 'get_absolute_url') and urlnode.is_published:
            actions.append(
                u'<a href="{url}" title="{title}" target="_blank"><img src="{static}fluent_pages/img/admin/world.gif" width="16" height="16" alt="{title}" /></a>'.format(
                    url=urlnode.get_absolute_url(), title=_('View on site'), static=settings.STATIC_URL)
                )
        return actions


    # ---- Custom actions ----

    def make_published(self, request, queryset):
        rows_updated = queryset.update(status=UrlNode.PUBLISHED)

        if rows_updated == 1:
            message = "1 page was marked as published."
        else:
            message = "{0} pages were marked as published.".format(rows_updated)
        self.message_user(request, message)


    make_published.short_description = _("Mark selected objects as published")



    # ---- Fixing the breadcrumb and templates ----



    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        # Get parent object for breadcrumb
        parent_object = None
        parent_id = request.REQUEST.get('parent')
        if add and parent_id:
            parent_object = UrlNode.objects.get(pk=int(parent_id))  # is polymorphic
        elif change:
            parent_object = obj.parent

        # Improve the breadcrumb
        base_opts = Page._meta
        base_app_label = base_opts.app_label
        context.update({
            'parent_object': parent_object,
            'app_label': base_app_label,
            'base_opts': base_opts,
        })

        # Standard stuff, with a slight twist that couldn't be overwritten.
        # The template is searched in both the derived class and base class paths.
        opts = self.model._meta
        app_label = opts.app_label
        ordered_objects = opts.get_ordered_objects()
        context.update({
            'add': add,
            'change': change,
            'has_add_permission': self.has_add_permission(request),
            'has_change_permission': self.has_change_permission(request, obj),
            'has_delete_permission': self.has_delete_permission(request, obj),
            'has_file_field': True, # FIXME - this should check if form or formsets have a FileField,
            'has_absolute_url': hasattr(self.model, 'get_absolute_url'),
            'ordered_objects': ordered_objects,
            'form_url': mark_safe(form_url),
            'opts': opts,
            'content_type_id': ContentType.objects.get_for_model(self.model).id,
            'save_as': self.save_as,
            'save_on_top': self.save_on_top,
            'root_path': self.admin_site.root_path,
        })
        if add and self.add_form_template is not None:
            form_template = self.add_form_template
        else:
            form_template = self.change_form_template
        context_instance = RequestContext(request, current_app=self.admin_site.name)
        return render_to_response(form_template or [
            "admin/%s/%s/change_form.html" % (app_label, opts.object_name.lower()),
            "admin/%s/change_form.html" % app_label,
            # Added:
            "admin/%s/%s/change_form.html" % (base_app_label, base_opts.object_name.lower()),
            "admin/%s/change_form.html" % base_app_label,
            "admin/change_form.html"
        ], context, context_instance=context_instance)