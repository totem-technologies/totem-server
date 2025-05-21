from ninja import Router
from ninja.errors import ValidationError as APIValidationError
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from .schemas import OnboardSchema
from .models import OnboardModel

onboard_router = Router()


@onboard_router.post("/", response={200: OnboardSchema}, url_name="onboard")
def onboard_post(request, data: OnboardSchema):
    onboard_model, _ = OnboardModel.objects.get_or_create(user=request.user)
    print(data)
    for attr, value in data.dict().items():
        setattr(onboard_model, attr, value)
    try:
        onboard_model.full_clean()
    except ValidationError as e:
        raise APIValidationError([e.message_dict])
    onboard_model.save()
    return data


@onboard_router.get("/", response={200: OnboardSchema})
def onboard_get(request):
    onboard_model = get_object_or_404(OnboardModel, user=request.user)
    return onboard_model
