from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.urls import reverse, reverse_lazy
from django.views.generic import FormView, TemplateView
from sesame.utils import get_query_string

from ..email.views import WaitListAddView
from .forms import ParticipateLoginForm, ParticipateOnboardForm

User = get_user_model()


@dataclass
class Member:
    name: str
    title: str
    image: str
    url: str

    def imageurl(self):
        return f"images/team/{self.image}"


class TeamView(TemplateView):
    team = [
        Member(name="Bo Lopker", title="Executive Director, Keeper", image="bo.jpg", url="pages:about"),
        Member(name="Pam Lopker", title="Board Member", image="pam.jpg", url="pages:team-pam"),
        Member(name="Gabe Kenny", title="User Research, Keeper", image="gabe.jpg", url="pages:keepers-gabe"),
        Member(
            name="Heather Gressett", title="Content Curator, Keeper", image="heather.jpg", url="pages:keepers-heather"
        ),
        Member(name="Steve Schalkhauser", title="Engineer, Phase 2", image="blank.jpg", url="pages:team"),
        Member(name="Steve Ansell", title="Engineer, Phase 2", image="blank.jpg", url="pages:team"),
    ]
    template_name = "pages/team.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["team"] = self.team
        return context


@dataclass
class Step:
    title: str
    description: str
    image: str

    def url(self):
        return f"images/steps/{self.image}"


book = """
<svg fill="currentColor"  class="w-12 h-12" viewBox="0 0 32 32">
    <path d="M0 26.016q0 0.832 0.576 1.408t1.44 0.576q1.92 0.096 3.808 0.288t4.352 0.736 3.904 1.28q0.096 0.736 0.64 1.216t1.28 0.48 1.28-0.48 0.672-1.216q1.44-0.736 3.872-1.28t4.352-0.736 3.84-0.288q0.8 0 1.408-0.576t0.576-1.408v-24q0-0.832-0.576-1.408t-1.408-0.608q-0.032 0-0.096 0.032t-0.128 0q-9.504 0.256-12.672 2.528-1.024 0.768-1.12 1.44l-0.096-0.32q-0.576-1.28-3.168-2.176-3.648-1.28-10.528-1.472-0.064 0-0.128 0t-0.064-0.032q-0.832 0-1.44 0.608t-0.576 1.408v24zM4 24.128v-19.936q6.88 0.512 10.016 2.080v19.744q-3.104-1.536-10.016-1.888zM6.016 20q0.096 0 0.32 0.032t0.832 0.032 1.216 0.096 1.248 0.224 1.184 0.352 0.832 0.544 0.352 0.736v-4q0-0.096-0.032-0.224t-0.352-0.48-0.896-0.608-1.792-0.48-2.912-0.224v4zM6.016 12q0.096 0 0.32 0.032t0.832 0.032 1.216 0.096 1.248 0.224 1.184 0.352 0.832 0.544 0.352 0.736v-4q0-0.096-0.032-0.224t-0.352-0.48-0.896-0.608-1.792-0.48-2.912-0.224v4zM18.016 26.016v-19.744q3.104-1.568 9.984-2.080v19.936q-6.912 0.352-9.984 1.888zM20 22.016q0-0.576 0.608-0.992t1.504-0.576 1.76-0.288 1.504-0.128l0.64-0.032v-4q-1.696 0-2.944 0.224t-1.792 0.48-0.864 0.608-0.384 0.512l-0.032 0.192v4zM20 14.016q0-0.576 0.608-0.992t1.504-0.576 1.76-0.288 1.504-0.128l0.64-0.032v-4q-1.696 0-2.944 0.224t-1.792 0.48-0.864 0.608-0.384 0.512l-0.032 0.192v4z"></path>
</svg>
"""

person = """
<svg viewBox="0 0 20 20" fill="currentColor"  class="w-12 h-12">
        <g id="Dribbble-Light-Preview" transform="translate(-180.000000, -2159.000000)" >
            <g id="icons" transform="translate(56.000000, 160.000000)">
                <path d="M134,2008.99998 C131.783496,2008.99998 129.980955,2007.20598 129.980955,2004.99998 C129.980955,2002.79398 131.783496,2000.99998 134,2000.99998 C136.216504,2000.99998 138.019045,2002.79398 138.019045,2004.99998 C138.019045,2007.20598 136.216504,2008.99998 134,2008.99998 M137.775893,2009.67298 C139.370449,2008.39598 140.299854,2006.33098 139.958235,2004.06998 C139.561354,2001.44698 137.368965,1999.34798 134.722423,1999.04198 C131.070116,1998.61898 127.971432,2001.44898 127.971432,2004.99998 C127.971432,2006.88998 128.851603,2008.57398 130.224107,2009.67298 C126.852128,2010.93398 124.390463,2013.89498 124.004634,2017.89098 C123.948368,2018.48198 124.411563,2018.99998 125.008391,2018.99998 C125.519814,2018.99998 125.955881,2018.61598 126.001095,2018.10898 C126.404004,2013.64598 129.837274,2010.99998 134,2010.99998 C138.162726,2010.99998 141.595996,2013.64598 141.998905,2018.10898 C142.044119,2018.61598 142.480186,2018.99998 142.991609,2018.99998 C143.588437,2018.99998 144.051632,2018.48198 143.995366,2017.89098 C143.609537,2013.89498 141.147872,2010.93398 137.775893,2009.67298" id="profile-[#1341]">

</path>
            </g>
        </g>
</svg>
"""

cycle = """
<svg fill="currentColor"  class="w-12 h-12"  viewBox="0 0 397.037 397.037">
<g>
 <path d="M336.875,190.616c-18.765,0-34.035,15.264-34.035,34.035c0,57.514-46.783,104.315-104.315,104.315
  c-57.517,0-104.318-46.802-104.318-104.315c0-45.252,28.727-84.358,70.283-98.527v12.439c0,11.181,5.503,21.65,14.727,28.021
  c5.716,3.942,12.397,6.02,19.314,6.02c4.08,0,8.095-0.718,11.926-2.152l1.117-0.478l2.18-1.048l1.051-0.553l87.958-51.557
  c11.541-5.72,18.963-17.606,18.963-30.52c0-12.91-7.422-24.809-18.963-30.517L214.804,4.224l-1.033-0.555l-2.144-1.021
  l-1.099-0.465C206.686,0.729,202.644,0,198.524,0c-6.992,0-13.694,2.089-19.326,6.02c-9.211,6.35-14.715,16.822-14.715,28.021
  v21.605C84.8,71.535,26.133,142.118,26.133,224.657c0,95.056,77.327,172.38,172.383,172.38c95.059,0,172.389-77.324,172.389-172.38
  C370.904,205.88,355.64,190.616,336.875,190.616z"/>
</g>
</svg>
"""

bye = """
<svg fill="none" stroke="currentColor"  class="w-12 h-12"  viewBox="0 0 48 48" >
<path d="M35 26.6139L15.1463 7.31395C13.9868 6.18686 12.1332 6.21308 11.0062 7.3725C10.9652 7.41459 10.9256 7.45789 10.8873 7.50235C9.74436 8.82907 9.8228 10.814 11.0669 12.0463L21.091 21.9763"  stroke-width="4" stroke-linecap="round"/>
<path d="M21.0909 21.9762L10.1773 11.1548C8.88352 9.87195 6.8201 9.80176 5.44214 10.9937C4.17554 12.0893 4.03694 14.0043 5.13256 15.2709C5.17411 15.3189 5.21715 15.3656 5.26164 15.411L16.2553 26.6138"  stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M16.2553 26.6138L10 20.5001C8.73766 19.2104 6.67317 19.1745 5.36682 20.4197C4.07445 21.6515 4.02538 23.6978 5.25721 24.9902C5.26288 24.9961 5.26857 25.002 5.27429 25.0079C14.5039 34.5444 19.294 39.0486 21.091 40.5535C24 42.9898 29.7351 44.0001 32.7305 42.0001C35.7259 40.0001 38.4333 37.1545 39.7183 34.3288C40.4833 32.6466 41.9692 27.4596 44.1759 18.768C44.6251 16.9987 43.5549 15.2002 41.7856 14.751C41.7627 14.7452 41.7397 14.7396 41.7167 14.7343C39.8835 14.3106 38.0431 15.4117 37.5499 17.2274L35 26.6138"  stroke-width="4" stroke-linecap="round"/>
<path d="M31.7159 12.666C31.004 11.6026 30.1903 10.6131 29.2887 9.71151C28.3871 8.80992 27.3976 7.9962 26.3342 7.28431C25.8051 6.9301 25.2577 6.6011 24.6937 6.29903C24.133 5.99872 23.5559 5.72502 22.9641 5.47963"  stroke-width="4" stroke-linecap="round"/>
<path d="M5.19397 33.7763C5.84923 34.8754 6.61005 35.9062 7.46322 36.8537C8.31639 37.8012 9.26192 38.6656 10.2866 39.4322C10.7964 39.8136 11.3259 40.1708 11.8733 40.502C12.4175 40.8312 12.9795 41.1348 13.5576 41.4108"  stroke-width="4" stroke-linecap="round"/>
</svg>
"""


class HowItWorksView(TemplateView):
    template_name = "pages/how_it_works.html"
    steps = [
        Step(
            title="Opening",
            description="The Keeper opens the Circle with a short poem, meditation or story.",
            image=book,
        ),
        Step(
            title="Presence",
            description="The Keeper asks an open-ended question to get everyone in the Circle grounded with each other.",
            image=person,
        ),
        Step(
            title="Rounds",
            description="The Circle goes around and the Keeper asks questions to the group for as long as time permits.",
            image=cycle,
        ),
        Step(
            title="Closing",
            description="The Keeper sends the totem around one more time to allow everyone to get their final thoughts out.",
            image=bye,
        ),
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["steps"] = self.steps
        return context


def participant_email(name, link):
    return f"""
Hi {name},
I'm excited to get you started with Totem. I hope you'll like the Circle experience as much as I do.

But first, in order for us to find the right group for you, we'll need to know a little more about you.

Please follow the link to continue to the next step. It should take less than 2 minutes.

Next step: {link}

If you have any questions for me, just reply to this email.

Yours
- Bo, Executive Director of Totem
    """


class ParticipateView(FormView):
    template_name = "pages/participate/start.html"
    form_class = ParticipateLoginForm
    success_url = reverse_lazy("pages:participate")
    _email_key = "participate_email"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get from query params (for testing) or session
        context["email"] = self.request.session.get(self._email_key, self.request.GET.get("email"))
        self.request.session.pop(self._email_key, None)
        return context

    def form_valid(self, form):
        email = form.cleaned_data["email"].lower()
        name = form.cleaned_data["name"]
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = User.objects.create_user(name=name, email=email, password=User.objects.make_random_password())  # type: ignore
        next_url = reverse("pages:participate-onboard")
        url = self.request.build_absolute_uri(reverse("magic-login")) + get_query_string(user) + "&next=" + next_url
        send_mail(
            "Welcome to Totem",
            participant_email(name, url),
            "bo@totem.org",
            fail_silently=False,
            recipient_list=[user.email],  # type: ignore
        )
        self.request.session[self._email_key] = email
        return super().form_valid(form)


class ParticipateOnboardView(LoginRequiredMixin, FormView):
    template_name = "pages/participate/onboard.html"
    form_class = ParticipateOnboardForm
    success_url = reverse_lazy("pages:participate")
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: ParticipateOnboardForm):
        form.save()
        return super().form_valid(form)


class HomeView(TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["quotes"] = [
            "I appreciate having a space to express myself and not feel the need to validate or respond to others.",
            "It was the best experience.",
            "I'm so glad I came, this is exactly what I've been needing.",
            "This is definitely a safe and welcoming environment.",
            "My expectations were exceeded 10000%.",
            "YES!!! I love the safe space that was created.",
        ]
        context["waitlist_form"] = WaitListAddView().get_form_class()
        return context
