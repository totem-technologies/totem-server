from dataclasses import dataclass
from django.views.generic import TemplateView


@dataclass
class Member:
    name: str
    title: str
    image: str

    def url(self):
        return f"images/team/{self.image}"


class TeamView(TemplateView):
    team = [
        Member(name="Bo Lopker", title="Executive Director, Keeper", image="bo.jpg"),
        Member(name="Pam Lopker", title="Board Member", image="pam.jpg"),
        Member(name="Gabe Kenny", title="User Research, Keeper", image="gabe.jpg"),
        Member(name="Heather Gressett", title="Content Curator, Keeper", image="heather.jpg"),
        Member(name="Steve Schalkhauser", title="Engineer, Phase 2", image="blank.jpg"),
        Member(name="Steve Ansell", title="Engineer, Phase 2", image="blank.jpg"),
    ]
    template_name = "pages/team.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["team"] = self.team
        return context
