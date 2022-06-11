from typing import Any

from django.http import Http404
from django.urls import reverse
from django.views.generic import DetailView, RedirectView, TemplateView

from cbv.models import Klass, Module, ProjectVersion


class RedirectToLatestVersionView(RedirectView):
    permanent = False

    def get_redirect_url(self, *, package: str, url_name: str, **kwargs):
        kwargs["version"] = ProjectVersion.objects.get_latest(package).version_number
        self.url = reverse(url_name, kwargs={"package": package, **kwargs})
        return super().get_redirect_url(**kwargs)


class KlassDetailView(DetailView):
    model = Klass
    template_name = "cbv/klass_detail.html"
    push_state_url = None

    def get_object(self, queryset=None):
        try:
            obj = self.get_precise_object()
        except self.model.DoesNotExist:
            try:
                obj = self.get_fuzzy_object()
            except self.model.DoesNotExist:
                raise Http404
            self.push_state_url = obj.get_absolute_url()

        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["push_state_url"] = self.push_state_url
        return context

    def get_precise_object(self):
        return (
            self.model.objects.filter(
                name=self.kwargs["klass"],
                module__name=self.kwargs["module"],
                module__project_version__version_number=self.kwargs["version"],
                module__project_version__project__name=self.kwargs["package"],
            )
            .select_related("module__project_version__project")
            .get()
        )

    def get_fuzzy_object(self):
        return (
            self.model.objects.filter(
                name__iexact=self.kwargs["klass"],
                module__name__iexact=self.kwargs["module"],
                module__project_version__version_number__iexact=self.kwargs["version"],
                module__project_version__project__name__iexact=self.kwargs["package"],
            )
            .select_related("module__project_version__project")
            .get()
        )


class LatestKlassDetailView(DetailView):
    model = Klass
    push_state_url = None
    template_name = "cbv/klass_detail.html"

    def get_object(self, queryset=None):
        try:
            obj = self.get_precise_object()
        except self.model.DoesNotExist:
            try:
                obj = self.get_fuzzy_object()
            except self.model.DoesNotExist:
                raise Http404
            self.push_state_url = obj.get_absolute_url()

        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["push_state_url"] = self.push_state_url
        return context

    def get_precise_object(self):
        # Even if we match case-sensitively,
        # we're still going to be pushing to a new url,
        # so we'll do both lookups in get_fuzzy_object
        raise self.model.DoesNotExist

    def get_fuzzy_object(self):
        return self.model.objects.get_latest_for_name(
            klass_name=self.kwargs["klass"],
            project_name=self.kwargs["package"],
        )


class ModuleDetailView(DetailView):
    model = Module
    template_name = "cbv/module_detail.html"
    push_state_url = None

    def get_object(self, queryset=None):
        try:
            obj = self.get_precise_object()
        except self.model.DoesNotExist:
            try:
                obj = self.get_fuzzy_object()
            except self.model.DoesNotExist:
                raise Http404
            self.push_state_url = obj.get_absolute_url()

        return obj

    def get(self, request, *args, **kwargs):
        try:
            self.project_version = (
                ProjectVersion.objects.filter(
                    version_number__iexact=kwargs["version"],
                    project__name__iexact=kwargs["package"],
                )
                .select_related("project")
                .get()
            )
        except ProjectVersion.DoesNotExist:
            raise Http404
        return super().get(request, *args, **kwargs)

    def get_precise_object(self, queryset=None):
        return self.model.objects.get(
            name=self.kwargs["module"], project_version=self.project_version
        )

    def get_fuzzy_object(self, queryset=None):
        return self.model.objects.get(
            name__iexact=self.kwargs["module"],
            project_version__version_number__iexact=self.kwargs["version"],
            project_version__project__name__iexact=self.kwargs["package"],
        )

    def get_context_data(self, **kwargs):
        kwargs.update(
            {
                "project_version": self.project_version,
                "klass_list": Klass.objects.filter(module=self.object).select_related(
                    "module__project_version", "module__project_version__project"
                ),
            }
        )
        context = super().get_context_data(**kwargs)
        context["push_state_url"] = self.push_state_url
        return context


class VersionDetailView(TemplateView):
    template_name = "cbv/version_detail.html"

    def get(self, request, *args, **kwargs):
        try:
            self.project_version = self.get_project_version(**kwargs)
        except ProjectVersion.DoesNotExist:
            raise Http404
        return super().get(request, *args, **kwargs)

    def get_project_version(self, **kwargs):
        project_version = (
            ProjectVersion.objects.filter(
                version_number__iexact=kwargs["version"],
                project__name__iexact=kwargs["package"],
            )
            .select_related("project")
            .get()
        )
        return project_version

    def get_context_data(self, **kwargs):
        return {
            "object_list": Klass.objects.filter(
                module__project_version=self.project_version
            ),
            "projectversion": self.project_version,
        }


class HomeView(VersionDetailView):
    template_name = "home.html"

    def get_project_version(self, **kwargs):
        return ProjectVersion.objects.get_latest("Django")


class Sitemap(TemplateView):
    content_type = "application/xml"
    template_name = "sitemap.xml"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        latest_version = ProjectVersion.objects.get_latest("Django")
        klasses = Klass.objects.select_related(
            "module__project_version__project"
        ).order_by(
            "module__project_version__project__name",
            "-module__project_version__sortable_version_number",
            "module__name",
            "name",
        )

        urls = [{"location": reverse("home"), "priority": 1.0}]
        for klass in klasses:
            priority = 0.9 if klass.module.project_version == latest_version else 0.5
            urls.append({"location": klass.get_absolute_url(), "priority": priority})
        return {"urlset": urls}
